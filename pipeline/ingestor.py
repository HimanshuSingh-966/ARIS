"""
pipeline/ingestor.py
Orchestrates the full pipeline:
  B2 PDF → extract text → chunk → embed → save to Supabase pgvector

Usage:
    # Run all sources
    python ingestor.py

    # Run specific source
    python ingestor.py --source cdsco

    # Dry run — show what would be processed without saving
    python ingestor.py --dry-run

    # Also ingest forms metadata
    python ingestor.py --include-forms
"""

import os
import sys
import re
import logging
import argparse
import time
import hashlib
import boto3
from datetime import datetime
from pathlib import Path

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(str(Path(__file__).resolve().parent.parent / ".env"))
except ImportError:
    pass

# The sibling imports below used to be bare (`from extractor import ...`), which
# resolves only when pipeline/ itself is on sys.path — i.e. only under the
# documented `python ingestor.py` invocation from inside the directory. That made
# this module unimportable as `pipeline.ingestor`, so classify_section() could not
# be reused by the API or covered by tests. Normalising on the absolute package
# path and fixing up sys.path for script mode keeps both entrypoints working.
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.extractor    import extract_text
from pipeline.chunker      import split_into_chunks, chunk_summary
from pipeline.embedder     import embed_chunks
from pipeline.vector_store import (
    save_chunks, doc_already_ingested,
    save_form_metadata, form_exists,
    save_doc_metadata,
    get_client,
    get_stats
)

logging.basicConfig(
    level  = logging.INFO,
    format = "%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# ── B2 helpers ────────────────────────────────────────────────────────────────

COUNTRY_MAP = {
    "fda":   "USA",
    "ema":   "Europe",
    "cdsco": "India",
}


# ── Section classification ────────────────────────────────────────────────────
#
# These rules drive the entire browse-by-section UI, so a false positive
# misfiles a document permanently. The previous implementation used bare
# substring tests, and `"ct" in hint` matched "a-ct", "produ-ct", "pra-ct-ice"
# and "prote-ct-ion" — so most documents were classified "clinical-trials".
#
# Note we cannot use \b: these match filenames and B2 keys, where tokens are
# separated by `-`, `_`, `.`, `/` and spaces, and \b treats `_` as a word
# character (so \btrial\b would not match "clinical_trial"). These lookarounds
# treat any non-alphanumeric as a token separator instead.
_L = r"(?<![a-z0-9])"   # left token boundary
_R = r"(?![a-z0-9])"    # right token boundary

# Order matters: first match wins, preserving the original if/elif priority.
SECTION_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("guidance-documents", re.compile(
        # Bounded `act` makes the old `and "fact" not in hint` guard unnecessary,
        # and also stops "practice", "compact", "enact" from matching.
        rf"{_L}guidance|{_L}guideline|{_L}rules?{_R}|{_L}acts?{_R}"
    )),
    ("clinical-trials", re.compile(
        # `ct` needs BOTH boundaries — this is the token in CDSCO codes like
        # "CT-01". Left boundary also keeps "trial" off "industrial".
        rf"{_L}trials?{_R}|{_L}clinical|{_L}ct{_R}"
    )),
    ("medical-devices", re.compile(
        rf"{_L}devices?{_R}|{_L}diagnostic"
    )),
    ("drug-approvals", re.compile(
        # `auth` is a prefix on purpose: authorisation / authorization.
        rf"{_L}approval|{_L}auth|{_L}clearance|{_L}new[-_ ]?drug"
    )),
    ("compliance-enforcement", re.compile(
        rf"{_L}warning|{_L}inspection|{_L}banned{_R}|{_L}enforcement"
    )),
    ("cosmetics", re.compile(rf"{_L}cosmetic")),
    ("biologicals-vaccines", re.compile(
        rf"{_L}biolog|{_L}vaccine|{_L}blood{_R}"
    )),
    ("notifications-advisories", re.compile(
        # `advisor` covers advisory / advisories.
        rf"{_L}notif|{_L}advisor"
    )),
]

DEFAULT_SECTION = "general"


def classify_section(hint: str) -> str:
    """
    Map a document name + B2 key into a browse category slug.

    Args:
        hint: lowercase-able string combining doc_name and b2_key.

    Returns:
        One of the SECTION_RULES slugs, or "general" if nothing matches.
    """
    hint = (hint or "").lower()
    for section, pattern in SECTION_RULES:
        if pattern.search(hint):
            return section
    return DEFAULT_SECTION


def get_b2_client():
    return boto3.client(
        "s3",
        endpoint_url          = os.environ["B2_ENDPOINT"],
        aws_access_key_id     = os.environ["B2_KEY_ID"],
        aws_secret_access_key = os.environ["B2_APP_KEY"],
        region_name           = "auto",
    )


def list_b2_files(source: str) -> list[dict]:
    """List all PDF files in a B2 source folder."""
    client  = get_b2_client()
    bucket  = os.environ["B2_BUCKET_NAME"]
    prefix  = f"{source}/"
    files   = []

    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".pdf"):
                files.append({
                    "b2_key":   key,
                    "doc_name": os.path.basename(key).replace(".pdf", ""),
                    "source":   source,
                    "country":  COUNTRY_MAP.get(source, "Unknown"),
                    "size_kb":  obj["Size"] / 1024,
                })

    return files


def list_b2_forms() -> list[dict]:
    """List all form PDFs in B2 forms folder."""
    client = get_b2_client()
    bucket = os.environ["B2_BUCKET_NAME"]
    files  = []

    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix="forms/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".pdf"):
                fname = os.path.basename(key)
                # Parse form number from filename e.g. CDSCO_FORM_44.pdf
                parts = fname.replace(".pdf", "").split("_")
                form_number = ""
                if "FORM" in parts:
                    idx = parts.index("FORM")
                    form_number = " ".join(parts[idx:])

                # Determine country from prefix
                if "CDSCO" in fname:
                    country = "India"
                    source  = "cdsco"
                elif "FDA" in fname or "fda" in fname:
                    country = "USA"
                    source  = "fda"
                else:
                    country = "Europe"
                    source  = "ema"

                files.append({
                    "b2_key":      key,
                    "form_number": form_number,
                    "form_name":   fname.replace(".pdf", "").replace("_", " "),
                    "country":     country,
                    "source":      source,
                    "source_doc":  fname,
                })

    return files


# ── Main pipeline ─────────────────────────────────────────────────────────────

def process_document(doc: dict, dry_run: bool = False) -> dict:
    """
    Run full pipeline for a single document.
    Returns result dict with stats.
    """
    b2_key   = doc["b2_key"]
    doc_name = doc["doc_name"]

    import hashlib
    doc_id = hashlib.md5(b2_key.encode('utf-8')).hexdigest()
    
    # Advanced Heuristics (inspecting source path + doc_name for better hinting)
    combined_hint = (doc_name + " " + b2_key).lower()
    section = classify_section(combined_hint)

    metadata = {
        "source":     doc["source"],
        "country":    doc["country"],
        "doc_name":   doc_name,
        "doc_id":     doc_id,
        "section":    section,
        "section_tag": section,
        "b2_key":     b2_key,
        "source_url": doc.get("source_url", ""),
        "file_size":  int(doc["size_kb"]),
        "page_count": 0 # Default placeholder for now
    }

    # Skip embedding chunks if already ingested, but backfill metadata for the V2 UI dashboard
    if doc_already_ingested(b2_key):
        if not dry_run:
            try:
                client = get_client()
                if hasattr(client, 'table'):
                    meta_check = client.table("doc_metadata").select("doc_id").eq("b2_key", b2_key).limit(1).execute()
                    if len(meta_check.data) == 0:
                        save_doc_metadata(metadata)
            except Exception as e:
                print(f"  WARNING: Failed metadata backfill for {b2_key}: {e}")
        return {"status": "skipped", "b2_key": b2_key, "chunks": 0}

    print(f"\n  Processing: {doc_name} ({doc['size_kb']:.0f} KB)")

    # Step 1 — Extract text
    text = extract_text(b2_key)
    if not text:
        print(f"  WARNING: No text extracted from {doc_name}")
        return {"status": "no_text", "b2_key": b2_key, "chunks": 0}

    # Step 2 — Chunk
    chunks = split_into_chunks(text, metadata)
    summary = chunk_summary(chunks)
    print(f"  Chunked → {summary['count']} chunks "
          f"(avg {summary.get('avg_chars', 0)} chars each)")

    if not chunks:
        return {"status": "no_chunks", "b2_key": b2_key, "chunks": 0}

    if dry_run:
        print(f"  [DRY RUN] Would save {len(chunks)} chunks to Supabase")
        return {"status": "dry_run", "b2_key": b2_key, "chunks": len(chunks)}

    # Step 3 — Embed
    chunks = embed_chunks(chunks)

    # Step 4 — Save HTML/Text chunks to Supabase
    saved = save_chunks(chunks)
    
    # Step 5 - Save Metadata explicitly to V2 Table
    #
    # get_client / save_doc_metadata are imported at module scope. They used to be
    # re-imported here as `from vector_store import ...` — a bare sibling import,
    # which resolves only when pipeline/ itself is on sys.path. Under
    # `python -m pipeline.ingestor` it raised ModuleNotFoundError from OUTSIDE the
    # try below, so run_pipeline's per-document handler caught it: the chunks were
    # already saved, but doc_metadata never was, and the final summary reported
    # "Chunks saved: 0" while the table held thousands. Nothing here is optional —
    # without a doc_metadata row the document cannot be browsed or opened.
    if saved > 0 and not dry_run:
        try:
            client = get_client()
            meta_check = client.table("doc_metadata").select("doc_id").eq("b2_key", b2_key).limit(1).execute()
            if len(meta_check.data) == 0:
                # save_doc_metadata swallows its own exceptions and returns False,
                # so the return value is the only signal that it failed.
                if not save_doc_metadata(metadata):
                    print(f"  WARNING: doc_metadata write failed for {b2_key} — "
                          f"this document will not appear in the browse UI")
        except Exception:
            log.exception("doc_metadata step failed for %s", b2_key)
        
    print(f"  Saved {saved} chunks to Supabase pgvector")

    return {"status": "done", "b2_key": b2_key, "chunks": saved}


def run_pipeline(
    sources:       list[str] | None = None,
    dry_run:       bool      = False,
    include_forms: bool      = False,
):
    """Main pipeline runner."""
    start = datetime.now()

    print("=" * 60)
    print("  PHARMA RAG — INGESTION PIPELINE")
    print(f"  Started: {start.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print("=" * 60)

    if sources is None:
        sources = ["cdsco", "ema", "fda"]

    total_docs   = 0
    total_chunks = 0
    skipped      = 0
    errors       = 0

    # ── Process documents ────────────────────────────────────────────────────
    for source in sources:
        print(f"\n{'─'*50}")
        print(f"  Source: {source.upper()} ({COUNTRY_MAP.get(source, '?')})")
        print(f"{'─'*50}")

        try:
            docs = list_b2_files(source)
            print(f"  Found {len(docs)} PDFs in B2/{source}/")
        except Exception as e:
            print(f"  ERROR listing B2/{source}/: {e}")
            continue

        for doc in docs:
            try:
                result = process_document(doc, dry_run=dry_run)
                if result["status"] == "skipped":
                    skipped += 1
                elif result["status"] == "done":
                    total_docs   += 1
                    total_chunks += result["chunks"]
                elif result["status"] == "dry_run":
                    total_docs   += 1
                    total_chunks += result["chunks"]
                else:
                    errors += 1
            except Exception as e:
                log.error(f"Error processing {doc['b2_key']}: {e}")
                errors += 1

    # ── Process forms ────────────────────────────────────────────────────────
    if include_forms:
        print(f"\n{'─'*50}")
        print("  Forms metadata")
        print(f"{'─'*50}")

        try:
            forms = list_b2_forms()
            print(f"  Found {len(forms)} forms in B2/forms/")
            saved_forms = 0
            for form in forms:
                if not form_exists(form["b2_key"]) and not dry_run:
                    if save_form_metadata(form):
                        saved_forms += 1
                        print(f"  ✓ {form['form_name']}")
                elif dry_run:
                    print(f"  [DRY RUN] Would save: {form['form_name']}")
                    saved_forms += 1
            print(f"\n  Saved {saved_forms} forms to Supabase")
        except Exception as e:
            print(f"  ERROR processing forms: {e}")

    # ── Summary ──────────────────────────────────────────────────────────────
    elapsed = (datetime.now() - start).seconds

    print(f"\n{'='*60}")
    print("  PIPELINE COMPLETE")
    print(f"{'='*60}")
    print(f"  Time elapsed : {elapsed//60}m {elapsed%60}s")
    print(f"  Docs ingested: {total_docs}")
    print(f"  Chunks saved : {total_chunks}")
    print(f"  Skipped      : {skipped} (already in Supabase)")
    print(f"  Errors       : {errors}")

    if not dry_run:
        print(f"\n  Supabase stats:")
        stats = get_stats()
        for k, v in stats.items():
            print(f"    {k}: {v}")

    print(f"{'='*60}")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Pharma RAG ingestion pipeline"
    )
    parser.add_argument(
        "--source",
        nargs="+",
        choices=["fda", "ema", "cdsco"],
        default=["cdsco", "ema", "fda"],
        help="Sources to ingest (default: all)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without saving"
    )
    parser.add_argument(
        "--include-forms",
        action="store_true",
        help="Also ingest forms metadata to Supabase"
    )
    args = parser.parse_args()

    run_pipeline(
        sources       = args.source,
        dry_run       = args.dry_run,
        include_forms = args.include_forms,
    )