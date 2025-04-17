import os
from fastapi import HTTPException, Body, Response
from supabase import create_client, Client
from fastapi.responses import JSONResponse
from typing import Dict, Any
from pydantic import BaseModel

# Initialize Supabase client
supabase: Client = create_client(
    supabase_url=os.getenv("SUPABASE_URL"),
    supabase_key=os.getenv("SUPABASE_KEY")
)

# Define request models
class LoginRequest(BaseModel):
    email: str
    password: str

class LogoutRequest(BaseModel):
    token: str = None

# Remove template rendering functions
async def signup(email: str = Body(...), password: str = Body(...)):
    try:
        response = supabase.auth.sign_up({
            "email": email,
            "password": password
        })
        return JSONResponse(
            status_code=201,
            content={"message": "User created successfully", "user_id": response.user.id if response.user else None}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def login(request: LoginRequest,response: Response):
    try:
        result = supabase.auth.sign_in_with_password({
            "email": request.email,
            "password": request.password
        })
        
        token = result.session.access_token
        
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
        raise HTTPException(status_code=401, detail="Invalid credentials")

async def logout(response: Response):
    try:
        response.delete_cookie(key="auth_token",path="/")
        return {"message": "Successfully logged out"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def verify_email(email: str = Body(...)):
    try:
        response = supabase.table("users").select("*").eq("email", email).execute()
        if not response.data:
            raise HTTPException(status_code=400, detail="User not found")
        return {"message": "Verification email sent"}  # TODO: implement actual email
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def change_password(email: str = Body(...), new_password: str = Body(...)):
    try:
        response = supabase.table("users").select("*").eq("email", email).execute()
        if not response.data:
            raise HTTPException(status_code=400, detail="User not found")

        supabase.table("users").update({"password": new_password}).eq("email", email).execute()
        return {"message": "Password updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def delete_account(email: str = Body(...)):
    try:
        response = supabase.table("users").select("*").eq("email", email).execute()
        if not response.data:
            raise HTTPException(status_code=400, detail="User not found")

        supabase.table("users").delete().eq("email", email).execute()
        return {"message": "Account deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def update_email(email: str = Body(...), new_email: str = Body(...)):
    try:
        response = supabase.table("users").select("*").eq("email", email).execute()
        if not response.data:
            raise HTTPException(status_code=400, detail="User not found")

        supabase.table("users").update({"email": new_email}).eq("email", email).execute()
        return {"message": "Email updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
