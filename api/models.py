"""
api/models.py
Pydantic request/response models for all API endpoints.
"""

from pydantic import BaseModel, Field
from typing import Optional


# ── Chat ──────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query:   str            = Field(..., min_length=1, max_length=2000, description="User question")
    country: Optional[str]  = Field(None, description="Filter: India / USA / Europe")
    source:  Optional[str]  = Field(None, description="Filter: cdsco / fda / ema")
    doc_id:  Optional[str]  = Field(None, description="Filter: Limit RAG context to a specific document ID")
    top_k:   int            = Field(5, ge=1, le=20, description="Number of chunks to retrieve")


class SourceCitation(BaseModel):
    doc_name:   str
    source:     str
    country:    str
    section:    str = ""
    b2_key:     str = ""
    similarity: float = 0.0


class FormItem(BaseModel):
    id:          int
    form_number: Optional[str] = ""
    form_name:   Optional[str] = ""
    country:     Optional[str] = ""
    source:      Optional[str] = ""
    description: Optional[str] = ""
    b2_key:      Optional[str] = ""


class ChatResponse(BaseModel):
    answer:  str
    sources: list[SourceCitation] = []
    forms:   list[FormItem]       = []
    query:   str


# ── Forms ─────────────────────────────────────────────────────────────────────

class FormListResponse(BaseModel):
    forms: list[FormItem]
    total: int


class FormDownloadResponse(BaseModel):
    form_name:    str
    download_url: str
    expires_in:   int = 3600


# ── Health ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status:  str = "ok"
    version: str = "1.0.0"