"""
Compat shim so existing tooling/tests can import `src.main.app`.
Actual FastAPI application object lives in `web/app.py`.
"""

from web.app import app  # noqa: F401
