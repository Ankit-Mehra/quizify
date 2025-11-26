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
import time
from collections import OrderedDict
from threading import Lock
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


# ============================================================================
# Webhook Idempotency Store
# ============================================================================

class WebhookIdempotencyStore:
    """
    Thread-safe in-memory store for tracking processed webhook event IDs.
    
    Prevents duplicate webhook processing by storing event IDs with timestamps.
    Uses LRU eviction with TTL to prevent memory bloat.
    
    Note: For horizontal scaling, this should be replaced with Redis.
    """
    
    def __init__(self, max_size: int = 10000, ttl_seconds: int = 86400):
        """
        Initialize the idempotency store.
        
        Args:
            max_size: Maximum number of event IDs to store (LRU eviction)
            ttl_seconds: Time-to-live for event IDs (default: 24 hours)
        """
        self._store: OrderedDict[str, float] = OrderedDict()
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._lock = Lock()
    
    def is_duplicate(self, event_id: str) -> bool:
        """
        Check if an event ID has been processed before.
        
        Args:
            event_id: Stripe event ID (e.g., evt_xxx)
            
        Returns:
            True if event was already processed, False otherwise
        """
        with self._lock:
            self._cleanup_expired()
            
            if event_id in self._store:
                return True
            
            # Add event ID with current timestamp
            self._store[event_id] = time.time()
            
            # LRU eviction if store is full
            while len(self._store) > self._max_size:
                self._store.popitem(last=False)
            
            return False
    
    def _cleanup_expired(self) -> None:
        """Remove expired event IDs from the store."""
        current_time = time.time()
        expired_keys = [
            key for key, timestamp in self._store.items()
            if current_time - timestamp > self._ttl_seconds
        ]
        for key in expired_keys:
            del self._store[key]


# Global idempotency store instance
_webhook_idempotency_store = WebhookIdempotencyStore()


# ============================================================================
# Rate Limiter for Billing Endpoints (Redis-backed with memory fallback)
# ============================================================================

class BillingRateLimiter:
    """
    Redis-backed rate limiter with automatic memory fallback.
    
    Uses Redis INCR with TTL for distributed rate limiting across instances.
    Falls back to in-memory tracking if Redis is unavailable.
    
    Rate limiting strategy: Sliding window using Redis sorted sets.
    """
    
    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        """
        Initialize the rate limiter.
        
        Args:
            max_requests: Maximum requests per window
            window_seconds: Time window in seconds
        """
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._prefix = "billing:rate_limit:"
        
        # Memory fallback storage
        self._memory_requests: dict[str, list[float]] = {}
        self._memory_lock = Lock()
    
    async def is_rate_limited(self, user_id: str) -> bool:
        """
        Check if a user is rate limited.
        
        Uses Redis if available, falls back to memory otherwise.
        
        Args:
            user_id: User ID to check
            
        Returns:
            True if rate limited, False otherwise
        """
        from services.redis.client import get_redis_client
        
        redis_client = get_redis_client()
        
        if redis_client:
            try:
                return await self._check_redis(redis_client, user_id)
            except Exception as e:
                logger.warning(f"Redis rate limit check failed, using memory fallback: {e}")
        
        return self._check_memory(user_id)
    
    async def _check_redis(self, redis_client, user_id: str) -> bool:
        """
        Redis-based rate limiting using sorted sets for sliding window.
        
        Uses ZADD with timestamp as score, ZREMRANGEBYSCORE to cleanup,
        and ZCARD to count requests in window.
        """
        key = f"{self._prefix}{user_id}"
        current_time = time.time()
        window_start = current_time - self._window_seconds
        
        # Use pipeline for atomic operations
        pipe = redis_client.pipeline()
        
        # Remove old entries outside the window
        pipe.zremrangebyscore(key, 0, window_start)
        
        # Count current requests in window
        pipe.zcard(key)
        
        # Add current request with timestamp as score
        pipe.zadd(key, {str(current_time): current_time})
        
        # Set expiry on key (cleanup if user goes inactive)
        pipe.expire(key, self._window_seconds * 2)
        
        results = await pipe.execute()
        current_count = results[1]  # ZCARD result
        
        if current_count >= self._max_requests:
            logger.debug(f"Rate limit exceeded for user {user_id[:8]} (Redis): {current_count}/{self._max_requests}")
            return True
        
        return False
    
    def _check_memory(self, user_id: str) -> bool:
        """Memory fallback for rate limiting."""
        with self._memory_lock:
            current_time = time.time()
            window_start = current_time - self._window_seconds
            
            if user_id not in self._memory_requests:
                self._memory_requests[user_id] = []
            
            # Remove old requests
            self._memory_requests[user_id] = [
                ts for ts in self._memory_requests[user_id]
                if ts > window_start
            ]
            
            # Check limit
            if len(self._memory_requests[user_id]) >= self._max_requests:
                logger.debug(f"Rate limit exceeded for user {user_id[:8]} (memory): {len(self._memory_requests[user_id])}/{self._max_requests}")
                return True
            
            # Record request
            self._memory_requests[user_id].append(current_time)
            return False


# Global rate limiter for billing endpoints
# 10 requests per minute per user for checkout/portal sessions
_billing_rate_limiter = BillingRateLimiter(max_requests=10, window_seconds=60)


async def check_rate_limit(user_id: str = Depends(get_current_user_id)):
    """FastAPI dependency to check rate limit before processing."""
    if await _billing_rate_limiter.is_rate_limited(user_id):
        logger.warning(f"Rate limit exceeded for user {user_id[:8]}")
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please wait before trying again."
        )
    return user_id


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
    user_id: str = Depends(check_rate_limit),  # Rate limit before processing
    user_token: str = Depends(get_current_user_token),
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
        user_token=user_token,
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
    user_id: str = Depends(check_rate_limit),  # Rate limit before processing
    user_token: str = Depends(get_current_user_token),
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
    
    portal_url = await billing_service.create_portal_session(user_id, user_token)
    
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
    - Billing status:
        - no_subscription: User has never subscribed
        - active: Subscription is active and not scheduled for cancellation
        - canceling: Subscription is active but scheduled to cancel at period end
        - grace_period: Subscription is canceled but still within paid period
        - past_due: Payment failed, subscription at risk
        - expired: Subscription ended and grace period passed
    - Quota information (current count, limit, exceeded flag)
    
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
    - Checks event ID for idempotency (prevents duplicate processing)
    - Database updates use Supabase's atomic operations and RLS policies for consistency
    
    **Epic 3: Webhook processing IMPLEMENTED**
    """
    
    config = Config()
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    # Validate webhook secret is configured (server configuration issue)
    if not config.STRIPE_WEBHOOK_SECRET:
        logger.error("STRIPE_WEBHOOK_SECRET not configured")
        raise HTTPException(
            status_code=400,
            detail="Webhook endpoint not properly configured"
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
    
    # Idempotency check - prevent duplicate processing
    event_id = event["id"]
    if _webhook_idempotency_store.is_duplicate(event_id):
        logger.info(f"Webhook event {event_id} already processed, skipping")
        return {"status": "already_processed", "event_id": event_id}
    
    # Handle the event
    event_type = event["type"]
    data_object = event["data"]["object"]
    
    logger.info(f"Processing webhook event: {event_type} (ID: {event_id})")
    
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
            f"Error processing webhook {event_type} (ID: {event_id}): {e}",
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
