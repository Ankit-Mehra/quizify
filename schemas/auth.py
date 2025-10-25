"""Authentication request/response schemas"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional


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
    token: str = Field(..., description="Recovery token from email link")
    new_password: str = Field(..., min_length=8, description="New password must be at least 8 characters")


class ResendVerificationRequest(BaseModel):
    """Request model for resending email verification"""
    email: EmailStr  # Validates email format
