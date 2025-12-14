"""
Shared cookie utilities for authentication.

This module provides centralized cookie settings and operations to ensure
consistent cookie handling across the codebase (handlers, middleware, etc).

SECURITY NOTE: For cross-origin deployments (frontend on Vercel, backend on Railway),
we use SameSite=None to allow cookies to be sent with cross-origin requests.
This is safe because we use JWT + Redis session validation (not cookie-only auth).
CSRF attacks cannot forge JWT signatures.
"""
from typing import TYPE_CHECKING

from config import config as app_config

if TYPE_CHECKING:
    from fastapi import Response

# Token expiration times (must match across all modules)
ACCESS_TOKEN_EXPIRE = 3600  # 1 hour
REFRESH_TOKEN_EXPIRE = 60 * 60 * 24 * 30  # 30 days


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
        key: Cookie name to delete (e.g., "access_token", "refresh_token")
    """
    cookie_settings = get_cookie_settings()
    response.delete_cookie(
        key=key,
        path=cookie_settings.get("path", "/"),
        domain=cookie_settings.get("domain"),
        secure=cookie_settings.get("secure", True),
        samesite=cookie_settings.get("samesite", "none"),
        httponly=cookie_settings.get("httponly", True)
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
    cookie_settings = get_cookie_settings()
    
    response.set_cookie(
        key="access_token",
        value=access_token,
        **cookie_settings
    )
    
    # Refresh token uses longer expiration
    refresh_settings = {**cookie_settings, "max_age": REFRESH_TOKEN_EXPIRE}
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        **refresh_settings
    )
