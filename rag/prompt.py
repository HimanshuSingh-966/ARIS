"""
rag/prompt.py
Builds prompts for the LLM from retrieved chunks.
Always instructs LLM to cite sources and never hallucinate.
"""

from typing import Any

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
            header += f" | Section: {section}"
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
    """
    seen    = set()
    sources = []
    for chunk in chunks:
        key = chunk.get("b2_key", "")
        if key not in seen:
            seen.add(key)
            sources.append({
                "doc_name":   chunk.get("doc_name", ""),
                "source":     chunk.get("source", "").upper(),
                "country":    chunk.get("country", ""),
                "section":    chunk.get("section", ""),
                "b2_key":     key,
                "similarity": round(chunk.get("similarity", 0), 3),
            })
    return sources


def is_form_query(query: str) -> bool:
    """Detect if user is asking for a downloadable form."""
    keywords = [
        "form", "download", "application form", "template",
        "form 44", "form 8", "form 40", "ct-", "nda form",
        "anda form", "ind form", "give me the form",
        "where can i get", "application document"
    ]
    query_lower = query.lower()
    return any(kw in query_lower for kw in keywords)