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
    # Note: email field removed - user identified by JWT token (user_id from Depends(get_current_user_id))
