"""
api/routes/forms.py
Search, view, and download regulatory forms.
"""

import os
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from api.models import FormListResponse, FormDownloadResponse, FormItem
from pipeline.vector_store import get_client
from pipeline.embedder import embed_query

log = logging.getLogger(__name__)

router = APIRouter(tags=["forms"])

class FormSearchRequest(BaseModel):
    query: str
    limit: int = 20

@router.get("/forms", response_model=FormListResponse)
async def list_forms(
    q:    Optional[str] = Query(None, description="Search query"),
    type: Optional[str] = Query(None, description="Filter: Manufacturing / Import / etc"),
    source: Optional[str] = Query(None, description="Filter: cdsco / fda / ema"),
):
    """
    Search or list forms. If 'q' is provided, performs a hybrid keyword+semantic search.
    """
    client = get_client()
    
    if q:
        # 1. Semantic Search
        embedding = embed_query(q)
        semantic_res = client.rpc(
            "search_forms_semantic", 
            {"query_embedding": embedding, "match_threshold": 0.25, "match_count": 20}
        ).execute()
        
        # 2. Keyword Search
        keyword_res = client.rpc(
            "search_forms_keyword", 
            {"query_text": q}
        ).execute()
        
        # 3. Merge & Deduplicate
        merged = {f["id"]: f for f in keyword_res.data}
        for f in semantic_res.data:
            if f["id"] not in merged:
                merged[f["id"]] = f
        
        form_data = list(merged.values())
    else:
        # Default listing
        query = client.table("forms").select("*")
        if type:   query = query.eq("form_type", type)
        if source: query = query.eq("source", source)
        
        res = query.order("form_number").limit(50).execute()
        form_data = res.data

    items = [
        FormItem(
            id          = f["id"],
            form_number = f.get("form_number") or "FORM",
            form_name   = f.get("title") or f.get("form_name") or "",
            country     = f.get("country") or "",
            source      = f.get("source") or "",
            description = f.get("rule_reference") or f.get("description") or "",
            b2_key      = f.get("b2_key") or "",
        )
        for f in form_data
    ]
    
    return FormListResponse(forms=items, total=len(items))


@router.get("/forms/{form_id}/download", response_model=FormDownloadResponse)
async def download_form(form_id: int):
    """Generate a presigned URL for downloading the form segment."""
    client = get_client()
    res = client.table("forms").select("*").eq("id", form_id).execute()
    
    if not res.data:
        raise HTTPException(status_code=404, detail="Form not found")
        
    form = res.data[0]
    b2_key = form.get("b2_key")
    
    if not b2_key:
        raise HTTPException(status_code=400, detail="No source file for this form")

    # Generate presigned URL
    import boto3
    from botocore.config import Config
    b2_client = boto3.client(
        "s3",
        endpoint_url          = os.environ["B2_ENDPOINT"],
        aws_access_key_id     = os.environ["B2_KEY_ID"],
        aws_secret_access_key = os.environ["B2_APP_KEY"],
        region_name           = "auto",
        config                = Config(signature_version='s3v4')
    )

    try:
        url = b2_client.generate_presigned_url(
            "get_object",
            Params    = {"Bucket": os.environ["B2_BUCKET_NAME"], "Key": b2_key},
            ExpiresIn = 3600,
        )
        return FormDownloadResponse(
            form_name    = form.get("title", form.get("form_number", "Form")),
            download_url = url
        )
    except Exception as e:
        log.error(f"Download Error: {e}")
        raise HTTPException(status_code=500, detail="Cloud storage error")