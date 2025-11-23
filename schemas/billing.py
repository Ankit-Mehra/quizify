"""
Billing and subscription Pydantic schemas.

This module defines request/response models for Stripe billing operations,
including checkout sessions, customer portal, subscription status, and webhooks.
"""

from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field, HttpUrl


# ============================================================================
# Checkout Session Schemas
# ============================================================================

class CheckoutSessionRequest(BaseModel):
    """
    Request to create a Stripe Checkout session.
    
    Frontend sends this when user clicks "Upgrade to Basic" or "Upgrade to Pro".
    Backend returns a checkout URL to redirect the user to Stripe's hosted payment page.
    """
    tier: Literal["basic", "pro"] = Field(
        ...,
        description="The subscription tier to purchase (basic or pro)"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "tier": "basic"
            }
        }


class CheckoutSessionResponse(BaseModel):
    """
    Response containing Stripe Checkout session URL.
    
    Frontend should redirect user to this URL to complete payment.
    """
    checkout_url: HttpUrl = Field(
        ...,
        description="Stripe Checkout session URL - redirect user here"
    )
    session_id: str = Field(
        ...,
        description="Stripe Checkout session ID (cs_XXXXXXXXX)"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "checkout_url": "https://checkout.stripe.com/c/pay/cs_test_a1b2c3d4...",
                "session_id": "cs_test_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0"
            }
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
    """Response from checkout session verification"""
    session_id: str = Field(..., description="Checkout session ID")
    customer_id: str = Field(..., description="Stripe customer ID")
    subscription_id: str = Field(..., description="Stripe subscription ID")
    tier: str = Field(..., description="Account tier (basic/pro)")
    status: str = Field(..., description="Subscription status")
    current_period_end: Optional[int] = Field(None, description="Unix timestamp of period end")
    payment_status: str = Field(..., description="Payment status (paid/unpaid)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "cs_test_a1b2c3d4e5f6g7h8i9j0",
                "customer_id": "cus_ABC123xyz",
                "subscription_id": "sub_DEF456uvw",
                "tier": "basic",
                "status": "active",
                "current_period_end": 1734566400,
                "payment_status": "paid"
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
    """
    account_tier: Literal["free", "basic", "pro"] = Field(
        ...,
        description="Current account tier"
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
                "account_tier": "basic",
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
