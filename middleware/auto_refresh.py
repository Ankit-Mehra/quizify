from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.status import HTTP_401_UNAUTHORIZED
from starlette.datastructures import MutableHeaders
import os
import httpx
from services.logger import app_logger as logger
from services.cookie_utils import (
    delete_auth_cookie as _delete_auth_cookie,
    ACCESS_TOKEN_EXPIRE,
    REFRESH_TOKEN_EXPIRE,
)
from services.redis.sessions import SessionService
from config import config as app_config

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Module-level async HTTP client for connection reuse
_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    """Get or create the shared async HTTP client."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=10.0)
    return _http_client


async def close_http_client() -> None:
    """
    Close the shared HTTP client gracefully.
    
    Should be called during application shutdown to prevent resource leaks.
    """
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
        logger.debug("Auto-refresh HTTP client closed")


def _extract_refresh_token(request: Request) -> str | None:
    """Return the last refresh_token value from the Cookie header."""
    cookie_header = request.headers.get("cookie")
    if not cookie_header:
        return request.cookies.get("refresh_token")

    refresh_value = None
    for part in cookie_header.split(";"):
        name, _, value = part.strip().partition("=")
        if name == "refresh_token" and value:
            refresh_value = value

    if refresh_value is None:
        return request.cookies.get("refresh_token")

    return refresh_value

# Public routes that should NOT trigger token logic
EXCLUDE_PATHS = [
    "/docs",
    "/openapi.json",
    "/redoc",
    "/health",  # Health check endpoint (public, no auth required)
    "/api/contact",  # Contact form endpoints (public, no auth required)
    "/api/share/public",  # Public quiz sharing (no auth required)
    "/api/auth/login",
    "/api/auth/signup",
    "/api/auth/confirm",  # Email confirmation callback (no auth required)
    "/api/auth/forgot-password",  # Password reset request (no auth required)
    "/api/auth/reset-password",  # Password reset with token (no auth required)
    "/api/auth/resend-verification",  # Resend verification email (no auth required)
    "/api/auth/google/signin",  # Google OAuth initiate (no auth required)
    "/api/auth/google/signin/callback",  # Google OAuth callback (no auth required)
    "/api/auth/google/signin/token",  # Google ID token signin (no auth required)
]

class SupabaseAutoRefreshMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip middleware for public endpoints
        if any(path.startswith(p) for p in EXCLUDE_PATHS):
            return await call_next(request)

        access_token = request.cookies.get("access_token")
        refresh_token = _extract_refresh_token(request)

        if access_token:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "apikey": SUPABASE_KEY
            }

            try:
                client = _get_http_client()
                user_resp = await client.get(f"{SUPABASE_URL}/auth/v1/user", headers=headers)
                if user_resp.status_code == 200:
                    return await call_next(request)
                logger.info("Access token invalid, attempting refresh", extra={"status": user_resp.status_code})
            except Exception:
                logger.exception("Access token validation failed, attempting refresh")
                pass  # Fall through to refresh

        if refresh_token:
            try:
                logger.debug("Attempting token refresh via Supabase")
                client = _get_http_client()
                refresh_resp = await client.post(
                    f"{SUPABASE_URL}/auth/v1/token?grant_type=refresh_token",
                    headers={
                        "apikey": SUPABASE_KEY,
                        "Content-Type": "application/json"
                    },
                    json={"refresh_token": refresh_token}
                )

                if refresh_resp.status_code == 200:
                    session = refresh_resp.json()
                    new_access_token = session.get("access_token")
                    new_refresh_token = session.get("refresh_token")
                    if not new_access_token:
                        raise Exception("No access token returned")

                    # Make refreshed token available to downstream dependencies immediately
                    request.state.access_token = new_access_token

                    # Inject Authorization header so HTTPBearer dependencies pick it up
                    headers = MutableHeaders(scope=request.scope)
                    headers["Authorization"] = f"Bearer {new_access_token}"
                    logger.debug("Successfully refreshed access token")

                    response = await call_next(request)
                    response.set_cookie(
                        key="access_token",
                        value=new_access_token,
                        httponly=True,
                        secure=True,
                        samesite="lax",
                        domain=app_config.COOKIE_DOMAIN if not app_config.is_testing() else None,
                        max_age=ACCESS_TOKEN_EXPIRE
                    )
                    if new_refresh_token:
                        response.set_cookie(
                            key="refresh_token",
                            value=new_refresh_token,
                            httponly=True,
                            secure=True,
                            samesite="lax",
                            domain=app_config.COOKIE_DOMAIN if not app_config.is_testing() else None,
                            max_age=REFRESH_TOKEN_EXPIRE
                        )
                    return response

                else:
                    logger.warning(
                        "Refresh token invalid - clearing cookies",
                        extra={"status": refresh_resp.status_code, "response": refresh_resp.text}
                    )
                    
                    # Cleanup Redis session before returning 401
                    redis_client = getattr(request.app.state, "redis", None)
                    if redis_client and refresh_token:
                        try:
                            session_service = SessionService(redis_client)
                            session_id = await session_service.find_session_by_refresh_token(refresh_token)
                            if session_id:
                                await session_service.logout(session_id)
                                logger.info(f"Cleaned up expired session {session_id[:12]}... on auto-logout (refresh failed)")
                        except Exception as cleanup_error:
                            logger.warning(f"Failed to cleanup session on auto-logout: {cleanup_error}")
                    
                    # Don't call the next handler - return 401 directly and clear cookies
                    response = JSONResponse(
                        status_code=HTTP_401_UNAUTHORIZED,
                        content={"detail": "Session expired. Please log in again."}
                    )
                    # Clear both tokens so frontend knows user is logged out
                    _delete_auth_cookie(response, "refresh_token")
                    _delete_auth_cookie(response, "access_token")
                    return response
            except Exception:
                logger.exception("Token refresh failed - clearing cookies")
                
                # Cleanup Redis session before returning 401
                redis_client = getattr(request.app.state, "redis", None)
                if redis_client and refresh_token:
                    try:
                        session_service = SessionService(redis_client)
                        session_id = await session_service.find_session_by_refresh_token(refresh_token)
                        if session_id:
                            await session_service.logout(session_id)
                            logger.info(f"Cleaned up expired session {session_id[:12]}... on auto-logout (refresh exception)")
                    except Exception as cleanup_error:
                        logger.warning(f"Failed to cleanup session on auto-logout: {cleanup_error}")
                
                response = JSONResponse(
                    status_code=HTTP_401_UNAUTHORIZED,
                    content={"detail": "Session expired. Please log in again."}
                )
                # Clear both tokens
                _delete_auth_cookie(response, "refresh_token")
                _delete_auth_cookie(response, "access_token")
                return response

        # No access and no refresh token — let route-level auth handle it
        return await call_next(request)
