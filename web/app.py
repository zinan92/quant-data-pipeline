from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from src.api.router import api_router
from src.config import Settings, get_settings
from src.lifecycle import lifespan
from src.exceptions import (
    AShareBaseException,
    DataNotFoundError,
    ValidationError,
    ExternalAPIError,
    DatabaseError,
    BusinessLogicError,
    ConfigurationError,
    AuthenticationError,
    AuthorizationError,
    ServiceUnavailableError,
)
from src.utils.logging import get_logger

from src.api.rate_limit import limiter

settings = get_settings()
logger = get_logger(__name__)


def create_app() -> FastAPI:
    """Instantiate the FastAPI application with routing and middleware."""
    application = FastAPI(
        title="A-Share Monitor API",
        version="0.1.0",
        description="Batch K-line data service for A-share monitoring dashboard.",
        lifespan=lifespan,
    )

    # Rate limiting
    application.state.limiter = limiter
    application.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-API-Key"],
    )

    # Register exception handlers
    register_exception_handlers(application)

    application.include_router(api_router, prefix="/api")

    return application


def register_exception_handlers(app: FastAPI) -> None:
    """Register custom exception handlers for business exceptions."""

    @app.exception_handler(DataNotFoundError)
    async def data_not_found_handler(request: Request, exc: DataNotFoundError) -> JSONResponse:
        """Handle data not found errors with 404 status."""
        logger.warning(f"Data not found: {exc.message}", extra=exc.details)
        return JSONResponse(
            status_code=404,
            content=exc.to_dict()
        )

    @app.exception_handler(ValidationError)
    async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
        """Handle validation errors with 400 status."""
        logger.warning(f"Validation error: {exc.message}", extra=exc.details)
        return JSONResponse(
            status_code=400,
            content=exc.to_dict()
        )

    @app.exception_handler(AuthenticationError)
    async def authentication_error_handler(request: Request, exc: AuthenticationError) -> JSONResponse:
        """Handle authentication errors with 401 status."""
        logger.warning(f"Authentication error: {exc.message}")
        return JSONResponse(
            status_code=401,
            content=exc.to_dict()
        )

    @app.exception_handler(AuthorizationError)
    async def authorization_error_handler(request: Request, exc: AuthorizationError) -> JSONResponse:
        """Handle authorization errors with 403 status."""
        logger.warning(f"Authorization error: {exc.message}", extra=exc.details)
        return JSONResponse(
            status_code=403,
            content=exc.to_dict()
        )

    @app.exception_handler(ExternalAPIError)
    async def external_api_error_handler(request: Request, exc: ExternalAPIError) -> JSONResponse:
        """Handle external API errors with 502 status."""
        logger.error(f"External API error: {exc.message}", extra=exc.details)
        return JSONResponse(
            status_code=502,
            content=exc.to_dict()
        )

    @app.exception_handler(ServiceUnavailableError)
    async def service_unavailable_handler(request: Request, exc: ServiceUnavailableError) -> JSONResponse:
        """Handle service unavailable errors with 503 status."""
        logger.error(f"Service unavailable: {exc.message}", extra=exc.details)
        return JSONResponse(
            status_code=503,
            content=exc.to_dict()
        )

    @app.exception_handler(DatabaseError)
    async def database_error_handler(request: Request, exc: DatabaseError) -> JSONResponse:
        """Handle database errors with 500 status."""
        logger.error(f"Database error: {exc.message}", extra=exc.details, exc_info=True)
        return JSONResponse(
            status_code=500,
            content=exc.to_dict()
        )

    @app.exception_handler(BusinessLogicError)
    async def business_logic_error_handler(request: Request, exc: BusinessLogicError) -> JSONResponse:
        """Handle business logic errors with 422 status."""
        logger.warning(f"Business logic error: {exc.message}", extra=exc.details)
        return JSONResponse(
            status_code=422,
            content=exc.to_dict()
        )

    @app.exception_handler(ConfigurationError)
    async def configuration_error_handler(request: Request, exc: ConfigurationError) -> JSONResponse:
        """Handle configuration errors with 500 status."""
        logger.error(f"Configuration error: {exc.message}", extra=exc.details)
        return JSONResponse(
            status_code=500,
            content=exc.to_dict()
        )

    @app.exception_handler(AShareBaseException)
    async def base_exception_handler(request: Request, exc: AShareBaseException) -> JSONResponse:
        """Catch-all handler for any custom business exception."""
        logger.error(f"Unhandled business exception: {exc.message}", extra=exc.details, exc_info=True)
        return JSONResponse(
            status_code=500,
            content=exc.to_dict()
        )


app = create_app()
