"""
rag/prompt.py
Builds prompts for the LLM from retrieved chunks.
Always instructs LLM to cite sources and never hallucinate.
"""

from typing import Any
import re

SYSTEM_PROMPT = """You are an expert pharmaceutical regulatory affairs assistant specializing in regulations for India (CDSCO), USA (FDA), and Europe (EMA).

Your role:
- Answer questions about drug regulations, approval processes, clinical trials, and compliance
- Base your answers ONLY on the provided context documents
- Always cite the source document and country for every claim
- If a question asks for a form, mention the form number and that it can be downloaded
- If the context does not contain enough information, say: "I could not find sufficient information in the available regulatory documents to answer this question completely."
- Never make up regulations or requirements not present in the context
- Be precise and professional — your answers will be used by regulatory affairs professionals

Format your response as:
1. A clear, direct answer to the question
2. Key points with source citations in brackets [Source: Document Name, Country]
3. If relevant forms are available, mention them at the end
"""


def build_prompt(
    query:   str,
    chunks:  list[dict[str, Any]],
    country: str | None = None,
) -> list[dict]:
    """
    Build message list for LLM API call.

    Args:
        query   : user question
        chunks  : retrieved chunks from vector search
        country : optional country filter context

    Returns:
        messages list for LLM API
    """
    # Build context string from chunks
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        source  = chunk.get("source", "").upper()
        country_name = chunk.get("country", "")
        doc_name = chunk.get("doc_name", "")
        section  = chunk.get("section", "")
        content  = chunk.get("content", "")

        header = f"[Document {i}: {doc_name} | {source} | {country_name}"
        if section:
            # This is the heading detected inside the document (chunker.detect_section),
            # not the category slug in section_tag. Label it accordingly so the model
            # doesn't conflate the two.
            header += f" | Heading: {section}"
        header += "]"

        context_parts.append(f"{header}\n{content}")

    context = "\n\n---\n\n".join(context_parts)

    # Build user message
    country_note = f" (focusing on {country} regulations)" if country else ""
    user_message = f"""Question{country_note}: {query}

Context from regulatory documents:
{context}

Please provide a comprehensive answer based on the above context."""

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_message},
    ]


def build_sources(chunks: list[dict[str, Any]]) -> list[dict]:
    """
    Build source citation list for API response.

    Includes doc_id so the frontend can link citations at the streaming proxy
    (/api/v1/documents/{doc_id}/stream) instead of guessing a public bucket URL.
    """
    seen    = set()
    sources = []
    for chunk in chunks:
        key = chunk.get("b2_key", "")
        doc_id = chunk.get("doc_id", "")
        # Prefer doc_id for dedup: if b2_key is ever blank, keying on it alone
        # would collapse every such chunk into a single citation.
        dedup_key = doc_id or key
        if dedup_key not in seen:
            seen.add(dedup_key)
            sources.append({
                "doc_name":   chunk.get("doc_name", ""),
                "source":     chunk.get("source", "").upper(),
                "country":    chunk.get("country", ""),
                "section":    chunk.get("section", ""),
                "doc_id":     doc_id,
                "b2_key":     key,
                "similarity": round(chunk.get("similarity", 0), 3),
            })
    return sources


# Word-bounded so the substring "form" inside "information", "platform",
# "performance", "reform", "transform" and "conform" no longer triggers form
# retrieval — all of which are common in regulatory text, making the old
# substring check fire on a large share of ordinary questions.
_FORM_QUERY_RE = re.compile(
    r"""
      \bforms?\b                    # form, forms — also covers "application form",
                                    # "form 44", "nda form", "give me the form"
    | \bdownload(?:s|ing|able)?\b
    | \btemplates?\b
    | \bct-\s*\d+                   # CDSCO clinical-trial form codes, e.g. CT-01
                                    # \b keeps this off "act-1", "product-1"
    | \bwhere\s+can\s+i\s+get\b
    | \bapplication\s+document\b
    """,
    re.IGNORECASE | re.VERBOSE,
)


def is_form_query(query: str) -> bool:
    """Detect if user is asking for a downloadable form."""
    if not query:
        return False
    return _FORM_QUERY_RE.search(query) is not None