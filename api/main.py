"""
api/main.py
FastAPI entry point — ARIS Backend API
"""

import os
import sys
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass

# Project root is in sys.path when running via uvicorn from root

logging.basicConfig(
    level  = logging.INFO,
    format = "%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# Import routers
from api.routes.health import router as health_router
from api.routes.chat   import router as chat_router
from api.routes.forms  import router as forms_router
from api.routes.explore import router as explore_router  # type: ignore


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm up the embedding model at startup."""
    try:
        from pipeline.embedder import get_model
        log.info("[Startup] Pre-loading embedding model...")
        get_model()
        log.info("[Startup] Embedding model ready")
    except Exception as e:
        log.warning(f"[Startup] Could not pre-load model: {e}")
    yield
    log.info("[Shutdown] API shutting down")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title       = "ARIS API",
    description = "Automated Regulatory Intelligence System — India (CDSCO), USA (FDA), Europe (EMA)",
    version     = "1.0.0",
    lifespan    = lifespan,
)

# CORS — allow frontend origins
app.add_middleware(
    CORSMiddleware,
    allow_origins = [
        "http://localhost:3000",
        "http://localhost:5173",
        "https://*.vercel.app",
        "*",  # TODO: restrict in production
    ],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# Mount routers
app.include_router(health_router, prefix="/api/v1")
app.include_router(chat_router,   prefix="/api/v1")
app.include_router(forms_router,  prefix="/api/v1")
app.include_router(explore_router, prefix="/api/v1")


# Root redirect
@app.get("/")
async def root():
    return {
        "message": "ARIS API Endpoint",
        "docs":    "/docs",
        "health":  "/api/v1/health",
    }