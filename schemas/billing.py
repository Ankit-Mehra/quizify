"""
Billing and subscription Pydantic schemas.

This module defines request/response models for Stripe billing operations,
including checkout sessions, customer portal, subscription status, and webhooks.
"""

from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field, HttpUrl, model_validator


# ============================================================================
# Checkout Session Schemas
# ============================================================================

class CheckoutSessionRequest(BaseModel):
    """
    Request to create a Stripe Checkout session.
    
    Frontend sends this when user clicks "Upgrade to Pro".
    Backend returns a checkout URL to redirect the user to Stripe's hosted payment page.
    
    Note: 'premium' is accepted for backward compatibility but maps to 'pro'.
    """
    tier: Literal["pro"] = Field(
        ...,
        description="The subscription tier to purchase (pro)"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "tier": "pro"
            }
        }


class CheckoutSessionResponse(BaseModel):
    """
    Response containing Stripe Checkout session URL OR upgrade confirmation.
    
    For new subscriptions: Frontend should redirect user to checkout_url.
    For upgrades: Returns status and message, no redirect needed.
    
    Response type is determined by the presence of fields:
    - If checkout_url is present → new subscription flow
    - If status is present → upgrade/downgrade flow
    """
    # For new subscriptions
    checkout_url: Optional[HttpUrl] = Field(
        None,
        description="Stripe Checkout session URL - redirect user here (only for new subscriptions)"
    )
    session_id: Optional[str] = Field(
        None,
        description="Stripe Checkout session ID (cs_XXXXXXXXX) (only for new subscriptions)"
    )
    
    # For subscription upgrades/downgrades
    status: Optional[str] = Field(
        None,
        description="Status: 'upgraded', 'downgraded', or 'already_subscribed'"
    )
    message: Optional[str] = Field(
        None,
        description="Human-readable message about the upgrade/downgrade"
    )
    subscription_id: Optional[str] = Field(
        None,
        description="Subscription ID (for upgrades/downgrades)"
    )
    
    @model_validator(mode='after')
    def validate_response_type(self) -> 'CheckoutSessionResponse':
        """
        Ensure response is either a checkout response OR an upgrade response, not a mix.
        This prevents invalid states where some fields from both types are present.
        """
        has_checkout = self.checkout_url is not None or self.session_id is not None
        has_upgrade = self.status is not None
        
        if has_checkout and has_upgrade:
            raise ValueError(
                "Response cannot contain both checkout fields (checkout_url/session_id) "
                "and upgrade fields (status). Must be one or the other."
            )
        
        if not has_checkout and not has_upgrade:
            raise ValueError(
                "Response must contain either checkout fields (checkout_url, session_id) "
                "or upgrade fields (status, message, subscription_id)."
            )
        
        # Validate checkout response has both required fields
        if has_checkout and (self.checkout_url is None or self.session_id is None):
            raise ValueError(
                "Checkout response must include both checkout_url and session_id."
            )
        
        # Validate upgrade response has required fields
        if has_upgrade and (self.message is None or self.subscription_id is None):
            raise ValueError(
                "Upgrade response must include status, message, and subscription_id."
            )
        
        return self
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "description": "New subscription checkout",
                    "value": {
                        "checkout_url": "https://checkout.stripe.com/c/pay/cs_test_a1b2c3d4...",
                        "session_id": "cs_test_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0"
                    }
                },
                {
                    "description": "Subscription upgrade",
                    "value": {
                        "status": "upgraded",
                        "message": "Successfully upgraded to pro",
                        "subscription_id": "sub_abc123"
                    }
                },
                {
                    "description": "Subscription downgrade",
                    "value": {
                        "status": "downgraded",
                        "message": "Successfully downgraded to basic (effective next billing cycle)",
                        "subscription_id": "sub_abc123"
                    }
                }
            ]
        }


# ============================================================================
# Customer Portal Schemas
# ============================================================================

class PortalSessionResponse(BaseModel):
    """
    Response containing Stripe Customer Portal URL.
    
    Frontend should redirect user to this URL to manage their subscription
    (view invoices, update payment method, cancel subscription).
    """
    portal_url: HttpUrl = Field(
        ...,
        description="Stripe Customer Portal URL - redirect user here"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "portal_url": "https://billing.stripe.com/p/session/test_YWNjdF8xT..."
            }
        }


class CheckoutSessionVerification(BaseModel):
    """
    Response from checkout session verification.
    
    Called by frontend after user returns from Stripe Checkout to confirm
    payment was successful and check subscription provisioning status.
    
    The 'provisioned' field indicates if the webhook has already processed
    the subscription. If False, frontend should poll /subscription-status
    until the tier is updated.
    """
    session_id: str = Field(..., description="Checkout session ID")
    customer_id: str = Field(..., description="Stripe customer ID")
    subscription_id: str = Field(..., description="Stripe subscription ID")
    tier: str = Field(..., description="Account tier (premium/pro)")
    status: str = Field(..., description="Subscription status")
    current_period_end: Optional[int] = Field(None, description="Unix timestamp of period end")
    payment_status: str = Field(..., description="Payment status (paid/unpaid)")
    provisioned: bool = Field(
        default=False, 
        description="True if subscription is already active in database. "
                    "If False, webhook is still processing - poll /subscription-status."
    )
    message: Optional[str] = Field(
        None,
        description="Human-readable status message for UI display"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "cs_test_a1b2c3d4e5f6g7h8i9j0",
                "customer_id": "cus_ABC123xyz",
                "subscription_id": "sub_DEF456uvw",
                "tier": "pro",
                "status": "active",
                "current_period_end": 1734566400,
                "payment_status": "paid",
                "provisioned": True,
                "message": "Subscription active"
            }
        }


# ============================================================================
# Subscription Status Schemas
# ============================================================================

class SubscriptionStatusResponse(BaseModel):
    """
    Current subscription and billing status for a user.
    
    Returned by GET /api/billing/subscription-status endpoint.
    Frontend uses this to display billing information and subscription details.
    
    Note: account_tier may be 'premium' for legacy users (maps to 'pro').
    """
    account_tier: Literal["free", "premium", "pro"] = Field(
        ...,
        description="Current account tier (premium is legacy, treated as pro)"
    )
    subscription_status: Optional[str] = Field(
        None,
        description="Stripe subscription status (null for free tier)"
    )
    billing_status: str = Field(
        ...,
        description="Human-readable billing status"
    )
    stripe_customer_id: Optional[str] = Field(
        None,
        description="Stripe customer ID (null if never subscribed)"
    )
    stripe_subscription_id: Optional[str] = Field(
        None,
        description="Stripe subscription ID (null for free tier)"
    )
    subscription_canceled_at: Optional[str] = Field(
        None,
        description="ISO timestamp when subscription was canceled (null if active)"
    )
    current_period_start: Optional[str] = Field(
        None,
        description="ISO timestamp for start of current billing period"
    )
    current_period_end: Optional[str] = Field(
        None,
        description="ISO timestamp for end of current billing period"
    )
    current_quiz_count: int = Field(
        ...,
        description="Number of quizzes user has created"
    )
    quota_limit: int = Field(
        ...,
        description="Maximum quizzes allowed for current tier"
    )
    quota_exceeded: bool = Field(
        ...,
        description="True if user has reached quota limit"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "account_tier": "premium",
                "subscription_status": "active",
                "billing_status": "active",
                "stripe_customer_id": "cus_ABC123XYZ789",
                "stripe_subscription_id": "sub_DEF456UVW012",
                "subscription_canceled_at": None,
                "current_period_start": "2025-11-01T00:00:00Z",
                "current_period_end": "2025-12-01T00:00:00Z",
                "in_grace_period": False,
                "current_quiz_count": 42,
                "quota_limit": 100,
                "quota_exceeded": False
            }
        }


# ============================================================================
# Webhook Event Schemas
# ============================================================================

class WebhookEventMetadata(BaseModel):
    """
    Metadata extracted from Stripe webhook events.
    
    Used internally by webhook handler to process subscription events.
    Not exposed in API responses.
    """
    event_id: str = Field(
        ...,
        description="Stripe event ID (evt_XXXXXXXXX) for idempotency"
    )
    event_type: str = Field(
        ...,
        description="Stripe event type (e.g., customer.subscription.created)"
    )
    customer_id: str = Field(
        ...,
        description="Stripe customer ID (cus_XXXXXXXXX)"
    )
    subscription_id: Optional[str] = Field(
        None,
        description="Stripe subscription ID (sub_XXXXXXXXX) if applicable"
    )
    subscription_status: Optional[str] = Field(
        None,
        description="Stripe subscription status if applicable"
    )
    price_id: Optional[str] = Field(
        None,
        description="Stripe price ID to determine tier"
    )
    cancel_at: Optional[datetime] = Field(
        None,
        description="Subscription cancellation timestamp if applicable"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "event_id": "evt_1A2B3C4D5E6F7G8H9I0J1K2L",
                "event_type": "customer.subscription.created",
                "customer_id": "cus_ABC123XYZ789",
                "subscription_id": "sub_DEF456UVW012",
                "subscription_status": "active",
                "price_id": "price_1A2B3C4D5E6F7G8H",
                "cancel_at": None
            }
        }


# ============================================================================
# Upgrade Preview Schemas
# ============================================================================

class UpgradePreviewRequest(BaseModel):
    """
    Request to preview upgrade/downgrade cost before confirming.
    
    Frontend calls this to show the user what they'll be charged (proration)
    before they confirm the subscription change.
    """
    tier: Literal["premium", "pro"] = Field(
        ...,
        description="The target subscription tier to preview"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "tier": "pro"
            }
        }


class UpgradePreviewResponse(BaseModel):
    """
    Response containing proration preview for subscription upgrade/downgrade.
    
    Shows the user exactly what they'll be charged, including:
    - Credit for unused time on current plan
    - Charge for remaining time on new plan
    - Net amount due today
    - What the next regular invoice will be
    """
    # Current subscription info
    current_tier: str = Field(
        ...,
        description="User's current subscription tier"
    )
    target_tier: str = Field(
        ...,
        description="The tier user wants to upgrade/downgrade to"
    )
    
    # Proration details
    is_upgrade: bool = Field(
        ...,
        description="True if upgrading (higher tier), False if downgrading"
    )
    proration_amount: int = Field(
        ...,
        description="Amount charged today in cents (positive = charge, negative = credit)"
    )
    proration_amount_formatted: str = Field(
        ...,
        description="Human-readable proration amount (e.g., '$2.50')"
    )
    
    # Credit/Debit breakdown
    credit_amount: int = Field(
        ...,
        description="Credit for unused time on current plan (in cents, always positive or zero)"
    )
    credit_amount_formatted: str = Field(
        ...,
        description="Human-readable credit amount"
    )
    debit_amount: int = Field(
        ...,
        description="Charge for remaining time on new plan (in cents, always positive)"
    )
    debit_amount_formatted: str = Field(
        ...,
        description="Human-readable debit amount"
    )
    
    # Future billing
    next_billing_amount: int = Field(
        ...,
        description="Amount of next regular billing (in cents)"
    )
    next_billing_amount_formatted: str = Field(
        ...,
        description="Human-readable next billing amount (e.g., '$15.00/month')"
    )
    next_billing_date: datetime = Field(
        ...,
        description="Date of next regular billing"
    )
    
    # Payment method
    card_last4: Optional[str] = Field(
        None,
        description="Last 4 digits of card on file (e.g., '4242')"
    )
    card_brand: Optional[str] = Field(
        None,
        description="Card brand (e.g., 'visa', 'mastercard')"
    )
    
    # For frontend messaging
    message: str = Field(
        ...,
        description="Human-readable summary for the user"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "current_tier": "premium",
                "target_tier": "pro",
                "is_upgrade": True,
                "proration_amount": 250,
                "proration_amount_formatted": "$2.50",
                "credit_amount": 500,
                "credit_amount_formatted": "$5.00",
                "debit_amount": 750,
                "debit_amount_formatted": "$7.50",
                "next_billing_amount": 1500,
                "next_billing_amount_formatted": "$15.00/month",
                "next_billing_date": "2025-12-15T00:00:00Z",
                "card_last4": "4242",
                "card_brand": "visa",
                "message": "You'll be charged $2.50 today. Then $15.00/month starting Dec 15."
            }
        }


# ============================================================================
# Storage Quota Schemas
# ============================================================================

class StorageQuotaResponse(BaseModel):
    """
    Response containing user's storage quota information.
    
    Storage Quotas:
    - Free plan: 250 MB
    - Pay-as-you-go (purchased credits, no subscription): 2 GB
    - Pro subscription: 5 GB
    """
    user_id: str = Field(..., description="User ID")
    plan_type: Literal["free", "payg", "pro"] = Field(
        ...,
        description="Plan type for storage quota purposes"
    )
    storage_used_bytes: int = Field(
        ...,
        description="Current storage usage in bytes"
    )
    storage_quota_bytes: int = Field(
        ...,
        description="Maximum allowed storage in bytes"
    )
    storage_remaining_bytes: int = Field(
        ...,
        description="Remaining available storage in bytes"
    )
    storage_used_formatted: str = Field(
        ...,
        description="Human-readable storage usage (e.g., '125.5 MB')"
    )
    storage_quota_formatted: str = Field(
        ...,
        description="Human-readable storage quota (e.g., '250 MB')"
    )
    storage_remaining_formatted: str = Field(
        ...,
        description="Human-readable remaining storage (e.g., '124.5 MB')"
    )
    usage_percentage: float = Field(
        ...,
        description="Storage usage as percentage (0-100)"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                "plan_type": "free",
                "storage_used_bytes": 52428800,
                "storage_quota_bytes": 262144000,
                "storage_remaining_bytes": 209715200,
                "storage_used_formatted": "50.0 MB",
                "storage_quota_formatted": "250 MB",
                "storage_remaining_formatted": "200.0 MB",
                "usage_percentage": 20.0
            }
        }


class StorageQuotaExceededError(BaseModel):
    """
    Error detail when storage quota is exceeded.
    Returned with HTTP 402 status code.
    """
    error: Literal["storage_quota_exceeded"] = "storage_quota_exceeded"
    message: str = Field(
        ...,
        description="Human-readable error message with upgrade suggestions"
    )
    storage_used_bytes: int = Field(
        ...,
        description="Current storage usage in bytes"
    )
    storage_quota_bytes: int = Field(
        ...,
        description="Maximum allowed storage in bytes"
    )
    storage_remaining_bytes: int = Field(
        ...,
        description="Remaining available storage in bytes"
    )
    file_size_bytes: int = Field(
        ...,
        description="Size of the file that was rejected"
    )
    plan: Literal["free", "payg", "pro"] = Field(
        ...,
        description="User's current plan type"
    )
    storage_used_formatted: str = Field(
        ...,
        description="Human-readable storage usage"
    )
    storage_quota_formatted: str = Field(
        ...,
        description="Human-readable storage quota"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "error": "storage_quota_exceeded",
                "message": "Storage quota exceeded. You have used 245 MB of your 250 MB limit. Purchase credits to unlock 2 GB storage, or upgrade to Pro for 5 GB storage.",
                "storage_used_bytes": 256901120,
                "storage_quota_bytes": 262144000,
                "storage_remaining_bytes": 5242880,
                "file_size_bytes": 10485760,
                "plan": "free",
                "storage_used_formatted": "245 MB",
                "storage_quota_formatted": "250 MB"
            }
        }


# ============================================================================
# Billing State Schema (Epic 2.2)
# ============================================================================

class UserBillingState(BaseModel):
    """
    Represents the user's current billing and credit state.
    Maps to the extended profiles table structure.
    """
    user_id: str
    plan: Literal["free", "pro"]
    credit_units_monthly: int  # legacy monthly field (kept for compatibility)
    credit_units_remaining: int  # subscription/paid recurring bucket
    credit_units_purchased: int  # paid one-time (credit packs)
    free_credit_units_monthly: int = 6
    free_credit_units_remaining: int = 6
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    
    @property
    def available_units(self) -> int:
        return (
            self.credit_units_purchased
            + self.credit_units_remaining
            + self.free_credit_units_remaining
        )
    
    @property
    def available_credits(self) -> float:
        return self.available_units / 2.0
