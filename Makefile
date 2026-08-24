# =============================================================================
# ARIS — Makefile
# =============================================================================
# Linux / macOS / WSL / Git Bash. Run `make` or `make help` for the target list.
#
# Assumes a virtualenv at .venv (create it with `make venv`). Every Python target
# invokes .venv/bin/python explicitly rather than relying on an activated shell,
# so targets behave the same in CI, in a subshell, and from an editor.
# =============================================================================

SHELL := /bin/bash

PY     := python3
PIP    := python3 -m pip
PYTEST := python3 -m pytest

FRONTEND_DIR := frontend
MASTER_PDFS  := data/master_pdfs

# Checked by `require-env`. ARIS_API_KEY is included because the backend fails
# closed: without it every gated route returns 503, which looks like an outage.
REQUIRED_VARS := \
	SUPABASE_URL SUPABASE_SERVICE_KEY \
	B2_KEY_ID B2_APP_KEY B2_ENDPOINT B2_BUCKET_NAME \
	GEMINI_API_KEY ARIS_API_KEY

.DEFAULT_GOAL := help

.PHONY: help install install-dev install-frontend install-all \
        require-env check-pdfs \
        api frontend dev \
        ingest-dry ingest forms reembed \
        check-db check-model diagnose cors \
        test test-cov lint lint-fix build \
        docker-build docker-up docker-down docker-logs \
        smoke schema \
        clean clean-py clean-frontend clean-all

# ── Help ─────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "  ARIS — make targets"
	@echo ""
	@echo "  SETUP"
	@echo "    install           Runtime deps"
	@echo "    install-dev       Runtime + test deps"
	@echo "    install-frontend  npm ci in frontend/"
	@echo "    install-all       Everything above"
	@echo "    require-env       Verify .env exists and required vars are set"
	@echo "    check-pdfs        Verify the master PDFs are present"
	@echo ""
	@echo "  RUN"
	@echo "    api               uvicorn on :8000 with --reload"
	@echo "    frontend          vite dev server on :3000"
	@echo "    dev               Both at once (Ctrl-C stops both)"
	@echo ""
	@echo "  DATA PIPELINE"
	@echo "    ingest-dry        Chunk everything, write NOTHING. Do this first."
	@echo "    ingest            Extract, chunk, embed, save to Supabase"
	@echo "    forms             Slice forms out of the master PDFs"
	@echo "    reembed           Rewrite every embedding (guarded, asks first)"
	@echo ""
	@echo "  DIAGNOSTICS"
	@echo "    check-db          Row counts in Supabase"
	@echo "    check-model       Which Gemini models the key can call"
	@echo "    diagnose          Stored vs fresh embedding similarity"
	@echo "    cors              Apply read-only CORS to the B2 bucket"
	@echo "    smoke             curl the API's auth and health behaviour"
	@echo ""
	@echo "  QUALITY"
	@echo "    test              pytest"
	@echo "    test-cov          pytest with coverage"
	@echo "    lint              eslint the frontend"
	@echo "    build             Production frontend build"
	@echo ""
	@echo "  DOCKER"
	@echo "    docker-build / docker-up / docker-down / docker-logs"
	@echo ""
	@echo "  CLEAN"
	@echo "    clean             Python caches"
	@echo "    clean-frontend    node_modules + dist"
	@echo "    clean-all         Both, plus .venv"
	@echo ""

# ── Setup ────────────────────────────────────────────────────────────────────

install:
	$(PIP) install -r requirements.txt

install-dev:
	$(PIP) install -r requirements.txt -r requirements-dev.txt

install-frontend:
	cd $(FRONTEND_DIR) && npm ci

install-all: install-dev install-frontend
	@echo "✓ Backend and frontend dependencies installed"

# ── Guards ───────────────────────────────────────────────────────────────────

require-env:
	@test -f .env || { \
	  echo "ERROR: .env not found."; \
	  echo "       cp .env.example .env    then fill it in"; \
	  exit 1; }
	@missing=""; \
	for v in $(REQUIRED_VARS); do \
	  grep -qE "^$$v=.+" .env || missing="$$missing $$v"; \
	done; \
	if [ -n "$$missing" ]; then \
	  echo "ERROR: unset or empty in .env:$$missing"; \
	  exit 1; \
	fi
	@echo "✓ .env has all required variables"

check-pdfs:
	@test -d $(MASTER_PDFS) || { \
	  echo "ERROR: $(MASTER_PDFS)/ does not exist."; \
	  echo "       The master regulatory PDFs are gitignored — a fresh clone"; \
	  echo "       does not have them. Put them there before running 'make forms'."; \
	  exit 1; }
	@n=$$(ls -1 $(MASTER_PDFS)/*.pdf 2>/dev/null | wc -l); \
	if [ "$$n" -eq 0 ]; then \
	  echo "ERROR: no PDFs in $(MASTER_PDFS)/ — 'make forms' would save nothing."; \
	  exit 1; \
	fi; \
	echo "✓ $$n master PDF(s) in $(MASTER_PDFS)/"

# ── Run ──────────────────────────────────────────────────────────────────────

api: require-env
	$(PY) -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

frontend:
	cd $(FRONTEND_DIR) && npm run dev

# `trap 'kill 0' ...` kills the whole process group on exit, so Ctrl-C takes down
# uvicorn AND vite. Without it one survives, holds its port, and the next
# `make dev` fails with "address already in use".
dev: require-env
	@echo "→ API http://localhost:8000   frontend http://localhost:3000"
	@echo "  Ctrl-C stops both."
	@trap 'kill 0' INT TERM EXIT; \
	$(PY) -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000 & \
	( cd $(FRONTEND_DIR) && npm run dev ) & \
	wait

# ── Data pipeline ────────────────────────────────────────────────────────────

# Always the first step. Lists B2, extracts, chunks and reports counts without
# embedding, without writing, and without downloading the embedding model.
ingest-dry: require-env
	$(PY) pipeline/ingestor.py --dry-run

ingest: require-env
	$(PY) pipeline/ingestor.py

# Deliberately NOT `ingestor.py --include-forms`. That path calls
# save_form_metadata, which writes no embedding, so its rows can never be
# returned by search_forms_semantic. This script writes the complete record.
forms: require-env check-pdfs
	$(PY) pipeline/extract_forms_from_master_pdfs.py

reembed: require-env
	@echo ""
	@echo "  This REWRITES the embedding column of EVERY row in documents."
	@echo "  Run 'make diagnose' first. After a fresh ingest it is never needed."
	@echo ""
	@printf "  Type REEMBED to continue: "; \
	read ans; \
	[ "$$ans" = "REEMBED" ] || { echo "  Aborted."; exit 1; }
	$(PY) scripts/reembed_all.py

# ── Diagnostics ──────────────────────────────────────────────────────────────

check-db: require-env
	$(PY) scripts/check_db_status.py

check-model: require-env
	$(PY) scripts/check_model.py

diagnose: require-env
	$(PY) scripts/diagnose_embeddings.py

cors: require-env
	$(PY) scripts/set_cors.py

# Verifies the three behaviours that are easy to get wrong and silent when wrong:
# health is open, gated routes reject an unkeyed request, and the key works.
smoke:
	@echo "→ /health            expect 200"
	@curl -s -o /dev/null -w "  got %{http_code}\n" \
	  http://localhost:8000/api/v1/health || echo "  (is the API running?)"
	@echo "→ /chat  no key      expect 401 (or 503 if ARIS_API_KEY is unset)"
	@curl -s -o /dev/null -w "  got %{http_code}\n" \
	  -X POST http://localhost:8000/api/v1/chat \
	  -H 'Content-Type: application/json' \
	  -d '{"query":"ping"}'
	@echo "→ /chat  with key    expect 200"
	@curl -s -o /dev/null -w "  got %{http_code}\n" \
	  -X POST http://localhost:8000/api/v1/chat \
	  -H 'Content-Type: application/json' \
	  -H "X-API-Key: $$(grep -E '^ARIS_API_KEY=' .env | cut -d= -f2-)" \
	  -d '{"query":"What is Form 44?"}'

schema:
	@echo ""
	@echo "  supabase/schema.sql is a DESTRUCTIVE rebuild — it drops documents,"
	@echo "  doc_metadata and forms, including every row."
	@echo ""
	@echo "  There is no psql connection configured here, and running it by"
	@echo "  accident from a Makefile is exactly the wrong ergonomics. Paste it"
	@echo "  into the Supabase SQL editor yourself, then run the verification"
	@echo "  queries at the bottom of the file."
	@echo ""

# ── Quality ──────────────────────────────────────────────────────────────────

test:
	$(PYTEST)

test-cov:
	$(PYTEST) --cov=api --cov=rag --cov=pipeline --cov-report=term-missing

lint:
	cd $(FRONTEND_DIR) && npm run lint

lint-fix:
	cd $(FRONTEND_DIR) && npm run lint -- --fix

build:
	cd $(FRONTEND_DIR) && npm run build

# ── Docker ───────────────────────────────────────────────────────────────────

docker-build: require-env
	docker compose build

docker-up: require-env
	docker compose up --build

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

# ── Clean ────────────────────────────────────────────────────────────────────

# -prune on .venv, node_modules and .git before matching. Without it find walks
# tens of thousands of dependency files, which is slow enough to look hung, and
# risks deleting caches that belong to installed packages.
clean-py:
	@find . \
	  -path ./.venv -prune -o \
	  -path ./$(FRONTEND_DIR)/node_modules -prune -o \
	  -path ./.git -prune -o \
	  -type d -name __pycache__ -print0 2>/dev/null \
	  | xargs -0 --no-run-if-empty rm -rf
	@find . \
	  -path ./.venv -prune -o \
	  -path ./.git -prune -o \
	  -type f -name '*.py[co]' -print0 2>/dev/null \
	  | xargs -0 --no-run-if-empty rm -f
	@rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	@echo "✓ Python caches removed"

clean: clean-py

clean-frontend:
	@rm -rf $(FRONTEND_DIR)/node_modules $(FRONTEND_DIR)/dist
	@echo "✓ frontend/node_modules and frontend/dist removed"

# Does not touch data/master_pdfs/ — those are gitignored, so deleting them means
# re-obtaining 18MB of source documents by hand.
clean-all: clean-py clean-frontend
	@echo "✓ .Python and frontend artifacts removed."
