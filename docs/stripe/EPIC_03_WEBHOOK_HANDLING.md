# Epic 3: Webhook Handling & Subscription Provisioning (Days 5-7)

**Status**: Not Started  
**Duration**: 3 days  
**Priority**: Critical (Blocking)  
**Dependencies**: Epic 1 (Infrastructure), Epic 2 (Checkout Flow)

---

## Overview

Implement secure webhook endpoint to receive Stripe events and automatically provision/manage user subscription tiers based on payment status.

---

## Tasks Breakdown

### Task 3.1: Implement Webhook Signature Verification (2 hours)

**File**: `services/billing_service.py`

**Action**: Add signature verification method

```python
def verify_webhook_signature(
    self,
    payload: bytes,
    signature: str
) -> stripe.Event:
    """
    Verify Stripe webhook signature for security
    
    Args:
        payload: Raw request body bytes
        signature: Stripe-Signature header value
        
    Returns:
        Verified Stripe Event object
        
    Raises:
        HTTPException: If signature verification fails
    """
    if not config.STRIPE_WEBHOOK_SECRET:
        logger.error("STRIPE_WEBHOOK_SECRET not configured")
        raise HTTPException(
            status_code=500,
            detail="Webhook secret not configured"
        )
    
    try:
        event = stripe.Webhook.construct_event(
            payload, 
            signature, 
            config.STRIPE_WEBHOOK_SECRET
        )
        logger.info(f"Webhook signature verified: event_id={event.id}, type={event.type}")
        return event
        
    except ValueError as e:
        # Invalid payload
        logger.error(f"Invalid webhook payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")
        
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        logger.error(f"Invalid webhook signature: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")
```

---

### Task 3.2: Implement Idempotency Check (1 hour)

**File**: `services/billing_service.py`

**Action**: Add idempotency methods using Redis

```python
async def is_event_processed(self, event_id: str) -> bool:
    """
    Check if webhook event has already been processed
    
    Args:
        event_id: Stripe event ID (evt_xxx)
        
    Returns:
        True if event already processed, False otherwise
    """
    from services.redis.client import get_redis
    
    try:
        redis = get_redis()
        key = f"stripe:event:{event_id}"
        exists = await redis.exists(key)
        
        if exists:
            logger.info(f"Event {event_id} already processed (idempotency check)")
        
        return exists > 0
        
    except Exception as e:
        # If Redis fails, log but don't block webhook processing
        logger.warning(f"Redis idempotency check failed for event {event_id}: {e}")
        return False

async def mark_event_processed(self, event_id: str):
    """
    Mark webhook event as processed
    
    Args:
        event_id: Stripe event ID (evt_xxx)
    """
    from services.redis.client import get_redis
    
    try:
        redis = get_redis()
        key = f"stripe:event:{event_id}"
        # Store for 24 hours (Stripe retries for 3 days max)
        await redis.setex(key, 86400, "processed")
        logger.debug(f"Marked event {event_id} as processed")
        
    except Exception as e:
        # If Redis fails, log but don't fail webhook processing
        logger.warning(f"Failed to mark event {event_id} as processed: {e}")
```

---

### Task 3.3: Implement Subscription Provisioning (3 hours)

**File**: `services/billing_service.py`

**Action**: Implement subscription provisioning logic

```python
async def provision_subscription(
    self,
    user_id: str,
    tier: str,
    subscription_id: str,
    status: str,
    current_period_end: int
):
    """
    Provision subscription access by updating user tier
    
    Args:
        user_id: Quizify user ID (UUID)
        tier: Account tier to provision (basic/educator)
        subscription_id: Stripe subscription ID
        status: Subscription status (active/past_due/etc)
        current_period_end: Unix timestamp of period end
    """
    try:
        # Use service role client (webhooks bypass RLS)
        supabase = get_supabase()
        
        # Convert Unix timestamp to ISO datetime
        from datetime import datetime
        period_end_dt = datetime.utcfromtimestamp(current_period_end)
        
        # Update user profile with subscription details
        result = supabase.table("profiles").update({
            "account_tier": tier,
            "stripe_subscription_id": subscription_id,
            "subscription_status": status,
            "subscription_current_period_end": period_end_dt.isoformat(),
            "subscription_grace_period_end": None,  # Clear grace period
            "cancel_at_period_end": False
        }).eq("id", user_id).execute()
        
        logger.info(
            f"Provisioned {tier} subscription for user {user_id[:8]} - "
            f"subscription={subscription_id}, status={status}, "
            f"period_end={period_end_dt.isoformat()}"
        )
        
        # TODO: Send confirmation email (implement in Epic 6)
        
    except Exception as e:
        logger.error(
            f"Failed to provision subscription for user {user_id[:8]}: {e}",
            exc_info=True
        )
        raise

async def handle_failed_payment(
    self,
    user_id: str,
    grace_days: int = 7
):
    """
    Handle failed payment by setting grace period
    
    Args:
        user_id: Quizify user ID (UUID)
        grace_days: Number of days until grace period expires
    """
    try:
        from datetime import datetime, timedelta
        
        supabase = get_supabase()
        grace_period_end = datetime.utcnow() + timedelta(days=grace_days)
        
        # Update subscription status to past_due with grace period
        supabase.table("profiles").update({
            "subscription_status": "past_due",
            "subscription_grace_period_end": grace_period_end.isoformat()
        }).eq("id", user_id).execute()
        
        logger.warning(
            f"User {user_id[:8]} payment failed - "
            f"grace period until {grace_period_end.isoformat()}"
        )
        
        # TODO: Send payment failure email (implement in Epic 6)
        
    except Exception as e:
        logger.error(
            f"Failed to handle failed payment for user {user_id[:8]}: {e}",
            exc_info=True
        )
        raise

async def cancel_subscription(
    self,
    user_id: str
):
    """
    Cancel subscription and downgrade to free tier
    
    Args:
        user_id: Quizify user ID (UUID)
    """
    try:
        supabase = get_supabase()
        
        # Downgrade to free tier and clear subscription data
        supabase.table("profiles").update({
            "account_tier": "free",
            "stripe_subscription_id": None,
            "subscription_status": "canceled",
            "subscription_current_period_end": None,
            "subscription_grace_period_end": None,
            "cancel_at_period_end": False
        }).eq("id", user_id).execute()
        
        logger.info(f"Canceled subscription for user {user_id[:8]}")
        
        # TODO: Send cancellation confirmation email (implement in Epic 6)
        
    except Exception as e:
        logger.error(
            f"Failed to cancel subscription for user {user_id[:8]}: {e}",
            exc_info=True
        )
        raise
```

---

### Task 3.4: Implement Webhook Event Handlers (4 hours)

**File**: `handlers/billing_handler.py`

**Action**: Add event-specific handler functions

```python
from services.billing_service import billing_service

async def handle_checkout_completed(event: stripe.Event):
    """
    Handle checkout.session.completed event
    
    This event fires when checkout completes successfully.
    Store customer and subscription IDs, but don't provision yet.
    Wait for invoice.paid to confirm payment processing.
    """
    session = event.data.object
    
    # Extract metadata
    user_id = session.metadata.get("user_id")
    tier = session.metadata.get("tier")
    
    if not user_id or not tier:
        logger.error(
            f"Missing metadata in checkout session {session.id}: "
            f"user_id={user_id}, tier={tier}"
        )
        return
    
    logger.info(
        f"Checkout completed for user {user_id[:8]}: "
        f"session={session.id}, tier={tier}"
    )
    
    # Store customer and subscription IDs
    try:
        supabase = get_supabase()
        supabase.table("profiles").update({
            "stripe_customer_id": session.customer,
            "stripe_subscription_id": session.subscription
        }).eq("id", user_id).execute()
        
        logger.info(
            f"Stored subscription IDs for user {user_id[:8]}: "
            f"customer={session.customer}, subscription={session.subscription}"
        )
        
    except Exception as e:
        logger.error(
            f"Failed to store subscription IDs for user {user_id[:8]}: {e}",
            exc_info=True
        )
        raise

async def handle_invoice_paid(event: stripe.Event):
    """
    Handle invoice.paid event
    
    This event confirms payment was successful.
    Provision subscription access here.
    """
    invoice = event.data.object
    subscription_id = invoice.subscription
    
    if not subscription_id:
        logger.warning(f"Invoice {invoice.id} has no subscription")
        return
    
    # Retrieve subscription to get metadata
    stripe.api_key = config.STRIPE_SECRET_KEY
    subscription = stripe.Subscription.retrieve(subscription_id)
    
    user_id = subscription.metadata.get("user_id")
    tier = subscription.metadata.get("tier")
    
    if not user_id or not tier:
        logger.error(
            f"Missing metadata in subscription {subscription_id}: "
            f"user_id={user_id}, tier={tier}"
        )
        return
    
    logger.info(
        f"Invoice paid for user {user_id[:8]}: "
        f"invoice={invoice.id}, subscription={subscription_id}, tier={tier}"
    )
    
    # Provision subscription access
    await billing_service.provision_subscription(
        user_id=user_id,
        tier=tier,
        subscription_id=subscription_id,
        status=subscription.status,
        current_period_end=subscription.current_period_end
    )

async def handle_invoice_payment_failed(event: stripe.Event):
    """
    Handle invoice.payment_failed event
    
    This event fires when payment fails (e.g., card declined).
    Set grace period and notify user.
    """
    invoice = event.data.object
    subscription_id = invoice.subscription
    
    if not subscription_id:
        logger.warning(f"Invoice {invoice.id} has no subscription")
        return
    
    # Retrieve subscription to get user_id
    stripe.api_key = config.STRIPE_SECRET_KEY
    subscription = stripe.Subscription.retrieve(subscription_id)
    
    user_id = subscription.metadata.get("user_id")
    
    if not user_id:
        logger.error(f"Missing user_id in subscription {subscription_id}")
        return
    
    logger.warning(
        f"Payment failed for user {user_id[:8]}: "
        f"invoice={invoice.id}, subscription={subscription_id}"
    )
    
    # Set grace period
    await billing_service.handle_failed_payment(user_id, grace_days=7)

async def handle_subscription_updated(event: stripe.Event):
    """
    Handle customer.subscription.updated event
    
    This event fires when subscription changes (upgrade, downgrade, cancel scheduled).
    Update subscription status and period end.
    """
    subscription = event.data.object
    
    user_id = subscription.metadata.get("user_id")
    tier = subscription.metadata.get("tier")
    
    if not user_id:
        logger.error(f"Missing user_id in subscription {subscription.id}")
        return
    
    logger.info(
        f"Subscription updated for user {user_id[:8]}: "
        f"subscription={subscription.id}, status={subscription.status}"
    )
    
    # Update subscription status and period
    try:
        from datetime import datetime
        
        supabase = get_supabase()
        period_end_dt = datetime.utcfromtimestamp(subscription.current_period_end)
        
        supabase.table("profiles").update({
            "subscription_status": subscription.status,
            "subscription_current_period_end": period_end_dt.isoformat(),
            "cancel_at_period_end": subscription.cancel_at_period_end
        }).eq("id", user_id).execute()
        
        logger.info(
            f"Updated subscription status for user {user_id[:8]}: "
            f"status={subscription.status}, cancel_at_period_end={subscription.cancel_at_period_end}"
        )
        
    except Exception as e:
        logger.error(
            f"Failed to update subscription for user {user_id[:8]}: {e}",
            exc_info=True
        )
        raise

async def handle_subscription_deleted(event: stripe.Event):
    """
    Handle customer.subscription.deleted event
    
    This event fires when subscription is canceled/expires.
    Downgrade user to free tier.
    """
    subscription = event.data.object
    
    user_id = subscription.metadata.get("user_id")
    
    if not user_id:
        logger.error(f"Missing user_id in subscription {subscription.id}")
        return
    
    logger.info(
        f"Subscription deleted for user {user_id[:8]}: "
        f"subscription={subscription.id}"
    )
    
    # Cancel subscription and downgrade to free
    await billing_service.cancel_subscription(user_id)

# Event handler mapping
WEBHOOK_HANDLERS = {
    "checkout.session.completed": handle_checkout_completed,
    "invoice.paid": handle_invoice_paid,
    "invoice.payment_failed": handle_invoice_payment_failed,
    "customer.subscription.updated": handle_subscription_updated,
    "customer.subscription.deleted": handle_subscription_deleted,
}
```

---

### Task 3.5: Implement Webhook API Endpoint (2 hours)

**File**: `api/billing_routes.py`

**Action**: Implement webhook route

```python
from handlers.billing_handler import WEBHOOK_HANDLERS
from services.billing_service import billing_service

@router.post(
    "/webhook",
    summary="Stripe Webhook Handler",
    description="Receive and process Stripe webhook events",
    include_in_schema=False,  # Hidden from OpenAPI docs (security)
    status_code=200
)
async def stripe_webhook(request: Request):
    """
    Stripe webhook event handler
    
    **IMPORTANT**: This endpoint must be publicly accessible (no auth)
    Stripe signs requests with webhook secret for security
    
    **Security**: Signature verification prevents unauthorized requests
    
    **Idempotency**: Uses Redis to prevent duplicate processing
    
    **Supported Events**:
    - `checkout.session.completed`: Store customer/subscription IDs
    - `invoice.paid`: Provision subscription access
    - `invoice.payment_failed`: Set grace period
    - `customer.subscription.updated`: Update subscription status
    - `customer.subscription.deleted`: Downgrade to free tier
    """
    # Get raw body bytes for signature verification
    body = await request.body()
    signature = request.headers.get("Stripe-Signature")
    
    if not signature:
        logger.error("Missing Stripe-Signature header")
        raise HTTPException(
            status_code=400,
            detail="Missing signature"
        )
    
    # Verify webhook signature
    event = billing_service.verify_webhook_signature(body, signature)
    
    logger.info(f"Received webhook: event_id={event.id}, type={event.type}")
    
    # Check idempotency (prevent duplicate processing)
    if await billing_service.is_event_processed(event.id):
        logger.info(f"Event {event.id} already processed, skipping")
        return {"status": "success", "message": "Event already processed"}
    
    # Get handler for event type
    handler = WEBHOOK_HANDLERS.get(event.type)
    
    if handler:
        try:
            # Process event
            await handler(event)
            
            # Mark as processed
            await billing_service.mark_event_processed(event.id)
            
            logger.info(f"Successfully processed event {event.id} ({event.type})")
            return {"status": "success"}
            
        except Exception as e:
            # Log error but return 200 to prevent Stripe retries for bugs
            logger.error(
                f"Error processing event {event.id} ({event.type}): {e}",
                exc_info=True
            )
            # Return 500 to trigger Stripe retry for transient errors
            raise HTTPException(
                status_code=500,
                detail=f"Error processing event: {e}"
            )
    else:
        # Unknown event type - log but don't fail
        logger.info(f"Unhandled event type: {event.type}")
        return {"status": "success", "message": f"Event type {event.type} not handled"}
```

---

### Task 3.6: Configure Webhook in Stripe Dashboard (1 hour)

**Platform**: Stripe Dashboard

**Actions**:

1. **Navigate to Webhooks** (https://dashboard.stripe.com/test/webhooks)

2. **Add Endpoint**:
   - Click "Add endpoint"
   - **Endpoint URL**:
     - Development: `https://your-ngrok-url.ngrok.io/api/billing/webhook`
     - Staging: `https://staging.quizify.ca/api/billing/webhook`
     - Production: `https://api.quizify.ca/api/billing/webhook`

3. **Select Events**:
   - `checkout.session.completed`
   - `invoice.paid`
   - `invoice.payment_failed`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`

4. **Copy Webhook Secret**:
   - After creation, click "Reveal" next to signing secret
   - Copy webhook secret (starts with `whsec_`)
   - Add to `.env` file: `STRIPE_WEBHOOK_SECRET=whsec_...`

5. **Restart Application** to load new webhook secret

---

### Task 3.7: Add Unit Tests (3 hours)

**File**: `tests/unit/test_webhook_handling.py` (NEW)

**Action**: Create comprehensive webhook tests

```python
"""
Unit tests for webhook handling and provisioning
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import stripe
from handlers.billing_handler import (
    handle_checkout_completed,
    handle_invoice_paid,
    handle_invoice_payment_failed,
    handle_subscription_updated,
    handle_subscription_deleted
)

@pytest.mark.asyncio
class TestWebhookHandlers:
    """Test webhook event handlers"""
    
    async def test_handle_checkout_completed(self, mock_supabase):
        """Test checkout.session.completed handler"""
        event = MagicMock()
        event.data.object = MagicMock(
            id="cs_test123",
            customer="cus_test123",
            subscription="sub_test123",
            metadata={"user_id": "user_123", "tier": "basic"}
        )
        
        await handle_checkout_completed(event)
        
        # Verify customer/subscription IDs stored
        mock_supabase.table().update.assert_called_once()
    
    @patch("stripe.Subscription.retrieve")
    async def test_handle_invoice_paid(self, mock_retrieve, mock_supabase):
        """Test invoice.paid handler provisions subscription"""
        # Mock subscription retrieval
        mock_retrieve.return_value = MagicMock(
            id="sub_test123",
            status="active",
            current_period_end=1734566400,
            metadata={"user_id": "user_123", "tier": "basic"}
        )
        
        event = MagicMock()
        event.data.object = MagicMock(
            id="in_test123",
            subscription="sub_test123"
        )
        
        await handle_invoice_paid(event)
        
        # Verify subscription provisioned
        mock_supabase.table().update.assert_called_once()
    
    async def test_handle_payment_failed(self, mock_supabase):
        """Test invoice.payment_failed handler sets grace period"""
        event = MagicMock()
        event.data.object = MagicMock(
            id="in_test123",
            subscription="sub_test123"
        )
        
        with patch("stripe.Subscription.retrieve") as mock_retrieve:
            mock_retrieve.return_value = MagicMock(
                id="sub_test123",
                metadata={"user_id": "user_123"}
            )
            
            await handle_invoice_payment_failed(event)
            
            # Verify grace period set
            mock_supabase.table().update.assert_called_once()
    
    async def test_handle_subscription_deleted(self, mock_supabase):
        """Test subscription.deleted handler downgrades user"""
        event = MagicMock()
        event.data.object = MagicMock(
            id="sub_test123",
            metadata={"user_id": "user_123"}
        )
        
        await handle_subscription_deleted(event)
        
        # Verify downgrade to free tier
        update_call = mock_supabase.table().update.call_args[0][0]
        assert update_call["account_tier"] == "free"
        assert update_call["subscription_status"] == "canceled"
```

---

### Task 3.8: Test with Stripe CLI (1 hour)

**Tool**: Stripe CLI (https://stripe.com/docs/stripe-cli)

**Installation**:
```bash
# macOS
brew install stripe/stripe-cli/stripe

# Login
stripe login
```

**Testing Webhooks Locally**:
```bash
# 1. Start FastAPI server
uvicorn main:app --reload

# 2. Forward webhooks to localhost (in another terminal)
stripe listen --forward-to localhost:8000/api/billing/webhook

# 3. Trigger specific events (in third terminal)
stripe trigger checkout.session.completed
stripe trigger invoice.paid
stripe trigger invoice.payment_failed
stripe trigger customer.subscription.deleted

# 4. Monitor logs in FastAPI server and Stripe CLI
```

---

## Verification Checklist

### Code Verification
- [ ] Webhook signature verification implemented
- [ ] Idempotency checks using Redis
- [ ] All 5 event handlers implemented
- [ ] Webhook API endpoint functional
- [ ] Unit tests written and passing
- [ ] Stripe CLI forwarding working

### Stripe Dashboard Verification
- [ ] Webhook endpoint created
- [ ] All 5 events selected
- [ ] Webhook secret copied to `.env`
- [ ] Test events deliverable

### Manual Testing
```bash
# Test complete checkout → provisioning flow:
# 1. Create checkout session (use API from Epic 2)
# 2. Complete payment with test card
# 3. Check webhook logs for events received
# 4. Verify user tier updated in database:
psql -h <supabase-host> -U postgres -d postgres
SELECT id, account_tier, subscription_status, stripe_subscription_id 
FROM profiles 
WHERE id = 'user_id';
```

---

## Common Issues & Troubleshooting

### Issue 1: Webhook Signature Verification Fails
**Solution**: 
- Ensure `STRIPE_WEBHOOK_SECRET` matches Dashboard value
- Don't parse request body before verification (must be raw bytes)
- Check for extra whitespace in `.env` file

### Issue 2: Events Not Being Received
**Solution**:
- Use ngrok/Stripe CLI for local development
- Check webhook endpoint is publicly accessible
- Verify URL in Stripe Dashboard is correct

### Issue 3: Duplicate Event Processing
**Solution**:
- Ensure Redis is running
- Check idempotency logic is called
- Use Stripe event ID as idempotency key

### Issue 4: Subscription Not Provisioned
**Solution**:
- Check metadata exists in checkout session
- Verify `invoice.paid` event is subscribed
- Check logs for errors in provisioning logic

---

## Next Steps

Once complete:
1. ✅ Run tests: `pytest tests/unit/test_webhook_handling.py -v`
2. ✅ Test with Stripe CLI
3. ✅ Manual end-to-end test (checkout → payment → provisioning)
4. ✅ Commit: `feat: implement webhook handling and provisioning (Epic 3)`
5. ➡️ Proceed to **Epic 4: Customer Portal Integration**

---

**Epic Owner**: GitHub Copilot  
**Last Updated**: 2025-11-19
