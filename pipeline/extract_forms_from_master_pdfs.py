"""
pipeline/extract_forms_from_master_pdfs.py
Scans three master PDF documents, identifies form boundaries, slices individual PDFs, 
and ingests metadata + embeddings into Supabase.
"""

import os
import re
import sys
import logging
import tempfile
import boto3
import pdfplumber
from pypdf import PdfReader, PdfWriter
from pathlib import Path
from datetime import datetime
from botocore.config import Config

# Load .env
try:
    from dotenv import load_dotenv
    env_path = str(Path(__file__).resolve().parent.parent / ".env")
    load_dotenv(env_path)
except ImportError:
    pass

# Absolute package imports so this is importable as pipeline.* and not only
# runnable as a bare script from inside pipeline/ — see the note in ingestor.py.
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.form_classifier import classify_form
from pipeline.embedder        import embed_texts
from pipeline.vector_store    import get_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# The master PDFs are 18 MB of input corpus that the running application never
# reads — they are needed only to (re)build the forms table. They now live under
# data/master_pdfs/ and are gitignored, so a fresh clone does not have them.
#
# Resolve them relative to THIS FILE, not the working directory. The previous
# version passed a bare filename to os.path.exists(), which is CWD-relative, so
# the script only worked when launched from the repo root and failed confusingly
# from anywhere else.
MASTER_PDF_DIR = Path(__file__).resolve().parent.parent / "data" / "master_pdfs"

# `file` is the bare filename: it is stored in forms.source_pdf, which is half of
# the (form_number, source_pdf) unique key, so it must stay stable and must not
# become an absolute path that embeds one machine's directory layout.
MASTER_PDFS = [
    {
        "file": "2016DrugsandCosmeticsAct1940Rules1945.pdf",
        "year": "2016",
        "source": "cdsco",
        "country": "India"
    },
    {
        "file": "NEW DRUGS ANDctrS RULE, 2019.pdf",
        "year": "2019",
        "source": "cdsco",
        "country": "India"
    },
    {
        "file": "2. Drugs Rules 1945_2024.pdf",
        "year": "2024",
        "source": "cdsco",
        "country": "India"
    }
]

# Pattern for form headers: "FORM 1", "FORM CT-04", etc.
FORM_PATTERN = re.compile(r"^\s*FORM\s+(?:NO\.?\s*)?([A-Z0-9-]+[A-Z]?)\b", re.MULTILINE | re.IGNORECASE)

def get_b2_client():
    return boto3.client(
        "s3",
        endpoint_url          = os.environ["B2_ENDPOINT"],
        aws_access_key_id     = os.environ["B2_KEY_ID"],
        aws_secret_access_key = os.environ["B2_APP_KEY"],
        region_name           = "auto",
        config                = Config(signature_version='s3v4')
    )

def extract_metadata_from_text(text: str, form_number: str) -> dict:
    """
    Tries to find the title and rule reference near the form header.
    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    title = ""
    rule_ref = ""
    
    # Typically title is within lines 1-5
    for i, line in enumerate(lines[:6]):
        # Match "Refer rule 23" or similar
        rule_match = re.search(r"\(?See\s+rules?\s*([^)]+)\)?", line, re.I) or \
                     re.search(r"\(?Refer\s+rules?\s*([^)]+)\)?", line, re.I)
        if rule_match:
            rule_ref = f"Rule {rule_match.group(1).strip()}"
        
        # If line is longer than 10 chars and doesn't start with "FORM", it's likely part of the title
        if len(line) > 10 and not line.upper().startswith("FORM"):
            if not title:
                title = line
            elif len(title) < 150:
                title += " " + line

    return {
        "title": title[:200] if title else f"Form {form_number} (Untitled)",
        "rule_reference": rule_ref
    }

def process_master_pdf(config: dict) -> dict:
    """
    Scan and extract forms from one master PDF.

    Returns a result dict so main() can exit non-zero on failure. This used to log
    an error and return None, after which main() finished normally — a missing
    corpus, or an upsert rejected for a missing unique constraint, looked exactly
    like a successful run that happened to produce an empty forms table.
    """
    result = {"file": config["file"], "found": False, "detected": 0, "saved": 0, "failed": 0}

    pdf_path = MASTER_PDF_DIR / config["file"]
    if not pdf_path.exists():
        log.error(f"Master PDF not found: {pdf_path}")
        return result

    result["found"] = True
    log.info(f"\nScanning: {pdf_path.name} ({config['year']})")
    
    b2           = get_b2_client()
    bucket_name  = os.environ["B2_BUCKET_NAME"]
    
    reader       = PdfReader(pdf_path)
    total_pages  = len(reader.pages)
    form_marks   = [] # List of (form_num, page_idx, header_text)

    # 1. Identify Form boundaries
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            # Only check top 15% of the page for headers
            top_text = "\n".join(text.split("\n")[:10])
            match = FORM_PATTERN.search(top_text)
            if match:
                form_num = match.group(1).upper()
                # Use entire page text for metadata later
                form_marks.append((form_num, i, text))
                log.info(f" Found FORM {form_num} on page {i+1}")

    if not form_marks:
        log.warning(f" No forms detected in {pdf_path.name}")
        return result

    result["detected"] = len(form_marks)

    # 2. Extract and Upload each form
    for idx, (f_num, start_page, full_text) in enumerate(form_marks):
        end_page = form_marks[idx + 1][1] if idx + 1 < len(form_marks) else total_pages
        
        # Metadata logic
        meta     = extract_metadata_from_text(full_text, f_num)
        f_type   = classify_form(f_num, meta["title"])
        
        # Slice PDF
        writer = PdfWriter()
        for p in range(start_page, end_page):
            writer.add_page(reader.pages[p])
            
        # Temporarily save
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            writer.write(tmp)
            tmp_path = tmp.name
        
        # B2 Upload
        b2_key = f"forms/{config['year']}/FORM_{f_num.replace(' ','_')}.pdf"
        log.info(f"   Uploading {f_num} ({f_type}) -> B2")
        b2.upload_file(tmp_path, bucket_name, b2_key)
        os.unlink(tmp_path)
        
        # Embedding
        embedding_text = f"FORM {f_num}: {meta['title']} | Categorized as {f_type}"
        embedding = embed_texts([embedding_text])[0]
        
        # Save to Supabase using RPC function (or direct insert)
        try:
            client = get_client()
            # Use upsert to avoid duplicates and preserve "other data"
            client.table("forms").upsert({
                "form_number":     f"FORM {f_num}",
                "form_name":       meta["title"],
                "form_number_raw": f_num,
                "title":           meta["title"],
                "rule_reference":  meta["rule_reference"],
                "form_type":       f_type,
                "description":     meta["title"],
                "country":         config["country"],
                "source":          config["source"],
                "source_pdf":      config["file"],
                "source_pdf_year": config["year"],
                "b2_key":          b2_key,
                "page_start":      start_page + 1,
                "page_end":        end_page,
                "content_text":    full_text[:5000],
                "embedding":       embedding
            }, on_conflict="form_number,source_pdf").execute()
            result["saved"] += 1
        except Exception as e:
            # Counted, not just logged. This except clause is why the forms table
            # was empty: without a unique index on (form_number, source_pdf) every
            # upsert raised "there is no unique or exclusion constraint matching
            # the ON CONFLICT specification", each one was logged as a single line
            # among hundreds, and the script still finished with "Done".
            log.error(f"   Failed to save {f_num} to Supabase: {e}")
            result["failed"] += 1

    log.info(
        f"Done with {pdf_path.name}: "
        f"{result['detected']} detected, {result['saved']} saved, {result['failed']} failed."
    )
    return result


def main() -> int:
    results = [process_master_pdf(config) for config in MASTER_PDFS]

    missing      = [r["file"] for r in results if not r["found"]]
    no_forms     = [r["file"] for r in results if r["found"] and r["detected"] == 0]
    total_saved  = sum(r["saved"] for r in results)
    total_failed = sum(r["failed"] for r in results)

    log.info("=" * 70)
    log.info("FORMS EXTRACTION SUMMARY")
    log.info(f"  Master PDFs read : {len(results) - len(missing)}/{len(results)}")
    log.info(f"  Forms saved      : {total_saved}")
    log.info(f"  Forms failed     : {total_failed}")
    log.info("=" * 70)

    if missing:
        log.error("")
        log.error(f"{len(missing)} master PDF(s) were not found in {MASTER_PDF_DIR}:")
        for name in missing:
            log.error(f"    {name}")
        log.error("")
        log.error("These files are gitignored, so a fresh clone does not include them.")
        log.error("Put them in that directory and re-run. Without them the forms table")
        log.error("stays empty and form search returns nothing.")

    if no_forms:
        log.error("")
        log.error("No FORM headers matched in: " + ", ".join(no_forms))
        log.error("Check FORM_PATTERN against the document's actual heading style.")

    if total_failed:
        log.error("")
        log.error(f"{total_failed} form(s) failed to save. If the error above mentions")
        log.error("ON CONFLICT, the unique index on forms (form_number, source_pdf) is")
        log.error("missing — apply supabase/schema.sql, then re-run this script.")

    # Non-zero on any failure, so this cannot be mistaken for a clean run.
    return 1 if (missing or no_forms or total_failed or total_saved == 0) else 0


if __name__ == "__main__":
    sys.exit(main())
