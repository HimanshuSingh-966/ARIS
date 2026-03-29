import os
import logging
import time
from typing import Any

log = logging.getLogger(__name__)

# Model: gemini-embedding-2-preview — high performance, low memory footprint (API based)
MODEL_NAME = "models/gemini-embedding-2-preview"
DIMENSION  = 384   # Matching existing Supabase/pgvector schema

def get_model():
    """Gemini embeddings don't need a local model instance, just the API key."""
    if not os.environ.get("GEMINI_API_KEY"):
        log.warning("[Embedder] GEMINI_API_KEY not set!")
    return None

def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for a list of texts using Google Gemini API.
    """
    if not texts:
        return []

    try:
        import google.generativeai as genai
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        
        # Batch processing is handled by the API itself or we can loop
        # For simplicity and reliability with smaller inputs, we use the batch API
        result = genai.embed_content(
            model=MODEL_NAME,
            content=texts,
            task_type="retrieval_document",
            output_dimensionality=DIMENSION
        )
        return result['embedding']
    except Exception as e:
        log.error(f"[Embedder] Gemini embedding failed: {e}")
        raise

def embed_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add embeddings to a list of chunk dicts."""
    if not chunks:
        return []

    texts      = [c["content"] for c in chunks]
    embeddings = embed_texts(texts)

    for chunk, embedding in zip(chunks, embeddings):
        chunk["embedding"] = embedding

    return chunks

def embed_query(query: str) -> list[float]:
    """Embed a single query string for vector search."""
    try:
        import google.generativeai as genai
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        
        result = genai.embed_content(
            model=MODEL_NAME,
            content=query,
            task_type="retrieval_query",
            output_dimensionality=DIMENSION
        )
        return result['embedding']
    except Exception as e:
        log.error(f"[Embedder] Gemini query embedding failed: {e}")
        return [0.0] * DIMENSION
