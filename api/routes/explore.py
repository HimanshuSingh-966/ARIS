"""
api/routes/explore.py
Browse sources, sections and documents; stream or presign the underlying PDFs.
"""

import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from api.deps import get_supabase, get_b2_client, bucket_name
from api.utils import pdf_filename, safe_content_disposition

log = logging.getLogger(__name__)

router = APIRouter(tags=["explore"])

# Single source of truth for the agency list. Dashboard.jsx previously kept its
# own copy of these names alongside a third in pipeline/ingestor.COUNTRY_MAP;
# serving them from here lets the frontend hold only icons and colours.
#
# `description` exists for Dashboard.jsx's card subtitle, and the order is the one
# the dashboard already renders in — the frontend maps over this list as-is.
SOURCES = [
    {
        "id": "cdsco",
        "name": "CDSCO",
        "full_name": "India CDSCO",
        "description": "Central Drugs Standard Control Organisation",
        "country": "India",
    },
    {
        "id": "fda",
        "name": "FDA",
        "full_name": "US FDA",
        "description": "Food and Drug Administration",
        "country": "USA",
    },
    {
        "id": "ema",
        "name": "EMA",
        "full_name": "Europe EMA",
        "description": "European Medicines Agency",
        "country": "Europe",
    },
]


# 1. Get Sources Overview
@router.get("/sources")
async def get_sources():
    return {"sources": SOURCES}


# 2. Get Sections for a Source
@router.get("/sources/{source}/sections")
async def get_sections(source: str):
    """
    Distinct section slugs for a source.

    Uses the distinct_sections RPC (see supabase/schema.sql). Previously this
    selected every doc_metadata row and deduplicated in Python, which silently
    lost categories once a source passed Supabase's 1000-row response cap.
    """
    supabase = get_supabase()
    src = source.lower()

    try:
        res = supabase.rpc("distinct_sections", {"filter_source": src}).execute()
        sections = [row["section"] for row in (res.data or []) if row.get("section")]
        return {"source": source, "sections": sections}
    except Exception as e:
        # The RPC may not exist yet on a database that predates schema.sql. Fall
        # back to the old client-side dedupe so browsing keeps working, but say so
        # loudly — the fallback is the one with the truncation bug.
        log.warning(
            "distinct_sections RPC unavailable (%s); falling back to in-memory "
            "dedupe, which truncates above 1000 rows. Apply supabase/schema.sql.",
            e,
        )
        try:
            res = (
                supabase.table("doc_metadata")
                .select("section")
                .eq("source", src)
                .execute()
            )
            sections = sorted({r["section"] for r in res.data if r.get("section")})
            return {"source": source, "sections": sections}
        except Exception:
            log.exception("Failed to list sections for source=%s", src)
            raise HTTPException(status_code=502, detail="Could not load sections.")


# 3. Get Documents within a Section
@router.get("/sources/{source}/sections/{section}/documents")
async def get_documents(
    source: str,
    section: str,
    search: str = Query(None),
    sort: str = Query("newest"),
    limit: int = Query(50, ge=1, le=200),
):
    supabase = get_supabase()

    try:
        query = (
            supabase.table("doc_metadata")
            .select("*")
            .eq("source", source.lower())
            .eq("section", section.lower())
        )

        if search:
            query = query.ilike("doc_name", f"%{search}%")

        if sort == "newest":
            query = query.order("created_at", desc=True)
        elif sort == "oldest":
            query = query.order("created_at")
        elif sort == "az":
            query = query.order("doc_name")
        elif sort == "za":
            query = query.order("doc_name", desc=True)

        res = query.limit(limit).execute()
        return {"documents": res.data}
    except Exception:
        log.exception("Failed to list documents source=%s section=%s", source, section)
        raise HTTPException(status_code=502, detail="Could not load documents.")


def _lookup_document(doc_id: str) -> tuple[str, str]:
    """Resolve a doc_id to (b2_key, doc_name), or raise 404."""
    supabase = get_supabase()
    try:
        res = (
            supabase.table("doc_metadata")
            .select("b2_key, doc_name")
            .eq("doc_id", doc_id)
            .limit(1)
            .execute()
        )
    except Exception:
        log.exception("doc_metadata lookup failed for doc_id=%s", doc_id)
        raise HTTPException(status_code=502, detail="Could not load document.")

    if not res.data:
        raise HTTPException(status_code=404, detail="Document not found.")

    row = res.data[0]
    b2_key = row.get("b2_key")
    if not b2_key:
        log.error("doc_metadata row for doc_id=%s has no b2_key", doc_id)
        raise HTTPException(status_code=404, detail="Document not found.")

    return b2_key, row.get("doc_name") or ""


# 4. Stream PDF bytes directly from B2 through FastAPI (avoids CORS entirely)
@router.get("/documents/{doc_id}/stream")
async def stream_document(doc_id: str):
    b2_key, doc_name = _lookup_document(doc_id)
    b2 = get_b2_client()

    try:
        obj = b2.get_object(Bucket=bucket_name(), Key=b2_key)
        body = obj["Body"]

        def iter_chunks():
            for chunk in body.iter_chunks(chunk_size=65536):
                yield chunk

        return StreamingResponse(
            iter_chunks(),
            media_type="application/pdf",
            headers={
                # Sanitised: a doc_name containing a quote, a newline or any
                # non-Latin-1 character would otherwise corrupt this header or
                # make the ASGI server raise while encoding the response.
                "Content-Disposition": safe_content_disposition(
                    pdf_filename(doc_name), "inline"
                ),
                "Cache-Control": "private, max-age=3600",
            },
        )
    except Exception:
        # Full detail to the log; nothing about bucket names, keys or boto
        # internals goes back to the caller.
        log.exception("B2 stream failed for doc_id=%s key=%s", doc_id, b2_key)
        raise HTTPException(status_code=502, detail="Could not retrieve document.")


# 5. Generate Presigned URL for direct downloading
@router.get("/documents/{doc_id}/url")
async def get_document_url(doc_id: str):
    b2_key, doc_name = _lookup_document(doc_id)
    b2 = get_b2_client()

    try:
        url = b2.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": bucket_name(),
                "Key": b2_key,
                # Also sanitised: this value is signed into the URL and returned
                # verbatim by B2 as a response header.
                "ResponseContentDisposition": safe_content_disposition(
                    pdf_filename(doc_name), "attachment"
                ),
            },
            ExpiresIn=3600,
        )
        # doc_name comes back too: the route param is an md5 doc_id, so without it
        # the viewer has nothing but a hash to show in the breadcrumb, the iframe
        # title and the chat's "context" label.
        return {"url": url, "doc_name": doc_name}
    except Exception:
        log.exception("Presign failed for doc_id=%s key=%s", doc_id, b2_key)
        raise HTTPException(status_code=502, detail="Could not generate download link.")
