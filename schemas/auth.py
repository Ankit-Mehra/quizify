"""Authentication request/response schemas"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from schemas.user import ACCOUNT_TIERS, USER_ROLES


class SignupRequest(BaseModel):
    """Request model for user signup"""
    email: EmailStr  # Validates email format
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters")
    name: str = Field(..., min_length=1, description="Name cannot be empty")


class LoginRequest(BaseModel):
    """Request model for user login"""
    email: EmailStr  # Validates email format
    password: str


class LogoutRequest(BaseModel):
    """Request model for user logout"""
    token: Optional[str] = None


class UpdateEmailRequest(BaseModel):
    """Request model for updating user email"""
    new_email: EmailStr  # Validates email format


class ChangePasswordRequest(BaseModel):
    """Request model for changing user password - user identified by JWT token"""
    current_password: str = Field(..., description="Current password for verification")
    new_password: str = Field(..., min_length=8, description="New password must be at least 8 characters")


class ForgotPasswordRequest(BaseModel):
    """Request model for forgot password - triggers password reset email"""
    email: EmailStr  # Validates email format


class ResetPasswordRequest(BaseModel):
    """Request model for resetting password with recovery token"""
    token: Optional[str] = Field(None, description="(Deprecated) Access token - now read from HttpOnly cookie")
    refresh_token: Optional[str] = Field(None, description="(Deprecated) Refresh token - now read from HttpOnly cookie")
    new_password: str = Field(..., min_length=8, description="New password must be at least 8 characters")


class ResendVerificationRequest(BaseModel):
    """Request model for resending email verification"""
    email: EmailStr  # Validates email format


# === Auth Response Schemas ===

class AuthSuccessResponse(BaseModel):
    """Response for successful authentication (login/signup)"""
    message: str
    user_id: str
    email: str
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None


class AuthMessageResponse(BaseModel):
    """Simple message response for auth operations"""
    message: str


class UserInfoResponse(BaseModel):
    """Response for GET /auth/me endpoint"""
    user_id: str
    email: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None  # User's avatar URL from OAuth providers (Google, etc.)
    account_tier: ACCOUNT_TIERS
    role: USER_ROLES
    current_quiz_count: int  # Number of quizzes created
    quizzes_attempted: int  # Number of quizzes attempted (submissions)
    quota_limit: int
    quota_exceeded: bool
    created_at: Optional[str] = None
    
    # New credit fields (Epic 6.3)
    available_credits: Optional[float] = None
    monthly_credits: Optional[float] = None
    purchased_credits: Optional[float] = None
    plan: Optional[str] = None
    period_end: Optional[str] = None


class AdminUpdateResponse(BaseModel):
    """Response for admin update operations (tier/role changes)"""
    message: str
    user_id: str
    updated_field: str  # "tier" or "role"
    new_value: str  # New tier or role value


# === Google OAuth Sign-In Schemas (for Supabase Auth) ===

class GoogleSignInRequest(BaseModel):
    """Request model for Google Sign-In using ID token from Google Sign-In button"""
    id_token: str = Field(..., description="Google ID token (JWT credential) from Google Sign-In")
    nonce: Optional[str] = Field(None, description="Optional nonce for extra security (must match the one used in Google Sign-In)")


class GoogleOAuthUrlResponse(BaseModel):
    """Response containing Google OAuth URL for PKCE flow"""
    auth_url: str = Field(..., description="URL to redirect user to for Google Sign-In")
    message: str = "Redirect to auth_url to complete Google Sign-In"


class OAuthCallbackResponse(BaseModel):
    """Response for OAuth callback - contains session tokens"""
    message: str
    user_id: str
    email: str
    access_token: Optional[str] = None  # Only in dev mode or via cookies
    refresh_token: Optional[str] = None  # Only in dev mode or via cookies
    is_new_user: bool = False  # True if this is the user's first login
