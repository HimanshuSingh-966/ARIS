"""
scripts/check_model.py
Diagnostic: list the Gemini models this API key can actually call for generation,
and say whether the configured GEMINI_MODEL is among them.

This script used to filter on 'embedContent'. Embeddings moved to FastEmbed — local
CPU inference, BAAI/bge-small-en-v1.5, 384-dim, see pipeline/embedder.py — so Gemini
is now used for generation only. The old output listed models the app cannot use and
never showed the one it actually depends on, which made it useless for diagnosing the
failure it exists to diagnose ("why is chat returning 502?").

Run: python scripts/check_model.py
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# parent.parent, not the script's own directory: this file lives in scripts/ and
# the .env is at the repo root.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    # The bare os.environ[...] this replaced raised KeyError with a traceback, which
    # reads like a bug in the script rather than a missing variable.
    sys.exit("GEMINI_API_KEY is not set. Add it to .env (see .env.example).")

import google.generativeai as genai  # noqa: E402  (after the key check, by design)

genai.configure(api_key=api_key)

configured = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

print("Gemini models available for generation:")
available = []
for m in genai.list_models():
    if "generateContent" in m.supported_generation_methods:
        available.append(m.name)
        print(f" - {m.name}")

if not available:
    sys.exit("\nNo generation-capable models returned. Check the key's permissions.")

# list_models() returns fully-qualified names ("models/gemini-2.0-flash") while
# rag/llm.py passes the short form, so compare on the suffix.
match = any(name == configured or name.endswith(f"/{configured}") for name in available)
print(
    f"\nGEMINI_MODEL={configured}: "
    + ("available." if match else "NOT in the list above — generation will fail.")
)
if not match:
    sys.exit(1)
