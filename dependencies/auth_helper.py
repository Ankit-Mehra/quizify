from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os
import requests

security = HTTPBearer(auto_error=False)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def get_current_user_id(
        request: Request,
        credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    
    # First check for Authorization header (preferred for API clients)
    token = None
    if credentials:
        token = credentials.credentials
    
    # Fallback to cookie for backward compatibility
    if not token:
        token = request.cookies.get("auth_token")
    
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "apikey": SUPABASE_KEY
    }

    try:
        response = requests.get(f"{SUPABASE_URL}/auth/v1/user", headers=headers)
        if response.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        user_info = response.json()

        # Use user ID (recommended) or email as identifier
        return user_info.get("id") or user_info.get("email")

    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")

def get_current_user_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    token = None
    if credentials:
        token = credentials.credentials
    
    if not token:
        token = request.cookies.get("auth_token")
    
    return token