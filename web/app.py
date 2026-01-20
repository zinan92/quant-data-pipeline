from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.router import api_router
from src.config import Settings, get_settings
from src.lifecycle import register_startup_shutdown

settings = get_settings()


def create_app() -> FastAPI:
    """Instantiate the FastAPI application with routing and middleware."""
    application = FastAPI(
        title="A-Share Monitor API",
        version="0.1.0",
        description="Batch K-line data service for A-share monitoring dashboard.",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(api_router, prefix="/api")

    register_startup_shutdown(application)
    return application


app = create_app()
