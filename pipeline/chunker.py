"""
pipeline/chunker.py
Splits extracted text into ~500 token chunks with 50 token overlap.
Tags each chunk with metadata for RAG retrieval.
"""

import re
import logging
from typing import Any

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
CHUNK_SIZE    = 500    # tokens (approx 4 chars per token → ~2000 chars)
CHUNK_OVERLAP = 50     # tokens overlap between chunks
CHARS_PER_TOK = 4      # rough estimate


# ── Section detection ─────────────────────────────────────────────────────────

# Patterns that indicate a new section heading
SECTION_PATTERNS = [
    r"^CHAPTER\s+\d+",
    r"^SECTION\s+\d+",
    r"^PART\s+[IVX]+",
    r"^SCHEDULE\s+[A-Z]",
    r"^\d+\.\s+[A-Z]",          # 1. Introduction
    r"^[A-Z][A-Z\s]{10,}$",     # ALL CAPS HEADING
    r"^Article\s+\d+",
    r"^Regulation\s+\d+",
    r"^Guideline\s+\d+",
]

SECTION_RE = re.compile("|".join(SECTION_PATTERNS), re.MULTILINE)


def detect_section(text_before: str) -> str:
    """Find the most recent section heading before this chunk."""
    matches = list(SECTION_RE.finditer(text_before))
    if matches:
        last = matches[-1]
        return last.group(0).strip()[:100]
    return ""


# ── Chunking ──────────────────────────────────────────────────────────────────

def split_into_chunks(text: str, metadata: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Split text into overlapping chunks.
    Each chunk is a dict with content + full metadata.

    Args:
        text     : cleaned extracted text
        metadata : {source, country, doc_name, b2_key, source_url}

    Returns:
        list of chunk dicts ready for embedding
    """
    if not text or not text.strip():
        return []

    chunk_chars   = CHUNK_SIZE    * CHARS_PER_TOK   # ~2000 chars
    overlap_chars = CHUNK_OVERLAP * CHARS_PER_TOK   # ~200 chars

    chunks = []
    start  = 0
    text_len = len(text)

    while start < text_len:
        end = start + chunk_chars

        # Try to end at a sentence boundary
        if end < text_len:
            # Look for sentence end within last 20% of chunk
            search_start = start + int(chunk_chars * 0.8)
            snippet      = text[search_start:end + 200]

            # Find last sentence-ending punctuation
            sentence_end = max(
                snippet.rfind(". "),
                snippet.rfind(".\n"),
                snippet.rfind("? "),
                snippet.rfind("! "),
            )

            if sentence_end > 0:
                end = search_start + sentence_end + 1

        chunk_text = text[start:end].strip()

        if len(chunk_text) < 50:
            start = end - overlap_chars
            continue

        # Detect which section this chunk belongs to
        section = detect_section(text[:start])

        chunk = {
            "content":    chunk_text,
            "source":     metadata.get("source", ""),
            "country":    metadata.get("country", ""),
            "doc_name":   metadata.get("doc_name", ""),
            "section":    section,
            "b2_key":     metadata.get("b2_key", ""),
            "source_url": metadata.get("source_url", ""),
            "char_start": start,
            "char_end":   end,
        }
        chunks.append(chunk)

        # Move forward with overlap
        start = end - overlap_chars
        if start <= 0:
            break

    log.info(f"Chunked '{metadata.get('doc_name', '')}' → {len(chunks)} chunks")
    return chunks


def estimate_tokens(text: str) -> int:
    """Rough token count estimate (1 token ≈ 4 chars)."""
    return len(text) // CHARS_PER_TOK


def chunk_summary(chunks: list[dict]) -> dict:
    """Return summary stats about chunks."""
    if not chunks:
        return {"count": 0}
    sizes = [len(c["content"]) for c in chunks]
    return {
        "count":        len(chunks),
        "avg_chars":    sum(sizes) // len(sizes),
        "min_chars":    min(sizes),
        "max_chars":    max(sizes),
        "total_chars":  sum(sizes),
        "approx_tokens": sum(sizes) // CHARS_PER_TOK,
    }