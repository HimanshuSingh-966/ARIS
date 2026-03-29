"""
rag/retriever.py
Vector similarity search against Supabase pgvector.
Returns top-k relevant chunks for a user query.
"""

import os
import logging
from supabase import create_client

log = logging.getLogger(__name__)

_client = None


def get_client():
    global _client
    if _client is None:
        _client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_KEY"]
        )
    return _client


def retrieve(
    query_embedding: list[float],
    top_k:           int            = 5,
    threshold:       float          = 0.3,
    country:         str | None     = None,
    source:          str | None     = None,
    doc_id:          str | None     = None,
) -> list[dict]:
    """
    Search pgvector for relevant chunks.

    Args:
        query_embedding : 384-dim vector from embedder
        top_k           : number of results to return
        threshold       : minimum similarity score (0-1)
        country         : filter by "India" / "USA" / "Europe"
        source          : filter by "cdsco" / "fda" / "ema"
        doc_id          : filter strictly by document id


    Returns:
        list of chunk dicts with similarity scores
    """
    try:
        params = {
            "query_embedding": query_embedding,
            "match_threshold": threshold,
            "match_count":     top_k,
            "filter_source":   source,
            "filter_country":  country,
            "filter_doc_id":   doc_id,
        }
        result = get_client().rpc("match_documents", params).execute()
        return result.data or []
    except Exception as e:
        log.error(f"[Retriever] Search failed: {e}")
        return []


def retrieve_forms(
    country: str | None = None,
    source:  str | None = None,
) -> list[dict]:
    """
    Fetch forms from Supabase forms table.
    Used when user asks for downloadable forms.
    """
    try:
        query = get_client().table("forms").select("*")
        if country:
            query = query.eq("country", country)
        if source:
            query = query.eq("source", source)
        result = query.order("form_number").execute()
        return result.data or []
    except Exception as e:
        log.error(f"[Retriever] Forms fetch failed: {e}")
        return []


def search_forms_by_query(query_text: str) -> list[dict]:
    """
    Search forms by name/number using text matching.
    Used when user specifically asks for a form.
    """
    try:
        result = get_client().table("forms").select("*").ilike(
            "form_name", f"%{query_text}%"
        ).execute()
        return result.data or []
    except Exception as e:
        log.error(f"[Retriever] Form search failed: {e}")
        return []