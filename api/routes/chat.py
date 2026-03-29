"""
api/routes/chat.py
POST /chat — Main RAG query endpoint.
"""

import sys
import os
import logging
from fastapi import APIRouter, Depends

# Project root is in sys.path when running via uvicorn from root

from api.models import ChatRequest, ChatResponse

log = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    Ask a question about pharma regulations.
    Returns an answer with source citations and relevant forms.
    """
    from rag.chain import run as rag_run

    log.info(f"[API] /chat query={req.query[:80]}, country={req.country}, doc_id={req.doc_id}")

    try:
        result = rag_run(
            query   = req.query,
            country = req.country,
            source  = req.source,
            doc_id  = req.doc_id,
            top_k   = req.top_k,
        )

        return ChatResponse(
            answer  = result["answer"],
            sources = result.get("sources", []),
            forms   = result.get("forms", []),
            query   = result["query"],
        )

    except Exception as e:
        log.error(f"[API] /chat error: {e}")
        return ChatResponse(
            answer  = f"Sorry, an error occurred: {str(e)}",
            sources = [],
            forms   = [],
            query   = req.query,
        )