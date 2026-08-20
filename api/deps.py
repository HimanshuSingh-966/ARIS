"""
api/deps.py
Shared FastAPI dependencies: API-key auth, rate limiting, and cached clients.

THREAT MODEL
  The frontend is a static SPA, so it cannot hold a secret. The API key lives in
  the Vercel Edge proxy (frontend/api/[...path].js) and is injected server-side;
  the browser never sees it and never learns the backend origin. This is what
  stops an anonymous caller from draining the Gemini/Groq quota or streaming
  private B2 PDFs directly.

  CORS is not part of this: it is a browser policy and does nothing against curl.
  The key is the access control; CORS just stops other websites from using a
  user's browser as a proxy.
"""

import os
import time
import secrets
import logging
import threading
from collections import defaultdict, deque

from fastapi import Header, HTTPException, Request, status

log = logging.getLogger(__name__)


# ── API key ───────────────────────────────────────────────────────────────────

API_KEY_HEADER = "X-API-Key"


def _expected_key() -> str | None:
    # Read per-request rather than at import so a platform that injects env vars
    # late (and tests that monkeypatch) both behave predictably.
    key = os.environ.get("ARIS_API_KEY", "").strip()
    return key or None


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """
    Reject requests without a valid X-API-Key.

    Fails CLOSED: if ARIS_API_KEY is not configured, every protected request is
    refused rather than silently allowing anonymous access. That turns a
    misconfigured deploy into an obvious outage instead of a quiet security hole.
    """
    expected = _expected_key()

    if expected is None:
        log.error(
            "ARIS_API_KEY is not set - refusing all authenticated requests. "
            "Set it in the backend environment and in the Vercel proxy."
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service is not configured.",
        )

    # compare_digest to avoid leaking the key through response-timing differences.
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
            headers={"WWW-Authenticate": API_KEY_HEADER},
        )


# ── Rate limiting ─────────────────────────────────────────────────────────────

class SlidingWindowRateLimiter:
    """
    In-process sliding-window limiter.

    LIMITS OF THIS APPROACH, stated plainly:
      * Per-process. Render running two instances gives roughly 2x the intended
        allowance, and the window resets on every deploy.
      * Client identity comes from X-Forwarded-For, which a caller can spoof.

    It is still worth having: it bounds accidental runaway loops and casual abuse
    of the LLM quota. It is NOT the access control - require_api_key is. Move to
    Redis if you need a limit you can actually rely on.
    """

    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, bucket: deque[float], now: float) -> None:
        cutoff = now - self.window
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

    def allow(self, key: str, now: float | None = None) -> bool:
        """Record a hit for `key`; return False if it exceeds the window budget."""
        now = time.monotonic() if now is None else now
        with self._lock:
            bucket = self._hits[key]
            self._prune(bucket, now)

            if len(bucket) >= self.max_requests:
                return False

            bucket.append(now)

            # Keep the dict from growing without bound under many distinct keys.
            if len(self._hits) > 10_000:
                for k in [k for k, v in self._hits.items() if not v]:
                    del self._hits[k]

            return True

    def retry_after(self, key: str, now: float | None = None) -> int:
        """Seconds until the oldest hit in the window expires."""
        now = time.monotonic() if now is None else now
        with self._lock:
            bucket = self._hits.get(key)
            if not bucket:
                return 0
            return max(1, int(bucket[0] + self.window - now) + 1)


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        log.warning("%s=%r is not an integer - using default %d", name, raw, default)
        return default


_WINDOW = _int_env("ARIS_RATE_LIMIT_WINDOW", 60)

# General read endpoints: browsing is cheap.
_general_limiter = SlidingWindowRateLimiter(
    _int_env("ARIS_RATE_LIMIT_REQUESTS", 120), _WINDOW
)
# Chat is the expensive path - every call costs an LLM token spend, so it gets a
# tighter budget of its own.
_chat_limiter = SlidingWindowRateLimiter(
    _int_env("ARIS_CHAT_RATE_LIMIT_REQUESTS", 15), _WINDOW
)


def client_identifier(request: Request) -> str:
    """
    Best-effort caller identity.

    Takes the leftmost X-Forwarded-For entry, which is the original client as
    reported by the edge. Spoofable by design of the header - see the class
    docstring - so treat it as abuse-dampening, not identity.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


def _enforce(limiter: SlidingWindowRateLimiter, request: Request) -> None:
    key = client_identifier(request)
    if not limiter.allow(key):
        retry = limiter.retry_after(key)
        log.warning("Rate limit exceeded for %s on %s", key, request.url.path)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please slow down.",
            headers={"Retry-After": str(retry)},
        )


async def rate_limit(request: Request) -> None:
    """Standard per-caller limit for read endpoints."""
    _enforce(_general_limiter, request)


async def chat_rate_limit(request: Request) -> None:
    """Tighter limit for LLM-backed endpoints."""
    _enforce(_chat_limiter, request)


# ── Cached clients ────────────────────────────────────────────────────────────

def get_supabase():
    """
    Cached Supabase client.

    Reuses pipeline.vector_store.get_client so the whole app shares one client
    instead of explore.py building a fresh one on every request.
    """
    from pipeline.vector_store import get_client

    try:
        return get_client()
    except KeyError as e:
        log.error("Supabase credentials missing: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service is not configured.",
        )


_b2_client = None
_b2_lock = threading.Lock()


def get_b2_client():
    """
    Cached B2 (S3-compatible) client.

    Single definition so the s3v4 signature config cannot drift between callers -
    B2 rejects presigned URLs signed with s3v2, and that failure only shows up at
    download time.
    """
    global _b2_client
    if _b2_client is not None:
        return _b2_client

    with _b2_lock:
        if _b2_client is not None:
            return _b2_client

        import boto3
        from botocore.config import Config

        endpoint = os.environ.get("B2_ENDPOINT")
        key_id = os.environ.get("B2_KEY_ID")
        app_key = os.environ.get("B2_APP_KEY")

        if not all([endpoint, key_id, app_key]):
            log.error("B2 credentials missing (B2_ENDPOINT / B2_KEY_ID / B2_APP_KEY)")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service is not configured.",
            )

        _b2_client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=key_id,
            aws_secret_access_key=app_key,
            region_name="auto",
            config=Config(signature_version="s3v4"),
        )
        return _b2_client


def bucket_name() -> str:
    return os.environ.get("B2_BUCKET_NAME", "pharma-rag-docs")
