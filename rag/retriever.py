"""
rag/retriever.py
Vector similarity search against Supabase pgvector.
Returns top-k relevant chunks or forms for a user query.
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
    """Search pgvector for relevant document chunks."""
    try:
        params = {
            "query_embedding": query_embedding,
            "match_threshold": threshold,
            "match_count":     top_k,
            "filter_source":   source,
            "filter_country":  country,
            "filter_doc_id":   doc_id,
        }
        log.info(f"[Retriever] match_documents call: threshold={threshold}, top_k={top_k}, country={country}, source={source}")
        result = get_client().rpc("match_documents", params).execute()
        
        found_count = len(result.data) if result.data else 0
        log.info(f"[Retriever] match_documents results: found={found_count}")
        if found_count > 0:
            top_score = result.data[0].get('similarity', 0)
            log.info(f"[Retriever] Match found: top_score={top_score:.4f}")
            
        return result.data or []
    except Exception as e:
        log.error(f"[Retriever] Doc search failed: {e}")
        return []


def retrieve_forms(
    country: str | None = None,
    source:  str | None = None,
) -> list[dict]:
    """Fetch all forms from Supabase forms table."""
    try:
        query = get_client().table("forms").select("*")
        if country: query = query.eq("country", country)
        if source:  query = query.eq("source", source)
        result = query.order("form_number").execute()
        return result.data or []
    except Exception as e:
        log.error(f"[Retriever] Forms fetch failed: {e}")
        return []


def search_forms_by_query(query_text: str) -> list[dict]:
    """
    Keywords search for forms.
    """
    try:
        result = get_client().rpc("search_forms_keyword", {"query_text": query_text}).execute()
        return result.data or []
    except Exception as e:
        log.error(f"[Retriever] Form keyword search failed: {e}")
        return []

def search_forms_semantic(query_embedding: list[float], limit: int = 5) -> list[dict]:
    """
    Semantic search for forms using pgvector.
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