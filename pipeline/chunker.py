"""
pipeline/chunker.py
Splits extracted text into ~400 token chunks with 60 token overlap.
Tags each chunk with metadata for RAG retrieval.
"""

import re
import logging
from typing import Any

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
#
# These three are pinned by the embedding model, not chosen for retrieval taste.
# BAAI/bge-small-en-v1.5 is BERT-based with max_position_embeddings = 512, which is
# a hard architectural cap — 2 of those go to the [CLS]/[SEP] markers, leaving 510
# usable. FastEmbed truncates past that **silently**: no exception, no warning. The
# full chunk text still reaches documents.content, so a row that is too long looks
# completely correct while its embedding represents only the opening ~510 tokens.
# The tail is stored and unsearchable, and the only symptom is answers being quietly
# worse.
#
# CHARS_PER_TOK is 3, not the more familiar 4. Two reasons:
#
#   1. 4.0 chars/token is a GPT-family BPE figure over English prose (50-100k
#      vocab). bge-small uses BERT WordPiece with a 30,522 vocab, which compresses
#      worse — nearer 3.5-3.8 on plain English, and 3.0-3.4 on this corpus, where
#      form codes, rule numbers, dates and acronyms fragment into many tokens each.
#
#   2. The sentence-boundary search below may overshoot the nominal size by up to
#      200 chars, so the real ceiling is CHUNK_SIZE * CHARS_PER_TOK + 200. At 3 that
#      is 1400 chars — roughly 410-480 real tokens, inside 510 even on the worst
#      ratio. At 4 it was 2200 chars, which needs 4.3 chars/token to fit and so
#      overflowed by the config's own assumption before the corpus was considered.
#
# Keep CHARS_PER_TOK an int: it multiplies into the slice indices below.
#
# Note this cannot rescue non-English text. bge-small-**en** has almost no Cyrillic
# wordpieces, so Bulgarian degrades toward per-character tokens (~1-1.5 chars/token)
# and no chunk size fits. Those documents need excluding, not resizing.
CHUNK_SIZE    = 400    # tokens (approx 3 chars per token → ~1200 chars)
CHUNK_OVERLAP = 60     # tokens overlap between chunks
CHARS_PER_TOK = 3      # rough estimate


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
        metadata : {source, country, doc_name, doc_id, section_tag, b2_key, source_url}
                   doc_id and section_tag are required for doc-scoped retrieval and
                   browse-by-section; a missing doc_id is warned about rather than
                   stored as '' silently.

    Returns:
        list of chunk dicts ready for embedding
    """
    if not text or not text.strip():
        return []

    if not metadata.get("doc_id"):
        log.warning(
            "No doc_id in metadata for '%s' - chunks will not be retrievable by "
            "document. Caller should set it (see ingestor.process_document).",
            metadata.get("doc_name", "<unknown>"),
        )

    chunk_chars   = CHUNK_SIZE    * CHARS_PER_TOK   # ~1200 chars
    overlap_chars = CHUNK_OVERLAP * CHARS_PER_TOK   # ~180 chars

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
            # `section` is the heading detected inside the document; `section_tag`
            # is the category slug assigned by the ingestor. Two different things
            # that happen to live in adjacent columns — keep them separate.
            "section":    section,
            "section_tag": metadata.get("section_tag", ""),
            # Must be propagated: vector_store.save_chunks writes doc_id straight
            # into the documents table, and every doc-scoped query filters on it.
            # Omitting it here silently stores '' and breaks per-document chat.
            "doc_id":     metadata.get("doc_id", ""),
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
    """Rough token count estimate (1 token ≈ CHARS_PER_TOK chars)."""
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
