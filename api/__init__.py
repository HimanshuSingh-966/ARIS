"""
api — FastAPI application package for ARIS.

Single source of truth for the version. It used to be hardcoded in three places
(main.py's FastAPI(version=...), models.HealthResponse's default, and health.py's
literal) and had already drifted from frontend/package.json, so /health could
report a version the app was not. Import __version__ instead of writing a literal.
"""

__version__ = "1.7.0"
