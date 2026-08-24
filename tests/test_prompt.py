"""
tests/test_prompt.py

Covers rag/prompt.py: the form-query detector and citation building.

is_form_query() gates an extra pair of database round-trips per question, and the
old implementation was a bare substring check for "form" — which matches
"information", "platform", "performance", "reform", "transform" and "conform".
Those words are everywhere in regulatory text, so it fired on a large share of
ordinary questions. The negative cases below are the actual regression suite.
"""

import pytest

from rag.prompt import build_prompt, build_sources, is_form_query


# ── is_form_query — must NOT fire ─────────────────────────────────────────────

@pytest.mark.parametrize("query", [
    "What information is required for a new drug application?",
    "Describe the platform technology requirements.",
    "What are the performance standards for medical devices?",
    "Explain the 2019 reform of clinical trial rules.",
    "How do I transform the data before submission?",
    "Does the product conform to Schedule M?",
    "What is the transformation timeline?",
    "Summarise the Drugs and Cosmetics Act-1940.",   # 'ct-1' must not match 'ct-\d'
    "Which product-1 category applies?",
    "What is the approval process in India?",
    "",
])
def test_is_form_query_negative(query):
    assert is_form_query(query) is False


def test_is_form_query_handles_none():
    assert is_form_query(None) is False


# ── is_form_query — must fire ─────────────────────────────────────────────────

@pytest.mark.parametrize("query", [
    "Give me Form 44.",
    "Which forms do I need for an import licence?",
    "I need the application form.",
    "Where can I download it?",
    "downloads for clinical trial submissions",
    "Is there a downloadable version?",
    "downloading the licence paperwork",
    "Do you have a template?",
    "Fill CT-01 for clinical trials.",
    "ct- 5 requirements",
    "Where can I get the import licence?",
    "Send the application document.",
])
def test_is_form_query_positive(query):
    assert is_form_query(query) is True


def test_is_form_query_is_case_insensitive():
    assert is_form_query("GIVE ME FORM 44") is True
    assert is_form_query("INFORMATION REQUIRED") is False


# ── build_sources ─────────────────────────────────────────────────────────────

def _chunk(**kw):
    base = {
        "doc_name": "d", "source": "cdsco", "country": "India",
        "section": "", "doc_id": "id1", "b2_key": "k1", "similarity": 0.5,
    }
    base.update(kw)
    return base


def test_build_sources_emits_doc_id():
    """The frontend links citations at /documents/{doc_id}/stream — without this
    field it fell back to guessing a public bucket URL, which 403s."""
    [src] = build_sources([_chunk(doc_id="abc123")])
    assert src["doc_id"] == "abc123"


def test_build_sources_dedups_on_doc_id():
    sources = build_sources([
        _chunk(doc_id="a", b2_key="k1"),
        _chunk(doc_id="a", b2_key="k1"),
        _chunk(doc_id="b", b2_key="k2"),
    ])
    assert [s["doc_id"] for s in sources] == ["a", "b"]


def test_blank_b2_key_does_not_collapse_distinct_documents():
    """Keying dedup on b2_key alone folded every blank-key chunk into one citation."""
    sources = build_sources([
        _chunk(doc_id="a", b2_key=""),
        _chunk(doc_id="b", b2_key=""),
    ])
    assert len(sources) == 2


def test_build_sources_uppercases_source_and_rounds_similarity():
    [src] = build_sources([_chunk(source="fda", similarity=0.123456)])
    assert src["source"] == "FDA"
    assert src["similarity"] == 0.123


def test_build_sources_tolerates_missing_keys():
    [src] = build_sources([{}])
    assert src["doc_name"] == "" and src["similarity"] == 0


# ── build_prompt ──────────────────────────────────────────────────────────────

def test_build_prompt_labels_the_in_document_heading_as_heading():
    """`section` is a detected heading, `section_tag` is a category slug. Labelling
    the former "Section" invited the model to conflate them."""
    messages = build_prompt("q", [_chunk(section="CHAPTER 4")])
    user = messages[1]["content"]
    assert "Heading: CHAPTER 4" in user


def test_build_prompt_omits_empty_heading():
    messages = build_prompt("q", [_chunk(section="")])
    assert "Heading:" not in messages[1]["content"]


def test_build_prompt_shape_and_country_note():
    messages = build_prompt("What is X?", [_chunk()], country="India")
    assert [m["role"] for m in messages] == ["system", "user"]
    assert "focusing on India" in messages[1]["content"]
    assert "What is X?" in messages[1]["content"]
