from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
import os
import boto3
from botocore.config import Config
from supabase import create_client, Client

router = APIRouter(tags=["explore"])

# Helper: Supabase Client
def get_supabase() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY", os.environ.get("SUPABASE_ANON_KEY"))
    if not url or not key:
        raise HTTPException(status_code=500, detail="Supabase credentials missing.")
    return create_client(url, key)

# Helper: B2 Client (Using S3 compat API)
def get_b2_client():
    endpoint = os.environ.get("B2_ENDPOINT")
    key_id = os.environ.get("B2_KEY_ID")
    app_key = os.environ.get("B2_APP_KEY")
    
    if not all([endpoint, key_id, app_key]):
        raise HTTPException(status_code=500, detail="B2 credentials missing.")
        
    return boto3.client(
        's3',
        endpoint_url=endpoint,
        aws_access_key_id=key_id,
        aws_secret_access_key=app_key,
        region_name='auto',
        config=Config(signature_version='s3v4')
    )

# 1. Get Sources Overview
@router.get("/sources")
async def get_sources():
    # In a full system, we might query distinct sources. 
    # For now, we return the hardcoded structure.
    return {
        "sources": [
            {"id": "cdsco", "name": "India CDSCO"},
            {"id": "ema", "name": "Europe EMA"},
            {"id": "fda", "name": "US FDA"}
        ]
    }

# 2. Get Sections for a Source
@router.get("/sources/{source}/sections")
async def get_sections(source: str):
    supabase = get_supabase()
    # Query distinct sections for this source
    # Note: Supabase Python currently requires RPC for grouped/distinct counts, 
    # so we'll fetch them normally or use predefined mappings.
    res = supabase.table("doc_metadata").select("section").eq("source", source.lower()).execute()
    
    # Deduplicate in memory, filtering out null/empty sections
    sections = list(set([row["section"] for row in res.data if row.get("section")]))
    return {"source": source, "sections": sections}

# 3. Get Documents within a Section
@router.get("/sources/{source}/sections/{section}/documents")
async def get_documents(
    source: str, 
    section: str, 
    search: str = Query(None), 
    sort: str = Query("newest"),
    limit: int = 50
):
    supabase = get_supabase()
    query = supabase.table("doc_metadata").select("*").eq("source", source.lower()).eq("section", section.lower())
    
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
        
    # Apply limit
    query = query.limit(limit)
    res = query.execute()
    
    return {"documents": res.data}

# 4. Stream PDF bytes directly from B2 through FastAPI (avoids CORS entirely)
@router.get("/documents/{doc_id}/stream")
async def stream_document(doc_id: str):
    supabase = get_supabase()
    res = supabase.table("doc_metadata").select("b2_key, doc_name").eq("doc_id", doc_id).execute()
    
    if not res.data:
        raise HTTPException(status_code=404, detail="Document not found.")
        
    b2_key = res.data[0]["b2_key"]
    doc_name = res.data[0]["doc_name"]
    bucket_name = os.environ.get("B2_BUCKET_NAME", "pharma-rag-docs")

    b2 = get_b2_client()
    
    try:
        obj = b2.get_object(Bucket=bucket_name, Key=b2_key)
        body = obj["Body"]
        
        def iter_chunks():
            for chunk in body.iter_chunks(chunk_size=65536):
                yield chunk
        
        return StreamingResponse(
            iter_chunks(),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{doc_name}.pdf"',
                "Cache-Control": "private, max-age=3600",
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 5. Generate Presigned URL for direct downloading
@router.get("/documents/{doc_id}/url")
async def get_document_url(doc_id: str):
    supabase = get_supabase()
    res = supabase.table("doc_metadata").select("b2_key, doc_name").eq("doc_id", doc_id).execute()
    
    if not res.data:
        raise HTTPException(status_code=404, detail="Document not found.")
        
    b2_key = res.data[0]["b2_key"]
    doc_name = res.data[0]["doc_name"]
    bucket_name = os.environ.get("B2_BUCKET_NAME", "pharma-rag-docs")
    
    b2 = get_b2_client()
    
    try:
        url = b2.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': bucket_name, 
                'Key': b2_key,
                'ResponseContentDisposition': f'attachment; filename="{doc_name}.pdf"',
            },
            ExpiresIn=3600
        )
        return {"url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

