"""
OAuth utility functions for Google Sign-In authentication.

This module provides helper functions for:
- CSRF token generation and validation
- OAuth state parameter handling
- Redirect URL validation
- New user detection

These utilities are used by the Google Sign-In endpoints in auth_handlers.py
to implement secure OAuth flows with CSRF protection.
"""

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from config import config as app_config
from services.logger import app_logger as logger


# ============================================================================
# Constants
# ============================================================================

# CSRF token settings for OAuth flows
OAUTH_STATE_COOKIE_NAME = "oauth_state"
OAUTH_STATE_MAX_AGE = 600  # 10 minutes - enough time to complete OAuth flow

# Configurable threshold for detecting new users (seconds since account creation)
NEW_USER_THRESHOLD_SECONDS = 10


# ============================================================================
# User Detection Helpers
# ============================================================================

def is_new_user(user) -> bool:
    """
    Check if a user was recently created (new user detection).
    
    This is used to determine if the user just signed up vs returning user,
    allowing the frontend to show appropriate welcome messages or onboarding.
    
    Args:
        user: Supabase user object with created_at attribute
        
    Returns:
        bool: True if user was created within NEW_USER_THRESHOLD_SECONDS, False otherwise
    """
    if not user or not getattr(user, 'created_at', None):
        return False
    
    try:
        created_at = user.created_at
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        return (now - created_at) < timedelta(seconds=NEW_USER_THRESHOLD_SECONDS)
    except Exception as parse_error:
        logger.warning(f"Failed to parse user.created_at ({getattr(user, 'created_at', None)}): {parse_error}")
        return False


# ============================================================================
# Redirect URL Validation
# ============================================================================

def validate_redirect_url(redirect_url: Optional[str]) -> Optional[str]:
    """
    Validate and sanitize redirect_url to prevent open redirects and CRLF injection.
    
    Only allows:
    - Relative paths starting with / (but not //)
    - No protocol:// embedded
    - No control characters
    
    Args:
        redirect_url: The URL to validate
        
    Returns:
        Sanitized URL or None if invalid
    """
    if not redirect_url:
        return None
    
    # Check for control characters that could enable CRLF header injection
    control_chars = "\r\n\x00"
    if any(c in redirect_url for c in control_chars):
        logger.warning("Rejecting redirect_url with control characters (CRLF injection attempt)")
        return None
    
    # Only allow relative paths starting with / (but not // which could be protocol-relative)
    if redirect_url.startswith("/") and not redirect_url.startswith("//"):
        # Reject if protocol:// is embedded anywhere
        if "://" in redirect_url:
            logger.warning(f"Rejecting redirect_url with embedded protocol: {redirect_url[:50]}...")
            return None
        logger.debug(f"Validated redirect_url: {redirect_url}")
        return redirect_url
    
    logger.warning(f"Rejecting non-relative redirect_url: {redirect_url[:50]}...")
    return None


# ============================================================================
# CSRF Token Management
# ============================================================================

def get_csrf_signing_key() -> bytes:
    """
    Get the key used for signing CSRF tokens.
    
    Uses SUPABASE_JWT_SECRET as the signing key to ensure it's consistent
    across server restarts and secure enough for HMAC signing.
    
    In development/testing mode, falls back to SUPABASE_KEY if JWT secret not set.
    In production, requires SUPABASE_JWT_SECRET to be set for security.
    
    Returns:
        bytes: The signing key encoded as bytes
        
    Raises:
        RuntimeError: If no signing key is available in production mode
    """
    secret = app_config.SUPABASE_JWT_SECRET
    if not secret:
        # In development/testing, allow fallback to prevent blocking local dev
        if app_config.is_development() or app_config.is_testing():
            secret = app_config.SUPABASE_KEY or "dev-fallback-key"
            logger.warning("Using SUPABASE_KEY as CSRF signing fallback (dev mode only)")
        else:
            # In production, CSRF signing key MUST be secure
            raise RuntimeError(
                "SUPABASE_JWT_SECRET must be set in production for CSRF token signing. "
                "This is required for secure OAuth state validation."
            )
    return secret.encode()


def generate_oauth_state(redirect_url: Optional[str] = None) -> Tuple[str, str]:
    """
    Generate a secure OAuth state parameter with CSRF protection.
    
    The state contains:
    - csrf_token: A cryptographically random token
    - redirect_url: Optional validated redirect URL
    - ts: Timestamp for expiration checking
    
    Args:
        redirect_url: Optional URL to redirect to after OAuth completes
        
    Returns:
        Tuple of (state_string, csrf_token):
        - state_string: Base64-encoded JSON with HMAC signature (for URL)
        - csrf_token: The raw CSRF token to store in cookie
    """
    # Generate a cryptographically secure random token
    csrf_token = secrets.token_urlsafe(32)
    
    # Build state payload
    state_payload = {
        "csrf": csrf_token,
        "ts": int(datetime.now(timezone.utc).timestamp())
    }
    
    # Add redirect URL if provided and validated
    if redirect_url:
        safe_redirect = validate_redirect_url(redirect_url)
        if safe_redirect:
            state_payload["redirect"] = safe_redirect
    
    # Serialize and sign the state
    payload_json = json.dumps(state_payload, separators=(',', ':'))
    
    # Create HMAC signature to prevent tampering
    signature = hmac.new(
        get_csrf_signing_key(),
        payload_json.encode(),
        hashlib.sha256
    ).hexdigest()[:16]  # Use first 16 chars for brevity
    
    # Combine payload and signature
    signed_state = f"{payload_json}.{signature}"
    
    # Base64 encode for URL safety
    state_string = base64.urlsafe_b64encode(signed_state.encode()).decode()
    
    return state_string, csrf_token


def verify_oauth_state(state: str, expected_csrf: Optional[str]) -> Tuple[bool, Optional[str]]:
    """
    Verify an OAuth state parameter and extract the redirect URL.
    
    Validates:
    - HMAC signature to prevent tampering
    - CSRF token matches the cookie value
    - Timestamp is not too old (OAUTH_STATE_MAX_AGE seconds)
    
    Args:
        state: The state parameter from OAuth callback
        expected_csrf: The CSRF token from the cookie
        
    Returns:
        Tuple of (is_valid, redirect_url):
        - is_valid: True if state is valid, False otherwise
        - redirect_url: The redirect URL from state, or None
    """
    if not state:
        logger.warning("OAuth state parameter is missing")
        return False, None
    
    if not expected_csrf:
        logger.warning("OAuth CSRF cookie is missing - possible CSRF attack or expired session")
        return False, None
    
    try:
        # Decode base64
        signed_state = base64.urlsafe_b64decode(state.encode()).decode()
        
        # Split payload and signature
        if '.' not in signed_state:
            logger.warning("OAuth state missing signature separator")
            return False, None
        
        payload_json, signature = signed_state.rsplit('.', 1)
        
        # Verify HMAC signature
        expected_signature = hmac.new(
            get_csrf_signing_key(),
            payload_json.encode(),
            hashlib.sha256
        ).hexdigest()[:16]
        
        if not hmac.compare_digest(signature, expected_signature):
            logger.warning("OAuth state signature verification failed - tampering detected")
            return False, None
        
        # Parse payload
        payload = json.loads(payload_json)
        
        # Verify CSRF token matches cookie
        if not hmac.compare_digest(payload.get("csrf", ""), expected_csrf):
            logger.warning("OAuth CSRF token mismatch - possible CSRF attack")
            return False, None
        
        # Verify timestamp is not too old
        state_ts = payload.get("ts", 0)
        now_ts = int(datetime.now(timezone.utc).timestamp())
        if now_ts - state_ts > OAUTH_STATE_MAX_AGE:
            logger.warning(f"OAuth state expired (age: {now_ts - state_ts}s)")
            return False, None
        
        # Extract and validate redirect URL
        redirect_url = payload.get("redirect")
        if redirect_url:
            # Re-validate redirect URL to be safe
            redirect_url = validate_redirect_url(redirect_url)
        
        logger.debug("OAuth state verification successful")
        return True, redirect_url
        
    except Exception as e:
        logger.warning(f"OAuth state verification failed: {e}")
        return False, None
