"""
FastAPI application surface for the A-share monitoring backend.
"""

from .app import create_app, app

__all__ = ["create_app", "app"]
