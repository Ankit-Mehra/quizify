from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import config as app_config
from dependencies.auth_dependencies import get_current_user_id, get_current_user_token
from schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    SignupRequest,
    UpdateEmailRequest,
)
from services.db_services.supabase_quiz import get_user_tier_info_cached
from services.logger import app_logger as logger
from services.redis.sessions import SessionInfo, SessionService, TooManySessionsError
from services.oauth_utils import (
    OAUTH_STATE_COOKIE_NAME,
    OAUTH_STATE_MAX_AGE,
    is_new_user as _is_new_user,
    generate_oauth_state as _generate_oauth_state,
    verify_oauth_state as _verify_oauth_state,
)

security = HTTPBearer(auto_error=False)

# Lazy load Supabase client to avoid initialization issues in tests
def get_supabase():
    """Get Supabase client (lazy loaded)"""
    return app_config.get_supabase_client()

if app_config.is_testing():
    logger.info("Auth handlers initialized in TEST mode")
else:
    logger.info("Auth handlers initialized with Supabase client")

ACCESS_TOKEN_EXPIRE = 3600  # 1 hour
REFRESH_TOKEN_EXPIRE = 60 * 60 * 24 * 30  # 30 days


def _get_cookie_settings() -> dict:
    """
    Get cookie settings based on environment.
    
    Returns secure cookie settings for production, consistent settings for testing.
    Note: secure=True always (matches existing login() behavior) - tests run with HTTPS mocking.
    """
    if app_config.is_testing():
        # Match existing login() behavior: secure=True, no domain for testing
        return {
            "httponly": True,
            "secure": True,  # Consistent with login() function
            "samesite": "lax",
            "max_age": ACCESS_TOKEN_EXPIRE,
            "path": "/"
        }
    
    return {
        "httponly": True,
        "secure": True,
        "samesite": "lax",
        "domain": app_config.COOKIE_DOMAIN,
        "max_age": ACCESS_TOKEN_EXPIRE,
        "path": "/"
    }


def _short_user_id(user_id: Optional[str]) -> str:
    """Return obfuscated user identifier for logging."""
    if not user_id:
        return "unknown"
    return f"{user_id[:8]}..."


def _mask_email(email: Optional[str]) -> str:
    """
    Mask email for logging to prevent PII exposure.
    
    Examples:
        "john.doe@example.com" -> "j***e@e***.com"
        "ab@cd.org" -> "a*b@c*.org"
    """
    if not email or "@" not in email:
        return "[no-email]"
    
    local, domain = email.split("@", 1)
    
    # Mask local part: show first and last char if long enough
    if len(local) <= 2:
        masked_local = local[0] + "*"
    else:
        masked_local = local[0] + "***" + local[-1]
    
    # Mask domain: show first char and TLD
    domain_parts = domain.rsplit(".", 1)
    if len(domain_parts) == 2:
        domain_name, tld = domain_parts
        if len(domain_name) <= 2:
            masked_domain = domain_name[0] + "*." + tld
        else:
            masked_domain = domain_name[0] + "***." + tld
    else:
        masked_domain = domain[0] + "***"
    
    return f"{masked_local}@{masked_domain}"


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """
    Set authentication cookies on a response object.
    
    This helper ensures consistent cookie settings across all auth endpoints:
    - login, google_signin_callback, google_signin_token
    
    Args:
        response: FastAPI Response or RedirectResponse object
        access_token: JWT access token from Supabase
        refresh_token: Refresh token from Supabase
    """
    cookie_settings = _get_cookie_settings()
    
    response.set_cookie(
        key="access_token",
        value=access_token,
        **cookie_settings
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=REFRESH_TOKEN_EXPIRE,
        httponly=True,
        secure=cookie_settings["secure"],
        samesite=cookie_settings["samesite"],
        domain=cookie_settings.get("domain"),
        path="/"
    )


def get_redis_client(request: Request) -> Optional[Any]:
    """
    Get Redis client from request app state.
    
    Returns Redis client stored in app.state during startup, or None if unavailable.
    This approach is consistent with auth_dependencies and ensures we use the same
    Redis instance initialized during app startup.
    """
    return getattr(request.app.state, "redis", None)


def detect_device_type(user_agent: Optional[str]) -> str:
    """
    Detect device type from user agent string.
    
    Returns:
        "mobile" for mobile devices
        "browser" for desktop/laptop browsers
        "api" for API clients or unknown
    """
    if not user_agent:
        return "api"
    
    user_agent_lower = user_agent.lower()
    
    # Check for mobile devices
    mobile_keywords = ["mobile", "android", "iphone", "ipad", "ipod", "windows phone", "blackberry"]
    if any(keyword in user_agent_lower for keyword in mobile_keywords):
        return "mobile"
    
    # Check for known browsers (desktop)
    browser_keywords = ["mozilla", "chrome", "safari", "firefox", "edge", "opera"]
    if any(keyword in user_agent_lower for keyword in browser_keywords):
        return "browser"
    
    # Default to API for unknown user agents (curl, postman, etc.)
    return "api"

# Remove template rendering functions
async def signup(request: SignupRequest):
    try:
        supabase = get_supabase()
        logger.info(f"Attempting to sign up user with email: {_mask_email(request.email)}")

        # Pydantic already validates min_length=8, but double-check for defense-in-depth
        # Don't strip() - whitespace is valid in passwords
        raw_password = request.password or ""
        if len(raw_password) < 8:
            logger.warning("Signup rejected for %s due to weak password", _mask_email(request.email))
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters long")
        
        # Sign up user - name goes to raw_user_meta_data
        response = supabase.auth.sign_up({
            "email": request.email,
            "password": raw_password,
            "options": {
                "data": {
                    "name": request.name
                }
            }
        })
        logger.info(f"User created successfully with ID: {response.user.id if response.user else None}")
        return JSONResponse(
            status_code=201,
            content={"message": "User created successfully. Please check your email for verification.", "user_id": response.user.id if response.user else None}
        )
    except Exception as e:
        logger.error(f"Error during signup for {_mask_email(request.email)}: {str(e)}")
        error_message = str(e)
        
        # Handle specific Supabase errors with appropriate status codes
        if "already registered" in error_message.lower() or "already exists" in error_message.lower():
            raise HTTPException(status_code=400, detail="Email already registered")
        elif "invalid" in error_message.lower() and "email" in error_message.lower():
            raise HTTPException(status_code=400, detail=error_message)
        elif "password" in error_message.lower() and ("weak" in error_message.lower() or "at least" in error_message.lower()):
            raise HTTPException(status_code=400, detail=error_message)
        elif "unable to validate" in error_message.lower():
            raise HTTPException(status_code=400, detail=error_message)
        else:
            # Generic server error for unexpected cases
            raise HTTPException(status_code=500, detail=str(e))


async def login(request_body: LoginRequest, response: Response, request: Request):
    try:
        supabase = get_supabase()
        logger.info(f"Login attempt for user: {_mask_email(request_body.email)}")
        result = supabase.auth.sign_in_with_password({
            "email": request_body.email,
            "password": request_body.password
        })
        
        session = result.session

        if session is None:
            logger.warning(f"Login failed: No session returned for {_mask_email(request_body.email)}")
            raise HTTPException(status_code=401, detail="Invalid credentials")

        access_token = session.access_token
        refresh_token = session.refresh_token
        user_id = result.user.id if result.user and getattr(result.user, "id", None) else None

        logger.info(f"User logged in: {_short_user_id(user_id)}")

        # Create Redis session for multi-device tracking
        # SECURITY: Redis is REQUIRED for session management. Fail hard if unavailable.
        redis_client = get_redis_client(request)
        if not redis_client:
            logger.error(
                "Redis unavailable during login for user %s - failing request",
                _short_user_id(user_id)
            )
            raise HTTPException(
                status_code=503,
                detail="Session management service temporarily unavailable. Please try again."
            )
        
        try:
            session_service = SessionService(redis_client)
            user_agent = request.headers.get("user-agent")
            device_type = detect_device_type(user_agent)
            client_session_token = await session_service.create_session(
                user_id=user_id,
                device_type=device_type,
                ip_address=request.client.host if request.client else None,
                user_agent=user_agent,
                refresh_token=refresh_token  # Enable cookie-based lookup
            )
            logger.info(
                "Redis session created for user %s (device: %s, client_token: %s)",
                _short_user_id(user_id),
                device_type,
                client_session_token[:16] + "..." if len(client_session_token) > 16 else client_session_token
            )
        except TooManySessionsError as e:
            # Hard fail for session limits - this is a security control
            # User must explicitly manage their sessions (logout or revoke)
            logger.warning(f"Too many sessions for user {_short_user_id(user_id)}: {e}")
            raise HTTPException(
                status_code=429,
                detail="Too many active sessions. Please logout from other devices or revoke old sessions."
            )
        except Exception as redis_error:
            # Hard fail for any Redis errors - prevents unusable token loop
            # If session creation fails, subsequent requests will fail with 401
            logger.error(
                f"Failed to create Redis session for user {_short_user_id(user_id)}: {redis_error}"
            )
            raise HTTPException(
                status_code=503,
                detail="Session management service temporarily unavailable. Please try again."
            )
        
        # Set access token cookie
        # Domain allows cookie to be shared across all subdomains (www, api, etc.)
        # Without Domain attribute, cookie would be host-only (locked to api.quizify.ca)
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=True,
            samesite="lax",
            domain=app_config.COOKIE_DOMAIN if not app_config.is_testing() else None,
            max_age=ACCESS_TOKEN_EXPIRE
        )
        # Set refresh token cookie
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=True,
            samesite="lax",
            domain=app_config.COOKIE_DOMAIN if not app_config.is_testing() else None,
            max_age=REFRESH_TOKEN_EXPIRE
        )

        # Prepare response - only include access_token in test mode for testing convenience
        response_data = {
            "message": "Successfully logged in",
            "user": {
                "id": user_id,
                "email": result.user.email if result.user else None
            },
            "client_session_token": client_session_token  # HMAC-signed token for UI identification only (XSS-safe)
        }
        
        # SECURITY: Only expose tokens in response body during testing or development
        # In production, tokens are only available via HttpOnly cookie
        if app_config.is_testing() or app_config.is_development():
            response_data["access_token"] = access_token
            response_data["refresh_token"] = refresh_token
        
        return response_data

    except HTTPException:
        raise
    except Exception as e:
        error_message = str(e).lower()
        logger.warning(f"Failed login for {_mask_email(request_body.email)}: {e}")
        
        # Check for Supabase rate limiting
        # Use specific patterns to avoid false positives (e.g., "429" could match IP "192.168.4.29")
        is_rate_limited = (
            "rate limit" in error_message or 
            "too many requests" in error_message or
            "status code 429" in error_message or
            "status: 429" in error_message or
            "http 429" in error_message
        )
        if is_rate_limited:
            logger.warning(f"Supabase rate limit hit for {_mask_email(request_body.email)}")
            raise HTTPException(
                status_code=429,
                detail="Too many login attempts. Please wait a few minutes before trying again."
            )
        
        # Provide specific error messages for common issues
        if "email not confirmed" in error_message or "email confirmation" in error_message:
            raise HTTPException(
                status_code=403, 
                detail="Please verify your email address before logging in. Check your inbox for the confirmation email."
            )
        elif "invalid login credentials" in error_message or "invalid credentials" in error_message:
            raise HTTPException(
                status_code=401, 
                detail="Invalid email or password"
            )
        elif "email or phone not confirmed" in error_message:
            raise HTTPException(
                status_code=403, 
                detail="Please verify your email address before logging in. Check your inbox for the confirmation email."
            )
        else:
            # Generic error for other cases
            raise HTTPException(status_code=401, detail="Invalid credentials")


async def refresh_session(request: Request, response: Response):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Missing refresh token")

    try:
        supabase = get_supabase()
        session = supabase.auth.refresh_session(refresh_token)
        if session.session is None or not hasattr(session.session, "access_token"):
            raise HTTPException(status_code=401, detail="Invalid refresh token or session expired")
        new_access_token = session.session.access_token

        response.set_cookie(
            key="access_token",
            value=new_access_token,
            httponly=True,
            secure=True,
            samesite="lax",
            domain=app_config.COOKIE_DOMAIN if not app_config.is_testing() else None,
            max_age=ACCESS_TOKEN_EXPIRE
        )
        return {"message": "Session refreshed"}
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token")


async def logout(
    request: Request,
    response: Response,
    user_id: str = Depends(get_current_user_id),
    session_id: Optional[str] = Query(None, alias="session_id")
):
    """
    Logout current device.
    
    Deletes the Redis session and clears auth cookies.
    Session lookup priority:
    1. Query parameter: /auth/logout?session_id=sess_xxx
    2. request.state.session_id (set during auth validation)
    3. Lookup via refresh_token cookie (fallback for stale sessions)
    """
    try:
        logger.info(f"User {_short_user_id(user_id)} logout requested")

        # Priority 1: Query parameter
        # Priority 2: request.state (set during auth validation)
        if not session_id:
            session_id = getattr(request.state, "session_id", None)

        redis_client = get_redis_client(request)
        session_service = None
        
        # Priority 3: Lookup via refresh_token (header in dev mode, cookie in production)
        # This is critical for proper cleanup when frontend doesn't pass session_id
        if not session_id and redis_client:
            # Match the same logic used in auth_dependencies.py
            if app_config.is_development():
                refresh_token_header = request.headers.get("X-Refresh-Token")
                refresh_token = refresh_token_header or request.cookies.get("refresh_token")
            else:
                refresh_token = request.cookies.get("refresh_token")
            
            if refresh_token:
                try:
                    session_service = SessionService(redis_client)
                    found_session_id = await session_service.find_session_by_refresh_token(refresh_token)
                    if found_session_id:
                        # SECURITY: Verify session belongs to authenticated user before allowing logout
                        session_info = await session_service.validate_session(found_session_id)
                        if session_info and session_info.user_id == user_id:
                            session_id = found_session_id
                            logger.debug(f"Session found via refresh_token for user {_short_user_id(user_id)}")
                        else:
                            if session_info:
                                logger.warning(
                                    f"Session {found_session_id[:12]}... does not belong to user {_short_user_id(user_id)} - ignoring"
                                )
                            else:
                                logger.debug(f"Session {found_session_id[:12]}... not found or expired - ignoring")
                except Exception as lookup_error:
                    logger.warning(f"Failed to lookup session via refresh_token: {lookup_error}")

        # Delete Redis session if session_id was found
        if session_id:
            try:
                if redis_client:
                    if not session_service:
                        session_service = SessionService(redis_client)
                    success = await session_service.logout(session_id)
                    if success:
                        logger.info(f"Redis session deleted for user {_short_user_id(user_id)}")
                    else:
                        logger.warning(f"Redis session not found: {session_id[:12]}...")
            except Exception as redis_error:
                # Don't fail logout if Redis deletion fails (fallback mode)
                logger.warning(f"Failed to delete Redis session (fallback mode): {redis_error}")
        else:
            logger.warning(f"No session_id found for user {_short_user_id(user_id)} during logout - session may remain in Redis")
        
        # Must match domain used when setting cookies
        domain = app_config.COOKIE_DOMAIN if not app_config.is_testing() else None
        response.delete_cookie(key="access_token", path="/", domain=domain, httponly=True)
        response.delete_cookie(key="refresh_token", path="/", domain=domain, httponly=True)
        logger.info(f"User {_short_user_id(user_id)} logged out successfully")
        return {"message": "Successfully logged out"}
    except Exception as e:
        logger.error(f"Error during logout: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def change_password(request: ChangePasswordRequest,
                           user_id: str = Depends(get_current_user_id),
                           user_token: str = Depends(get_current_user_token)):
    """
    Change password for authenticated user.
    
    SECURITY: Requires current password verification to prevent unauthorized
    password changes with stolen tokens.
    
    User is identified by JWT token (user_id), not by email in request body.
    """
    try:
        logger.info(f"Password change requested for user ID: {_short_user_id(user_id)}")
        
        # Use authenticated client for user operations
        supabase = app_config.get_authenticated_supabase_client(user_token)
        
        # SECURITY: Get user's email for current password verification
        # With authenticated client, we can get the user's own details
        user_response = supabase.auth.get_user()
        if not user_response or not user_response.user:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_email = user_response.user.email
        if not user_email:
            raise HTTPException(status_code=400, detail="User has no email configured")
        
        # SECURITY: Verify current password by attempting sign-in
        # We use a fresh client for this to avoid messing with the current session
        auth_client = get_supabase()
        try:
            auth_client.auth.sign_in_with_password({
                "email": user_email,
                "password": request.current_password
            })
        except Exception as auth_error:
            error_msg = str(auth_error).lower()
            if "invalid" in error_msg or "credentials" in error_msg or "password" in error_msg:
                logger.warning(f"Password change failed: incorrect current password for user {_short_user_id(user_id)}")
                raise HTTPException(status_code=401, detail="Current password is incorrect")
            # Re-raise unexpected auth errors
            raise
        
        # Current password verified, now update to new password using authenticated client
        supabase.auth.update_user({"password": request.new_password})
        logger.info(f"Password updated successfully for user ID: {_short_user_id(user_id)}")
        return {"message": "Password updated successfully"}
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Error during password change for user {_short_user_id(user_id)}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

async def delete_account(user_id: str = Depends(get_current_user_id)):
    try:
        supabase = get_supabase()
        logger.info(f"Account deletion requested for user ID: {user_id}")
        
        # Use Supabase Auth API to delete the user
        supabase.auth.admin.delete_user(user_id)
        
        logger.info(f"Account deleted successfully for user ID: {user_id}")
        return {"message": "Account deleted successfully"}
    except Exception as e:
        logger.error(f"Error during account deletion: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

async def update_email(request: UpdateEmailRequest,
                       credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Update user email with confirmation.
    
    Supabase Secure Email Change Flow:
    1. Sends confirmation email to the NEW email address
    2. User clicks link in NEW email to confirm
    3. Sends confirmation email to the CURRENT email address  
    4. User clicks link in CURRENT email to confirm
    5. Email is changed after BOTH confirmations
    
    This double confirmation prevents account takeover attacks.
    """
    try:
        # Get the user's access token from the credentials
        token = credentials.credentials if credentials else None
        
        if not token:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        new_email = request.new_email
        # SECURITY: Log masked email to prevent PII exposure
        logger.info(f"Email update requested to: {_mask_email(new_email)}")
        
        # Create authenticated Supabase client with user's token
        # This ensures the update is made on behalf of the authenticated user
        supabase = app_config.get_authenticated_supabase_client(token)
        
        # Use the Python SDK to update email - triggers Secure Email Change flow
        response = supabase.auth.update_user({"email": new_email})
        
        current_email = response.user.email if response.user else None
        logger.info("Email change initiated. Confirmation emails being sent.")
        # SECURITY: Log masked emails to prevent PII exposure
        logger.info(f"Update response: email={_mask_email(current_email)}, new_email={_mask_email(response.user.new_email if response.user else None)}")
        
        return {
            "message": f"Email change initiated. Please check BOTH email addresses: (1) Confirm the change from your NEW email ({new_email}) (2) Then confirm from your CURRENT email ({current_email}). Both confirmations are required to complete the email change.",
            "current_email": current_email,
            "new_email": new_email,
            "note": "Secure Email Change is enabled. You must verify both email addresses.",
            "steps": [
                f"Step 1: Check {new_email} and click the confirmation link",
                f"Step 2: Check {current_email} and click the confirmation link",
                "Step 3: Email will be changed after both confirmations"
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during email update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

async def get_user_info(
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token)
):
    """
    Get authenticated user's profile information including tier and quota status.
    
    Uses Redis caching for 50x performance improvement (5 min TTL).
    
    Returns:
        User profile with tier, role, quota, and display name information
    """
    try:
        logger.info(f"Fetching user info for user ID: {user_id}")
        # Use cached version for 50x performance improvement (200ms → 4ms)
        tier_info = await get_user_tier_info_cached(user_id)
        
        return {
            "user_id": str(tier_info["id"]),
            "email": tier_info["email"],
            "display_name": tier_info.get("display_name"),
            "avatar_url": tier_info.get("avatar_url"),  # Avatar from OAuth providers
            "account_tier": tier_info["account_tier"],
            "role": tier_info.get("role", "user"),
            "current_quiz_count": tier_info["current_quiz_count"],  # Quizzes created
            "quizzes_attempted": tier_info.get("quizzes_attempted", 0),  # Quizzes attempted (NEW)
            "quota_limit": tier_info["quota_limit"],
            "quota_exceeded": tier_info["quota_exceeded"],
            "created_at": tier_info.get("created_at"),
            
            # New credit fields (Epic 6.3)
            "available_credits": tier_info.get("available_credits"),
            "monthly_credits": tier_info.get("monthly_credits"),
            "purchased_credits": tier_info.get("purchased_credits"),
            "plan": tier_info.get("billing_plan"),
            "period_end": tier_info.get("period_end")
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching user info: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

async def confirm_email(
    token: str = Query(..., description="Email confirmation token from Supabase"),
    type: str = Query(default="signup", description="Confirmation type: signup, email_change, recovery, etc."),
):
    """
    Handle email confirmation from Supabase.
    This endpoint is called when user clicks the link in their confirmation email.
    
    Flow:
    1. User clicks link in email → redirects to this endpoint with token
    2. Backend verifies token with Supabase
    3. Redirects user to frontend with success/error message
    """
    try:
        supabase = get_supabase()
        logger.info(f"Email confirmation attempt - type: {type}")
        
        # Verify the token with Supabase
        try:
            response = supabase.auth.verify_otp({
                "token_hash": token,
                "type": type  # 'signup', 'email_change', 'recovery', etc.
            })
        except Exception as verify_error:
            logger.warning(f"Token verification failed: {str(verify_error)}")
            return RedirectResponse(
                url=f"{app_config.FRONTEND_URL}/login?error=invalid_token&message=Invalid+or+expired+confirmation+link",
                status_code=302
            )
        
        if not response.user:
            logger.warning("Email confirmation failed - no user returned")
            return RedirectResponse(
                url=f"{app_config.FRONTEND_URL}/login?error=invalid_token&message=Invalid+or+expired+confirmation+link",
                status_code=302
            )
        
        user_id = response.user.id
        user_email = response.user.email
        # SECURITY: Use masked email and short user ID to prevent PII exposure
        logger.info(f"Email confirmed successfully for user: {_short_user_id(user_id)} ({_mask_email(user_email)})")
        
        # Handle different confirmation types
        if type == "signup":
            # User just confirmed their signup email
            return RedirectResponse(
                url=f"{app_config.FRONTEND_URL}/login?confirmed=true&message=Email+verified+successfully!+You+can+now+log+in.",
                status_code=302
            )
        elif type == "email_change":
            # User confirmed email change
            return RedirectResponse(
                url=f"{app_config.FRONTEND_URL}/dashboard?email_changed=true&message=Email+address+updated+successfully",
                status_code=302
            )
        elif type == "recovery":
            # Password reset confirmation - token verified, now create session for password update
            # The verified response contains session tokens we can pass to frontend
            if response.session:
                access_token = response.session.access_token
                refresh_token = response.session.refresh_token
                # Redirect to password reset page with both tokens
                # Frontend will use these when calling /reset-password
                return RedirectResponse(
                    url=f"{app_config.FRONTEND_URL}/reset-password?access_token={access_token}&refresh_token={refresh_token}&message=Please+enter+your+new+password",
                    status_code=302
                )
            else:
                logger.error("Recovery token verified but no session returned")
                return RedirectResponse(
                    url=f"{app_config.FRONTEND_URL}/login?error=recovery_failed&message=Password+reset+failed.+Please+request+a+new+link.",
                    status_code=302
                )
        else:
            # Default redirect for unknown types
            logger.warning(f"Unknown confirmation type: {type}")
            return RedirectResponse(
                url=f"{app_config.FRONTEND_URL}/dashboard?confirmed=true",
                status_code=302
            )
            
    except Exception as e:
        logger.error(f"Error during email confirmation: {str(e)}", exc_info=True)
        return RedirectResponse(
            url=f"{app_config.FRONTEND_URL}/login?error=confirmation_failed&message=Confirmation+failed.+Please+try+again.",
            status_code=302
        )


async def forgot_password(request: ForgotPasswordRequest):
    """
    Trigger password reset email.
    
    Sends a password recovery email to the user with a reset link.
    For security, always returns success even if email doesn't exist
    (prevents email enumeration attacks).
    
    Flow:
    1. User enters email on forgot password page
    2. Backend calls Supabase to send recovery email
    3. Supabase sends email with link to /api/auth/confirm?token=xxx&type=recovery
    4. User clicks link → backend verifies → redirects to frontend reset-password page
    5. Frontend calls /api/auth/reset-password with new password
    """
    try:
        email = request.email
        logger.info(f"Password reset requested for email (first 3 chars): {email[:3]}***")
        
        supabase = get_supabase()
        
        # Request password reset from Supabase
        # This sends an email with recovery link to the user
        try:
            supabase.auth.reset_password_email(
                email=email,
                options={
                    "redirect_to": f"{app_config.FRONTEND_URL}/reset-password"  # Not used, we handle in /confirm
                }
            )
            logger.info("Password reset email sent successfully")
        except Exception as supabase_error:
            # Log error but don't reveal to user (security)
            logger.warning(f"Supabase password reset error: {str(supabase_error)}")
        
        # ALWAYS return success to prevent email enumeration
        # Even if email doesn't exist, we say we sent it
        return {
            "message": "If an account exists with that email, we've sent password reset instructions.",
            "note": "Check your email inbox (and spam folder). The link expires in 1 hour."
        }
        
    except Exception as e:
        logger.error(f"Error during forgot password: {str(e)}", exc_info=True)
        # Still return success for security
        return {
            "message": "If an account exists with that email, we've sent password reset instructions.",
            "note": "Check your email inbox (and spam folder). The link expires in 1 hour."
        }


async def reset_password(request: ResetPasswordRequest):
    """
    Reset user password with recovery tokens.
    
    This endpoint is called by the frontend after user:
    1. Clicks reset link in email
    2. Gets redirected to /reset-password page (via /confirm handler)
    3. Enters new password in form
    4. Frontend submits new password + tokens to this endpoint
    
    The tokens are provided in the URL by the /confirm handler after
    validating the recovery token. These tokens give temporary access to update password.
    """
    try:
        access_token = request.token
        refresh_token = request.refresh_token
        new_password = request.new_password
        
        logger.info("Password reset attempt with recovery tokens")
        
        supabase = get_supabase()
        
        # Update password using the temporary recovery session tokens
        try:
            # Set the session with both access and refresh tokens from recovery
            # This authenticates the user temporarily for password update
            if refresh_token:
                supabase.auth.set_session(access_token, refresh_token)
            else:
                # Fallback: if only access_token provided (shouldn't happen with new flow)
                logger.warning("Only access_token provided, no refresh_token. This may cause issues.")
                # Use authenticated client approach instead
                supabase = app_config.get_authenticated_supabase_client(access_token)
            
            # Now update the password - user is authenticated via the recovery session
            response = supabase.auth.update_user({"password": new_password})
            
            if not response.user:
                logger.warning("Password reset failed - invalid or expired token")
                raise HTTPException(
                    status_code=401,
                    detail="Invalid or expired recovery token. Please request a new password reset link."
                )
            
            logger.info(f"Password reset successful for user: {response.user.id}")
            
            return {
                "message": "Password updated successfully! You can now log in with your new password.",
                "success": True
            }
            
        except HTTPException:
            raise
        except Exception as update_error:
            logger.error(f"Supabase password update error: {str(update_error)}", exc_info=True)
            raise HTTPException(
                status_code=400,
                detail="Failed to update password. The reset link may have expired. Please request a new one."
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during password reset: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while resetting your password. Please try again."
        )


async def resend_verification_email(request: ResendVerificationRequest):
    """
    Resend email verification link to user.
    
    This is useful when:
    - User didn't receive the original signup confirmation email
    - Email link expired (24 hours)
    - User accidentally deleted the email
    
    For security, always returns success even if:
    - Email doesn't exist (prevents email enumeration)
    - Email is already verified (no harm in sending again)
    
    Flow:
    1. User enters email on "resend verification" page
    2. Backend calls Supabase to resend verification email
    3. Supabase sends email with link to /api/auth/confirm?token=xxx&type=signup
    4. Always returns success message
    """
    try:
        email = request.email
        logger.info(f"Verification email resend requested for email (first 3 chars): {email[:3]}***")
        
        supabase = get_supabase()
        
        try:
            # Resend the confirmation email
            # Supabase Python SDK v2+ takes a single dictionary parameter
            supabase.auth.resend({
                "type": "signup",  # Type: 'signup' or 'email_change'
                "email": email,
                "options": {
                    "email_redirect_to": f"{app_config.FRONTEND_URL}/login"  # Not used, we handle in /confirm
                }
            })
            logger.info("Verification email resent successfully")
            
        except Exception as supabase_error:
            # Log error but don't reveal to user (security)
            logger.warning(f"Supabase resend error: {str(supabase_error)}")
        
        # ALWAYS return success to prevent email enumeration
        # Even if:
        # - Email doesn't exist
        # - Email is already verified  
        # - Rate limit exceeded
        return {
            "message": "If your email is registered and unverified, we've sent a new verification link.",
            "note": "Check your email inbox (and spam folder). The link expires in 24 hours.",
            "email": email
        }
        
    except Exception as e:
        logger.error(f"Error during resend verification: {str(e)}", exc_info=True)
        # Still return success for security
        return {
            "message": "If your email is registered and unverified, we've sent a new verification link.",
            "note": "Check your email inbox (and spam folder). The link expires in 24 hours."
        }


# ============================================================================
# SESSION MANAGEMENT ENDPOINTS (Epic 4 - Task 4.3 & 4.4)
# ============================================================================

async def logout_all_devices(
    request: Request,
    response: Response,
    user_id: str = Depends(get_current_user_id)
):
    """
    Logout all devices for current user.
    
    Useful for security actions like:
    - Password change
    - Suspicious activity detected
    - User wants to revoke all sessions
    
    This will:
    1. Delete all Redis sessions for the user
    2. Clear cookies for current device
    3. Force re-login on all devices
    """
    try:
        logger.info(f"Logout all devices requested for user {_short_user_id(user_id)}")
        
        # Delete all Redis sessions
        count = 0
        try:
            redis_client = get_redis_client(request)
            if redis_client:
                session_service = SessionService(redis_client)
                count = await session_service.logout_all_devices(user_id)
                logger.info(f"Deleted {count} Redis sessions for user {_short_user_id(user_id)}")
        except Exception as redis_error:
            # Don't fail if Redis deletion fails (fallback mode)
            logger.warning(f"Failed to delete Redis sessions (fallback mode): {redis_error}")
        
        # Clear cookies for current device
        domain = app_config.COOKIE_DOMAIN if not app_config.is_testing() else None
        response.delete_cookie(key="access_token", path="/", domain=domain, httponly=True)
        response.delete_cookie(key="refresh_token", path="/", domain=domain, httponly=True)
        
        return {
            "message": f"Successfully logged out from {count} device(s)",
            "devices_logged_out": count
        }
        
    except Exception as e:
        logger.error(f"Error during logout all devices: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def get_active_sessions(
    request: Request,
    user_id: str = Depends(get_current_user_id)
) -> List[Dict[str, Any]]:
    """
    Get list of active sessions for current user across all devices.
    
    Returns session metadata:
    - session_id: Unique identifier
    - device_type: browser, mobile, api
    - created_at: When session was created
    - last_active: Last activity timestamp
    - ip_address: Hashed IP for privacy
    - user_agent: Truncated user agent string
    
    Frontend can display this in "Active Sessions" page for security management.
    """
    try:
        logger.info(f"Fetching active sessions for user {_short_user_id(user_id)}")
        
        # Get current session ID from request state (set by auth middleware)
        current_session_id = getattr(request.state, "session_id", None)
        
        # Get sessions from Redis
        sessions: List[SessionInfo] = []
        try:
            redis_client = get_redis_client(request)
            if redis_client:
                session_service = SessionService(redis_client)
                sessions = await session_service.list_sessions(user_id)
                logger.info(f"Found {len(sessions)} active sessions for user {_short_user_id(user_id)}")
        except Exception as redis_error:
            logger.warning(f"Failed to fetch Redis sessions (fallback mode): {redis_error}")
            # Return empty list in fallback mode
            return []
        
        # Convert to dict for API response
        return [
            {
                "client_session_token": session.client_session_token,  # HMAC-signed token for UI identification
                "device_type": session.device_type,
                "created_at": session.created_at.isoformat(),
                "last_active": session.last_active.isoformat(),
                "ip_address": session.ip_address,  # Already hashed
                "user_agent": session.user_agent,  # Already truncated
                "is_expired": session.is_expired,
                "is_current": session.session_id == current_session_id  # Server-computed (no client comparison needed)
            }
            for session in sessions
        ]
        
    except Exception as e:
        logger.error(f"Error fetching active sessions: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def revoke_session(
    session_id_to_revoke: str,
    request: Request,
    user_id: str = Depends(get_current_user_id)
):
    """
    Revoke a specific session by ID or client token.
    
    Accepts either:
    - Real session_id (starts with sess_)
    - Client session token (starts with cst_sess_) - will be mapped to real session_id
    
    Security check: Verifies the session belongs to the authenticated user
    before revoking it. Prevents users from revoking other users' sessions.
    
    Use case: User sees suspicious device in "Active Sessions" and wants to logout that device.
    """
    try:
        logger.info(
            "Session revoke requested: %s by user %s",
            f"{session_id_to_revoke[:12]}...",
            _short_user_id(user_id),
        )
        
        redis_client = get_redis_client(request)
        if not redis_client:
            raise HTTPException(
                status_code=503,
                detail="Session management unavailable (Redis not connected)"
            )
        
        session_service = SessionService(redis_client)
        
        # If it's a client token (starts with cst_sess_), map it to real session_id
        actual_session_id = session_id_to_revoke
        if session_id_to_revoke.startswith("cst_sess_"):
            logger.debug("Client token provided, mapping to real session_id")
            actual_session_id = await session_service.find_session_by_client_token(
                session_id_to_revoke, user_id
            )
            if not actual_session_id:
                raise HTTPException(
                    status_code=404,
                    detail="Session not found for provided client token"
                )
            logger.debug(f"Mapped to session: {actual_session_id[:12]}...")
        
        # SECURITY: Verify session belongs to user
        session_info = await session_service.validate_session(actual_session_id)
        if not session_info:
            raise HTTPException(
                status_code=404,
                detail="Session not found or already expired"
            )
        
        if session_info.user_id != user_id:
            logger.warning(
                "User %s attempted to revoke session belonging to %s",
                _short_user_id(user_id),
                _short_user_id(session_info.user_id),
            )
            raise HTTPException(
                status_code=403,
                detail="You can only revoke your own sessions"
            )
        
        # Revoke the session
        success = await session_service.logout(actual_session_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Session not found")
        
        logger.info(f"Session {actual_session_id[:12]}... revoked successfully")
        return {
            "message": "Session revoked successfully",
            "session_id": actual_session_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error revoking session: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# GOOGLE OAUTH ENDPOINTS (Epic QUIZ-002 - Google Forms Export)
# ============================================================================

async def google_connect(
    user_id: str = Depends(get_current_user_id)
):
    """
    Initiate Google OAuth flow for Google Forms export.
    
    Returns an authorization URL that the frontend should redirect to.
    After user authorizes, they will be redirected to /auth/google/callback.
    
    Available to all tiers (December 2025).
    """
    from services.google_auth_service import (
        GoogleAuthError,
        generate_auth_url,
        generate_secure_state_token,
        is_google_auth_configured,
    )
    
    logger.info(f"Google connect initiated for user {_short_user_id(user_id)}")
    
    # NOTE (December 2025): Google Forms export is now available to all tiers.
    # Tier check removed - all users can connect their Google account for exports.
    
    # Check if Google OAuth is configured
    if not is_google_auth_configured():
        logger.error("Google OAuth not configured")
        raise HTTPException(
            status_code=503,
            detail="Google Forms export is not configured. Please contact support."
        )
    
    try:
        # Generate secure state token (HMAC-signed) for CSRF protection
        # Format: timestamp:user_id:signature
        secure_state = generate_secure_state_token(user_id)
        
        # Generate authorization URL with secure state for CSRF protection
        auth_url, _ = generate_auth_url(state=secure_state)
        
        logger.info(f"Google OAuth URL generated for user {_short_user_id(user_id)}")
        
        return {
            "auth_url": auth_url,
            "state": secure_state,
            "message": "Redirect to auth_url to connect your Google account"
        }
        
    except GoogleAuthError as e:
        logger.error(f"Google OAuth error: {e.message}")
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        logger.error(f"Error generating Google auth URL: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to initiate Google authorization")


async def google_callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(None, description="Signed state parameter for CSRF protection"),
    error: str = Query(None, description="Error from Google OAuth")
):
    """
    Handle Google OAuth callback.
    
    After user authorizes on Google, they are redirected here with an authorization code.
    We exchange the code for tokens and store the refresh token.
    
    SECURITY: 
    - Validates HMAC-signed state token to prevent CSRF and tampering
    - State format: "timestamp:user_id:signature"
    
    Available to all tiers (December 2025).
    """
    from services.google_auth_service import (
        GoogleAuthError,
        exchange_code_for_tokens,
        store_google_tokens,
        validate_secure_state_token,
    )
    
    # Check for OAuth errors from Google
    if error:
        logger.warning(f"Google OAuth error: {error}")
        return RedirectResponse(
            url=f"{app_config.FRONTEND_URL}/settings?google_error={error}",
            status_code=302
        )
    
    # Validate signed state token using shared utility
    # Use 15 minute window (900 seconds) for OAuth flow completion
    user_id, redirect_url, error_code = validate_secure_state_token(state, max_age_seconds=900)
    
    if error_code:
        logger.error(f"Invalid state token in Google OAuth callback: {error_code}")
        return RedirectResponse(
            url=f"{app_config.FRONTEND_URL}/settings?google_error={error_code}",
            status_code=302
        )
    
    logger.info(f"Google OAuth callback for user {_short_user_id(user_id)}")
    
    # Validate and sanitize redirect_url to prevent open redirects and CRLF injection
    # Must be a relative path (starts with /) or None
    safe_redirect_path = None
    if redirect_url:
        # Check for control characters that could enable CRLF header injection
        control_chars = "\r\n\x00"
        if any(c in redirect_url for c in control_chars):
            logger.warning("Rejecting redirect_url with control characters (CRLF injection attempt)")
        # Only allow relative paths starting with /
        elif redirect_url.startswith("/") and not redirect_url.startswith("//"):
            # Strip any protocol:// that might be embedded
            if "://" not in redirect_url:
                safe_redirect_path = redirect_url
                logger.debug(f"Using custom redirect path: {safe_redirect_path}")
            else:
                logger.warning(f"Rejecting redirect_url with protocol: {redirect_url[:50]}...")
        else:
            logger.warning(f"Rejecting non-relative redirect_url: {redirect_url[:50]}...")
    
    # Helper to build redirect URL with fallback to /settings
    def build_redirect_url(query_params: str) -> str:
        if safe_redirect_path:
            separator = "&" if "?" in safe_redirect_path else "?"
            return f"{app_config.FRONTEND_URL}{safe_redirect_path}{separator}{query_params}"
        return f"{app_config.FRONTEND_URL}/settings?{query_params}"
    
    # NOTE (December 2025): Google Forms export is now available to all tiers.
    # Tier check removed - all users can connect their Google account for exports.
    
    try:
        # Exchange authorization code for tokens
        credentials = exchange_code_for_tokens(code)
        
        # Store refresh token in database
        await store_google_tokens(user_id, credentials)
        
        logger.info(f"Google account connected for user {_short_user_id(user_id)}")
        
        # Redirect to frontend with success (use custom path or /settings)
        return RedirectResponse(
            url=build_redirect_url("google_connected=true"),
            status_code=302
        )
        
    except GoogleAuthError as e:
        logger.error(f"Google OAuth error: {e.message}")
        return RedirectResponse(
            url=build_redirect_url(f"google_error={e.error_code}"),
            status_code=302
        )
    except Exception as e:
        logger.error(f"Error in Google OAuth callback: {str(e)}", exc_info=True)
        return RedirectResponse(
            url=build_redirect_url("google_error=callback_failed"),
            status_code=302
        )


async def google_disconnect(
    user_id: str = Depends(get_current_user_id)
):
    """
    Disconnect Google account by removing stored OAuth tokens.
    
    After this, user will need to re-authorize to use Google Forms export.
    """
    from services.google_auth_service import disconnect_google
    
    logger.info(f"Google disconnect requested for user {_short_user_id(user_id)}")
    
    try:
        success = await disconnect_google(user_id)
        
        if success:
            logger.info(f"Google account disconnected for user {_short_user_id(user_id)}")
            return {
                "message": "Google account disconnected successfully",
                "google_connected": False
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to disconnect Google account"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disconnecting Google: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to disconnect Google account")


async def google_status(
    user_id: str = Depends(get_current_user_id)
):
    """
    Check if user has connected their Google account.
    
    Returns connection status and whether Google Forms export is available.
    """
    from services.google_auth_service import (
        is_google_auth_configured,
        is_user_connected,
    )
    
    logger.debug(f"Google status check for user {_short_user_id(user_id)}")
    
    try:
        # Check if OAuth is configured at all
        configured = is_google_auth_configured()
        
        # Check if user is connected
        connected = await is_user_connected(user_id) if configured else False
        
        return {
            "google_configured": configured,
            "google_connected": connected,
            "can_export_to_forms": configured and connected
        }
        
    except Exception as e:
        logger.error(f"Error checking Google status: {str(e)}", exc_info=True)
        # Return safe defaults on error
        return {
            "google_configured": False,
            "google_connected": False,
            "can_export_to_forms": False
        }


# ============================================================================
# GOOGLE SIGN-IN AUTHENTICATION ENDPOINTS (OAuth Login via Supabase Auth)
# ============================================================================
# These are different from the Google Forms export OAuth above.
# These endpoints handle user authentication via Google Sign-In.
# OAuth utilities imported from services/oauth_utils.py
# ============================================================================


async def google_signin_initiate(
    redirect_url: Optional[str] = Query(None, description="URL to redirect after successful sign-in"),
    request: Request = None
):
    """
    Initiate Google OAuth Sign-In flow with CSRF protection.
    
    Returns a URL that the frontend should redirect to for Google Sign-In.
    After user authenticates with Google, they'll be redirected back to
    /api/auth/google/signin/callback with an authorization code.
    
    Security features:
    - CSRF token is generated and stored in a signed HttpOnly cookie
    - State parameter contains HMAC-signed payload with CSRF token
    - Redirect URL is validated to prevent open redirects
    
    This uses Supabase's built-in Google OAuth provider.
    """
    logger.info("Initiating Google Sign-In OAuth flow")
    
    try:
        supabase = get_supabase()
        
        # Build the callback URL
        backend_url = app_config.BACKEND_URL
        callback_url = f"{backend_url}/api/auth/google/signin/callback"
        
        # Generate CSRF-protected state with optional redirect URL
        # NOTE: Our state is passed as a query param in redirect_to, NOT as OAuth's state parameter.
        # This works because:
        # 1. Supabase uses its OWN state parameter for PKCE with Google
        # 2. Our redirect_to URL (with ?state=...) is where Supabase redirects AFTER OAuth completes
        # 3. Supabase preserves existing query params when redirecting (see prepPKCERedirectURL in gotrue)
        # 4. The 'code' we receive is from Supabase (not Google) - Supabase already exchanged with Google
        state_string, csrf_token = _generate_oauth_state(redirect_url)
        callback_url = f"{callback_url}?state={state_string}"
        
        # Use Supabase's signInWithOAuth to get the OAuth URL
        # SECURITY: Supabase handles PKCE internally. Our CSRF protection (state + cookie) is
        # separate and provides protection against login CSRF attacks where an attacker tricks
        # a user into logging into the attacker's account.
        # See: https://supabase.com/docs/guides/auth/social-login/auth-google
        oauth_response = supabase.auth.sign_in_with_oauth({
            "provider": "google",
            "options": {
                "redirect_to": callback_url,
                "query_params": {
                    "access_type": "offline",  # Get refresh token
                    "prompt": "consent"  # Force consent screen for refresh token
                }
            }
        })
        
        if oauth_response and oauth_response.url:
            logger.info("Google Sign-In OAuth URL generated successfully")
            
            # Create response with CSRF cookie
            response_data = {
                "auth_url": oauth_response.url,
                "message": "Redirect to auth_url to complete Google Sign-In"
            }
            
            json_response = JSONResponse(content=response_data)
            
            # Set CSRF token in HttpOnly cookie for validation on callback
            cookie_settings = _get_cookie_settings()
            json_response.set_cookie(
                key=OAUTH_STATE_COOKIE_NAME,
                value=csrf_token,
                max_age=OAUTH_STATE_MAX_AGE,
                httponly=True,
                secure=cookie_settings["secure"],
                samesite="lax",  # Must be lax for OAuth redirect to work
                path="/",
                domain=cookie_settings.get("domain")
            )
            
            return json_response
        else:
            logger.error("Failed to generate Google OAuth URL - no URL returned")
            raise HTTPException(
                status_code=500,
                detail="Failed to generate Google Sign-In URL"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error initiating Google Sign-In: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to initiate Google Sign-In"
        )


async def google_signin_callback(
    code: str = Query(None, description="Authorization code from Google"),
    state: str = Query(None, description="State parameter containing CSRF token and redirect URL"),
    error: str = Query(None, description="Error from Google OAuth"),
    error_description: str = Query(None, description="Error description from Google"),
    response: Response = None,
    request: Request = None
):
    """
    Handle Google Sign-In OAuth callback with CSRF protection.
    
    This endpoint receives the authorization code from Google after user
    authenticates. It validates the CSRF token and exchanges the code for a session.
    
    Security features:
    - CSRF token from state is validated against HttpOnly cookie
    - State signature is verified to prevent tampering
    - Redirect URL is re-validated before use
    - Auth tokens are set in HttpOnly cookies only
    """
    logger.info("Processing Google Sign-In callback")
    
    # Get CSRF token from cookie for validation
    csrf_cookie = request.cookies.get(OAUTH_STATE_COOKIE_NAME) if request else None
    
    # Helper to clear the CSRF cookie on any response
    def clear_csrf_cookie(resp):
        cookie_settings = _get_cookie_settings()
        resp.delete_cookie(
            key=OAUTH_STATE_COOKIE_NAME,
            path="/",
            domain=cookie_settings.get("domain")
        )
        return resp
    
    # Check for OAuth errors from Google
    if error:
        logger.error(f"Google Sign-In error: {error} - {error_description}")
        # Even on error, try to extract redirect from state (if valid)
        redirect_path = None
        if state and csrf_cookie:
            is_valid, redirect_path = _verify_oauth_state(state, csrf_cookie)
            # Don't fail on invalid state for error redirects - just use default
        
        # Use generic error message to avoid information disclosure from OAuth provider
        # Log the actual error for debugging, but show generic message to user
        base_url = f"{app_config.FRONTEND_URL}{redirect_path}" if redirect_path else app_config.FRONTEND_URL
        separator = "&" if "?" in base_url else "?"
        redirect_resp = RedirectResponse(
            url=f"{base_url}{separator}error=oauth_error&message=Authentication%20failed.%20Please%20try%20again."
        )
        return clear_csrf_cookie(redirect_resp)
    
    if not code:
        logger.error("No authorization code in Google Sign-In callback")
        redirect_resp = RedirectResponse(
            url=f"{app_config.FRONTEND_URL}/login?error=no_code&message=No%20authorization%20code%20received"
        )
        return clear_csrf_cookie(redirect_resp)
    
    # ===== CSRF VALIDATION (Critical Security Check) =====
    # Validate state parameter against CSRF cookie to prevent login CSRF attacks
    is_valid, redirect_path = _verify_oauth_state(state, csrf_cookie)
    
    if not is_valid:
        logger.warning("OAuth state validation failed - possible CSRF attack")
        redirect_resp = RedirectResponse(
            url=f"{app_config.FRONTEND_URL}/login?error=csrf_failed&message=Security%20validation%20failed.%20Please%20try%20again."
        )
        return clear_csrf_cookie(redirect_resp)
    
    try:
        supabase = get_supabase()
        
        # Exchange the code for a session
        # This is equivalent to supabase.auth.exchangeCodeForSession(code)
        auth_response = supabase.auth.exchange_code_for_session({
            "auth_code": code
        })
        
        if not auth_response or not auth_response.session:
            logger.error("Failed to exchange code for session")
            redirect_resp = RedirectResponse(
                url=f"{app_config.FRONTEND_URL}/login?error=exchange_failed&message=Failed%20to%20complete%20sign-in"
            )
            return clear_csrf_cookie(redirect_resp)
        
        session = auth_response.session
        user = auth_response.user
        
        user_id = user.id if user else None
        
        logger.info(f"Google Sign-In successful for user {_short_user_id(user_id)}")
        
        # Check if this is a new user (created within threshold)
        is_new_user = _is_new_user(user)
        
        # Create Redis session for multi-device tracking
        # SECURITY: Redis is REQUIRED for session management to match login() behavior
        redis_client = get_redis_client(request)
        if not redis_client:
            logger.error(f"Redis unavailable during Google Sign-In for user {_short_user_id(user_id)} - failing request")
            redirect_resp = RedirectResponse(
                url=f"{app_config.FRONTEND_URL}/login?error=service_unavailable&message=Session%20service%20temporarily%20unavailable"
            )
            return clear_csrf_cookie(redirect_resp)
        
        try:
            session_service = SessionService(redis_client)
            user_agent = request.headers.get("user-agent") if request else None
            device_type = detect_device_type(user_agent)
            await session_service.create_session(
                user_id=user_id,
                device_type=device_type,
                ip_address=request.client.host if request and request.client else None,
                user_agent=user_agent,
                refresh_token=session.refresh_token
            )
            logger.debug(f"Redis session created for Google Sign-In user {_short_user_id(user_id)}")
        except TooManySessionsError as e:
            # Hard fail for session limits - matches login() behavior
            logger.warning(f"Too many sessions for Google Sign-In user {_short_user_id(user_id)}: {e}")
            redirect_resp = RedirectResponse(
                url=f"{app_config.FRONTEND_URL}/login?error=too_many_sessions&message=Too%20many%20active%20sessions.%20Please%20logout%20from%20other%20devices."
            )
            return clear_csrf_cookie(redirect_resp)
        except Exception as redis_error:
            logger.error(f"Redis error during Google Sign-In session creation: {redis_error}")
            redirect_resp = RedirectResponse(
                url=f"{app_config.FRONTEND_URL}/login?error=session_failed&message=Failed%20to%20create%20session"
            )
            return clear_csrf_cookie(redirect_resp)
        
        # Build safe redirect URL (redirect_path already validated in _verify_oauth_state)
        # Strip any query params from redirect_path since we'll add our own
        clean_redirect_path = redirect_path.split('?')[0] if redirect_path and '?' in redirect_path else redirect_path
        base_redirect_url = f"{app_config.FRONTEND_URL}{clean_redirect_path}" if clean_redirect_path else app_config.FRONTEND_URL
        
        # Add success parameters (always use ? since we stripped any existing query)
        redirect_params = "?login=success&provider=google"
        if is_new_user:
            redirect_params += "&new_user=true"
        
        # Return redirect with cookies set
        final_redirect = RedirectResponse(
            url=f"{base_redirect_url}{redirect_params}",
            status_code=302
        )
        
        # Set auth cookies using helper for consistency
        _set_auth_cookies(final_redirect, session.access_token, session.refresh_token)
        
        # Clear the CSRF cookie since OAuth flow is complete
        clear_csrf_cookie(final_redirect)
        
        return final_redirect
        
    except Exception as e:
        logger.error(f"Error in Google Sign-In callback: {str(e)}", exc_info=True)
        redirect_resp = RedirectResponse(
            url=f"{app_config.FRONTEND_URL}/login?error=signin_failed&message=Failed%20to%20complete%20sign-in"
        )
        return clear_csrf_cookie(redirect_resp)


async def google_signin_token(
    request_body: dict,
    response: Response,
    request: Request
):
    """
    Sign in with Google ID token (from Google Sign-In button on frontend).
    
    This endpoint is for when the frontend uses Google's Sign-In button/SDK
    and receives an ID token (credential) directly from Google. The backend
    then exchanges this token with Supabase.
    
    Request body:
    - id_token: The Google ID token (JWT credential) from Google Sign-In
    - nonce: Optional nonce for extra security
    
    This is the recommended approach when using Google's pre-built sign-in buttons.
    """
    from schemas.auth import GoogleSignInRequest
    
    # Parse and validate request
    try:
        signin_request = GoogleSignInRequest(**request_body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request: {str(e)}")
    
    logger.info("Processing Google Sign-In with ID token")
    
    try:
        supabase = get_supabase()
        
        # Exchange the Google ID token with Supabase
        # This is equivalent to supabase.auth.signInWithIdToken()
        sign_in_data = {
            "provider": "google",
            "token": signin_request.id_token,
        }
        
        if signin_request.nonce:
            sign_in_data["nonce"] = signin_request.nonce
        
        auth_response = supabase.auth.sign_in_with_id_token(sign_in_data)
        
        if not auth_response or not auth_response.session:
            logger.error("Failed to sign in with Google ID token")
            raise HTTPException(
                status_code=401,
                detail="Invalid Google credentials"
            )
        
        session = auth_response.session
        user = auth_response.user
        
        user_id = user.id if user else None
        
        logger.info(f"Google ID token Sign-In successful for user {_short_user_id(user_id)}")
        
        # Check if this is a new user (created within threshold)
        is_new_user = _is_new_user(user)
        
        # Create Redis session for multi-device tracking
        # SECURITY: Redis is REQUIRED for session management to match login() behavior
        redis_client = get_redis_client(request)
        if not redis_client:
            logger.error(f"Redis unavailable during Google ID token Sign-In for user {_short_user_id(user_id)} - failing request")
            raise HTTPException(
                status_code=503,
                detail="Session management service temporarily unavailable. Please try again."
            )
        
        try:
            session_service = SessionService(redis_client)
            user_agent = request.headers.get("user-agent")
            device_type = detect_device_type(user_agent)
            await session_service.create_session(
                user_id=user_id,
                device_type=device_type,
                ip_address=request.client.host if request.client else None,
                user_agent=user_agent,
                refresh_token=session.refresh_token
            )
        except TooManySessionsError as e:
            # Hard fail for session limits - matches login() behavior
            logger.warning(f"Too many sessions for Google ID token user {_short_user_id(user_id)}: {e}")
            raise HTTPException(
                status_code=429,
                detail="Too many active sessions. Please logout from other devices or revoke old sessions."
            )
        except Exception as redis_error:
            logger.error(f"Redis error during Google ID token session creation: {redis_error}")
            raise HTTPException(
                status_code=503,
                detail="Failed to create session. Please try again."
            )
        
        # Set auth cookies using helper for consistency
        _set_auth_cookies(response, session.access_token, session.refresh_token)
        
        # Build response
        result = {
            "message": "Google Sign-In successful",
            "user_id": user_id,
            "email": user.email if user else "unknown",
            "is_new_user": is_new_user
        }
        
        # SECURITY: Only expose tokens in response body during testing or development
        # In production, tokens are only available via HttpOnly cookies
        # This matches the login function behavior for consistency
        if app_config.is_testing() or app_config.is_development():
            result["access_token"] = session.access_token
            result["refresh_token"] = session.refresh_token
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in Google ID token Sign-In: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to sign in with Google"
        )
