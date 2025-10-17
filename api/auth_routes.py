from fastapi import APIRouter
from handlers.auth_handlers import (
    signup, login, logout,
    change_password, delete_account, update_email,
    get_current_user_info
)
from typing import Dict, Any
from services.logger import app_logger as logger

router = APIRouter(prefix="/auth", tags=["Auth"])
logger.info("Auth routes initialized")

router.add_api_route(
    "/signup",
    signup,
    methods=["POST"],
    response_model=Dict[str, Any]
)

router.add_api_route(
    "/login",
    login,
    methods=["POST"],
    response_model=Dict[str, Any]
)
# router.add_api_route("/refresh-session", refresh_session, methods=["POST"], response_model=Dict[str, Any])

router.add_api_route(
    "/logout",
    logout,
    methods=["POST"],
    response_model=Dict[str, str]
)

router.add_api_route(
    "/change-password",
    change_password,
    methods=["POST"],
    response_model=Dict[str, str],
    tags=["Auth"]
)
router.add_api_route(
    "/delete-account",
    delete_account,
    methods=["POST"],
    response_model=Dict[str, str],
    tags=["Auth"]
)

router.add_api_route(
    "/update-email",
    update_email,
    methods=["POST"],
    response_model=Dict[str, str],
    tags=["Auth"]
)

router.add_api_route(
    "/me",
    get_current_user_info,
    methods=["GET"],
    response_model=Dict[str, Any],
    summary="Get Current User Info",
    description="Get authenticated user's profile, tier, role, and quota information",
    tags=["Auth"]
)
