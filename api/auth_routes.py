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
    resend_verification_email,
    logout_all_devices,
    get_active_sessions,
    revoke_session,
    google_connect,
    google_callback,
    google_disconnect,
    google_status
)
from schemas.auth import AuthMessageResponse, UserInfoResponse
from typing import Dict, Any, List
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
    methods=["GET", "OPTIONS"],  # OPTIONS required for CORS preflight when X-Refresh-Token header is sent
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

# ============================================================================
# SESSION MANAGEMENT ENDPOINTS (Epic 4 - Task 4.3 & 4.4)
# ============================================================================

router.add_api_route(
    "/logout-all-devices",
    logout_all_devices,
    methods=["POST"],
    response_model=Dict[str, Any],
    summary="Logout All Devices",
    description="Logout from all devices. Deletes all Redis sessions and forces re-login. Useful for security actions like password change.",
    tags=["Auth", "Session Management"]
)

router.add_api_route(
    "/sessions",
    get_active_sessions,
    methods=["GET"],
    response_model=List[Dict[str, Any]],
    summary="Get Active Sessions",
    description="Get list of active sessions for current user across all devices. Shows device type, last activity, IP (hashed), and user agent.",
    tags=["Auth", "Session Management"]
)

router.add_api_route(
    "/sessions/{session_id_to_revoke}",
    revoke_session,
    methods=["DELETE"],
    response_model=Dict[str, Any],
    summary="Revoke Session",
    description="Revoke a specific session by ID. User can only revoke their own sessions. Useful for removing suspicious or lost devices.",
    tags=["Auth", "Session Management"]
)

# ============================================================================
# GOOGLE OAUTH ENDPOINTS (Epic QUIZ-002 - Google Forms Export)
# ============================================================================

router.add_api_route(
    "/google/connect",
    google_connect,
    methods=["GET"],
    response_model=Dict[str, Any],
    summary="Connect Google Account",
    description="Initiate Google OAuth flow to connect user's Google account for Google Forms export.",
    tags=["Auth", "Google OAuth"]
)

router.add_api_route(
    "/google/callback",
    google_callback,
    methods=["GET"],
    summary="Google OAuth Callback",
    description="Handle OAuth callback from Google. Exchanges code for tokens and stores refresh token.",
    tags=["Auth", "Google OAuth"]
)

router.add_api_route(
    "/google/disconnect",
    google_disconnect,
    methods=["POST"],
    response_model=Dict[str, Any],
    summary="Disconnect Google Account",
    description="Remove Google OAuth tokens. User will need to re-authorize to use Google Forms export.",
    tags=["Auth", "Google OAuth"]
)

router.add_api_route(
    "/google/status",
    google_status,
    methods=["GET"],
    response_model=Dict[str, Any],
    summary="Google Connection Status",
    description="Check if user has connected their Google account and can export to Google Forms.",
    tags=["Auth", "Google OAuth"]
)
