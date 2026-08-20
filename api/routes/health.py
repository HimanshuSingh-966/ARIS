"""
api/routes/health.py
Health check endpoint for Render / monitoring.
"""

from fastapi import APIRouter

from api import __version__
from api.models import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok", version=__version__)