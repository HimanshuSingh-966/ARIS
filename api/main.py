"""
api/main.py
FastAPI entry point — ARIS Backend API
"""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
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
from api import __version__
from api.deps import require_api_key, rate_limit, chat_rate_limit
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
    version     = __version__,
    lifespan    = lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
#
# CORS is a browser policy, not access control — it does nothing against curl.
# require_api_key is the access control; this just stops other websites from
# using a visitor's browser to call the API.
#
# Two things the previous config got wrong: "*" alongside allow_credentials=True
# is rejected outright by browsers, and Starlette matches allow_origins by exact
# string, so "https://*.vercel.app" never matched anything. Wildcards need
# allow_origin_regex.

_DEFAULT_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
]

# Comma-separated list, e.g. ARIS_ALLOWED_ORIGINS="https://aris.example.com"
_configured = [
    o.strip()
    for o in os.environ.get("ARIS_ALLOWED_ORIGINS", "").split(",")
    if o.strip()
]
allowed_origins = _configured or _DEFAULT_ORIGINS

# Vercel preview deployments get a generated subdomain, so they need a pattern.
# Anchored at both ends so it cannot match e.g. "https://evil-vercel.app.attacker.com".
vercel_preview_re = os.environ.get(
    "ARIS_ALLOWED_ORIGIN_REGEX",
    r"^https://[a-z0-9-]+\.vercel\.app$",
)

log.info("[CORS] allowed origins: %s (+ regex %s)", allowed_origins, vercel_preview_re)

app.add_middleware(
    CORSMiddleware,
    allow_origins      = allowed_origins,
    allow_origin_regex = vercel_preview_re,
    # No cookies or browser-managed credentials are used; the API key is injected
    # server-side by the Vercel proxy. Keeping this False also means a wildcard
    # origin could never be combined with credentials by accident later.
    allow_credentials  = False,
    allow_methods      = ["GET", "POST", "OPTIONS"],
    allow_headers      = ["Content-Type", "X-API-Key"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
#
# /health stays open: Render polls it to decide whether the instance is live, and
# it exposes nothing. Everything else requires the API key and is rate limited.
app.include_router(health_router, prefix="/api/v1")

app.include_router(
    chat_router,
    prefix="/api/v1",
    dependencies=[Depends(require_api_key), Depends(chat_rate_limit)],
)
app.include_router(
    forms_router,
    prefix="/api/v1",
    dependencies=[Depends(require_api_key), Depends(rate_limit)],
)
app.include_router(
    explore_router,
    prefix="/api/v1",
    dependencies=[Depends(require_api_key), Depends(rate_limit)],
)


# Root redirect
@app.get("/")
async def root():
    return {
        "message": "ARIS API Endpoint",
        "docs":    "/docs",
        "health":  "/api/v1/health",
    }