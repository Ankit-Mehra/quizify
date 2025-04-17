from fastapi import FastAPI
from api import auth_routes, quiz_routes, file_routes
from fastapi.security import HTTPBearer
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
import os
import json
from services.logger import app_logger as logger


# Get the CORS origins from environment variable or use default
try:
    BACKEND_CORS_ORIGINS = json.loads(os.getenv("BACKEND_CORS_ORIGINS", '["http://localhost:3000", "http://localhost:3001"]'))
    logger.info(f"CORS origins loaded: {BACKEND_CORS_ORIGINS}")
except json.JSONDecodeError:
    BACKEND_CORS_ORIGINS = ["http://localhost:3000", "http://localhost:3001"]  # Fallback default
    logger.warning("Failed to parse CORS origins from env, using defaults")

app = FastAPI(
    title="Quiz Generator API",
    description="Backend API for Quizify application",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)
logger.info("FastAPI application initialized")

# Configure CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept"],
    max_age=3600,  # Cache preflight requests for 1 hour
)
logger.info("CORS middleware configured")

# Include API routers
app.include_router(quiz_routes.router, prefix="/api")
app.include_router(auth_routes.router, prefix="/api")
app.include_router(file_routes.router, prefix="/api")
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

    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT"
        }
    }

    # Do NOT apply globally — individual routes will declare Depends
    app.openapi_schema = openapi_schema
    logger.debug("Custom OpenAPI schema generated")
    return app.openapi_schema

app.openapi = custom_openapi
logger.info("Application startup complete")