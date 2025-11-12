import os
from typing import Optional, Tuple

import httpx
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from services.logger import app_logger as logger
from services.redis.sessions import SessionService

security = HTTPBearer(auto_error=False)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

SESSION_HEADER = "X-Session-ID"


def _short_id(value: Optional[str], length: int = 12) -> str:
    """Return obfuscated identifier for logging."""
    if not value:
        return "unknown"
    return f"{value[:length]}..."


logger.info("Auth helper initialized")


async def _validate_request_session(request: Request, user_id: str) -> Optional[str]:
    """Validate Redis session associated with the request and refresh its TTL."""

    if getattr(request.state, "session_validated", False):
        return getattr(request.state, "session_id", None)

    redis_client = getattr(request.app.state, "redis", None)
    if not redis_client:
        logger.warning("Redis client unavailable; skipping session validation (fallback mode)")
        request.state.session_validated = True
        request.state.session_id = None
        return None

    session_id = request.headers.get(SESSION_HEADER)
    if not session_id:
        session_id = request.query_params.get("session_id")
    if not session_id:
        session_id = request.cookies.get("session_id")

    if not session_id:
        logger.warning("Session ID missing for user %s", _short_id(user_id, length=8))
        raise HTTPException(status_code=401, detail="Session expired or missing")

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
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{SUPABASE_URL}/auth/v1/user", headers=headers)

        if response.status_code != 200:
            logger.warning("Invalid token. Supabase status: %s", response.status_code)
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        user_info = response.json()
        logger.debug("Full user info: %s", user_info)

        user_id = user_info.get("id") or user_info.get("email")
        if not user_id:
            logger.error("No valid user identifier found in token payload")
            raise HTTPException(status_code=401, detail="Invalid user token - no identifier found")

        await _validate_request_session(request, user_id)

        request.state.auth_cached = True
        request.state.access_token = token
        request.state.auth_user_id = user_id
        request.state.auth_token = token

        logger.debug("Authenticated user %s", _short_id(user_id, 8))
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