# ARIS — Automated Regulatory Intelligence System

ARIS is a full-stack RAG application for searching, analysing, and citing regulatory
guidelines and forms across the **US FDA**, **Europe EMA**, and **India CDSCO**.

React (Vite) frontend, FastAPI backend, Supabase pgvector for retrieval, Gemini 2.0
for generation, Backblaze B2 for document storage.

**Version 1.7.0** — see [CHANGELOG.md](CHANGELOG.md). If you are upgrading from an
earlier revision, read the "Action required before deploying" sections first: 1.5.0
adds a fail-closed API key and needs a deliberate choice about your database (rebuild
and re-ingest, or hand-apply the diff and backfill), and 1.6.0 requires a re-ingest
from scratch because the changed chunk size does not propagate to documents already
stored.

---

## 🏗 Architecture

**Frontend** — React 18 + Vite + Tailwind CSS v4
- Light "mint" theme defined CSS-first in `src/index.css` via Tailwind v4's `@theme`.
  There is no `tailwind.config.js`; v4 does not read one without an `@config`
  directive. The PDF viewer and navbar deliberately keep dark chrome.
- A document explorer (agency → category → document) with a slide-in AI chat panel,
  available both per-document and globally.
- **No client-side authentication.** The browser holds no Supabase credentials and
  does not know the backend's URL — see Security below.

**Backend** — Python 3.11 + FastAPI, routers mounted under `/api/v1`
- **RAG pipeline:** hand-written in `rag/` (`retriever` → `prompt` → `llm` → `chain`).
  No LangChain — it is not a dependency and never was imported.
- **Embeddings:** [FastEmbed](https://github.com/qdrant/fastembed) running locally on
  CPU — `BAAI/bge-small-en-v1.5`, **384 dimensions**. No embedding API calls, so the
  vector columns in Supabase must be `vector(384)`.
- **Vector DB:** Supabase pgvector, queried through the `match_documents`,
  `search_forms_semantic`, `search_forms_keyword`, and `distinct_sections` RPCs.
- **LLM:** Google Gemini (`gemini-2.0-flash`) as the generative engine.
- **Failover:** falls back to Groq (`llama-3.3-70b-versatile`) **only** on quota,
  rate-limit, 5xx, and network failures. Configuration errors (a missing
  `GEMINI_API_KEY`, a bad model name) are raised, not silently downgraded.
- **Storage:** Backblaze B2 over the S3-compatible API. PDFs are served through a
  streaming proxy on the backend; form downloads use presigned URLs (signed `s3v4` —
  B2 rejects `s3v2`).

---

## 🔐 Security model

The frontend is a static SPA, so it cannot keep a secret. Instead:

1. The browser only ever calls **same-origin `/api/*`**.
2. On Vercel, `frontend/api/[...path].js` — an **Edge** function — forwards those
   calls to the backend, adding the `X-API-Key` header server-side. The key and the
   backend origin both stay in Vercel's environment; neither reaches the client
   bundle, and the backend URL is not in the repo.
3. `api/deps.py` requires that key on every route except `/api/v1/health` (left open
   for Render's health probe), and **fails closed**: if `ARIS_API_KEY` is unset the
   API answers `503`, never anonymous-allow.
4. CORS is restricted to configured origins with `allow_credentials=False`. CORS is a
   browser policy and does nothing against `curl` — the API key is the access
   control.
5. Rate limiting is in-process and per-instance (see `SlidingWindowRateLimiter`).
   It bounds runaway loops and casual quota abuse; it is not a limit you can rely on
   across multiple instances. Move it to Redis if you need that.

`SUPABASE_SERVICE_KEY` bypasses RLS and is **server-side only**. `vite.config.js`
restricts `envPrefix` to `VITE_` so no `SUPABASE_*` or `ARIS_*` value can be inlined
into the client bundle.

---

## 🚀 Getting Started

### 1. Environment

```bash
cp .env.example .env
```

Fill in your keys. Both the backend and the frontend's dev proxy read this single
root file. `ARIS_API_KEY` is required — without it every protected endpoint returns
503 by design. Generate one with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 2. Database

For a new Supabase project, run `supabase/schema.sql` in the SQL editor. It creates
the `documents`, `doc_metadata`, and `forms` tables, the trigram indexes, the RLS
state, and every RPC the API calls. Then run the five verification queries at the
bottom of the file — in particular, confirm the vector columns report `vector(384)`.
`information_schema` renders them as `USER-DEFINED`, which is why those queries use
`format_type` instead.

> **`schema.sql` is a destructive rebuild.** It drops `documents`, `doc_metadata` and
> `forms` with `cascade`, including every row. It is written that way deliberately:
> `create table if not exists` is a total no-op on an existing table, so an idempotent
> version would have silently skipped every fix.
>
> **If you have an existing database, you have two options.** Either run it and
> re-ingest from B2 with `make ingest` — recommended, because every chunk written
> before v1.5.0 is missing `doc_id` and has a `section_tag` conflated with the category
> slug, and a re-ingest repairs both at no API cost (embeddings are local CPU). Or keep
> your rows: don't run `schema.sql`, hand-apply its diff, then run
> `supabase/backfill_doc_id.sql` step by step as documented in that file. The backfill
> repairs `doc_id` only, not `section_tag`, and is **unnecessary** on the re-ingest
> path — there are no old rows left to repair.

### 3. Run locally (without Docker)

Two terminals.

**Backend** — Python 3.11 (matches `.python-version` and the Docker image):

```bash
python -m venv .venv
# Windows: .\.venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

`pytesseract` is the OCR fallback for scanned pages and needs the `tesseract` binary
installed separately; ingestion works without it for text-based PDFs.

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

Then open [http://localhost:3000](http://localhost:3000). The vite dev proxy adds the
same `X-API-Key` the Edge function adds in production, so the backend can require it
unconditionally.

### 4. Tests

Run on **Python 3.11** (matching `.python-version` and the Docker image) with the dev
dependencies installed — `pytest` itself is in `requirements-dev.txt`, not
`requirements.txt`:

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest
```

161 tests. The suite covers pure logic only — no network, no Supabase, no B2, and
nothing that loads the FastEmbed model — so it runs offline and needs no `.env`.
`tests/test_app_wiring.py` is the exception worth knowing about: it drives HTTP
against the real app to prove every `/api/v1` route actually has the auth dependency
attached, since the other auth tests mount that dependency on throwaway apps and
would stay green if a router were mounted without it.

Frontend lint and build:

```bash
cd frontend && npm run lint && npm run build
```

---

## 🔧 Operational scripts

Five scripts in `scripts/`, runnable from any directory (they resolve `.env` and the
project root relative to their own location). None are imported by the application;
they are one-off tools. Each has a `make` shortcut.

| Script | `make` | What it does | Safe to re-run? |
|---|---|---|---|
| `scripts/check_db_status.py` | `make check-db` | Prints chunk and form counts plus a sample of rows. First thing to run when retrieval returns nothing. | Yes — read-only |
| `scripts/check_model.py` | `make check-model` | Lists Gemini models supporting `generateContent` and checks your configured `GEMINI_MODEL` is among them. | Yes — read-only |
| `scripts/diagnose_embeddings.py` | `make diagnose` | Re-embeds one stored chunk and compares it to the stored vector by cosine similarity. A score below ~0.3 means the stored embeddings came from a different model. | Yes — read-only |
| `scripts/reembed_all.py` | `make reembed` | Rewrites the `embedding` column of **every** `documents` row using the current FastEmbed model. Needed only if `diagnose_embeddings.py` reports a mismatch — never after a fresh ingest. | **Writes to your database.** `make reembed` requires typing `REEMBED` to confirm |
| `scripts/set_cors.py` | `make cors` | Applies GET/HEAD-only CORS to the B2 bucket from `ARIS_ALLOWED_ORIGINS`. Refuses `*`. | Yes — idempotent |

### The master regulatory PDFs

The three master rule PDFs live in **`data/master_pdfs/`** and are **gitignored** —
about 18 MB that the running application never reads.

They are build-time input to `pipeline/extract_forms_from_master_pdfs.py`, which
slices individual forms out of them, uploads each to B2 under `forms/{year}/`, and
writes a row per form. Once that has run, the app serves the sliced forms from B2 and
never opens the masters again. B2 holds only the slices, so it is not a backup of the
originals — keep them somewhere.

A fresh clone will not have them. `make forms` checks first and refuses to run; the
script itself exits non-zero with the directory it looked in. Verify with
`make check-pdfs`.

---

## 🐳 Running with Docker

Both services read the **root `.env`**, so create it first — Compose fails with
`env file .env not found` if you skip this, and the backend would fail closed anyway:

```bash
cp .env.example .env
```

```bash
docker compose up --build
```

- Frontend: [http://localhost:3000](http://localhost:3000)
- Backend API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

Hot-reloading works for both services: the source is bind-mounted, the API gets
`--reload` from compose's `command:` override, and `CHOKIDAR_USEPOLLING` is set so
vite's watcher sees changes through the mount on Windows and macOS hosts.

```bash
docker compose down
```

Use `docker compose` (v2, a Docker CLI subcommand), not the old standalone
`docker-compose` binary. `make docker-up` wraps this and validates `.env` first,
which gives a clearer failure than Compose's.

---

## ☁️ Deploying

**Backend (Render):** set `ARIS_API_KEY`, `ARIS_ALLOWED_ORIGINS` (comma-separated
exact origins, no wildcards), plus the `GEMINI_*`, `GROQ_*`, `B2_*`, and `SUPABASE_*`
values.

**Frontend (Vercel):** set `ARIS_API_KEY` — the *same* value as Render — and
`ARIS_API_ORIGIN`, the backend's URL. Both are read only by the Edge function, so
neither is exposed to the browser. There is no `VITE_API_URL`: the client always
calls its own origin.

Set these **before** deploying. The backend fails closed, so a deploy without
`ARIS_API_KEY` will correctly refuse every request.

If the B2 bucket needs browser access, run `make cors` (`scripts/set_cors.py`) — it
applies GET/HEAD-only CORS from `ARIS_ALLOWED_ORIGINS` and refuses to accept `*`.

---

## 📁 Layout

```
api/                 FastAPI app: routes, models, shared deps (auth, rate limiting, clients)
                     __init__.py holds __version__ — the single source of truth
rag/                 Retrieval → prompt → LLM → chain
pipeline/            Ingestion: extract, chunk, embed, upload to B2, write to Supabase
scripts/             Operational / diagnostic scripts — see the table above
supabase/            schema.sql (destructive rebuild) and the doc_id backfill
frontend/            React SPA + the Vercel Edge API proxy (frontend/api/)
tests/               pytest suite over the pure logic
data/master_pdfs/    Master rule PDFs — gitignored, build-time input to
                     pipeline/extract_forms_from_master_pdfs.py
Makefile             Task runner; `make help` lists every target
CHANGELOG.md         Release history
```

## Not implemented

Called out because earlier revisions of this file claimed otherwise: there is **no**
user authentication (no Supabase Auth, no Google OAuth, no login UI) and **no**
persisted chat history — conversations live in React state for the lifetime of the
page, and there are no `chats`/`messages` tables. Access control is the shared API
key described above.

Rate limiting is in-process, so it is per-instance and resets on deploy. The Docker
setup has been written and reviewed but never built — `docker compose up --build` is
unverified.
