from fastapi import APIRouter
from handlers.auth_handlers import (
    signup, login, logout,
    verify_email_token, change_password,
    delete_account, update_email
)
from typing import Dict, Any
from services.logger import app_logger as logger
from fastapi import Depends
from dependencies.auth_dependencies import get_current_user_id

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
    response_model=Dict[str, str],
    dependencies=[Depends(get_current_user_id)],
    openapi_extra={
        "security": [{"BearerAuth": []}]
    }
)

router.add_api_route(
    "/verify-email",
    verify_email_token,
    methods=["POST"],
    response_model=Dict[str, str]
)

router.add_api_route(
    "/change-password",
    change_password,
    methods=["POST"],
    response_model=Dict[str, str],
    dependencies=[Depends(get_current_user_id)],
    openapi_extra={
        "security": [{"BearerAuth": []}]
    },
    tags=["Auth"]
)
router.add_api_route(
    "/delete-account",
    delete_account,
    methods=["POST"],
    response_model=Dict[str, str],
    dependencies=[Depends(get_current_user_id)],
    openapi_extra={
        "security": [{"BearerAuth": []}]
    },
    tags=["Auth"]
)

router.add_api_route(
    "/update-email",
    update_email,
    methods=["POST"],
    response_model=Dict[str, str],
    dependencies=[Depends(get_current_user_id)],
    openapi_extra={
        "security": [{"BearerAuth": []}]
    },
    tags=["Auth"]
)