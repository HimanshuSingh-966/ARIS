"""
rag/retriever.py
Vector similarity search against Supabase pgvector.
Returns top-k relevant chunks or forms for a user query.

On failure these functions RAISE rather than returning []. An empty list is a
meaningful answer — "nothing in the corpus matches" — so using it for errors too
made a database outage indistinguishable from a genuine miss, and the chain then
told the user "I could not find relevant information" while Supabase was down.
Form lookups are the exception: they are an optional enrichment, so a failure
there degrades to "no forms" rather than failing the whole answer.
"""

import logging

log = logging.getLogger(__name__)


def get_client():
    """
    Shared Supabase client.

    Delegates to pipeline.vector_store.get_client instead of holding a second
    module-level singleton, so the whole process uses one connection pool and one
    definition of which credentials to read.
    """
    from pipeline.vector_store import get_client as _get_client

    return _get_client()


def retrieve(
    query_embedding: list[float],
    top_k:           int            = 5,
    threshold:       float          = 0.3,
    country:         str | None     = None,
    source:          str | None     = None,
    doc_id:          str | None     = None,
) -> list[dict]:
    """
    Search pgvector for relevant document chunks.

    Raises on transport/RPC failure — see the module docstring.
    """
    params = {
        "query_embedding": query_embedding,
        "match_threshold": threshold,
        "match_count":     top_k,
        "filter_source":   source,
        "filter_country":  country,
        "filter_doc_id":   doc_id,
    }
    log.info(
        "[Retriever] match_documents call: threshold=%s, top_k=%s, country=%s, "
        "source=%s, doc_id=%s",
        threshold, top_k, country, source, doc_id,
    )

    try:
        result = get_client().rpc("match_documents", params).execute()
    except Exception:
        log.exception("[Retriever] match_documents failed")
        raise

    rows = result.data or []
    log.info("[Retriever] match_documents results: found=%d", len(rows))
    if rows:
        log.info("[Retriever] top_score=%.4f", rows[0].get("similarity", 0.0))

    return rows


# `retrieve_forms(country, source)` used to sit here — an unfiltered
# `select("*")` over the whole forms table. Nothing imported it: api/routes/forms.py
# lists forms through its own paginated query and the chain reaches forms through
# the two search functions below.


def search_forms_by_query(query_text: str) -> list[dict]:
    """
    Keyword search for forms.

    Returns [] on failure: forms are supplementary to the answer, so a forms
    outage should not fail an otherwise-good response.
    """
    try:
        result = get_client().rpc("search_forms_keyword", {"query_text": query_text}).execute()
        return result.data or []
    except Exception as e:
        log.error(f"[Retriever] Form keyword search failed: {e}")
        return []

def search_forms_semantic(query_embedding: list[float], limit: int = 5) -> list[dict]:
    """
    Semantic search for forms using pgvector. Returns [] on failure (see above).
    """
    try:
        params = {
            "query_embedding": query_embedding,
            "match_threshold": 0.2,
            "match_count":     limit
        }
        result = get_client().rpc("search_forms_semantic", params).execute()
        return result.data or []
    except Exception as e:
        log.error(f"[Retriever] Form semantic search failed: {e}")
        return []