"""
api/routes/chat.py
POST /chat — Main RAG query endpoint.
"""

import logging
from fastapi import APIRouter, HTTPException

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

    except HTTPException:
        raise

    except Exception:
        # This used to return HTTP 200 with the exception text inside `answer`.
        # Two problems with that: the frontend's `if (!response.ok)` branch could
        # never fire, so an outage rendered as an ordinary assistant message, and
        # str(e) put internal detail (keys, hostnames, SQL) in a public response.
        log.exception("[API] /chat failed for query=%r", req.query[:200])
        raise HTTPException(
            status_code=502,
            detail="The assistant is temporarily unavailable. Please try again.",
        )