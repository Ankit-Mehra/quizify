from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.status import HTTP_401_UNAUTHORIZED
import os
import requests
from config import config as app_config

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ACCESS_TOKEN_EXPIRE = 3600  # 1 hour

# Public routes that should NOT trigger token logic
EXCLUDE_PATHS = [
    "/docs",
    "/openapi.json",
    "/redoc",
    "/api/auth/login",
    "/api/auth/signup",
    "/api/auth/logout"
]

class SupabaseAutoRefreshMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip middleware for public endpoints
        if any(path.startswith(p) for p in EXCLUDE_PATHS):
            return await call_next(request)

        access_token = request.cookies.get("access_token")
        refresh_token = request.cookies.get("refresh_token")

        if access_token:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "apikey": SUPABASE_KEY
            }

            try:
                user_resp = requests.get(f"{SUPABASE_URL}/auth/v1/user", headers=headers)
                if user_resp.status_code == 200:
                    return await call_next(request)
            except Exception:
                pass  # Fall through to refresh

        if refresh_token:
            try:
                refresh_resp = requests.post(
                    f"{SUPABASE_URL}/auth/v1/token?grant_type=refresh_token",
                    headers={
                        "apikey": SUPABASE_KEY,
                        "Content-Type": "application/json"
                    },
                    json={"refresh_token": refresh_token}
                )

                if refresh_resp.status_code == 200:
                    session = refresh_resp.json()
                    new_access_token = session.get("access_token")
                    if not new_access_token:
                        raise Exception("No access token returned")

                    # Make refreshed token available to downstream dependencies immediately
                    request.state.access_token = new_access_token

                    response = await call_next(request)
                    response.set_cookie(
                        key="access_token",
                        value=new_access_token,
                        httponly=True,
                        secure=True,
                        samesite="lax",
                        domain=app_config.COOKIE_DOMAIN if not app_config.is_testing() else None,
                        max_age=ACCESS_TOKEN_EXPIRE
                    )
                    return response

                else:
                    return JSONResponse(
                        status_code=HTTP_401_UNAUTHORIZED,
                        content={"detail": "Session expired or invalid refresh token"}
                    )
            except Exception as e:
                return JSONResponse(
                    status_code=HTTP_401_UNAUTHORIZED,
                    content={"detail": f"Token refresh failed: {str(e)}"}
                )

        # No access and no refresh token — let route-level auth handle it
        return await call_next(request)
