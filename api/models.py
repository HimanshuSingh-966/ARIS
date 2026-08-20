"""
api/models.py
Pydantic request/response models for all API endpoints.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional

from api import __version__


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
    # Lets the frontend link a citation at /api/v1/documents/{doc_id}/stream
    # instead of guessing a public Backblaze URL, which 403s on a private bucket.
    doc_id:     str = ""


class FormItem(BaseModel):
    id:          int
    form_number: Optional[str] = ""
    form_name:   Optional[str] = ""
    country:     Optional[str] = ""
    source:      Optional[str] = ""
    description: Optional[str] = ""
    b2_key:      Optional[str] = ""
    # Both are read by the frontend (FormCard renders a source_pdf_year badge and
    # FormsPage filters on category) but were never returned, so the badge was
    # dead markup and the client had no way to show which category a hit was in.
    form_type:       Optional[str] = ""
    source_pdf_year: Optional[str] = ""

    @field_validator("source_pdf_year", mode="before")
    @classmethod
    def _stringify_year(cls, v):
        """
        source_pdf_year is a year and may well be an integer column. Pydantic v2
        does not coerce int -> str, so passing 2024 straight from the row would
        raise a validation error and turn the whole forms list into a 500.
        """
        return "" if v is None else str(v)


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
    version: str = __version__