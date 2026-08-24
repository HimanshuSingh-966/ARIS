"""
tests/test_app_wiring.py

Asserts that the REAL app in api/main.py actually has the auth gate attached.

tests/test_auth.py proves require_api_key behaves correctly, but it mounts the
dependency on throwaway FastAPI apps. That leaves the gap this file closes: a typo
in one of main.py's `include_router(..., dependencies=[...])` calls — or a new
router added without them — would leave that endpoint completely open, and every
test in test_auth.py would still pass. The dependency would be perfect and unused.

So these tests drive HTTP against `api.main.app` itself and check the response
codes, rather than inspecting route.dependencies (which would just be reading the
wiring back to itself).

Two things this file is careful about:

  * TestClient is NOT used as a context manager. Entering the context runs the
    lifespan handler, which calls pipeline.embedder.get_model() and downloads
    ~130 MB of FastEmbed weights. Plain `TestClient(app)` skips lifespan and still
    serves requests.
  * No authenticated request is ever sent, and the no_real_credentials fixture
    empties the environment of keys. A valid key would run the route body, and
    /chat's body spends real Gemini/Groq quota. Every assertion here is about a
    request being REFUSED, which happens in the dependency, before the handler.
"""

import re

import pytest
from fastapi.testclient import TestClient

from api import deps
from api.deps import API_KEY_HEADER, SlidingWindowRateLimiter
from api.main import app

GOOD_KEY = "wiring-test-key-4a91f2c7"

# Routes deliberately reachable without a key. /health is open because Render polls
# it to decide whether the instance is live, and it returns a static status object.
# Adding to this set should be a deliberate act, so the sweep below reads from it
# rather than special-casing paths inline.
OPEN_PATHS = {"/api/v1/health"}

# A body that passes ChatRequest validation, so a 401 here can only come from the
# auth dependency and not from a 422.
VALID_CHAT_BODY = {"query": "What is Form 44?"}


def protected_routes():
    """Every /api/v1 route that must refuse an unauthenticated caller."""
    found = []
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None)
        if not methods or not path.startswith("/api/v1"):
            continue
        if path in OPEN_PATHS:
            continue
        # No path on this app declares a converter ({form_id}, not {form_id:int}),
        # so any placeholder matches the route. The value itself is never validated:
        # the gate rejects the request before FastAPI coerces path params — which is
        # why asserting exactly 401 works even for /forms/{form_id}/download, whose
        # handler types form_id as an int.
        concrete = re.sub(r"\{[^}]+\}", "placeholder", path)
        for method in sorted(methods - {"HEAD", "OPTIONS"}):
            found.append((method, concrete))
    return found


@pytest.fixture
def client(no_real_credentials):
    # raise_server_exceptions=False so that a route which *does* reach its handler
    # (i.e. the gate is missing — the failure this file exists to catch) reports a
    # 500 the sweep can name, instead of aborting the whole test with a traceback
    # from deep inside the handler.
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def no_real_credentials(monkeypatch):
    """
    Strip every credential from the environment for the duration of a test.

    api.main calls load_dotenv() at import, so a developer's real keys are in
    os.environ while the suite runs. That matters here and nowhere else in the
    suite: if the auth gate is missing, the request reaches the handler, and with
    live credentials present the sweep below would query the real Supabase project
    and spend a real LLM call on /chat. The assertion would still fail correctly —
    but only after touching production. With the credentials gone the handler fails
    locally instead, and the test stays offline whether the app is wired right or not.
    """
    for var in (
        "SUPABASE_URL", "SUPABASE_SERVICE_KEY",
        "GEMINI_API_KEY", "GROQ_API_KEY",
        "B2_KEY_ID", "B2_APP_KEY", "B2_ENDPOINT", "B2_BUCKET_NAME",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("ARIS_API_KEY", GOOD_KEY)


@pytest.fixture
def unconfigured(monkeypatch):
    # api.main calls load_dotenv() at import, so the root .env may have put a real
    # key in the environment. Delete it explicitly instead of assuming it is absent.
    monkeypatch.delenv("ARIS_API_KEY", raising=False)


def send(client, method, path, ip):
    """Unauthenticated request. Distinct IP per caller keeps the module-level rate
    limiters in api/deps.py from bleeding one test's hits into another."""
    return client.request(
        method,
        path,
        json=VALID_CHAT_BODY if method == "POST" else None,
        headers={"X-Forwarded-For": ip},
    )


# ── The gate exists, on every protected route ─────────────────────────────────

def test_every_api_route_is_either_gated_or_explicitly_open(client, configured):
    """The core regression test: a router mounted without `dependencies` fails here."""
    routes = protected_routes()
    assert routes, "found no /api/v1 routes to check - has the app layout changed?"

    unguarded = []
    for i, (method, path) in enumerate(routes):
        res = send(client, method, path, f"192.0.2.{i + 10}")
        if res.status_code != 401:
            unguarded.append(f"{method} {path} -> {res.status_code}")

    assert not unguarded, (
        "these routes did not refuse an unauthenticated request: "
        + ", ".join(unguarded)
    )


def test_health_is_reachable_without_a_key(client, configured):
    """Render's probe carries no API key. If this 401s, deploys never go live."""
    res = client.get("/api/v1/health", headers={"X-Forwarded-For": "192.0.2.40"})
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_chat_refuses_a_wrong_key(client, configured):
    res = client.post(
        "/api/v1/chat",
        json=VALID_CHAT_BODY,
        headers={API_KEY_HEADER: "not-the-key", "X-Forwarded-For": "192.0.2.41"},
    )
    assert res.status_code == 401


def test_chat_fails_closed_when_the_key_is_unset(client, unconfigured):
    """
    Missing config must be an outage, not anonymous access. Sending the key the app
    *would* accept if configured, to prove the 503 comes from the missing env var.
    """
    res = client.post(
        "/api/v1/chat",
        json=VALID_CHAT_BODY,
        headers={API_KEY_HEADER: GOOD_KEY, "X-Forwarded-For": "192.0.2.42"},
    )
    assert res.status_code == 503


def test_refusals_do_not_leak_the_configured_key(client, configured):
    res = client.post(
        "/api/v1/chat",
        json=VALID_CHAT_BODY,
        headers={API_KEY_HEADER: "wrong", "X-Forwarded-For": "192.0.2.43"},
    )
    assert GOOD_KEY not in res.text
    assert "ARIS_API_KEY" not in res.text


# ── Docs and root ─────────────────────────────────────────────────────────────

def test_root_exposes_no_configuration(client, configured):
    """`/` is open and unauthenticated, so it must not describe the deployment."""
    res = client.get("/", headers={"X-Forwarded-For": "192.0.2.44"})
    assert res.status_code == 200
    body = res.text
    for leak in ("SUPABASE", "GEMINI", "GROQ", "B2_", "onrender", GOOD_KEY):
        assert leak not in body


# ── The rate limiters are attached too ────────────────────────────────────────
#
# require_api_key being wired says nothing about whether the limiters are. A /chat
# mounted with the key check but no chat_rate_limit accepts unlimited LLM calls from
# anyone holding the key — including a runaway retry loop in the frontend.
#
# These need a VALID key to get past auth and reach the limiter, so they must not be
# allowed to run the handler. A limiter with max_requests=0 rejects the very first
# request (allow() tests `len(bucket) >= max_requests`), so the 429 is raised in the
# dependency and no handler, LLM, or database is ever touched.

def test_chat_has_the_chat_rate_limiter_attached(client, configured, monkeypatch):
    monkeypatch.setattr(deps, "_chat_limiter", SlidingWindowRateLimiter(0, 60))
    res = client.post(
        "/api/v1/chat",
        json=VALID_CHAT_BODY,
        headers={API_KEY_HEADER: GOOD_KEY, "X-Forwarded-For": "192.0.2.50"},
    )
    assert res.status_code == 429


def test_read_routes_have_the_general_rate_limiter_attached(client, configured, monkeypatch):
    monkeypatch.setattr(deps, "_general_limiter", SlidingWindowRateLimiter(0, 60))
    res = client.get(
        "/api/v1/forms",
        headers={API_KEY_HEADER: GOOD_KEY, "X-Forwarded-For": "192.0.2.51"},
    )
    assert res.status_code == 429


# Note these two also pin down WHICH limiter each route uses, which is the point of
# having two: patching only _chat_limiter can only produce a 429 on /chat if /chat is
# wired to that specific limiter. If both routes shared one, the tests would fail.
# Asserting the separation any further would mean letting a chat request through to
# the handler, and that reaches embed_query -> get_model() -> the FastEmbed download.
