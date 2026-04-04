"""
rag/chain.py
Full RAG chain — ties everything together.
query → embed → retrieve → prompt → LLM → response with citations
"""

import os
import sys
import logging
from typing import Any

try:
    from dotenv import load_dotenv
    load_dotenv("../.env")
except ImportError:
    pass

# Project root is in sys.path when running via uvicorn from root

try:
    from pipeline.embedder import embed_query
except ImportError:
    raise ImportError("Could not import pipeline.embedder. Ensure pipeline/ module exists.")

from rag.retriever import retrieve, retrieve_forms, search_forms_by_query, search_forms_semantic
from rag.prompt    import build_prompt, build_sources, is_form_query
from rag.llm       import generate

log = logging.getLogger(__name__)


def run(
    query:   str,
    country: str | None = None,
    source:  str | None = None,
    doc_id:  str | None = None,
    top_k:   int        = 5,
) -> dict[str, Any]:
    """
    Full RAG chain.

    Args:
        query   : user question
        country : optional filter — "India" / "USA" / "Europe"
        source  : optional filter — "cdsco" / "fda" / "ema"
        doc_id  : optional filter - lock context to specific document
        top_k   : number of chunks to retrieve

    Returns:
        {
            answer  : str,
            sources : list of source citations,
            forms   : list of relevant downloadable forms,
            query   : original query
        }
    """
    log.info(f"[Chain] Query: {query[:80]}")

    # Step 1 — Embed query
    query_embedding = embed_query(query)

    # Step 2 — Retrieve relevant chunks
    chunks = retrieve(
        query_embedding = query_embedding,
        top_k           = top_k,
        threshold       = 0.15,
        country         = country,
        source          = source,
        doc_id          = doc_id,
    )
    log.info(f"[Chain] Retrieved {len(chunks)} chunks")

    # Step 3 — Find relevant forms if query asks for them
    forms = []
    if is_form_query(query):
        # 1. Keyword search (exact matches like "Form 44")
        keywords = _extract_form_keywords(query)
        for kw in keywords:
            forms.extend(search_forms_by_query(kw))

        # 2. Semantic search (intent-based matches like "licence")
        semantic_forms = search_forms_semantic(query_embedding, limit=5)
        forms.extend(semantic_forms)

        # 3. Deduplicate and Rank
        seen_ids = set()
        unique_forms = []
        for f in forms:
            if f["id"] not in seen_ids:
                seen_ids.add(f["id"])
                # Add download metadata for UI
                unique_forms.append({
                    "id":          f["id"],
                    "form_number": f.get("form_number", ""),
                    "form_name":   f.get("title", f.get("form_name", "")),
                    "country":     f.get("country", ""),
                    "source":      f.get("source", ""),
                    "description": f.get("rule_reference", ""),
                    "b2_key":      f.get("b2_key", ""),
                })
        
        forms = unique_forms[:5]

    # Step 4 — Build prompt
    if not chunks:
        return {
            "answer":  "I could not find relevant information in the regulatory documents for your query. Please try rephrasing or specifying the country (India, USA, or Europe).",
            "sources": [],
            "forms":   forms,
            "query":   query,
        }

    messages = build_prompt(query, chunks, country)

    # Step 5 — Generate answer
    try:
        answer = generate(messages, max_tokens=2048)
    except Exception as e:
        log.error(f"[Chain] LLM error: {e}")
        answer = f"Error generating response: {str(e)}"

    # Step 6 — Build sources
    sources = build_sources(chunks)

    return {
        "answer":  answer,
        "sources": sources,
        "forms":   forms,
        "query":   query,
    }


def _extract_form_keywords(query: str) -> list[str]:
    """Extract form-related keywords from query for form search."""
    import re
    keywords = []

    # Extract form numbers like "Form 44", "Form CT-04", "Form 8A"
    matches = re.findall(r"form\s+(?:no\.?\s*)?(\d+[a-z]?(?:-\d+[a-z]*)?)", query, re.IGNORECASE)
    keywords.extend([f"FORM {m.upper()}" for m in matches])

    # Extract CT form references
    ct_matches = re.findall(r"(CT[-\s]\d+[A-Z]?)", query, re.IGNORECASE)
    keywords.extend(ct_matches)

    # General form name keywords
    general = ["import licence", "registration", "clinical trial", "new drug", "nda", "anda"]
    for g in general:
        if g.lower() in query.lower():
            keywords.append(g)

    return keywords if keywords else [query[:50]]


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    test_queries = [
        "What is the process for new drug approval in India?",
        "How do I apply for an import licence in India? Give me the form.",
        "What are the requirements for clinical trials under CDSCO?",
    ]

    for q in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: {q}")
        print("="*60)

        result = run(q, country="India")

        print(f"\nAnswer:\n{result['answer']}")
        print(f"\nSources ({len(result['sources'])}):")
        for s in result["sources"]:
            print(f"  - {s['doc_name']} [{s['source']}] score={s['similarity']}")

        if result["forms"]:
            print(f"\nRelevant forms ({len(result['forms'])}):")
            for f in result["forms"]:
                print(f"  - {f['form_name']} ({f['country']})")