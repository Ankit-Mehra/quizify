"""
Shared cookie utilities for authentication.

This module provides centralized cookie settings and operations to ensure
consistent cookie handling across the codebase (handlers, middleware, etc).

SECURITY NOTE: For cross-origin deployments (frontend on Vercel, backend on Railway),
we use SameSite=None to allow cookies to be sent with cross-origin requests.
This is safe because we use JWT + Redis session validation (not cookie-only auth).
CSRF attacks cannot forge JWT signatures.
"""
import logging
from typing import TYPE_CHECKING

from config import config as app_config

if TYPE_CHECKING:
    from fastapi import Response

logger = logging.getLogger(__name__)

# Token expiration times (must match across all modules)
ACCESS_TOKEN_EXPIRE = 3600  # 1 hour
REFRESH_TOKEN_EXPIRE = 60 * 60 * 24 * 30  # 30 days

# Cookie names (renamed to prevent collision with legacy host-only cookies)
ACCESS_TOKEN_COOKIE_NAME = "quizify_access_token"
REFRESH_TOKEN_COOKIE_NAME = "quizify_refresh_token"


def get_cookie_settings() -> dict:
    """
    Get cookie settings based on environment.
    
    Returns secure cookie settings for production, consistent settings for testing.
    Note: secure=True always (matches existing login() behavior) - tests run with HTTPS mocking.
    
    IMPORTANT: For cross-origin deployments where the frontend and backend are on
    different domains, we must use SameSite=None to allow cookies to be sent with
    cross-origin requests. This requires Secure=True (enforced by browsers).
    """
    if app_config.is_testing():
        # Match existing login() behavior: secure=True, no domain for testing
        return {
            "httponly": True,
            "secure": True,
            "samesite": "lax",
            "max_age": ACCESS_TOKEN_EXPIRE,
            "path": "/"
        }
    
    # Production: Use SameSite=None for cross-origin cookie support
    return {
        "httponly": True,
        "secure": True,
        "samesite": "none",  # Required for cross-origin requests
        "domain": app_config.COOKIE_DOMAIN,
        "max_age": ACCESS_TOKEN_EXPIRE,
        "path": "/"
    }


def delete_auth_cookie(response: "Response", key: str) -> None:
    """
    Delete an auth cookie with proper attributes.
    
    IMPORTANT: Cookie deletion must use the same domain, path, secure, and samesite
    attributes as when the cookie was set. Otherwise browsers won't delete it.
    
    Args:
        response: FastAPI Response, JSONResponse, or RedirectResponse object
        key: Cookie name to delete (e.g., "quizify_access_token", "quizify_refresh_token")
    """
    cookie_settings = get_cookie_settings()
    response.delete_cookie(
        key=key,
        path=cookie_settings["path"],
        domain=cookie_settings.get("domain"),  # domain may not exist in test mode
        secure=cookie_settings["secure"],
        samesite=cookie_settings["samesite"],
        httponly=cookie_settings["httponly"]
    )


def set_auth_cookies(response: "Response", access_token: str, refresh_token: str) -> None:
    """
    Set authentication cookies on a response object.
    
    This helper ensures consistent cookie settings across all auth endpoints:
    - login, google_signin_callback, google_signin_token
    
    Args:
        response: FastAPI Response or RedirectResponse object
        access_token: JWT access token from Supabase
        refresh_token: Refresh token from Supabase
    """
    # DEBUG: Log token lengths before setting cookies
    logger.info(f"set_auth_cookies: access_token length={len(access_token) if access_token else 0}, refresh_token length={len(refresh_token) if refresh_token else 0}")
    
    cookie_settings = get_cookie_settings()
    
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE_NAME,
        value=access_token,
        **cookie_settings
    )
    
    # Refresh token uses longer expiration
    refresh_settings = {**cookie_settings, "max_age": REFRESH_TOKEN_EXPIRE}
    response.set_cookie(
        key=REFRESH_TOKEN_COOKIE_NAME,
        value=refresh_token,
        **refresh_settings
    )
