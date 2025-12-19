from fastapi import FastAPI, Request
from fastapi.security import HTTPBearer
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException, RequestValidationError
from pydantic import ValidationError
from contextlib import asynccontextmanager
import os
import json
import re
from dotenv import load_dotenv

# Load environment variables from .env file FIRST
load_dotenv()

# Import configuration and validate BEFORE importing other modules
# This ensures the app fails fast at startup if Supabase is misconfigured
from config import config as app_config  # noqa: E402

# Validate configuration at startup (will raise RuntimeError if misconfigured)
app_config.validate_config()

# Import modules that depend on environment variables
from services.logger import app_logger as logger  # noqa: E402
from api import auth_routes, quiz_routes, file_routes, submission_routes, admin_routes, health_routes, billing_routes, export_routes, share_routes, contact_routes, cron_routes  # noqa: E402
from middleware.auto_refresh import SupabaseAutoRefreshMiddleware, close_http_client  # noqa: E402
from services.redis.client import lifespan as redis_lifespan  # noqa: E402
from services.posthog_service import shutdown_posthog, is_posthog_enabled, capture_exception  # noqa: E402
from services.posthog_logging import setup_posthog_logging, shutdown_posthog_logging  # noqa: E402

# Get the CORS origins from environment variable or use default
# SECURITY: In production, BACKEND_CORS_ORIGINS must be explicitly set
# to prevent requests from unauthorized origins.
_cors_origins_env = os.getenv("BACKEND_CORS_ORIGINS")
_is_production = os.getenv("RAILWAY_ENVIRONMENT") == "production" or os.getenv("ENV", "").lower() == "production"

if _cors_origins_env:
    try:
        BACKEND_CORS_ORIGINS = json.loads(_cors_origins_env)
        logger.info(f"CORS origins loaded: {BACKEND_CORS_ORIGINS}")
    except json.JSONDecodeError as e:
        if _is_production:
            logger.error(f"CRITICAL: Failed to parse BACKEND_CORS_ORIGINS in production: {e}")
            raise RuntimeError(f"BACKEND_CORS_ORIGINS must be valid JSON in production: {e}")
        BACKEND_CORS_ORIGINS = ["http://localhost:3000", "http://localhost:3001"]
        logger.warning(f"Failed to parse CORS origins from env ({e}), using development defaults")
elif _is_production:
    # SECURITY: Fail fast in production if CORS is not configured
    # 
    # DESIGN RATIONALE (addressing Copilot review feedback):
    # We intentionally fail fast rather than defaulting to empty/restrictive CORS because:
    # 1. Empty CORS = app starts but rejects ALL cross-origin requests = silent failures
    # 2. Users would see the app as "healthy" (health checks pass) but API calls fail
    # 3. Fail-fast ensures configuration errors are caught during deployment, not after
    # 4. Railway health checks use same-origin requests, so /health still works pre-startup
    # 
    # The /health endpoint is CORS-agnostic (same-origin from Railway's perspective),
    # so deployment automation health checks will succeed even if this check fails.
    logger.error("CRITICAL: BACKEND_CORS_ORIGINS not set in production environment")
    raise RuntimeError(
        "BACKEND_CORS_ORIGINS environment variable must be set in production. "
        "Example: '[\"https://quizify.com\", \"https://www.quizify.com\"]'"
    )
else:
    # Development fallback
    BACKEND_CORS_ORIGINS = ["http://localhost:3000", "http://localhost:3001"]
    logger.info("Using development CORS origins: localhost:3000, localhost:3001")

# Get CORS origin regex for wildcard support (e.g., Vercel previews)

def is_overly_permissive_cors_regex(pattern: str) -> bool:
    """
    Check if a CORS regex pattern is overly permissive (e.g., allows all domains).
    
    Args:
        pattern: The regex pattern to check
        
    Returns:
        bool: True if the pattern is considered overly permissive
    """
    # Check for catch-all patterns
    if pattern in [".*", ".+", "^.*$", "^.+$"]:
        return True
        
    # Check for patterns that contain ".*" but don't have enough specificity
    # e.g., ".*" without any literal dots usually means "match anything"
    # whereas ".*\.example\.com" has a literal dot
    if ".*" in pattern and "." not in pattern.replace(".*", ""):
        return True
        
    return False

BACKEND_CORS_ORIGIN_REGEX = os.getenv("BACKEND_CORS_ORIGIN_REGEX", None)
if BACKEND_CORS_ORIGIN_REGEX:
    # Validate regex compiles correctly
    try:
        re.compile(BACKEND_CORS_ORIGIN_REGEX)
    except re.error as e:
        logger.error(f"Invalid BACKEND_CORS_ORIGIN_REGEX pattern: {e}")
        raise RuntimeError(f"BACKEND_CORS_ORIGIN_REGEX must be a valid regex pattern: {e}")
    
    # Security check: Warn if pattern appears overly permissive
    if is_overly_permissive_cors_regex(BACKEND_CORS_ORIGIN_REGEX):
        logger.warning(
            f"CORS regex pattern appears overly permissive: {BACKEND_CORS_ORIGIN_REGEX}. "
            "This may allow requests from any origin. Use specific domain patterns (e.g., ^https://.*\\.vercel\\.app$)"
        )
    
    logger.info(f"CORS origin regex enabled: {BACKEND_CORS_ORIGIN_REGEX}")

# Enable docs in development (use ENABLE_DOCS=true in .env)
enable_docs = os.getenv("ENABLE_DOCS", "false").lower() == "true"
docs_url = "/docs" if enable_docs else None
redoc_url = "/redoc" if enable_docs else None


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    """
    Application lifespan manager that handles startup and shutdown events.
    
    This replaces the deprecated @app.on_event("startup") and @app.on_event("shutdown")
    decorators with the modern lifespan context manager approach.
    """
    logger.info("Application startup: initializing resources...")
    
    # Initialize PostHog OpenTelemetry logging (attaches to root logger)
    # Note: Only loggers with propagate=True will send logs to PostHog
    if setup_posthog_logging():
        logger.info("PostHog OpenTelemetry logging is enabled")
    else:
        logger.info("PostHog OpenTelemetry logging is disabled")
    
    # Log PostHog analytics status
    if is_posthog_enabled():
        logger.info("PostHog LLM analytics is enabled")
    else:
        logger.info("PostHog LLM analytics is disabled (set POSTHOG_API_KEY to enable)")
    
    # Initialize Redis connection (delegates to redis_lifespan)
    async with redis_lifespan(app):
        logger.info("Application startup complete")
        yield
    
    # Cleanup on shutdown
    logger.info("Application shutdown: cleaning up resources...")
    
    # Close OpenAI httpx client to prevent connection pool leaks
    from services.ai_services.openai_service import cleanup_openai_client
    await cleanup_openai_client()
    
    # Close HTTP client used for token refresh
    await close_http_client()
    
    # Shutdown PostHog logging (flush pending logs)
    shutdown_posthog_logging()
    
    # Shutdown PostHog analytics (flush pending events)
    shutdown_posthog()


app = FastAPI(
    title="Quiz Generator API",
    description="Backend API for Quizify application",
    version="0.1.0",
    docs_url=docs_url,
    redoc_url=redoc_url,
    lifespan=app_lifespan
)
logger.info("FastAPI application initialized")


# =============================================================================
# Global Exception Handlers for PostHog Error Tracking
# =============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Handle HTTPExceptions (intentional errors like 400, 401, 404, etc.)
    
    Only capture 5xx errors to PostHog since 4xx are often expected (auth failures,
    validation errors, etc.) and would create too much noise.
    
    Uses capture_exception() for proper PostHog error tracking integration.
    """
    if exc.status_code >= 500:
        user_id = getattr(request.state, "auth_user_id", None)
        plan = getattr(request.state, "auth_plan", "unknown")
        
        # Use capture_exception for proper error tracking
        # PostHog will group these by exception type and provide stack traces
        capture_exception(
            exception=exc,
            distinct_id=user_id,
            properties={
                "path": str(request.url.path),
                "method": request.method,
                "plan": plan,
                "status_code": exc.status_code,
                "error_category": "http_5xx",
            }
        )
    
    # Return standard HTTP error response
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Handle FastAPI RequestValidationError (Pydantic validation errors for request bodies).
    
    Returns 422 Unprocessable Entity with detailed validation error messages.
    This ensures validation errors are returned as 422 instead of being caught
    by the global exception handler and returned as 500.
    """
    # Extract user-friendly error messages
    errors = []
    for error in exc.errors():
        # Build a user-friendly message
        loc = " -> ".join(str(x) for x in error.get("loc", []))
        msg = error.get("msg", "Invalid value")
        errors.append({"location": loc, "message": msg})
    
    logger.warning(
        f"Request validation error on {request.method} {request.url.path}: {errors}"
    )
    
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Request validation failed",
            "errors": errors
        }
    )


@app.exception_handler(ValidationError)
async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
    """
    Handle Pydantic ValidationError (validation errors from internal Pydantic models).
    
    This catches validation errors that occur during internal processing
    (not from request body validation which is handled by RequestValidationError).
    Returns 422 for consistency.
    """
    errors = []
    for error in exc.errors():
        loc = " -> ".join(str(x) for x in error.get("loc", []))
        msg = error.get("msg", "Invalid value")
        errors.append({"location": loc, "message": msg})
    
    logger.warning(
        f"Pydantic validation error on {request.method} {request.url.path}: {errors}"
    )
    
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Data validation failed",
            "errors": errors
        }
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global handler for unhandled exceptions.
    
    Captures all unhandled errors to PostHog Error Tracking for monitoring
    and debugging. Uses capture_exception() for proper stack traces and
    error grouping in PostHog's Error Tracking dashboard.
    
    Returns a generic 500 error to avoid leaking internal details.
    """
    # Extract user context from request state (set by auth middleware)
    user_id = getattr(request.state, "auth_user_id", None)
    plan = getattr(request.state, "auth_plan", "unknown")
    
    # Log to console for debugging
    logger.error(
        f"Unhandled exception on {request.method} {request.url.path}: {type(exc).__name__}: {exc}",
        exc_info=True
    )
    
    # Capture to PostHog Error Tracking
    # This provides proper stack traces, error grouping, and debugging tools
    capture_exception(
        exception=exc,
        distinct_id=user_id,
        properties={
            "path": str(request.url.path),
            "method": request.method,
            "plan": plan,
            "error_category": "unhandled",
        }
    )
    
    # Return generic error to client (don't leak internal details)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Please try again later."},
    )


# Configure CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=BACKEND_CORS_ORIGINS,
    allow_origin_regex=BACKEND_CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept", "X-Session-ID", "X-Refresh-Token"],
    max_age=3600,
)
app.add_middleware(SupabaseAutoRefreshMiddleware)
logger.info("CORS middleware configured")

# Mount protected sub-app for /files
app.include_router(auth_routes.router, prefix="/api")
app.include_router(quiz_routes.router, prefix="/api")
app.include_router(file_routes.router, prefix="/api")
app.include_router(submission_routes.router, prefix="/api")
app.include_router(admin_routes.router, prefix="/api")
app.include_router(export_routes.router, prefix="/api")  # Export routes at /api/quizzes/{id}/export
app.include_router(share_routes.router, prefix="/api")  # Share routes at /api/share
app.include_router(contact_routes.router, prefix="/api")  # Contact form at /api/contact
app.include_router(billing_routes.router)  # Billing routes have their own /api/billing prefix
app.include_router(cron_routes.router, prefix="/api")  # Cron routes at /api/cron
app.include_router(health_routes.router)  # No prefix - mount at root


# Include remaining routers directly
logger.info("API routers registered")


# Security scheme for Swagger UI
bearer_scheme = HTTPBearer()

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    logger.debug("Generating custom OpenAPI schema")
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    openapi_schema.setdefault("components", {})
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT"
        }
    }

    app.openapi_schema = openapi_schema
    logger.debug("Custom OpenAPI schema generated")
    return app.openapi_schema


app.openapi = custom_openapi
logger.info("Application startup complete")
