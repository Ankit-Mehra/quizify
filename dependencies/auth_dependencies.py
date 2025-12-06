import os
from typing import Optional, Tuple

import httpx
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import config
from services.logger import app_logger as logger
from services.redis.sessions import SessionService
from services.db_services.supabase_quiz import get_user_tier_info_cached

security = HTTPBearer(auto_error=False)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Module-level HTTP client for connection reuse (avoids TLS handshake overhead)
_http_client: Optional[httpx.AsyncClient] = None


def get_http_client() -> httpx.AsyncClient:
    """
    Get or create shared HTTP client for Supabase auth requests.
    
    Uses module-level singleton to reuse TCP connections and avoid TLS handshake
    overhead on every auth request. The client is created on first use and reused
    for subsequent requests.
    
    Note: In tests, httpx.AsyncClient is patched to return a mock client, so this
    function will return the mocked version.
    """
    global _http_client
    if _http_client is None:
        # This will be the mocked client in tests due to patch
        _http_client = httpx.AsyncClient(timeout=10)
    return _http_client


def reset_http_client():
    """Reset the shared HTTP client (used in tests to clear singleton state)."""
    global _http_client
    _http_client = None


def _short_id(value: Optional[str], length: int = 12) -> str:
    """Return obfuscated identifier for logging."""
    if not value:
        return "unknown"
    return f"{value[:length]}..."


logger.info("Auth helper initialized")


async def _validate_request_session(request: Request, user_id: str) -> Optional[str]:
    """
    Validate Redis session associated with the request and refresh its TTL.
    
    SECURITY: Redis is REQUIRED for session management. If Redis is unavailable,
    all session-based security controls (revocation, limits, logout-all) would be
    bypassed. Therefore, we fail closed and return 503 Service Unavailable.
    """

    if getattr(request.state, "session_validated", False):
        return getattr(request.state, "session_id", None)

    redis_client = getattr(request.app.state, "redis", None)
    if not redis_client:
        logger.error(
            "Redis client unavailable - cannot validate session for user %s. "
            "Failing closed to prevent security bypass.",
            _short_id(user_id, length=8)
        )
        raise HTTPException(
            status_code=503,
            detail="Session management service temporarily unavailable. Please try again."
        )

    # Lookup session_id via refresh_token (header in dev mode, cookie in production)
    if config.is_development():
        refresh_token_header = request.headers.get("X-Refresh-Token")
        refresh_token = refresh_token_header or request.cookies.get("refresh_token")
        token_source = "header" if refresh_token_header else "cookie"
    else:
        refresh_token = request.cookies.get("refresh_token")
        token_source = "cookie"
    
    session_id = None
    if refresh_token:
        session_service = SessionService(redis_client)
        session_id = await session_service.find_session_by_refresh_token(refresh_token)
        if session_id:
            logger.debug(
                "Session lookup via refresh_token %s for user %s",
                token_source,
                _short_id(user_id, length=8)
            )

    if not session_id:
        # SECURITY: Session ID is required for session management to work
        # Without it, session revocation, logout all devices, and session limits are bypassed
        # Log the request path to identify which endpoint is being called repeatedly
        request_path = request.url.path if hasattr(request, 'url') else 'unknown'
        logger.warning(
            "Session ID missing for user %s on %s - returning 401 (session required)",
            _short_id(user_id, length=8),
            request_path
        )
        raise HTTPException(
            status_code=401,
            detail="Session ID required. Please login again to create a new session."
        )

    session_service = SessionService(redis_client)
    session_info = await session_service.validate_session(session_id)
    if not session_info:
        logger.warning("Session %s not found for user %s", _short_id(session_id), _short_id(user_id, 8))
        raise HTTPException(status_code=401, detail="Session expired or invalid")

    if session_info.user_id != user_id:
        logger.warning(
            "User %s attempted to use session %s belonging to %s",
            _short_id(user_id, 8),
            _short_id(session_id),
            _short_id(session_info.user_id, 8),
        )
        raise HTTPException(status_code=403, detail="Session does not belong to authenticated user")

    refreshed = await session_service.refresh_session(session_id)
    if not refreshed:
        logger.warning("Session %s failed to refresh for user %s", _short_id(session_id), _short_id(user_id, 8))
        raise HTTPException(status_code=401, detail="Session expired or invalid")

    request.state.session_validated = True
    request.state.session_id = session_id
    request.state.session_info = session_info
    return session_id


async def _authenticate_request(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials],
) -> Tuple[str, str]:
    """Authenticate request with Supabase and validate Redis session."""

    if getattr(request.state, "auth_cached", False):
        return request.state.auth_user_id, request.state.auth_token

    token = credentials.credentials if credentials else request.cookies.get("access_token")
    if not token:
        token = getattr(request.state, "access_token", None)

    if not token:
        logger.warning("Authentication required but no token provided")
        raise HTTPException(status_code=401, detail="Authentication required")

    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("Supabase credentials not configured")
        raise HTTPException(status_code=500, detail="Authentication service misconfigured")

    headers = {
        "Authorization": f"Bearer {token}",
        "apikey": SUPABASE_KEY,
    }

    try:
        logger.debug("Verifying token with Supabase")
        # Use shared HTTP client for connection reuse (avoids TLS handshake on every request)
        client = get_http_client()
        response = await client.get(f"{SUPABASE_URL}/auth/v1/user", headers=headers)

        if response.status_code != 200:
            logger.warning("Invalid token. Supabase status: %s", response.status_code)
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        user_info = response.json()
        # Log only non-sensitive fields for debugging (avoid PII leakage)
        user_id_preview = user_info.get("id", "")[:8] if user_info.get("id") else "N/A"
        logger.debug("User auth successful for id=%s...", user_id_preview)

        user_id = user_info.get("id") or user_info.get("email")
        email = user_info.get("email")
        if not user_id:
            logger.error("No valid user identifier found in token payload")
            raise HTTPException(status_code=401, detail="Invalid user token - no identifier found")

        await _validate_request_session(request, user_id)

        # Fetch user plan/tier for error tracking context (uses Redis cache, ~1-5ms)
        # This is non-blocking on cache hit and gracefully degrades on failure
        try:
            tier_info = await get_user_tier_info_cached(user_id)
            request.state.auth_plan = tier_info.get("account_tier", "free")
        except Exception as tier_error:
            # Don't fail auth if tier lookup fails - just set default
            logger.warning(f"Failed to fetch user tier for context: {tier_error}")
            request.state.auth_plan = "unknown"

        request.state.auth_cached = True
        request.state.access_token = token
        request.state.auth_user_id = user_id
        request.state.auth_email = email
        request.state.auth_token = token

        logger.debug("Authenticated user %s (plan: %s)", _short_id(user_id, 8), request.state.auth_plan)
        return user_id, token

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Auth error: {exc}", exc_info=True)
        raise HTTPException(status_code=401, detail="Authentication failed")


async def get_current_user_id(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    user_id, _ = await _authenticate_request(request, credentials)
    return user_id


async def get_current_user_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    _, token = await _authenticate_request(request, credentials)
    logger.debug("Retrieved user token for request")
    return token


async def get_current_user_email(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    await _authenticate_request(request, credentials)
    return request.state.auth_email