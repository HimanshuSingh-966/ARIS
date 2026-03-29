"""
api/routes/forms.py
GET /forms         — List all forms (with optional filters)
GET /forms/{id}/download — Get presigned download URL for a form
"""

import os
import sys
import logging
from fastapi import APIRouter, Depends, HTTPException, Query

# Project root is in sys.path when running via uvicorn from root

from api.models import FormListResponse, FormDownloadResponse, FormItem

log = logging.getLogger(__name__)

router = APIRouter(tags=["forms"])


@router.get("/forms", response_model=FormListResponse)
async def list_forms(
    country: str | None = Query(None, description="Filter: India / USA / Europe"),
    source:  str | None = Query(None, description="Filter: cdsco / fda / ema"),
):
    """List all available regulatory forms."""
    from rag.retriever import retrieve_forms

    forms = retrieve_forms(country=country, source=source)

    form_items = [
        FormItem(
            id          = f.get("id", 0),
            form_number = f.get("form_number", ""),
            form_name   = f.get("form_name", ""),
            country     = f.get("country", ""),
            source      = f.get("source", ""),
            description = f.get("description", ""),
            b2_key      = f.get("b2_key", ""),
        )
        for f in forms
    ]

    return FormListResponse(forms=form_items, total=len(form_items))


@router.get("/forms/{form_id}/download", response_model=FormDownloadResponse)
async def download_form(
    form_id: int,
):
    """Get a presigned download URL for a specific form."""
    from supabase import create_client

    # Fetch form from Supabase
    client = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_KEY"],
    )

    result = client.table("forms").select("*").eq("id", form_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Form not found")

    form = result.data[0]
    b2_key = form.get("b2_key", "")

    if not b2_key:
        raise HTTPException(status_code=404, detail="No file associated with this form")

    # Generate presigned URL via B2
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
    except Exception as e:
        log.error(f"[API] Presigned URL error: {e}")
        raise HTTPException(status_code=500, detail="Could not generate download URL")

    return FormDownloadResponse(
        form_name    = form.get("form_name", ""),
        download_url = url,
        expires_in   = 3600,
    )