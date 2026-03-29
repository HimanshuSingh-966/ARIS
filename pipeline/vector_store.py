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


def save_chunks(chunks: list[dict[str, Any]]) -> int:
    """
    Save a batch of embedded chunks to Supabase documents table.
    Returns number of chunks saved.
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

    try:
        # Insert in batches of 50 to avoid Supabase limits
        saved = 0
        for i in range(0, len(rows), 50):
            batch = rows[i:i + 50]
            get_client().table("documents").insert(batch).execute()
            saved += len(batch)
        return saved
    except Exception as e:
        log.error(f"save_chunks error: {e}")
        return 0

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