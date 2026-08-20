"""
tests/test_models.py

Covers api/models.py validators.

source_pdf_year is a year, so it is very likely an integer column in Supabase.
Pydantic v2 does not coerce int -> str, so handing the raw row value to
FormItem(source_pdf_year=2024) raises a ValidationError — and because the whole
list is built in one comprehension, a single such row turned GET /forms into a 500.
"""

import pytest
from pydantic import ValidationError

from api.models import ChatRequest, FormItem, SourceCitation


# ── FormItem.source_pdf_year ──────────────────────────────────────────────────

@pytest.mark.parametrize("given, expected", [
    (2024, "2024"),        # the integer column case that used to 500
    ("2024", "2024"),
    (None, ""),
    ("", ""),
])
def test_source_pdf_year_is_coerced_to_string(given, expected):
    assert FormItem(id=1, source_pdf_year=given).source_pdf_year == expected


def test_form_type_is_returned():
    """FormsPage filters on this and FormCard renders it; it was never in the
    response, so both were reading a field that could not arrive."""
    assert FormItem(id=1, form_type="Manufacturing").form_type == "Manufacturing"


def test_form_item_requires_an_id():
    """id is the download route's parameter — a row without one is unusable."""
    with pytest.raises(ValidationError):
        FormItem()


def test_form_item_defaults_are_empty_strings_not_none():
    item = FormItem(id=1)
    assert item.form_number == "" and item.source_pdf_year == ""


# ── SourceCitation ────────────────────────────────────────────────────────────

def test_source_citation_carries_doc_id():
    """Without this the frontend had to guess a public Backblaze URL, which 403s
    on a private bucket."""
    cite = SourceCitation(doc_name="d", source="CDSCO", country="India", doc_id="abc")
    assert cite.doc_id == "abc"


def test_source_citation_doc_id_defaults_empty():
    cite = SourceCitation(doc_name="d", source="CDSCO", country="India")
    assert cite.doc_id == ""


# ── ChatRequest bounds ────────────────────────────────────────────────────────

def test_chat_request_rejects_empty_and_oversized_queries():
    with pytest.raises(ValidationError):
        ChatRequest(query="")
    with pytest.raises(ValidationError):
        ChatRequest(query="x" * 2001)


def test_chat_request_top_k_is_bounded():
    assert ChatRequest(query="q").top_k == 5
    with pytest.raises(ValidationError):
        ChatRequest(query="q", top_k=0)
    with pytest.raises(ValidationError):
        ChatRequest(query="q", top_k=21)


def test_chat_request_doc_id_defaults_to_none():
    """None means 'no filter'. The frontend used to send the literal string
    "Global Mode" here, which reached the database as a doc_id and matched nothing."""
    assert ChatRequest(query="q").doc_id is None
