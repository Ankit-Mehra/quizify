from fastapi import HTTPException, Body, Response, Request
from supabase import Client
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from services.logger import app_logger as logger
from fastapi import Depends
from dependencies.auth_dependencies import get_current_user_id
from typing import Optional
from config import config

# Use centralized configuration - guaranteed non-null in production (fail-fast at startup)
supabase: Client = config.get_supabase_client()

if config.is_testing():
    logger.info("Auth handlers initialized in TEST mode")
else:
    logger.info("Auth handlers initialized with Supabase client")

ACCESS_TOKEN_EXPIRE = 3600  # 1 hour
REFRESH_TOKEN_EXPIRE = 60 * 60 * 24 * 30  # 30 days

# Define request models
class LoginRequest(BaseModel):
    email: str
    password: str

class LogoutRequest(BaseModel):
    token: Optional[str] = None

# Remove template rendering functions
async def signup(email: str = Body(...), password: str = Body(...), name: str = Body(...)):
    try:
        logger.info(f"Attempting to sign up user with email: {email}")
        response = supabase.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "data": {
                    "name": name
                }
            }
        })
        logger.info(f"User created successfully with ID: {response.user.id if response.user else None}")
        return JSONResponse(
            status_code=201,
            content={"message": "User created successfully", "user_id": response.user.id if response.user else None}
        )
    except Exception as e:
        logger.error(f"Error during signup: {str(e)}")
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

        return {
            "message": "Successfully logged in",
            "access_token": access_token,  # Include for testing/integration purposes
            "user": {
                "id": result.user.id if result.user else None,
                "email": result.user.email if result.user else None
            }
        }

    except Exception as e:
        logger.warning(f"Failed login for {request.email}: {e}")
        raise HTTPException(status_code=401, detail="Invalid credentials")


async def refresh_session(request: Request, response: Response):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Missing refresh token")

    try:
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


async def logout(response: Response):
    try:
        logger.info("User logout requested")
        response.delete_cookie(key="access_token", path="/", httponly=True)
        response.delete_cookie(key="refresh_token", path="/", httponly=True)
        logger.info("User logged out successfully")
        return {"message": "Successfully logged out"}
    except Exception as e:
        logger.error(f"Error during logout: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

async def verify_email_token(request: Request):
    
    body = await request.json()
    code = body.get("code")
    email = body.get("email")

    if not code:
        raise HTTPException(status_code=400, detail="Missing verification code")
    if not email:
        raise HTTPException(status_code=400, detail="Missing email address")

    try:
        supabase.auth.verify_otp({
            "email": email,
            "token_hash": code,
            "type": "email"
        })

        return {"message": "Email verified successfully"}

    except Exception as e:
        logger.error(f"Error during email verification: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def change_password(email: str = Body(...),
                           new_password: str = Body(...),
                           user_id: str = Depends(get_current_user_id)):
    try:
        logger.info(f"Password change requested for user: {email}")
        supabase.auth.admin.update_user_by_id(user_id, {"password": new_password})
        logger.info(f"Password updated successfully for user: {email}")
        return {"message": "Password updated successfully"}
    except Exception as e:
        logger.error(f"Error during password change: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

async def delete_account(email: str = Body(...)):
    try:
        logger.info(f"Account deletion requested for user: {email}")
        response = supabase.table("users").select("*").eq("email", email).execute()
        if not response.data:
            logger.warning(f"Account deletion failed: User not found - {email}")
            raise HTTPException(status_code=400, detail="User not found")

        supabase.table("users").delete().eq("email", email).execute()
        logger.info(f"Account deleted successfully for user: {email}")
        return {"message": "Account deleted successfully"}
    except Exception as e:
        logger.error(f"Error during account deletion: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

async def update_email(email: str = Body(...), new_email: str = Body(...)):
    try:
        logger.info(f"Email update requested: {email} -> {new_email}")
        response = supabase.table("users").select("*").eq("email", email).execute()
        if not response.data:
            logger.warning(f"Email update failed: User not found - {email}")
            raise HTTPException(status_code=400, detail="User not found")

        supabase.table("users").update({"email": new_email}).eq("email", email).execute()
        logger.info(f"Email updated successfully: {email} -> {new_email}")
        return {"message": "Email updated successfully"}
    except Exception as e:
        logger.error(f"Error during email update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
