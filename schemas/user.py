from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Literal
from uuid import UUID

class User(BaseModel):
    email: str
    password: str

class UserProfile(BaseModel):
    """User profile with account tier information from profiles table"""
    id: UUID
    email: str
    account_tier: Literal["free", "basic", "educator"] = "free"
    created_at: Optional[datetime] = None

class UserTierInfo(BaseModel):
    """User tier information with quota details"""
    id: UUID
    email: str
    account_tier: Literal["free", "basic", "educator"]
    current_quiz_count: int
    quota_limit: int
    quota_exceeded: bool

class TierUpgradeRequest(BaseModel):
    """Request to upgrade user's account tier"""
    target_tier: Literal["basic", "educator"] = Field(
        ..., 
        description="Target tier to upgrade to (cannot downgrade to free)"
    )

