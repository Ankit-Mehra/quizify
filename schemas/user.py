from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Literal
from uuid import UUID

# Account tier options (legacy - kept for backward compatibility)
# IMPORTANT: These values MUST match the database CHECK constraint
# Database constraint: CHECK (account_tier IN ('free', 'premium', 'pro'))
# Note: 'basic' was renamed to 'premium' in migration 020
# DEPRECATED: Use billing_plan ('free'/'pro') for new code - premium maps to pro
ACCOUNT_TIERS = Literal["free", "premium", "pro"]

# Billing plan options (new credit-based system)
# This is the preferred model - premium users are mapped to 'pro'
BILLING_PLANS = Literal["free", "pro"]

# User role options  
# IMPORTANT: These values MUST match migrations/004_add_rbac_roles.sql CHECK constraint
# Database constraint: CHECK (role IN ('user', 'admin', 'moderator'))
USER_ROLES = Literal["user", "admin", "moderator"]

class User(BaseModel):
    email: str
    password: str

class UserProfile(BaseModel):
    """User profile with account tier and role information from profiles table"""
    id: UUID
    email: str
    display_name: Optional[str] = None  # User's display name from signup
    account_tier: ACCOUNT_TIERS = "free"
    role: USER_ROLES = "user"
    created_at: Optional[datetime] = None

class UserTierInfo(BaseModel):
    """User tier information with quota details and role"""
    id: UUID
    email: str
    display_name: Optional[str] = None  # User's display name
    account_tier: ACCOUNT_TIERS
    role: USER_ROLES = "user"
    current_quiz_count: int
    quota_limit: int
    quota_exceeded: bool
    
    # New credit fields (Epic 6.3)
    available_credits: Optional[float] = None
    monthly_credits: Optional[float] = None
    purchased_credits: Optional[float] = None
    plan: Optional[str] = None
    period_end: Optional[datetime] = None

class TierUpgradeRequest(BaseModel):
    """Request to upgrade user's account tier"""
    target_tier: Literal["pro"] = Field(
        ..., 
        description="Target tier to upgrade to (pro is the only paid tier)"
    )

class UserTierUpdate(BaseModel):
    """Admin request to update a user's tier"""
    new_tier: ACCOUNT_TIERS = Field(
        ...,
        description="New tier for the user (free, premium, pro)"
    )
    reason: Optional[str] = Field(
        None,
        description="Optional reason for the tier change (for audit logs)"
    )

class UserWithTier(BaseModel):
    """User information with tier, role, and quota details"""
    id: str
    email: str
    display_name: Optional[str] = None  # User's display name
    account_tier: ACCOUNT_TIERS
    role: USER_ROLES = "user"
    current_quiz_count: int
    quota_limit: int
    quota_exceeded: bool
    created_at: Optional[str] = None


class RoleUpdate(BaseModel):
    """Admin request to update a user's role"""
    new_role: USER_ROLES = Field(
        ...,
        description="New role for the user (user, admin, moderator)"
    )
    reason: Optional[str] = Field(
        None,
        description="Optional reason for the role change (for audit logs)"
    )

