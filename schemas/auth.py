"""Authentication request/response schemas"""
from pydantic import BaseModel
from typing import Optional


class SignupRequest(BaseModel):
    """Request model for user signup"""
    email: str
    password: str
    name: str


class LoginRequest(BaseModel):
    """Request model for user login"""
    email: str
    password: str


class LogoutRequest(BaseModel):
    """Request model for user logout"""
    token: Optional[str] = None


class UpdateEmailRequest(BaseModel):
    """Request model for updating user email"""
    new_email: str


class ChangePasswordRequest(BaseModel):
    """Request model for changing user password"""
    email: str
    new_password: str
