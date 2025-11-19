"""
Billing API routes for Stripe subscription management.

This module provides endpoints for:
- Creating checkout sessions (upgrade to paid tier)
- Creating customer portal sessions (manage subscription)
- Getting subscription status
- Handling Stripe webhooks

Epic 1: Infrastructure Setup - Skeleton routes returning 501 Not Implemented
Epic 2-4: Full implementation with Stripe integration
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from dependencies.auth_dependencies import get_current_user_id, get_current_user_token
from schemas.billing import (
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    PortalSessionResponse,
    SubscriptionStatusResponse,
)
from services.billing_service import BillingService
from config import Config

router = APIRouter(prefix="/api/billing", tags=["billing"])

# Placeholder for Supabase client initialization
# Will be properly initialized in Epic 2
def get_billing_service() -> BillingService:
    """
    Dependency to get BillingService instance.
    
    Epic 2: Initialize with proper Supabase client
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Billing service initialization not implemented yet (Epic 2)"
    )


# ============================================================================
# Checkout Session Endpoint
# ============================================================================

@router.post(
    "/create-checkout-session",
    response_model=CheckoutSessionResponse,
    status_code=status.HTTP_200_OK,
    summary="Create Stripe Checkout session",
    description=(
        "Create a Stripe Checkout session for upgrading to a paid tier. "
        "Returns a checkout URL to redirect the user to Stripe's payment page."
    ),
)
async def create_checkout_session(
    request: CheckoutSessionRequest,
    user_id: str = Depends(get_current_user_id),
    billing_service: BillingService = Depends(get_billing_service),
) -> CheckoutSessionResponse:
    """
    Create a Stripe Checkout session for subscription purchase.
    
    **Flow:**
    1. User clicks "Upgrade to Basic ($5/mo)" or "Upgrade to Pro ($15/mo)" on frontend
    2. Frontend calls this endpoint with tier selection
    3. Backend creates Stripe Checkout session
    4. Frontend redirects user to checkout URL
    5. User completes payment on Stripe
    6. Stripe webhook notifies backend of successful payment
    7. Backend provisions subscription and upgrades user tier
    8. User is redirected to success URL
    
    **Epic 2: Implement checkout session creation**
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "Checkout session creation not implemented yet (Epic 2). "
            "Will create Stripe Checkout session and return checkout URL."
        ),
    )


# ============================================================================
# Customer Portal Endpoint
# ============================================================================

@router.post(
    "/create-portal-session",
    response_model=PortalSessionResponse,
    status_code=status.HTTP_200_OK,
    summary="Create Stripe Customer Portal session",
    description=(
        "Create a Stripe Customer Portal session for managing subscription. "
        "Allows users to view invoices, update payment method, and cancel subscription."
    ),
)
async def create_portal_session(
    user_id: str = Depends(get_current_user_id),
    billing_service: BillingService = Depends(get_billing_service),
) -> PortalSessionResponse:
    """
    Create a Stripe Customer Portal session.
    
    **Flow:**
    1. User clicks "Manage Subscription" on frontend billing page
    2. Frontend calls this endpoint
    3. Backend creates Stripe Portal session
    4. Frontend redirects user to portal URL
    5. User manages subscription on Stripe's portal
    6. Changes sync back via webhooks
    
    **Requirements:**
    - User must have an active or canceled subscription (stripe_customer_id exists)
    
    **Epic 4: Implement portal session creation**
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "Customer Portal session creation not implemented yet (Epic 4). "
            "Will create Stripe Portal session and return portal URL."
        ),
    )


# ============================================================================
# Subscription Status Endpoint
# ============================================================================

@router.get(
    "/subscription-status",
    response_model=SubscriptionStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current subscription status",
    description=(
        "Get the user's current subscription and billing status, "
        "including tier, quota usage, and Stripe subscription details."
    ),
)
async def get_subscription_status(
    user_id: str = Depends(get_current_user_id),
) -> SubscriptionStatusResponse:
    """
    Get the user's current subscription and billing status.
    
    **Returns:**
    - Account tier (free, basic, educator)
    - Subscription status (active, canceled, past_due, etc.)
    - Billing status (no_subscription, active, grace_period, etc.)
    - Quota information (current count, limit, exceeded flag)
    - Grace period status (if subscription is canceled but still valid)
    
    **Epic 5: Implement subscription status query**
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "Subscription status query not implemented yet (Epic 5). "
            "Will query user_tier_info view and return subscription details."
        ),
    )


# ============================================================================
# Stripe Webhook Endpoint
# ============================================================================

@router.post(
    "/webhook",
    status_code=status.HTTP_200_OK,
    summary="Stripe webhook handler",
    description=(
        "Receives and processes Stripe webhook events for subscription lifecycle management. "
        "This endpoint is called by Stripe, not by the frontend."
    ),
    include_in_schema=False,  # Hide from OpenAPI docs (internal endpoint)
)
async def stripe_webhook(
    request: Request,
    billing_service: BillingService = Depends(get_billing_service),
):
    """
    Handle Stripe webhook events.
    
    **Webhook Events Handled:**
    - customer.subscription.created: New subscription created
    - customer.subscription.updated: Subscription status changed
    - customer.subscription.deleted: Subscription canceled
    - invoice.payment_succeeded: Successful payment
    - invoice.payment_failed: Failed payment
    
    **Security:**
    - Verifies webhook signature using STRIPE_WEBHOOK_SECRET
    - Implements idempotency to prevent duplicate processing
    
    **Epic 3: Implement webhook processing**
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "Webhook processing not implemented yet (Epic 3). "
            "Will verify signature, parse events, and update subscriptions."
        ),
    )


# ============================================================================
# Health Check Endpoint (for webhook URL validation)
# ============================================================================

@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Billing service health check",
    description="Health check endpoint for validating webhook URL configuration",
)
async def billing_health_check():
    """
    Health check for billing service.
    
    Used by Stripe to validate webhook endpoint URL during setup.
    """
    return {
        "status": "ok",
        "service": "billing",
        "message": "Billing service is operational (Epic 1: Infrastructure setup complete)",
    }
