from fastapi import HTTPException, Body, Response, Request, Query
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from services.logger import app_logger as logger
from fastapi import Depends
from dependencies.auth_dependencies import get_current_user_id, get_current_user_token
from services.db_services.supabase_quiz import get_user_tier_info
from typing import Dict, Any
from config import config as app_config
from schemas.auth import SignupRequest, LoginRequest, LogoutRequest, UpdateEmailRequest, ChangePasswordRequest, ForgotPasswordRequest, ResetPasswordRequest, ResendVerificationRequest

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

# Remove template rendering functions
async def signup(request: SignupRequest):
    try:
        supabase = get_supabase()
        logger.info(f"Attempting to sign up user with email: {request.email}")
        
        # Sign up user - name goes to raw_user_meta_data
        response = supabase.auth.sign_up({
            "email": request.email,
            "password": request.password,
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
        logger.error(f"Error during signup for {request.email}: {str(e)}")
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


async def login(request: LoginRequest, response: Response):
    try:
        supabase = get_supabase()
        logger.info(f"Login attempt for user: {request.email}")
        result = supabase.auth.sign_in_with_password({
            "email": request.email,
            "password": request.password
        })
        
        session = result.session
        
        if session is None:
            logger.warning(f"Login failed: No session returned for {request.email}")
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        access_token = session.access_token
        refresh_token = session.refresh_token
        
        logger.info(f"User logged in: {result.user.id if result.user else 'Unknown'}")
        
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
                "id": result.user.id if result.user else None,
                "email": result.user.email if result.user else None
            }
        }
        
        # SECURITY: Only expose token in response body during testing or development
        # In production, token is only available via HttpOnly cookie
        if app_config.is_testing() or app_config.is_development():
            response_data["access_token"] = access_token
        
        return response_data

    except Exception as e:
        error_message = str(e).lower()
        logger.warning(f"Failed login for {request.email}: {e}")
        
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


async def logout(response: Response, user_id: str = Depends(get_current_user_id)):
    try:
        logger.info(f"User {user_id} logout requested")
        # Must match domain used when setting cookies
        domain = app_config.COOKIE_DOMAIN if not app_config.is_testing() else None
        response.delete_cookie(key="access_token", path="/", domain=domain, httponly=True)
        response.delete_cookie(key="refresh_token", path="/", domain=domain, httponly=True)
        logger.info(f"User {user_id} logged out successfully")
        return {"message": "Successfully logged out"}
    except Exception as e:
        logger.error(f"Error during logout: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def change_password(request: ChangePasswordRequest,
                           user_id: str = Depends(get_current_user_id)):
    """
    Change password for authenticated user.
    User is identified by JWT token (user_id), not by email in request body.
    """
    try:
        supabase = get_supabase()
        logger.info(f"Password change requested for user ID: {user_id}")
        supabase.auth.admin.update_user_by_id(user_id, {"password": request.new_password})
        logger.info(f"Password updated successfully for user ID: {user_id}")
        return {"message": "Password updated successfully"}
    except Exception as e:
        logger.error(f"Error during password change for user {user_id}: {str(e)}", exc_info=True)
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
        logger.info(f"Email update requested to: {new_email}")
        
        # Create authenticated Supabase client with user's token
        # This ensures the update is made on behalf of the authenticated user
        supabase = app_config.get_authenticated_supabase_client(token)
        
        # Use the Python SDK to update email - triggers Secure Email Change flow
        response = supabase.auth.update_user({"email": new_email})
        
        current_email = response.user.email if response.user else None
        logger.info("Email change initiated. Confirmation emails being sent.")
        logger.info(f"Update response: email={current_email}, new_email={response.user.new_email if response.user else None}")
        
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
    
    Returns:
        User profile with tier, role, quota, and display name information
    """
    try:
        logger.info(f"Fetching user info for user ID: {user_id}")
        tier_info = get_user_tier_info(user_id, user_token)
        
        return {
            "user_id": str(tier_info["id"]),
            "email": tier_info["email"],
            "display_name": tier_info.get("display_name"),
            "account_tier": tier_info["account_tier"],
            "role": tier_info.get("role", "user"),
            "current_quiz_count": tier_info["current_quiz_count"],  # Quizzes created
            "quizzes_attempted": tier_info.get("quizzes_attempted", 0),  # Quizzes attempted (NEW)
            "quota_limit": tier_info["quota_limit"],
            "quota_exceeded": tier_info["quota_exceeded"],
            "created_at": tier_info.get("created_at")
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
        logger.info(f"Email confirmed successfully for user: {user_id} ({user_email})")
        
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
