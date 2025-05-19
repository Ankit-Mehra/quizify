import os
import requests
from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from services.logger import app_logger as logger

security = HTTPBearer(auto_error=False)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

logger.info("Auth helper initialized")

def get_current_user_id(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    token = credentials.credentials if credentials else request.cookies.get("access_token")

    if not token:
        logger.warning("Authentication required but no token provided")
        raise HTTPException(status_code=401, detail="Authentication required")

    headers = {
        "Authorization": f"Bearer {token}",
        "apikey": SUPABASE_KEY
    }

    try:
        logger.debug("Verifying token with Supabase")
        response = requests.get(f"{SUPABASE_URL}/auth/v1/user", headers=headers)

        if response.status_code != 200:
            logger.warning(f"Invalid token. Supabase status: {response.status_code}")
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        user_info = response.json()
        user_id = user_info.get("id") or user_info.get("email")
        logger.debug(f"Authenticated user: {user_id}")

        return user_id

    except Exception as e:
        logger.error(f"Auth error: {e}", exc_info=True)
        raise HTTPException(status_code=401, detail="Authentication failed")


def get_current_user_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    token = None
    if credentials:
        token = credentials.credentials
    
    if not token:
        token = request.cookies.get("auth_token")
    
    if token:
        logger.debug("Retrieved user token")
    else:
        logger.debug("No user token found")
        
    return token