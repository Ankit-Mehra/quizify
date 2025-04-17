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
        credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    
    # First check for Authorization header (preferred for API clients)
    token = None
    if credentials:
        logger.debug("Authentication token found in Authorization header")
        token = credentials.credentials
    
    # Fallback to cookie for backward compatibility
    if not token:
        token = request.cookies.get("auth_token")
        if token:
            logger.debug("Authentication token found in cookie")
        else:
            logger.warning("No authentication token found in request")
    
    if not token:
        logger.warning("Authentication required but no token provided")
        raise HTTPException(status_code=401, detail="Authentication required")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "apikey": SUPABASE_KEY
    }

    try:
        logger.debug("Verifying user token with Supabase")
        response = requests.get(f"{SUPABASE_URL}/auth/v1/user", headers=headers)
        if response.status_code != 200:
            logger.warning(f"Invalid token: Supabase returned status {response.status_code}")
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        user_info = response.json()
        user_id = user_info.get("id") or user_info.get("email")
        logger.debug(f"Authentication successful for user: {user_id}")

        # Use user ID (recommended) or email as identifier
        return user_id

    except Exception as e:
        logger.error(f"Authentication error: {str(e)}", exc_info=True)
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
    
    if token:
        logger.debug("Retrieved user token")
    else:
        logger.debug("No user token found")
        
    return token