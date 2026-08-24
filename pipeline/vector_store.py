"""
pipeline/vector_store.py
Supabase pgvector read/write helpers.
Stores document chunks + embeddings, forms metadata.
"""

import os
import logging
from typing import Any, cast

log = logging.getLogger(__name__)

_client = None


def get_client():
    """Return cached Supabase client."""
    global _client
    if _client is None:
        from supabase import create_client
        url  = os.environ["SUPABASE_URL"]
        key  = os.environ["SUPABASE_SERVICE_KEY"]
        _client = create_client(url, key)
    return _client


# ── Documents ─────────────────────────────────────────────────────────────────

def chunk_exists(b2_key: str, char_start: int) -> bool:
    """Check if a chunk from this doc+position already exists."""
    try:
        result = (
            get_client()
            .table("documents")
            .select("id")
            .eq("b2_key", b2_key)
            .eq("char_start", char_start)
            .limit(1)
            .execute()
        )
        return len(result.data) > 0
    except Exception:
        return False


def doc_already_ingested(b2_key: str) -> bool:
    """Check if any chunks from this document are already in Supabase."""
    try:
        result = (
            get_client()
            .table("documents")
            .select("id")
            .eq("b2_key", b2_key)
            .limit(1)
            .execute()
        )
        return len(result.data) > 0
    except Exception:
        return False


def delete_chunks_for_doc(b2_key: str) -> int:
    """
    Remove every chunk row belonging to one document.

    Used to roll back a partial save_chunks write. Returns the number of rows
    deleted, or -1 if the delete itself failed. The caller must distinguish those:
    "nothing to clean up" and "cleanup did not happen" look the same from a count of
    zero, and only the second one leaves the document permanently half-ingested.

    Refuses an empty b2_key. Chunks fall back to `""` when metadata omits the key
    (see save_chunks below), and `.eq("b2_key", "")` would match those rows across
    every document rather than none.
    """
    if not b2_key:
        log.error(
            "delete_chunks_for_doc called with an empty b2_key — refusing. An empty "
            "filter would match every chunk whose b2_key was never set, across all "
            "documents."
        )
        return -1

    try:
        result = (
            get_client()
            .table("documents")
            .delete()
            .eq("b2_key", b2_key)
            .execute()
        )
        return len(result.data or [])
    except Exception:
        log.exception("Failed to delete chunks for %s", b2_key)
        return -1


def save_chunks(chunks: list[dict[str, Any]]) -> int:
    """
    Save a batch of embedded chunks to Supabase documents table.
    Returns number of chunks saved.

    Raises on a failed write, after rolling back whatever landed. It does not return
    a partial count — see the except block for why that is unsafe.
    """
    if not chunks:
        return 0

    rows = []
    for c in chunks:
        if "embedding" not in c:
            log.warning("Chunk missing embedding — skipping")
            continue
        rows.append({
            "source":      c["source"],
            "country":     c["country"],
            "doc_name":    c["doc_name"],
            "section":     c.get("section", ""),
            "section_tag": c.get("section_tag", ""),
            "doc_id":      c.get("doc_id", ""),
            "content":     c["content"],
            "embedding":   c["embedding"],
            "b2_key":      c.get("b2_key", ""),
            "source_url":  c.get("source_url", ""),
            "char_start":  c.get("char_start", 0),
            "char_end":    c.get("char_end", 0),
        })

    if not rows:
        return 0

    # save_chunks only ever runs for a document with no rows in the table:
    # ingestor.process_document returns early when doc_already_ingested() is true.
    # That invariant is what makes the delete-by-b2_key rollback below safe — there
    # is nothing from an earlier successful run for it to destroy.
    keys   = {r["b2_key"] for r in rows if r["b2_key"]}
    b2_key = keys.pop() if len(keys) == 1 else ""

    saved = 0
    try:
        # Insert in batches of 50 to avoid Supabase limits
        for i in range(0, len(rows), 50):
            batch = rows[i:i + 50]
            get_client().table("documents").insert(batch).execute()
            saved += len(batch)
        return saved
    except BaseException:
        # Each batch is a separate autocommitted request, so a failure partway
        # through leaves the earlier batches in the table. Those rows are poison:
        # doc_already_ingested() asks only whether *any* chunk exists, so the next
        # run skips this document and it stays incomplete for the life of the
        # database, with nothing anywhere reporting it. Roll the partial write back
        # so the document is retried from scratch.
        #
        # BaseException, not Exception: Ctrl-C raises KeyboardInterrupt, which is a
        # sibling of Exception rather than a subclass. That is the likeliest
        # interruption of a multi-hour ingest and exactly the one `except Exception`
        # would let past without cleaning up.
        #
        # Re-raising rather than returning a count is deliberate. An earlier version
        # returned the partial count so the caller would not understate what landed,
        # but after the rollback nothing has landed — and a non-zero return makes
        # ingestor.process_document report "done", count the document as ingested,
        # and write its doc_metadata row, which then presents a two-thirds-empty
        # document as fully browsable. Raising instead means the per-document handler
        # in run_pipeline counts it under Errors, while KeyboardInterrupt passes
        # through that `except Exception` and stops the run as intended.
        log.exception(
            "save_chunks failed after %d/%d rows for %s",
            saved, len(rows), b2_key or "<unknown b2_key>",
        )

        if saved:
            removed = delete_chunks_for_doc(b2_key)
            if removed >= 0:
                log.warning(
                    "Rolled back %d partial chunks for %s — it will be re-ingested on "
                    "the next run",
                    removed, b2_key,
                )
            elif b2_key:
                log.error(
                    "ROLLBACK FAILED — %d orphaned chunks remain for %s. "
                    "doc_already_ingested() will treat this document as complete and "
                    "skip it on every future run. Delete them before re-ingesting:\n"
                    "    delete from documents where b2_key = '%s';",
                    saved, b2_key, b2_key,
                )
            else:
                log.error(
                    "ROLLBACK FAILED — %d orphaned chunks remain and carry no single "
                    "b2_key, so there is no delete filter that would not also match "
                    "other documents. Identify and remove them by hand before "
                    "re-ingesting.",
                    saved,
                )
        raise


def save_doc_metadata(meta: dict[str, Any]) -> bool:
    """Save document structural metadata explicitly for the V2 UI dashboard."""
    try:
        get_client().table("doc_metadata").insert({
            "doc_id":     meta.get("doc_id", ""),
            "source":     meta.get("source", ""),
            "country":    meta.get("country", ""),
            "section":    meta.get("section", ""),
            "doc_name":   meta.get("doc_name", ""),
            "b2_key":     meta.get("b2_key", ""),
            "file_size":  int(meta.get("file_size", 0)),
            "page_count": int(meta.get("page_count", 0)),
        }).execute()
        return True
    except Exception as e:
        log.error(f"save_doc_metadata error: {e}")
        return False

# ── Forms ─────────────────────────────────────────────────────────────────────

def save_form_metadata(form: dict[str, Any]) -> bool:
    """Save a form record to Supabase forms table."""
    try:
        get_client().table("forms").insert({
            "form_number": form.get("form_number", ""),
            "form_name":   form.get("form_name", ""),
            "country":     form.get("country", ""),
            "source":      form.get("source", ""),
            "description": form.get("description", ""),
            "b2_key":      form.get("b2_key", ""),
            "source_doc":  form.get("source_doc", ""),
        }).execute()
        return True
    except Exception as e:
        log.error(f"save_form_metadata error: {e}")
        return False


def form_exists(b2_key: str) -> bool:
    """Check if form already saved."""
    try:
        result = (
            get_client()
            .table("forms")
            .select("id")
            .eq("b2_key", b2_key)
            .limit(1)
            .execute()
        )
        return len(result.data) > 0
    except Exception:
        return False


# ── Stats ─────────────────────────────────────────────────────────────────────

def get_stats() -> dict:
    """Return current Supabase ingestion stats."""
    try:
        client = get_client()

        total = client.table("documents").select(
            "id",
            count=cast(Any, "exact")
        ).execute()

        fda = client.table("documents").select(
            "id",
            count=cast(Any, "exact")
        ).eq("source", "fda").execute()

        ema = client.table("documents").select(
            "id",
            count=cast(Any, "exact")
        ).eq("source", "ema").execute()

        cdsco = client.table("documents").select(
            "id",
            count=cast(Any, "exact")
        ).eq("source", "cdsco").execute()

        forms = client.table("forms").select(
            "id",
            count=cast(Any, "exact")
        ).execute()

        return {
            "total_chunks": total.count,
            "fda_chunks":   fda.count,
            "ema_chunks":   ema.count,
            "cdsco_chunks": cdsco.count,
            "total_forms":  forms.count,
        }
    except Exception as e:
        log.error(f"get_stats error: {e}")
        return {}