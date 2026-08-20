import logging
from typing import Any
from fastembed import TextEmbedding

log = logging.getLogger(__name__)

# Model: BAAI/bge-small-en-v1.5 — high performance, low memory footprint (CPU optimized)
# Dimension: 384 — Matching existing Supabase/pgvector schema
MODEL_NAME = "BAAI/bge-small-en-v1.5"
DIMENSION  = 384

_model = None

def get_model():
    """Lazy load FastEmbed model."""
    global _model
    if _model is None:
        log.info(f"[Embedder] Loading FastEmbed model: {MODEL_NAME}")
        _model = TextEmbedding(model_name=MODEL_NAME)
    return _model

def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for a list of texts using FastEmbed.
    Runs locally, CPU optimized, no rate limits.
    """
    if not texts:
        return []

    try:
        model = get_model()
        # model.embed returns an iterator of numpy arrays
        embeddings = list(model.embed(texts))
        
        # Convert numpy arrays to lists of floats for Supabase compatibility
        return [e.tolist() for e in embeddings]
    except Exception as e:
        log.error(f"[Embedder] FastEmbed embedding failed: {e}")
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
    """
    Embed a single query string for vector search.

    Raises on failure rather than returning a zero vector. A zero vector is a
    valid input to pgvector, so returning one turns a model failure into a
    successful search that finds nothing relevant — indistinguishable from "no
    matching documents" and effectively unobservable. Callers convert this into a
    502 so the frontend can show a real error.
    """
    if not query or not query.strip():
        raise ValueError("embed_query requires a non-empty query string")

    try:
        model = get_model()
        # FastEmbed expects a list, returns an iterator
        embeddings = list(model.embed([query]))
        if not embeddings:
            raise RuntimeError(f"{MODEL_NAME} returned no embedding for the query")
        return embeddings[0].tolist()
    except Exception as e:
        log.error(f"[Embedder] FastEmbed query embedding failed: {e}")
        raise