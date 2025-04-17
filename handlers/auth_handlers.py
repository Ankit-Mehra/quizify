import os
from fastapi import HTTPException, Body, Response
from supabase import create_client, Client
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from services.logger import app_logger as logger

# Initialize Supabase client
supabase: Client = create_client(
    supabase_url=os.getenv("SUPABASE_URL"),
    supabase_key=os.getenv("SUPABASE_KEY")
)
logger.info("Auth handlers initialized with Supabase client")

# Define request models
class LoginRequest(BaseModel):
    email: str
    password: str

class LogoutRequest(BaseModel):
    token: str = None

# Remove template rendering functions
async def signup(email: str = Body(...), password: str = Body(...)):
    try:
        logger.info(f"Attempting to sign up user with email: {email}")
        response = supabase.auth.sign_up({
            "email": email,
            "password": password
        })
        logger.info(f"User created successfully with ID: {response.user.id if response.user else None}")
        return JSONResponse(
            status_code=201,
            content={"message": "User created successfully", "user_id": response.user.id if response.user else None}
        )
    except Exception as e:
        logger.error(f"Error during signup: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

async def login(request: LoginRequest, response: Response):
    try:
        logger.info(f"Login attempt for user: {request.email}")
        result = supabase.auth.sign_in_with_password({
            "email": request.email,
            "password": request.password
        })
        
        token = result.session.access_token
        logger.info(f"User logged in successfully: {result.user.id}")
        
        response.set_cookie(
            key="auth_token",
            value=token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=60*60*24
        )
        return {"message": "Successfully logged in",
                "user": {
                    "id": result.user.id,
                    "email": result.user.email
                }
            }
    except Exception as e:
        logger.warning(f"Failed login attempt for {request.email}: {str(e)}")
        raise HTTPException(status_code=401, detail="Invalid credentials")

async def logout(response: Response):
    try:
        logger.info("User logout requested")
        response.delete_cookie(key="auth_token",path="/")
        logger.info("User logged out successfully")
        return {"message": "Successfully logged out"}
    except Exception as e:
        logger.error(f"Error during logout: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

async def verify_email(email: str = Body(...)):
    try:
        logger.info(f"Email verification requested for: {email}")
        response = supabase.table("users").select("*").eq("email", email).execute()
        if not response.data:
            logger.warning(f"Email verification failed: User not found - {email}")
            raise HTTPException(status_code=400, detail="User not found")
        logger.info(f"Verification email would be sent to: {email}")
        return {"message": "Verification email sent"}  # TODO: implement actual email
    except Exception as e:
        logger.error(f"Error during email verification: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

async def change_password(email: str = Body(...), new_password: str = Body(...)):
    try:
        logger.info(f"Password change requested for user: {email}")
        response = supabase.table("users").select("*").eq("email", email).execute()
        if not response.data:
            logger.warning(f"Password change failed: User not found - {email}")
            raise HTTPException(status_code=400, detail="User not found")

        supabase.table("users").update({"password": new_password}).eq("email", email).execute()
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
