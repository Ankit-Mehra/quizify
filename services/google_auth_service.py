"""
Google Auth Service - OAuth2 authentication for Google APIs.

This module handles:
- Generating OAuth2 authorization URLs
- Exchanging authorization codes for tokens
- Storing and retrieving refresh tokens (encrypted at rest)
- Refreshing expired access tokens
- Revoking user authorization

The OAuth flow:
1. User requests Google Forms export
2. If not connected, redirect to Google OAuth consent
3. User authorizes Quizify
4. Callback receives auth code, exchanges for tokens
5. Refresh token encrypted and stored in database
6. Access token used for API calls

Security:
- Refresh tokens are encrypted using Fernet (AES-128-CBC) before storage
- Encryption key must be set via GOOGLE_TOKEN_ENCRYPTION_KEY env var
- If key is not set, tokens are stored in plaintext (logs warning)
"""

import os
from datetime import datetime, timezone
from typing import Optional, Tuple

from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from config import config as app_config
from services.logger import app_logger as logger

# Google OAuth2 Configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv(
    "GOOGLE_REDIRECT_URI",
    "http://localhost:8000/api/auth/google/callback"
)

# Scopes required for Google Forms API
GOOGLE_FORMS_SCOPES = [
    "https://www.googleapis.com/auth/forms.body"
]

# Token encryption setup
_fernet = None
_encryption_warned = False


def _get_fernet():
    """
    Get or create Fernet encryption instance.
    
    Returns:
        Fernet instance if encryption key is configured, None otherwise
    """
    global _fernet, _encryption_warned
    
    if _fernet is not None:
        return _fernet
    
    encryption_key = app_config.GOOGLE_TOKEN_ENCRYPTION_KEY
    
    if not encryption_key:
        if not _encryption_warned:
            logger.warning(
                "GOOGLE_TOKEN_ENCRYPTION_KEY not set! "
                "Google OAuth tokens will be stored in PLAINTEXT. "
                "Set this environment variable in production!"
            )
            _encryption_warned = True
        return None
    
    try:
        from cryptography.fernet import Fernet
        _fernet = Fernet(encryption_key.encode())
        logger.info("Google OAuth token encryption initialized")
        return _fernet
    except Exception as e:
        logger.error(f"Failed to initialize token encryption: {e}")
        return None


def _encrypt_token(token: str) -> str:
    """
    Encrypt a refresh token for secure storage.
    
    Args:
        token: Plaintext refresh token
        
    Returns:
        Encrypted token (base64 encoded) or original token if encryption unavailable
    """
    fernet = _get_fernet()
    
    if fernet is None:
        return token  # Store plaintext if encryption not configured
    
    try:
        encrypted = fernet.encrypt(token.encode())
        return encrypted.decode()
    except Exception as e:
        logger.error(f"Failed to encrypt token: {e}")
        return token  # Fallback to plaintext


class TokenDecryptionError(Exception):
    """Exception raised when token decryption fails."""
    
    def __init__(self, message: str = "Failed to decrypt token"):
        self.message = message
        super().__init__(message)


def _decrypt_token(encrypted_token: str) -> str:
    """
    Decrypt a stored refresh token.
    
    Args:
        encrypted_token: Encrypted token from database
        
    Returns:
        Decrypted plaintext token
        
    Raises:
        TokenDecryptionError: If encryption is enabled but decryption fails
            (indicates corrupted, tampered, or wrongly-keyed token)
    """
    fernet = _get_fernet()
    
    if fernet is None:
        # Encryption was never enabled - token is stored as plaintext
        return encrypted_token
    
    try:
        decrypted = fernet.decrypt(encrypted_token.encode())
        return decrypted.decode()
    except Exception as e:
        # SECURITY: If encryption is enabled but decryption fails, the token is:
        # - Corrupted in database
        # - Tampered with
        # - Encrypted with a different key
        # Do NOT return it as plaintext - this could expose sensitive data
        # or cause authentication issues. The caller should clear the token.
        logger.error(
            f"Token decryption failed (possible corruption/tampering): {type(e).__name__}"
        )
        raise TokenDecryptionError(
            "Failed to decrypt token - token may be corrupted or encrypted with different key"
        )

# OAuth2 client config structure
def _get_client_config() -> dict:
    """Build OAuth2 client configuration from environment variables."""
    return {
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [GOOGLE_REDIRECT_URI],
        }
    }


class GoogleAuthError(Exception):
    """Exception raised for Google auth errors."""
    
    def __init__(self, message: str, error_code: str = "google_auth_error"):
        self.message = message
        self.error_code = error_code
        super().__init__(message)


def is_google_auth_configured() -> bool:
    """
    Check if Google OAuth is properly configured.
    
    Returns:
        True if client ID and secret are set
    """
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


def generate_auth_url(state: Optional[str] = None) -> Tuple[str, str]:
    """
    Generate Google OAuth2 authorization URL.
    
    Args:
        state: Optional state parameter for CSRF protection
        
    Returns:
        Tuple of (authorization_url, state)
        
    Raises:
        GoogleAuthError: If OAuth is not configured
    """
    if not is_google_auth_configured():
        raise GoogleAuthError(
            "Google OAuth is not configured. "
            "Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.",
            "oauth_not_configured"
        )
    
    flow = Flow.from_client_config(
        _get_client_config(),
        scopes=GOOGLE_FORMS_SCOPES,
        redirect_uri=GOOGLE_REDIRECT_URI
    )
    
    authorization_url, state = flow.authorization_url(
        access_type="offline",  # Request refresh token
        include_granted_scopes="true",
        prompt="consent",  # Force consent to always get refresh token
        state=state
    )
    
    logger.info("Generated Google OAuth authorization URL")
    return authorization_url, state


def exchange_code_for_tokens(code: str) -> Credentials:
    """
    Exchange authorization code for OAuth2 tokens.
    
    Args:
        code: Authorization code from Google OAuth callback
        
    Returns:
        Google OAuth2 Credentials object
        
    Raises:
        GoogleAuthError: If token exchange fails
    """
    if not is_google_auth_configured():
        raise GoogleAuthError(
            "Google OAuth is not configured",
            "oauth_not_configured"
        )
    
    try:
        flow = Flow.from_client_config(
            _get_client_config(),
            scopes=GOOGLE_FORMS_SCOPES,
            redirect_uri=GOOGLE_REDIRECT_URI
        )
        
        flow.fetch_token(code=code)
        credentials = flow.credentials
        
        logger.info("Successfully exchanged authorization code for tokens")
        return credentials
        
    except Exception as e:
        logger.error(f"Failed to exchange code for tokens: {str(e)}")
        raise GoogleAuthError(
            f"Failed to exchange authorization code: {str(e)}",
            "token_exchange_failed"
        )


def build_credentials_from_refresh_token(refresh_token: str) -> Optional[Credentials]:
    """
    Build Credentials object from a stored refresh token.
    
    Args:
        refresh_token: Stored refresh token
        
    Returns:
        Credentials object with refreshed access token, or None if refresh fails
    """
    if not is_google_auth_configured():
        return None
    
    try:
        credentials = Credentials(
            token=None,  # Will be refreshed
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            scopes=GOOGLE_FORMS_SCOPES
        )
        
        # Refresh the access token
        credentials.refresh(GoogleRequest())
        
        logger.debug("Refreshed Google OAuth access token")
        return credentials
        
    except Exception as e:
        logger.error(f"Failed to refresh Google token: {str(e)}")
        return None


async def store_google_tokens(user_id: str, credentials: Credentials) -> None:
    """
    Store Google OAuth tokens in the database (encrypted).
    
    Args:
        user_id: User ID to store tokens for
        credentials: Google Credentials object
        
    Note:
        Refresh token is encrypted before storage if GOOGLE_TOKEN_ENCRYPTION_KEY is set.
    """
    import asyncio

    from services.db_services.supabase_quiz import get_supabase
    
    supabase = get_supabase()
    
    # Encrypt the refresh token before storage
    encrypted_token = _encrypt_token(credentials.refresh_token)
    
    def update_profile():
        return supabase.table("profiles").update({
            "google_refresh_token": encrypted_token,
            "google_connected_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", user_id).execute()
    
    try:
        await asyncio.to_thread(update_profile)
        logger.info(f"Stored Google OAuth tokens for user {user_id[:8]}...")
    except Exception as e:
        logger.error(f"Failed to store Google tokens: {str(e)}")
        raise GoogleAuthError(
            "Failed to save Google connection",
            "storage_failed"
        )


async def get_google_credentials(user_id: str) -> Optional[Credentials]:
    """
    Get Google OAuth credentials for a user.
    
    Args:
        user_id: User ID to get credentials for
        
    Returns:
        Credentials object if user is connected, None otherwise
        
    Note:
        Decrypts the stored refresh token if GOOGLE_TOKEN_ENCRYPTION_KEY is set.
        If decryption fails (corrupted/tampered token), automatically disconnects
        the user to allow reconnection with fresh tokens.
    """
    import asyncio

    from services.db_services.supabase_quiz import get_supabase
    
    supabase = get_supabase()
    
    def get_profile():
        response = supabase.table("profiles").select(
            "google_refresh_token"
        ).eq("id", user_id).single().execute()
        return response.data
    
    try:
        profile = await asyncio.to_thread(get_profile)
        
        if not profile or not profile.get("google_refresh_token"):
            return None
        
        # Decrypt the stored refresh token
        encrypted_token = profile["google_refresh_token"]
        try:
            refresh_token = _decrypt_token(encrypted_token)
        except TokenDecryptionError as decrypt_error:
            # SECURITY: Token is corrupted or encrypted with different key
            # Auto-disconnect user so they can reconnect with fresh tokens
            logger.warning(
                f"Corrupted token for user {user_id[:8]}..., auto-disconnecting: {decrypt_error}"
            )
            await disconnect_google(user_id)
            return None
        
        credentials = build_credentials_from_refresh_token(refresh_token)
        
        return credentials
        
    except Exception as e:
        logger.error(f"Failed to get Google credentials: {str(e)}")
        return None


async def disconnect_google(user_id: str) -> bool:
    """
    Disconnect Google account by removing stored tokens.
    
    Args:
        user_id: User ID to disconnect
        
    Returns:
        True if successful
    """
    import asyncio

    from services.db_services.supabase_quiz import get_supabase
    
    supabase = get_supabase()
    
    def clear_tokens():
        return supabase.table("profiles").update({
            "google_refresh_token": None,
            "google_connected_at": None
        }).eq("id", user_id).execute()
    
    try:
        await asyncio.to_thread(clear_tokens)
        logger.info(f"Disconnected Google account for user {user_id[:8]}...")
        return True
    except Exception as e:
        logger.error(f"Failed to disconnect Google: {str(e)}")
        return False


async def is_user_connected(user_id: str) -> bool:
    """
    Check if a user has connected their Google account with valid credentials.
    
    If stored credentials exist but are invalid (expired and refresh fails),
    this function automatically disconnects the user and returns False.
    This prevents stale tokens from blocking reconnection.
    
    Args:
        user_id: User ID to check
        
    Returns:
        True if user has valid Google connection, False otherwise
    """
    import asyncio

    from services.db_services.supabase_quiz import get_supabase
    
    supabase = get_supabase()
    
    # First check if there's a stored token at all
    def get_profile():
        response = supabase.table("profiles").select(
            "google_refresh_token"
        ).eq("id", user_id).single().execute()
        return response.data
    
    try:
        profile = await asyncio.to_thread(get_profile)
        
        if not profile or not profile.get("google_refresh_token"):
            return False
        
        # Token exists, try to get valid credentials
        credentials = await get_google_credentials(user_id)
        
        if credentials is not None and credentials.valid:
            return True
        
        # Credentials exist but are invalid (refresh failed)
        # Auto-disconnect to allow user to reconnect cleanly
        logger.warning(
            f"User {user_id[:8]}... has invalid Google credentials, auto-disconnecting"
        )
        await disconnect_google(user_id)
        return False
        
    except Exception as e:
        logger.error(f"Error checking Google connection: {str(e)}")
        return False

