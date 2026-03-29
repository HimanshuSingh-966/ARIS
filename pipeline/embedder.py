"""
pipeline/embedder.py
Generates 384-dimensional embeddings using sentence-transformers.
Model: all-MiniLM-L6-v2 — free, fast, runs locally, no API needed.
"""

import logging
import time
from typing import Any

log = logging.getLogger(__name__)

MODEL_NAME = "all-MiniLM-L6-v2"
BATCH_SIZE = 32   # chunks per embedding batch

_model = None     # cached model instance


def get_model():
    """Load model once and cache it."""
    global _model
    if _model is None:
        print(f"  [Embedder] Loading {MODEL_NAME}...")
        start = time.time()
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)
        elapsed = time.time() - start
        print(f"  [Embedder] Model loaded in {elapsed:.1f}s")
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for a list of texts.
    Processes in batches to manage memory.

    Args:
        texts: list of text strings to embed

    Returns:
        list of 384-dimensional float vectors
    """
    if not texts:
        return []

    model      = get_model()
    embeddings = []

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        print(f"  [Embedder] Embedding batch {i//BATCH_SIZE + 1}/"
              f"{(len(texts) + BATCH_SIZE - 1)//BATCH_SIZE} "
              f"({len(batch)} texts)")
        batch_embeddings = model.encode(
            batch,
            show_progress_bar = False,
            convert_to_numpy  = True,
        )
        embeddings.extend([tensor.tolist() for tensor in batch_embeddings])

    return embeddings


def embed_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Add embeddings to a list of chunk dicts.

    Args:
        chunks: list of chunk dicts from chunker.py

    Returns:
        same chunks with 'embedding' field added
    """
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
    Used by the RAG retriever.

    Args:
        query: user question

    Returns:
        384-dimensional float vector
    """
    model     = get_model()
    embedding = model.encode([query], convert_to_numpy=True)
    return embedding[0].tolist()