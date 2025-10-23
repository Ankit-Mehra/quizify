from fastapi import HTTPException, Body, Response, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from services.logger import app_logger as logger
from fastapi import Depends
from dependencies.auth_dependencies import get_current_user_id
from services.db_services.supabase_quiz import get_user_tier_info
from typing import Dict, Any
from config import config
from schemas.auth import SignupRequest, LoginRequest, LogoutRequest, UpdateEmailRequest, ChangePasswordRequest

security = HTTPBearer(auto_error=False)

# Lazy load Supabase client to avoid initialization issues in tests
def get_supabase():
    """Get Supabase client (lazy loaded)"""
    return config.get_supabase_client()

if config.is_testing():
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
        
        # Set access token
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=ACCESS_TOKEN_EXPIRE
        )
        # Set refresh token
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=True,
            samesite="lax",
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
        if config.is_testing() or config.is_development():
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
            max_age=ACCESS_TOKEN_EXPIRE
        )
        return {"message": "Session refreshed"}
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token")


async def logout(response: Response, user_id: str = Depends(get_current_user_id)):
    try:
        logger.info(f"User {user_id} logout requested")
        response.delete_cookie(key="access_token", path="/", httponly=True)
        response.delete_cookie(key="refresh_token", path="/", httponly=True)
        logger.info(f"User {user_id} logged out successfully")
        return {"message": "Successfully logged out"}
    except Exception as e:
        logger.error(f"Error during logout: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def change_password(request: ChangePasswordRequest,
                           user_id: str = Depends(get_current_user_id)):
    try:
        supabase = get_supabase()
        logger.info(f"Password change requested for user: {request.email}")
        supabase.auth.admin.update_user_by_id(user_id, {"password": request.new_password})
        logger.info(f"Password updated successfully for user: {request.email}")
        return {"message": "Password updated successfully"}
    except Exception as e:
        logger.error(f"Error during password change: {str(e)}", exc_info=True)
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
        
        supabase = get_supabase()
        
        # Set the session with the user's token
        supabase.auth.set_session(token, token)
        
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

async def get_current_user_info(user_id: str = Depends(get_current_user_id)) -> Dict[str, Any]:
    """
    Get current authenticated user's information including tier and quota.
    
    Returns:
        User profile with tier, role, quota information
    """
    try:
        logger.info(f"Fetching user info for user ID: {user_id}")
        tier_info = get_user_tier_info(user_id)
        
        return {
            "user_id": str(tier_info["id"]),
            "email": tier_info["email"],
            "account_tier": tier_info["account_tier"],
            "role": tier_info.get("role", "user"),
            "current_quiz_count": tier_info["current_quiz_count"],
            "quota_limit": tier_info["quota_limit"],
            "quota_exceeded": tier_info["quota_exceeded"],
            "created_at": tier_info.get("created_at")
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching user info: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve user information")
