from fastapi import FastAPI
from fastapi.security import HTTPBearer
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import os
import json
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
from api import auth_routes, quiz_routes, file_routes, submission_routes, admin_routes, health_routes  # noqa: E402
from middleware.auto_refresh import SupabaseAutoRefreshMiddleware  # noqa: E402
from services.redis.client import lifespan as redis_lifespan  # noqa: E402

# Get the CORS origins from environment variable or use default
try:
    BACKEND_CORS_ORIGINS = json.loads(os.getenv("BACKEND_CORS_ORIGINS", '["http://localhost:3000", "http://localhost:3001"]'))
    logger.info(f"CORS origins loaded: {BACKEND_CORS_ORIGINS}")
except json.JSONDecodeError:
    BACKEND_CORS_ORIGINS = ["http://localhost:3000", "http://localhost:3001"]
    logger.warning("Failed to parse CORS origins from env, using defaults")

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
    
    # Initialize Redis connection (delegates to redis_lifespan)
    async with redis_lifespan(app):
        logger.info("Application startup complete")
        yield
    
    logger.info("Application shutdown: cleaning up resources...")


app = FastAPI(
    title="Quiz Generator API",
    description="Backend API for Quizify application",
    version="0.1.0",
    docs_url=docs_url,
    redoc_url=redoc_url,
    lifespan=app_lifespan
)
logger.info("FastAPI application initialized")

# Configure CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept", "X-Session-ID"],
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
