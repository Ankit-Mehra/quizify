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
    new_password: str = Field(..., min_length=8, description="Password must be at least 8 characters")


class ForgotPasswordRequest(BaseModel):
    """Request model for forgot password - triggers password reset email"""
    email: EmailStr  # Validates email format


class ResetPasswordRequest(BaseModel):
    """Request model for resetting password with recovery token"""
    token: str = Field(..., description="Access token from recovery email redirect")
    refresh_token: Optional[str] = Field(None, description="Refresh token from recovery email redirect")
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
    account_tier: ACCOUNT_TIERS
    role: USER_ROLES
    current_quiz_count: int  # Number of quizzes created
    quizzes_attempted: int  # Number of quizzes attempted (submissions)
    quota_limit: int
    quota_exceeded: bool
    created_at: Optional[str] = None


class AdminUpdateResponse(BaseModel):
    """Response for admin update operations (tier/role changes)"""
    message: str
    user_id: str
    updated_field: str  # "tier" or "role"
    new_value: str  # New tier or role value
