from fastapi import APIRouter, Response
from handlers.auth_handlers import (
    signup, login, logout,
    verify_email, change_password,
    delete_account, update_email
)
from typing import Dict, Any

router = APIRouter(prefix="/auth", tags=["Auth"])

@router.options("/login")
async def login_options():
    return Response(
        content="",
        status_code=200,
        headers={
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        },
    )

router.add_api_route("/signup", signup, methods=["POST"], response_model=Dict[str, Any])
router.add_api_route("/login", login, methods=["POST"], response_model=Dict[str, Any])
router.add_api_route("/logout", logout, methods=["POST"], response_model=Dict[str, str])
router.add_api_route("/verify-email", verify_email, methods=["POST"], response_model=Dict[str, str])
router.add_api_route("/change-password", change_password, methods=["POST"], response_model=Dict[str, str])
router.add_api_route("/delete-account", delete_account, methods=["POST"], response_model=Dict[str, str])
router.add_api_route("/update-email", update_email, methods=["POST"], response_model=Dict[str, str])
