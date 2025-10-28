from fastapi import APIRouter
from handlers.auth_handlers import (
    signup,
    login,
    logout,
    change_password,
    delete_account,
    update_email,
    get_user_info,
    confirm_email,
    forgot_password,
    reset_password,
    resend_verification_email
)
from schemas.auth import AuthMessageResponse, UserInfoResponse
from typing import Dict, Any
from services.logger import app_logger as logger

router = APIRouter(prefix="/auth", tags=["Auth"])
logger.info("Auth routes initialized")

router.add_api_route(
    "/signup",
    signup,
    methods=["POST"],
    response_model=Dict[str, Any]  # TODO: Should be AuthSuccessResponse but handler returns flexible dict
)

router.add_api_route(
    "/login",
    login,
    methods=["POST"],
    response_model=Dict[str, Any]  # TODO: Should be AuthSuccessResponse but handler returns flexible dict
)
# router.add_api_route("/refresh-session", refresh_session, methods=["POST"], response_model=Dict[str, Any])

router.add_api_route(
    "/logout",
    logout,
    methods=["POST"],
    response_model=AuthMessageResponse
)

router.add_api_route(
    "/change-password",
    change_password,
    methods=["PATCH"],  # Changed from POST to PATCH (partial update - modifying password field only)
    response_model=AuthMessageResponse,
    tags=["Auth"]
)
router.add_api_route(
    "/delete-account",
    delete_account,
    methods=["DELETE"],  # Changed from POST to DELETE (more RESTful for resource deletion)
    response_model=AuthMessageResponse,
    tags=["Auth"]
)

router.add_api_route(
    "/update-email",
    update_email,
    methods=["PATCH"],  # Changed from POST to PATCH (partial update - modifying email field only)
    response_model=AuthMessageResponse,
    tags=["Auth"]
)

router.add_api_route(
    "/me",
    get_user_info,
    methods=["GET"],
    response_model=UserInfoResponse,
    summary="Get Current User Info",
    description="Get authenticated user's profile, tier, role, and quota information",
    tags=["Auth"]
)

router.add_api_route(
    "/confirm",
    confirm_email,
    methods=["GET"],
    summary="Confirm Email",
    description="Handle email confirmation from Supabase. Called when user clicks link in their confirmation email.",
    tags=["Auth"]
)

router.add_api_route(
    "/forgot-password",
    forgot_password,
    methods=["POST"],
    response_model=AuthMessageResponse,
    summary="Forgot Password",
    description="Request a password reset email. Always returns success to prevent email enumeration.",
    tags=["Auth"]
)

router.add_api_route(
    "/reset-password",
    reset_password,
    methods=["POST"],
    response_model=Dict[str, Any],  # TODO: Define proper schema for reset password response
    summary="Reset Password",
    description="Reset password using the access token from the recovery email link.",
    tags=["Auth"]
)

router.add_api_route(
    "/resend-verification",
    resend_verification_email,
    methods=["POST"],
    response_model=Dict[str, Any],  # TODO: Define proper schema for resend verification response
    summary="Resend Verification Email",
    description="Resend email verification link. Always returns success to prevent email enumeration.",
    tags=["Auth"]
)
