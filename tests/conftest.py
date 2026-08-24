"""
Shared pytest configuration.

Puts the repository root on sys.path so `api.*`, `rag.*` and `pipeline.*` resolve
the same way they do under uvicorn. pytest prepends the *test file's* directory
(tests/), not the project root, so without this every import below fails.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
