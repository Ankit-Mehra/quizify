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
import stripe
from dependencies.auth_dependencies import get_current_user_id, get_current_user_token, get_current_user_email
from schemas.billing import (
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    PortalSessionResponse,
    SubscriptionStatusResponse,
    CheckoutSessionVerification,
)
from services.billing_service import BillingService
from services.db_services.supabase_quiz import get_supabase
from config import Config
from handlers.billing_handler import verify_checkout_session
from services.logger import app_logger as logger

router = APIRouter(prefix="/api/billing", tags=["billing"])

# Initialize BillingService with Supabase client
def get_billing_service() -> BillingService:
    """
    Dependency to get BillingService instance.
    
    Initialized with service role Supabase client for webhook handling
    and admin operations (like querying profiles).
    """
    return BillingService(get_supabase())


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
    email: str = Depends(get_current_user_email),
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
    """
    return await billing_service.create_checkout_session(
        user_id=user_id,
        email=email,
        tier=request.tier
    )


# ============================================================================
# Checkout Verification Endpoint
# ============================================================================

@router.get(
    "/verify-session/{session_id}",
    response_model=CheckoutSessionVerification,
    status_code=status.HTTP_200_OK,
    summary="Verify Checkout Session",
    description="Verify checkout session after successful payment",
)
async def verify_session(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
    billing_service: BillingService = Depends(get_billing_service),
) -> CheckoutSessionVerification:
    """
    Verify checkout session and return subscription details.
    
    Called by frontend after user returns from Stripe Checkout.
    
    **Returns:**
    - Subscription details including tier, status, period end
    
    **Errors:**
    - `403`: Session does not belong to authenticated user
    - `404`: Session ID not found
    - `400`: Payment not complete
    - `500`: Stripe API error
    """
    logger.info(
        f"Verifying checkout session {session_id} for user {user_id[:8]}"
    )
    
    result = await verify_checkout_session(session_id, user_id, billing_service)
    
    return result


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
    
    **Epic 4: Portal session creation IMPLEMENTED**
    """
    logger.info(f"Creating portal session for user {user_id[:8]}")
    
    portal_url = await billing_service.create_portal_session(user_id)
    
    return PortalSessionResponse(portal_url=portal_url)


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
    billing_service: BillingService = Depends(get_billing_service),
) -> SubscriptionStatusResponse:
    """
    Get the user's current subscription and billing status.
    
    **Returns:**
    - Account tier (free, basic, pro)
    - Subscription status (active, canceled, past_due, etc.)
    - Billing status (no_subscription, active, grace_period, etc.)
    - Quota information (current count, limit, exceeded flag)
    - Grace period status (if subscription is canceled but still valid)
    
    **Epic 5: Subscription status query IMPLEMENTED**
    """
    logger.info(f"Getting subscription status for user {user_id[:8]}")
    
    status_data = await billing_service.get_subscription_status(user_id)
    
    return status_data


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
    - checkout.session.completed: Checkout completed (initial subscription)
    - customer.subscription.created: New subscription created
    - customer.subscription.updated: Subscription status changed
    - customer.subscription.deleted: Subscription canceled
    - invoice.paid: Successful payment
    - invoice.payment_failed: Failed payment
    
    **Security:**
    - Verifies webhook signature using STRIPE_WEBHOOK_SECRET
    - Uses database transactions to handle concurrent webhook deliveries
    
    **Note:** Stripe has built-in idempotency for webhook retries. For additional 
    protection against race conditions, consider implementing event ID tracking in future.
    
    **Epic 3: Webhook processing IMPLEMENTED**
    """
    
    config = Config()
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    if not config.STRIPE_WEBHOOK_SECRET:
        logger.error("STRIPE_WEBHOOK_SECRET not configured")
        raise HTTPException(
            status_code=500,
            detail="Webhook secret not configured"
        )
    
    try:
        # Verify webhook signature
        event = stripe.Webhook.construct_event(
            payload, sig_header, config.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        # Invalid payload
        logger.error(f"Invalid webhook payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.SignatureVerificationError as e:
        # Invalid signature
        logger.error(f"Invalid webhook signature: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    # Handle the event
    event_type = event["type"]
    data_object = event["data"]["object"]
    
    logger.info(f"Processing webhook event: {event_type} (ID: {event['id']})")
    
    try:
        if event_type == "checkout.session.completed":
            # Payment successful, subscription created via Checkout
            await billing_service.handle_checkout_completed(data_object)
            
        elif event_type == "customer.subscription.created":
            # New subscription created (can also happen outside of Checkout)
            await billing_service.handle_subscription_created(data_object)
            
        elif event_type == "customer.subscription.updated":
            # Subscription status changed (renewal, upgrade, downgrade)
            await billing_service.handle_subscription_updated(data_object)
            
        elif event_type == "customer.subscription.deleted":
            # Subscription canceled or expired
            await billing_service.handle_subscription_deleted(data_object)
            
        elif event_type == "invoice.paid":
            # Successful payment (recurring or initial)
            await billing_service.handle_invoice_paid(data_object)
            
        elif event_type == "invoice.payment_failed":
            # Payment failed
            await billing_service.handle_invoice_payment_failed(data_object)
            
        else:
            logger.info(f"Unhandled webhook event type: {event_type}")
    
    except Exception as e:
        logger.error(
            f"Error processing webhook {event_type} (ID: {event['id']}): {e}",
            exc_info=True
        )
        # Return 500 so Stripe retries the webhook
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process webhook: {str(e)}"
        )
    
    return {"status": "success", "event_type": event_type}


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
