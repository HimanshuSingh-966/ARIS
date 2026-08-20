"""
tests/test_auth.py

Covers api/deps.py: API-key auth and rate limiting.

Deliberately mounted on a throwaway app with an empty route body rather than on
/api/v1/chat. Hitting the real route would drag in pipeline.embedder, which loads
the FastEmbed model on first use — a ~130 MB download — so a unit test of a header
comparison would depend on the network and take minutes.

The behaviour that matters most here is failing CLOSED: with ARIS_API_KEY unset,
every protected request must be refused. An auth dependency that no-ops when it
finds no configured key turns a missing environment variable into silent
anonymous access on a backend holding a service-role Supabase key.
"""

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from api.deps import (
    API_KEY_HEADER,
    SlidingWindowRateLimiter,
    _enforce,
    client_identifier,
    require_api_key,
)

GOOD_KEY = "test-key-6f1c2b9d"


@pytest.fixture
def auth_client(monkeypatch):
    monkeypatch.setenv("ARIS_API_KEY", GOOD_KEY)
    app = FastAPI()

    @app.get("/guarded", dependencies=[Depends(require_api_key)])
    async def guarded():
        return {"ok": True}

    return TestClient(app)


@pytest.fixture
def unconfigured_client(monkeypatch):
    monkeypatch.delenv("ARIS_API_KEY", raising=False)
    app = FastAPI()

    @app.get("/guarded", dependencies=[Depends(require_api_key)])
    async def guarded():
        return {"ok": True}

    return TestClient(app)


# ── require_api_key ───────────────────────────────────────────────────────────

def test_valid_key_is_accepted(auth_client):
    res = auth_client.get("/guarded", headers={API_KEY_HEADER: GOOD_KEY})
    assert res.status_code == 200


def test_missing_key_is_401(auth_client):
    res = auth_client.get("/guarded")
    assert res.status_code == 401


def test_wrong_key_is_401(auth_client):
    res = auth_client.get("/guarded", headers={API_KEY_HEADER: "nope"})
    assert res.status_code == 401


def test_key_prefix_is_rejected(auth_client):
    """compare_digest is not a prefix match."""
    res = auth_client.get("/guarded", headers={API_KEY_HEADER: GOOD_KEY[:-1]})
    assert res.status_code == 401


def test_empty_key_header_is_401(auth_client):
    res = auth_client.get("/guarded", headers={API_KEY_HEADER: ""})
    assert res.status_code == 401


def test_header_name_is_case_insensitive(auth_client):
    res = auth_client.get("/guarded", headers={"x-api-key": GOOD_KEY})
    assert res.status_code == 200


def test_401_carries_www_authenticate(auth_client):
    res = auth_client.get("/guarded")
    assert res.headers.get("WWW-Authenticate") == API_KEY_HEADER


def test_unset_key_fails_closed_with_503(unconfigured_client):
    """Not 200, and not 401 either: 503 says 'misconfigured', which is the truth
    and is what makes a bad deploy an obvious outage instead of an open door."""
    assert unconfigured_client.get("/guarded").status_code == 503


def test_unset_key_refuses_even_a_plausible_key(unconfigured_client):
    res = unconfigured_client.get("/guarded", headers={API_KEY_HEADER: GOOD_KEY})
    assert res.status_code == 503


def test_blank_env_key_is_treated_as_unset(monkeypatch):
    monkeypatch.setenv("ARIS_API_KEY", "   ")
    app = FastAPI()

    @app.get("/guarded", dependencies=[Depends(require_api_key)])
    async def guarded():
        return {"ok": True}

    assert TestClient(app).get("/guarded").status_code == 503


def test_error_bodies_leak_nothing(auth_client, unconfigured_client):
    """No key material, env var names, or internal hostnames in a client response."""
    for res in (auth_client.get("/guarded"), unconfigured_client.get("/guarded")):
        body = res.text
        assert GOOD_KEY not in body
        assert "ARIS_API_KEY" not in body


# ── SlidingWindowRateLimiter ──────────────────────────────────────────────────

def test_limiter_allows_up_to_the_budget():
    limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=60)
    assert [limiter.allow("a", now=t) for t in (0, 1, 2)] == [True, True, True]
    assert limiter.allow("a", now=3) is False


def test_window_slides():
    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=10)
    assert limiter.allow("a", now=0) is True
    assert limiter.allow("a", now=1) is True
    assert limiter.allow("a", now=5) is False
    # now=11 pushes the cutoff past the hit at t=0, freeing one slot.
    assert limiter.allow("a", now=11) is True


def test_buckets_are_per_key():
    limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=60)
    assert limiter.allow("a", now=0) is True
    assert limiter.allow("a", now=0) is False
    assert limiter.allow("b", now=0) is True


def test_retry_after_is_positive_once_limited_and_zero_when_unused():
    limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=30)
    assert limiter.retry_after("a", now=0) == 0
    limiter.allow("a", now=0)
    assert 0 < limiter.retry_after("a", now=0) <= 31


# ── client_identifier + _enforce over HTTP ────────────────────────────────────

@pytest.fixture
def limited_client():
    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60)
    app = FastAPI()

    async def limited(request: Request) -> None:
        _enforce(limiter, request)

    @app.get("/cheap", dependencies=[Depends(limited)])
    async def cheap():
        return {"ok": True}

    return TestClient(app)


def test_burst_gets_429_with_retry_after(limited_client):
    headers = {"X-Forwarded-For": "203.0.113.9"}
    codes = [limited_client.get("/cheap", headers=headers).status_code for _ in range(4)]
    assert codes == [200, 200, 429, 429]

    res = limited_client.get("/cheap", headers=headers)
    assert int(res.headers["Retry-After"]) >= 1


def test_limit_is_per_caller(limited_client):
    a = {"X-Forwarded-For": "198.51.100.1"}
    b = {"X-Forwarded-For": "198.51.100.2"}
    assert [limited_client.get("/cheap", headers=a).status_code for _ in range(3)] \
        == [200, 200, 429]
    assert limited_client.get("/cheap", headers=b).status_code == 200


def test_client_identifier_takes_the_leftmost_forwarded_entry():
    scope = {
        "type": "http",
        "headers": [(b"x-forwarded-for", b"203.0.113.5, 70.41.3.18, 150.172.238.178")],
        "client": ("10.0.0.1", 1234),
    }
    assert client_identifier(Request(scope)) == "203.0.113.5"


def test_client_identifier_falls_back_to_the_peer():
    scope = {"type": "http", "headers": [], "client": ("10.0.0.1", 1234)}
    assert client_identifier(Request(scope)) == "10.0.0.1"


def test_client_identifier_handles_no_peer_and_blank_header():
    scope = {"type": "http", "headers": [(b"x-forwarded-for", b" ")], "client": None}
    assert client_identifier(Request(scope)) == "unknown"
