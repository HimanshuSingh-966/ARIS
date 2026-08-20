# Changelog

All notable changes to ARIS are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.5.0] — 2026-08-18

A correctness and security release. Both headline features of the app — global chat
and per-document chat — were broken in production, and the API was publicly
reachable with no authentication on a backend holding a `SUPABASE_SERVICE_KEY` that
bypasses RLS. This release fixes 20 defects found in a full audit, plus the
configuration drift and dead code around them.

### ⚠️ Action required before deploying

This release does not upgrade cleanly on its own. These steps are yours, because they
need live credentials:

1. **Set `ARIS_API_KEY`.** The API now fails *closed* — with this unset, every
   endpoint except `/api/v1/health` returns `503`. Set the same value on Render
   (backend) and Vercel (`ARIS_API_KEY` + `ARIS_API_ORIGIN`, read only by the Edge
   proxy). Generate one with
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

2. **Choose a database path.** They are mutually exclusive — pick one.

   **Path A — rebuild and re-ingest (recommended).** Run `supabase/schema.sql`, which
   is a **destructive rebuild**: it drops `documents`, `doc_metadata` and `forms` with
   `cascade`, including every row. Then re-ingest from B2 with `make ingest`.

   Preferred because every chunk currently stored was written by the broken chunker —
   missing `doc_id` *and* carrying a `section_tag` conflated with the category slug.
   `backfill_doc_id.sql` repairs `doc_id` only; it cannot repair the heading. A
   re-ingest fixes both, and embeddings are local CPU FastEmbed, so it costs no API
   quota — only wall-clock. B2 still holds every source PDF, so nothing is lost.
   On this path you do **not** run `backfill_doc_id.sql`: there are no old rows left
   to repair, and the fixed chunker writes `doc_id` from the start.

   **Path B — preserve the existing rows.** Do *not* run `schema.sql`. Read it as the
   target state and hand-apply the diff (the six fixes are listed under "Changed"
   below; `create table if not exists` would have been a total no-op on an existing
   table, which is why the file is a rebuild rather than idempotent). Then run
   `supabase/backfill_doc_id.sql` step by step — its pre-flight checks are there to be
   read, not skipped. Choose this only if a re-ingest's wall-clock is unacceptable,
   and accept that `section_tag` stays wrong in the pre-existing rows.

3. **Verify end to end.** Confirm global chat returns sources *and* that per-document
   chat returns only that document's chunks. This is the only proof that the `doc_id`
   chain works; no offline test can cover it. Note that "I could not find relevant
   information" is returned with HTTP **200**, so a `200` alone proves nothing —
   inspect the `sources` array.

### Security

- **Added API-key authentication** on every route except `/api/v1/health` (left open
  for Render's health probe). Compared with `secrets.compare_digest` so the response
  time does not leak the key.
- **Fails closed.** With `ARIS_API_KEY` unset the API returns `503` rather than
  allowing anonymous access. A missing environment variable is now an obvious
  outage instead of a silent hole in front of a service-role database key.
- **The browser never sees the key or the backend's URL.** A new Vercel Edge
  function (`frontend/api/[...path].js`) proxies `/api/*` and injects `X-API-Key`
  server-side. Edge, not Node: Hobby Node functions buffer responses and cap them at
  4.5 MB, which would truncate the multi-MB PDFs `/documents/{id}/stream` serves.
- **Removed the hardcoded Render URL** from `frontend/vercel.json`. The backend
  origin now lives only in Vercel's environment, so it is not discoverable from the
  repo or the client bundle.
- **CORS locked down.** `"*"` is gone and `allow_credentials` is now `False`.
  `"https://*.vercel.app"` never matched anything — Starlette compares
  `allow_origins` by exact string — so preview deploys now use `allow_origin_regex`,
  anchored at both ends so it cannot match `https://evil-vercel.app.attacker.com`.
- **Stopped leaking internals in error responses.** Every `detail=str(e)` is now a
  generic message plus a server-side `log.exception`. Exception text in this codebase
  can carry hostnames, SQL, and key material.
- **Fixed B2 bucket CORS.** `scripts/set_cors.py` was granting `PUT`/`POST`/`DELETE` from
  `*` on a read-only bucket; it is now `GET`/`HEAD` from configured origins, and it
  refuses `'*'` outright.
- **Restricted `envPrefix` to `VITE_`** in `vite.config.js`, so no `SUPABASE_*` or
  `ARIS_*` value can be inlined into the client bundle.
- **Added per-caller rate limiting** — 120 requests/60s general, 15/60s for chat,
  which is the only path that spends LLM tokens. In-process and per-instance; the
  limits of that are documented in the class docstring rather than papered over.
- **Sanitised `Content-Disposition`** (new `api/utils.py`). Two real bugs were found
  while writing its tests: the RFC 5987 `filename*` parameter was built from the
  *unsanitised* input, percent-encoding `"` and `../../` back to any decoding client,
  and an all-CJK filename collapsed to `filename="pdf"` — the extension became the
  entire filename.

### Fixed

- **Global chat always answered "I could not find relevant information."** The
  frontend sent the UI label `"Global Mode"` as a `doc_id` database filter, so every
  query matched zero rows.
- **Per-document chat could never work.** `pipeline/chunker.py` never propagated
  `doc_id` onto the chunks it produced, so the column the API filters on was empty
  for every row ever ingested. This is the root cause behind both database paths above:
  re-ingesting rewrites the column correctly, and the backfill repairs it in place.
- **Chat returned HTTP 200 on failure**, with the exception text as the assistant's
  answer. `if (!response.ok)` in the frontend could therefore never fire, and an
  outage rendered as an ordinary chat message. Errors now propagate: `rag.retriever`
  no longer swallows Supabase failures into `[]`, `rag.chain` no longer swallows LLM
  failures into an answer string, and `api/routes/chat.py` converts what remains into
  a `502` with a generic detail.
- **`embed_query` returned a zero vector on failure.** A zero vector is *valid*
  pgvector input, so a model failure became a successful-but-meaningless search. It
  now raises.
- **Form-query detection matched the wrong words.** `"form" in query` matched
  "in**form**ation" — constant false positives in a regulatory corpus. Now a
  word-boundary regex.
- **Section classification matched substrings.** `"ct" in hint` matched "a**ct**" and
  "produ**ct**", misfiling documents. Replaced with bounded-token regexes (32 cases
  covered by tests).
- **Form search ignored its own filters.** A query with `type` or `source` set
  searched the entire corpus, so "search within Manufacturing" did nothing.
- **Form pagination reported the page size as the total**, so the UI could not tell
  how many results existed.
- **Typing a form query then switching category wiped the query** while the input
  still displayed the text — `useEffect` called the fetcher with no argument.
- **Clicking a form in a chat reply threw a `TypeError`.** `MessageBubble` rendered
  `FormCard` without the `onDownload` prop that `FormCard` called unconditionally,
  breaking exactly the "give me the form" flow. The handler is now shared through a
  new `frontend/src/lib/api.js`.
- **Source citations linked to a public B2 URL** that returns `403` on a private
  bucket. They now use the backend's existing streaming proxy.
- **Chat autoscroll targeted the wrong element** — `ChatPanel` wrapped the already
  scrollable `ChatWindow` in a second `overflow-y-auto`.
- **`AgencyDetail.jsx.jsx`** had a doubled extension; the import resolved only by
  luck of the bundler. Renamed, and its no-op `animate-fade-right` class fixed.
- **Presigned form downloads could 500** when `title` was present-but-`NULL`
  (`.get("title", fallback)` returns `None`, not the fallback).
- **Gemini fell back to Groq on *any* exception**, silently downgrading model quality
  when the real problem was a missing `GEMINI_API_KEY`. Now only quota, rate-limit,
  5xx, and network failures fall back; configuration errors raise.
- **`docker compose up --build` failed outright** — it referenced a
  `frontend/Dockerfile` that did not exist.
- **The production Docker image ran a dev server** (`uvicorn --reload`), and
  `COPY . .` pulled in `.git` plus ~18 MB of PDFs.
- **Favicon 404'd** (`/vite.svg` with no `public/` directory).
- **Unreadable text** in the PDF viewer — `text-white/50` on a near-transparent
  background over a light page.
- **Ingestion crashed per document and misreported the result as success.**
  `pipeline/ingestor.py` re-imported `vector_store` with a bare sibling import inside
  two functions. That resolves under `python pipeline/ingestor.py` (which puts
  `pipeline/` on `sys.path[0]`) but raises `ModuleNotFoundError` under
  `python -m pipeline.ingestor`, which puts the CWD there instead. The exception was
  caught by the per-document handler, so chunks *did* reach the database while the
  final summary printed `Docs ingested: 0, Chunks saved: 0` — the counters are only
  incremented after the failing line. Now imported once at module scope.
- **`doc_metadata` write failures were invisible.** `save_doc_metadata` swallows its
  own exceptions and returns `False`, and its return value was discarded — so a
  document could be fully ingested and searchable yet never appear in the browse UI,
  with nothing logged. The return value is now checked and names that consequence.
- **Form extraction reported success while saving nothing.** The per-form upsert
  swallowed every exception, so a missing `(form_number, source_pdf)` unique index —
  which makes `ON CONFLICT` raise — produced a clean run against an empty table. It
  now counts failures, exits non-zero, and prints which of the three failure modes it
  hit (PDFs absent / pattern matched nothing / index missing).

### Added

- `supabase/schema.sql` — a **destructive rebuild** (see "Action required" above)
  producing the tables, indexes, RLS state, and every RPC the code calls, including a
  new `distinct_sections`. Six things it fixes over the live schema: nullable text
  columns become `not null default ''` (a Pydantic `str = ""` default only fires when
  the *key* is absent, so a NULL reached a non-`Optional[str]` field and surfaced as a
  misleading 502); RPCs are dropped by `oid::regprocedure` before creation, because
  `create or replace function` with a changed signature creates an *overload* and
  PostgREST then fails with `PGRST203 could not choose the best candidate function`;
  `forms.source_pdf` becomes `not null default ''` so the `(form_number, source_pdf)`
  unique index actually applies (a unique index treats NULLs as distinct, so the
  extractor could insert unlimited duplicates); `doc_metadata` gains a unique index on
  `doc_id` as well as `b2_key`; RLS is enabled on all three tables with **zero**
  policies, which is free because the API uses the service key and closes the hole
  where the anon key was read/write on everything; and there is deliberately **no**
  ANN index — ivfflat probes its `lists` clusters *before* applying `WHERE`, so a
  selective `filter_doc_id` can return too few rows or none. An exact scan is correct
  and fast into the tens of thousands of chunks; an HNSW block is included, commented,
  for when that stops being true.
- `Makefile` — 34 targets covering setup, run, the data pipeline, diagnostics, tests,
  lint, Docker, and cleanup. `make help` lists them. `make reembed` requires typing
  `REEMBED`; `make schema` deliberately refuses to execute the SQL and explains why;
  `make dev` runs API and frontend under `trap 'kill 0'` so Ctrl-C takes down both
  instead of orphaning one on its port.
- `supabase/backfill_doc_id.sql` — populates `documents.doc_id` for existing rows.
  **Path B only** (see "Action required" above); a rebuild-and-re-ingest leaves no old
  rows for it to repair. It **copies** the authoritative value from `doc_metadata`
  across a `b2_key` join
  rather than recomputing `md5(b2_key)`. Recomputation would derive a second value
  that can silently disagree, and a wrong `doc_id` fails invisibly — chat just says
  "I could not find relevant information", indistinguishable from the bug being
  fixed. Step 0 gates on duplicate `b2_key`, step 2 reports every row where the two
  values would differ, and the `UPDATE` is wrapped in a transaction with a
  verification `SELECT` before `COMMIT`.
- `tests/` — 161 tests over the pure logic: form-query boundaries, section
  classification, chunker metadata propagation, `Content-Disposition` sanitisation,
  the rate limiter, `require_api_key`'s fail-closed behaviour, and a sweep asserting
  that every `/api/v1` route on the *real* app refuses an unauthenticated caller.
  That last one exists because the other auth tests mount the dependency on
  throwaway apps — a typo in `include_router(dependencies=...)` would leave an
  endpoint open with all of them still green. No network, no Supabase, no B2, and
  nothing that loads the FastEmbed model, so the suite runs offline.
- `frontend/.eslintrc.cjs` — lint had never been configured; it reported 29 errors
  on first run, now 0.
- `api/deps.py` — shared auth, rate limiting, and cached Supabase/B2 clients. The B2
  client has a single definition so its `s3v4` signature config cannot drift; B2
  rejects `s3v2` presigned URLs, and that failure only surfaces at download time.
- `.dockerignore` and `frontend/.dockerignore`.
- `pytest.ini`, `requirements-dev.txt`, `CHANGELOG.md`.

### Changed

- **`requirements.txt` was missing `google-generativeai`, `groq`, and
  `python-dotenv`** entirely — the deployed backend could not answer a single query.
  Added, and 10 verified-unused packages removed: `langchain`, `langchain-community`,
  `sqlalchemy`, `psycopg2-binary`, `pgvector`, `aiohttp`, `aiofiles`,
  `beautifulsoup4`, `lxml`, `websockets`. Dropping `langchain` freed `numpy` from its
  `<2` pin.
- **Version is now single-sourced** from `api/__init__.py`. It had been hardcoded in
  three Python places and had already drifted from `frontend/package.json`
  (`1.0.0` × 3 vs `0.0.0`), so `/health` could report a version the app was not.
- `docker-compose.yml` — dropped the obsolete `version:` key, moved `--reload` to a
  compose-level `command:` override, and pointed the frontend's dev proxy at
  `http://api:8000`. Inside a container `localhost` is the container itself, so the
  proxy target is now an env var (`ARIS_API_PROXY_TARGET`) that still defaults to
  `localhost:8000` for host development. `CHOKIDAR_USEPOLLING` is set because bind
  mounts from Windows and macOS hosts do not deliver inotify events, which silently
  kills HMR while the dev server still looks healthy.
- `.python-version` — `3.12.2` → `3.11`, matching both the `python:3.11-slim` image
  and the interpreter the tests actually run on.
- `scripts/check_model.py` — probed Gemini *embedding* models, which nothing uses since
  the move to local FastEmbed. Now probes `generateContent` models and compares against
  the configured `GEMINI_MODEL`.
- **The five diagnostic scripts moved from the repo root into `scripts/`** —
  `check_db_status.py`, `check_model.py`, `diagnose_embeddings.py`, `reembed_all.py`,
  `set_cors.py`. None is imported by the application. Each now resolves `.env` by a
  path relative to its own file instead of the working directory, so they run from
  anywhere; the two that import `pipeline.*` insert the project root on `sys.path`
  first, since the move would otherwise have reproduced the ingestor's
  `ModuleNotFoundError` exactly. `scripts/` is excluded from the Docker build context.
- **The three master regulatory PDFs moved to `data/master_pdfs/` and are now
  gitignored** (~18 MB). They are build-time input to
  `pipeline/extract_forms_from_master_pdfs.py`, which slices individual forms out of
  them and uploads each to B2; the running application never opens them. B2 holds only
  the slices, so it is **not** a backup of the originals — keep them. A fresh clone
  will not have them: `make check-pdfs` and the extractor both fail loudly with the
  directory they expected. Note `git rm --cached` leaves the blobs in history, so the
  clone does not get smaller without a history rewrite; the gain is to the Docker image
  and to future commits.
- `.dockerignore` — `*.pdf` became `**/*.pdf` (plus `data/`). Docker uses
  `filepath.Match`, where `*` does not cross a `/`, so unlike a `.gitignore` pattern a
  bare `*.pdf` matches only the context root — once the PDFs moved into a
  subdirectory it silently stopped matching and 18 MB returned to the image.
- `frontend/vite.config.js` — the missing-`ARIS_API_KEY` warning is now gated on
  `command === 'serve'`. Only the dev proxy consumes the key, and in production it
  legitimately lives in Vercel's environment, so firing during `vite build` trained
  people to ignore a warning that does mean something locally.
- `README.md` — corrected claims that were never true of this codebase: "RAG pipeline
  via LangChain" (never imported), "Supabase Authentication (Email & Google OAuth)"
  (no auth code exists), and "Landio-inspired Dark Mode" (the live theme is light
  mint). Added the security model, the Docker workflow, and a "Not implemented"
  section so the same drift is harder to reintroduce.
- `.env.example` — every variable is now verified against a source reference.
  Documents `ARIS_API_KEY`, `ARIS_ALLOWED_ORIGINS`, the three rate-limit overrides,
  `ARIS_API_ORIGIN`, and `ARIS_API_PROXY_TARGET`.

### Removed

- **`scraper`** — a dangling submodule gitlink with no `.gitmodules` entry. Any
  `git submodule` command in this repo failed with *"no submodule mapping found"*;
  clones got an empty directory. The referenced scraper was never part of this repo.
- **`test_b2_s3v4.py`** — a one-off manual B2 probe. Its `test_` prefix made it look
  like part of the suite (it is excluded by `testpaths`, but IDE collectors ignore
  that), it needs live credentials, and it imports `requests`, which was dropped from
  `requirements.txt` as unused — so it was already broken. The `s3v4` behaviour it
  verified is now permanent in `api/deps.py:get_b2_client()`.
- **`frontend/tailwind.config.js`** — inert under Tailwind v4, which reads a config
  only with an explicit `@config` directive. It held a *dark* palette contradicting
  the live mint theme in `index.css`, so it was a misleading second source of truth
  with no effect on output.
- **`@supabase/supabase-js` and `tailwind-merge`** from `frontend/package.json` —
  zero references in any source file; 15 packages leave the install tree.
  `supabase-js` in particular is worth being absent: the browser holds no Supabase
  credentials, and a client library sitting in `dependencies` is an invitation to
  reintroduce a direct browser-to-database call.
- Dead code: `rag/llm.py:get_provider()` (hardcoded `"gemini"`, never called),
  `rag/retriever.py:retrieve_forms()` (an unfiltered `select("*")` over the whole
  forms table, unreferenced), `FormSearchRequest`, unused `Depends`/`import sys`
  imports, and 14 dead `import React` lines — `@vitejs/plugin-react` uses the
  automatic JSX runtime, so none of them did anything.
- Dead env vars from `.env.example`: `LLM_PROVIDER`, `POSTGRES_URL`,
  `API_SECRET_KEY`, `SUPABASE_ANON_KEY` — all verified to have zero source
  references.

### Known limitations

- **Rate limiting is per-process.** Two Render instances give roughly twice the
  intended allowance and the window resets on deploy. It bounds runaway loops and
  casual quota abuse; it is not a limit to rely on. Move it to Redis if you need
  that.
- **No user authentication.** Access control is a single shared API key. Per-user
  accounts would require shipping `SUPABASE_URL` and an anon key to the browser,
  which works against keeping configuration out of the client.
- **No persisted chat history.** Conversations live in React state for the lifetime
  of the page.
- **The Docker changes are not build-verified.** They were written and reviewed
  statically; no `docker build` has run against them.

---

## [1.0.0] — earlier

Initial application: document explorer over CDSCO/FDA/EMA guidelines, form search,
RAG chat with Gemini, FastEmbed embeddings, Supabase pgvector retrieval, and
Backblaze B2 document storage. No changelog was kept for this or preceding revisions;
`1.0.0` is the version the API reported.
