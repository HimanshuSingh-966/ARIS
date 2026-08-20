"""
tests/test_chunker.py

Covers pipeline/chunker.split_into_chunks().

The bug this suite exists for: the chunk dicts did not carry `doc_id`, so
vector_store.save_chunks wrote '' into documents.doc_id for every row. Every
doc-scoped query filters on that column, so per-document chat could never return
anything and the failure was invisible — the API answered "I could not find
relevant information", exactly as it does for a genuinely empty search.
"""

import logging

from pipeline.chunker import (
    CHARS_PER_TOK,
    CHUNK_SIZE,
    chunk_summary,
    detect_section,
    split_into_chunks,
)

META = {
    "source":      "cdsco",
    "country":     "India",
    "doc_name":    "test-doc",
    "doc_id":      "d41d8cd98f00b204e9800998ecf8427e",
    "section_tag": "clinical-trials",
    "b2_key":      "cdsco/test-doc.pdf",
    "source_url":  "https://example.invalid/test-doc.pdf",
}

# Long enough to force several chunks (chunk target is ~2000 chars).
LONG_TEXT = ("The applicant shall submit the required particulars. " * 200)


def test_doc_id_reaches_every_chunk():
    chunks = split_into_chunks(LONG_TEXT, META)
    assert len(chunks) > 1
    assert all(c["doc_id"] == META["doc_id"] for c in chunks)


def test_section_tag_reaches_every_chunk():
    chunks = split_into_chunks(LONG_TEXT, META)
    assert all(c["section_tag"] == "clinical-trials" for c in chunks)


def test_section_tag_and_section_stay_distinct():
    """`section` is a heading found inside the text; `section_tag` is the browse
    category. They live in adjacent columns and were easy to conflate."""
    text = "CHAPTER 4\n" + LONG_TEXT
    chunks = split_into_chunks(text, META)
    later = [c for c in chunks if c["section"]]
    assert later, "expected the CHAPTER 4 heading to be detected for later chunks"
    assert all(c["section"] != c["section_tag"] for c in later)
    assert later[0]["section"] == "CHAPTER 4"


def test_all_metadata_fields_propagate():
    [chunk, *_] = split_into_chunks(LONG_TEXT, META)
    for field in ("source", "country", "doc_name", "b2_key", "source_url"):
        assert chunk[field] == META[field]


def test_missing_doc_id_warns_rather_than_failing_silently(caplog):
    meta = {k: v for k, v in META.items() if k != "doc_id"}
    with caplog.at_level(logging.WARNING, logger="pipeline.chunker"):
        chunks = split_into_chunks(LONG_TEXT, meta)
    assert chunks                      # still usable for global search
    assert all(c["doc_id"] == "" for c in chunks)
    assert "No doc_id" in caplog.text


def test_empty_input_returns_no_chunks():
    assert split_into_chunks("", META) == []
    assert split_into_chunks("   \n\t ", META) == []


def test_offsets_advance_and_overlap():
    chunks = split_into_chunks(LONG_TEXT, META)
    starts = [c["char_start"] for c in chunks]
    assert starts == sorted(starts)
    assert len(set(starts)) == len(starts), "chunk starts must not repeat"
    # Consecutive chunks overlap, so each start precedes the previous end.
    for prev, nxt in zip(chunks, chunks[1:]):
        assert nxt["char_start"] < prev["char_end"]


def test_chunks_are_near_the_target_size():
    chunks = split_into_chunks(LONG_TEXT, META)
    target = CHUNK_SIZE * CHARS_PER_TOK
    assert all(len(c["content"]) <= target + 400 for c in chunks)


def test_short_text_yields_one_chunk():
    text = "The applicant shall submit the prescribed fee along with the form."
    chunks = split_into_chunks(text, META)
    assert len(chunks) == 1
    assert chunks[0]["content"] == text
    assert chunks[0]["doc_id"] == META["doc_id"]


def test_text_below_the_minimum_is_dropped():
    assert split_into_chunks("too short", META) == []


def test_detect_section_returns_the_most_recent_heading():
    assert detect_section("CHAPTER 1\nfoo\nCHAPTER 2\nbar") == "CHAPTER 2"
    assert detect_section("no headings here") == ""


def test_chunk_summary():
    assert chunk_summary([]) == {"count": 0}
    summary = chunk_summary(split_into_chunks(LONG_TEXT, META))
    assert summary["count"] > 1
    assert summary["min_chars"] <= summary["avg_chars"] <= summary["max_chars"]
