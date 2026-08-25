# Changelog

All notable changes to ARIS are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.7.0] — 2026-08-25

A single-defect release. Every API call from the deployed frontend returned 404, so the
document browser, sources list, and chat were all dead in production while the SPA itself
loaded normally.

### Fixed

- **Every `/api/*` request with more than one path segment 404'd at Vercel's edge, so no
  deployed API call ever reached the backend.** The Edge proxy was named
  `frontend/api/[...path].js`, intending a catch-all. `[...param]` is a **Next.js**
  convention; this is a plain Vite SPA using Vercel's zero-config `api/` directory, which
  supports `[param]` but has no catch-all. Vercel read the filename as a parameter
  literally called `...path` and compiled it to a single-segment matcher, `[^/]+`.

  So `/api/foo` reached the function and `/api/v1/health` did not. Every route in the app
  is mounted under `prefix="/api/v1"` (`api/main.py`), so every real request missed by
  exactly one slash. The frontend surfaced this only as
  `AxiosError: Request failed with status code 404`.

  Nothing about the deployment looked wrong, which is why this took a while to find: the
  function was built, listed in the dashboard's Functions tab as `/api/[...path]` with the
  Edge runtime, deployed to eight regions, and correctly aliased to the production domain.
  The only wrong artefact was the generated route regex, which no page in the dashboard
  displays. What isolated it was that `/api/foo` returned FastAPI's own
  `{"detail":"Not Found"}` as `application/json` — proof the proxy ran and authenticated —
  while `/api/v1/health` returned Vercel's `text/plain` body with `x-vercel-error:
  NOT_FOUND`, which only the edge can emit and the function's code paths never can.

### Changed

- **Routing is now explicit instead of inferred from a filename.** The function moved to
  `frontend/api/proxy.js` — a static route name that needs no dynamic-route detection —
  and `frontend/vercel.json` rewrites `/api/(.*)` to it, carrying the caller's real path in
  an internal `__aris_path` query parameter. The handler reads that parameter, deletes it,
  and forwards the remaining query untouched, falling back to its own pathname when the
  parameter is absent. Rewrites are evaluated only after the filesystem check, so a direct
  request to `/api/proxy` still reaches the function and simply gets the backend's 404.

  `__aris_path` reaches neither the browser (rewrites are internal to Vercel) nor the
  backend (deleted before the upstream fetch). The two existing guards continue to carry
  the security weight unchanged: `new URL()` normalises `..` before the
  `startsWith('/api/')` check, so a crafted value cannot escape the API surface, and the
  origin comparison pins the upstream host. A caller who sets the parameter by hand gains
  nothing they could not already request through the proxy.

---

## [1.6.0] — 2026-08-24

An ingestion-durability release. 1.5.0 fixed what was stored; this fixes what happens
when storing it goes wrong. Both changes were found while sizing a full re-ingest of the
~200 PDFs in B2 — the longest single run this project performs, and the one most likely
to be interrupted.

### ⚠️ Action required before deploying

**Re-ingest from scratch — a partial re-ingest will not pick up the new chunk size.**
The already-ingested check is keyed on `b2_key` alone and has no idea what chunk size
produced the existing rows, so any document already in `documents` keeps its old
~2000-char chunks permanently and a re-run skips it. Truncate `documents` (or run
`supabase/schema.sql`, which rebuilds it) before `make ingest`. If you took Path A in
1.5.0 and have not ingested yet, there is nothing to do — this is already the state
you are in.

### Fixed

- **An interrupted ingest could leave a document permanently half-stored, reported as
  a success.** `pipeline/vector_store.save_chunks` writes in batches of 50, each a
  separate autocommitted request, and it caught the failure and returned the *partial*
  count. `doc_already_ingested()` asks only whether **any** chunk exists for a
  `b2_key`, so a document that died after batch 3 of 9 left 150 rows behind and was
  skipped as "already ingested" on every later run — two-thirds missing for the life
  of the database. The non-zero return then made `ingestor.process_document` report
  status `done`, count it under `Docs ingested`, and write its `doc_metadata` row, so
  the document appeared **fully browsable** in the UI while most of its text was
  unsearchable. Nothing logged an error, and the run's final summary looked clean.

  `save_chunks` now rolls the partial write back and raises. Failures land in `Errors`
  where they can be seen, and the document is retried from scratch on the next run.
  Two details that are load-bearing rather than incidental:

  - It catches `BaseException`, not `Exception`. Ctrl-C raises `KeyboardInterrupt`,
    which is a *sibling* of `Exception` rather than a subclass — so the likeliest
    interruption of a multi-hour ingest was the one case the original handler could
    not see. It cleans up and re-raises, so the interrupt still stops the run.
  - It raises instead of returning `0`. A count of zero would be honest after the
    rollback, but the caller has no way to tell it apart from "this document had no
    embeddable chunks", and raising is what routes it to `run_pipeline`'s
    per-document handler.

  The rollback is a delete filtered on `b2_key`, which is safe because `save_chunks`
  only ever runs for a document with no rows in the table — `process_document`
  returns early otherwise. If the delete *also* fails, the orphaned rows survive and
  that document is unreachable forever, so the log says `ROLLBACK FAILED` and prints
  the exact `delete from documents where b2_key = …` needed to recover.

  Not chosen: wiring up the unused `chunk_exists(b2_key, char_start)` for per-chunk
  resume. `char_start` is a function of the chunker constants, so after any change to
  them the offsets no longer line up, the comparison matches nothing, and the "resume"
  writes overlapping near-duplicate chunks instead of skipping. It is an optimisation
  that saves re-doing one document, at the cost of turning a config change into
  corruption. Also not chosen: a unique index on `(b2_key, char_start)` plus an
  upsert. That is the cleaner design and makes re-runs inherently idempotent, but it
  needs a schema change on the live database and still does not survive a constants
  change, so it does not remove the truncate above.

### Changed

- **Chunk size 500 → 400 tokens, overlap 50 → 60, chars-per-token 4 → 3.** These are
  pinned by the embedding model, not chosen for retrieval taste.
  `BAAI/bge-small-en-v1.5` is BERT-based with `max_position_embeddings = 512` — a hard
  architectural cap, of which 2 go to the `[CLS]`/`[SEP]` markers, leaving 510 usable.
  FastEmbed truncates past that **silently**: no exception, no warning. The full text
  still reaches `documents.content`, so an oversized row looks completely correct
  while its embedding represents only the opening ~510 tokens; the tail is stored and
  unsearchable, and the only symptom is answers being quietly worse.

  The old values overflowed by their own arithmetic. The sentence-boundary search may
  overshoot the nominal size by up to 200 chars, so the real ceiling is
  `CHUNK_SIZE * CHARS_PER_TOK + 200` — 2200 chars at the old settings, which needs
  4.3 chars/token to fit 510 while the config assumed 4.0. And 4.0 is itself the wrong
  figure here: it is a GPT-family BPE number over English prose (50–100k vocab), where
  bge-small uses BERT WordPiece with a 30,522 vocab, which compresses worse — nearer
  3.5–3.8 on plain English and 3.0–3.4 on this corpus, where form codes, rule numbers,
  dates and acronyms fragment into several tokens each. At 3 the ceiling is 1400 chars,
  roughly 410–480 real tokens, inside 510 even on the worst ratio. `CHARS_PER_TOK`
  stays an `int` because it multiplies into slice indices. Expect roughly 1.8× the
  chunk count for the same corpus (the stride drops from ~1800 to ~1020 chars), which
  is still well inside the range where the deliberate absence of an ANN index is
  correct.

  This does not help non-English text. `bge-small-`**`en`** has almost no Cyrillic
  wordpieces, so Bulgarian degrades toward per-character tokens (~1–1.5 chars/token)
  and no chunk size fits. Those documents need excluding, not resizing.

### Added

- `pipeline/vector_store.delete_chunks_for_doc()` — the rollback primitive. Returns
  `-1` rather than `0` when the delete itself fails, because "nothing to clean up" and
  "cleanup did not happen" are indistinguishable from a count of zero and only the
  second leaves a document permanently skipped. Refuses an empty `b2_key`: chunks fall
  back to `""` when metadata omits the key, and `.eq("b2_key", "")` would match those
  rows across *every* document rather than none.
- `tests/test_vector_store.py` — 13 tests over the save and rollback paths against a
  fake client injected into the module's cached `_client`, so the suite stays offline.
  Covers the batch arithmetic, rollback on both `Exception` and `KeyboardInterrupt`,
  that a first-batch failure attempts no delete, that the rollback leaves another
  document's rows alone, and that a failed rollback logs the recovery SQL.

### Known limitations

- **The rollback needs one working request to the database.** If the interruption is
  the connection itself, the delete fails too. That case is logged as
  `ROLLBACK FAILED` with the statement to run, but it is not automatic.
- Everything under 1.5.0's "Known limitations" still applies.

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
  function (`frontend/api/proxy.js`, added here as `frontend/api/[...path].js` and
  renamed in 1.7.0) proxies `/api/*` and injects `X-API-Key`
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
