"""
api/routes/forms.py
Search, view, and download regulatory forms.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from api.deps import get_b2_client, bucket_name
from api.models import FormListResponse, FormDownloadResponse, FormItem
from pipeline.vector_store import get_client
from pipeline.embedder import embed_query

log = logging.getLogger(__name__)

router = APIRouter(tags=["forms"])

# How many merged search hits to consider before filtering. Kept above the page
# size so that post-filtering a search by type/source doesn't routinely empty the
# result set.
_SEARCH_FETCH = 60
_PAGE_SIZE = 50


def _matches(form: dict[str, Any], type_: Optional[str], source: Optional[str]) -> bool:
    """
    Apply the same type/source filters the listing branch applies in SQL.

    The search branch used to ignore both parameters entirely, so selecting
    "Manufacturing" and then searching silently searched every category — the
    category chip stayed highlighted while the results contradicted it.
    """
    if type_ and (form.get("form_type") or "") != type_:
        return False
    if source and (form.get("source") or "") != source:
        return False
    return True


@router.get("/forms", response_model=FormListResponse)
async def list_forms(
    q:      Optional[str] = Query(None, description="Search query"),
    type:   Optional[str] = Query(None, description="Filter: Manufacturing / Import / etc"),
    source: Optional[str] = Query(None, description="Filter: cdsco / fda / ema"),
):
    """
    Search or list forms. If 'q' is provided, performs a hybrid keyword+semantic search.
    """
    client = get_client()

    if q:
        try:
            # 1. Semantic search
            embedding = embed_query(q)
            semantic_res = client.rpc(
                "search_forms_semantic",
                {
                    "query_embedding": embedding,
                    "match_threshold": 0.25,
                    "match_count": _SEARCH_FETCH,
                },
            ).execute()

            # 2. Keyword search
            keyword_res = client.rpc(
                "search_forms_keyword", {"query_text": q}
            ).execute()
        except Exception:
            log.exception("Form search failed for q=%r", q[:200])
            raise HTTPException(status_code=502, detail="Form search is unavailable.")

        # 3. Merge & deduplicate — keyword hits rank first as they are exact.
        merged: dict[Any, dict] = {}
        for f in (keyword_res.data or []) + (semantic_res.data or []):
            form_id = f.get("id")
            if form_id is not None and form_id not in merged:
                merged[form_id] = f

        # 4. Apply the filters the SQL branch gets for free.
        form_data = [f for f in merged.values() if _matches(f, type, source)]
    else:
        try:
            query = client.table("forms").select("*")
            if type:   query = query.eq("form_type", type)
            if source: query = query.eq("source", source)

            res = query.order("form_number").limit(_PAGE_SIZE).execute()
        except Exception:
            log.exception("Form listing failed type=%r source=%r", type, source)
            raise HTTPException(status_code=502, detail="Could not load forms.")
        form_data = res.data or []

    # `total` is the size of the full filtered match set; `forms` is the page.
    # It previously returned len(items), which is the page size by definition and
    # so could never tell the client there was anything more to see.
    total = len(form_data)
    page = form_data[:_PAGE_SIZE]

    items = [
        FormItem(
            id              = f["id"],
            form_number     = f.get("form_number") or "FORM",
            form_name       = f.get("title") or f.get("form_name") or "",
            country         = f.get("country") or "",
            source          = f.get("source") or "",
            description     = f.get("rule_reference") or f.get("description") or "",
            b2_key          = f.get("b2_key") or "",
            form_type       = f.get("form_type") or "",
            source_pdf_year = f.get("source_pdf_year") or "",
        )
        for f in page
        if f.get("id") is not None
    ]

    return FormListResponse(forms=items, total=total)


@router.get("/forms/{form_id}/download", response_model=FormDownloadResponse)
async def download_form(form_id: int):
    """Generate a presigned URL for downloading the form segment."""
    client = get_client()

    try:
        res = client.table("forms").select("*").eq("id", form_id).limit(1).execute()
    except Exception:
        log.exception("Form lookup failed for id=%s", form_id)
        raise HTTPException(status_code=502, detail="Could not load form.")

    if not res.data:
        raise HTTPException(status_code=404, detail="Form not found")

    form = res.data[0]
    b2_key = form.get("b2_key")

    if not b2_key:
        raise HTTPException(status_code=400, detail="No source file for this form")

    try:
        # Shared cached client — this route used to build its own via a
        # mid-function `import boto3`, which let the s3v4 signature config drift
        # from explore.py's. B2 rejects s3v2-signed URLs, and that only surfaces
        # when the user clicks download.
        url = get_b2_client().generate_presigned_url(
            "get_object",
            Params    = {"Bucket": bucket_name(), "Key": b2_key},
            ExpiresIn = 3600,
        )
        return FormDownloadResponse(
            # `or` chaining, not .get(x, default): a present-but-NULL title
            # returns None from .get and then fails FormDownloadResponse's
            # required str, turning a valid form into a 500.
            form_name    = form.get("title") or form.get("form_number") or "Form",
            download_url = url,
        )
    except HTTPException:
        raise
    except Exception:
        log.exception("Presign failed for form_id=%s key=%s", form_id, b2_key)
        raise HTTPException(status_code=502, detail="Cloud storage error")
