# Stripe Integration - Technical Reference

## API Endpoints Specification

### 1. Create Checkout Session
**Purpose**: Create a Stripe Checkout Session for subscription purchase

```
POST /api/billing/create-checkout-session
```

**Request**:
```json
{
  "price_id": "price_1234567890",
  "tier": "basic"  // or "educator"
}
```

**Headers**:
```
Authorization: Bearer <user_access_token>
Content-Type: application/json
```

**Response** (200 OK):
```json
{
  "session_id": "cs_test_1234567890",
  "url": "https://checkout.stripe.com/pay/cs_test_1234567890"
}
```

**Error Responses**:
- `401 Unauthorized`: Missing or invalid token
- `400 Bad Request`: Invalid price_id or tier
- `409 Conflict`: User already has active subscription
- `500 Internal Server Error`: Stripe API error

**Implementation Notes**:
- Validate `price_id` against allowed prices (don't trust frontend)
- Get or create Stripe customer for user
- Store `user_id` and `tier` in session metadata
- Set `success_url` with `{CHECKOUT_SESSION_ID}` template
- Set `cancel_url` for user to return on cancel

---

### 2. Create Portal Session
**Purpose**: Create a Stripe Customer Portal Session for subscription management

```
POST /api/billing/create-portal-session
```

**Request**: Empty body (user ID from auth token)

**Headers**:
```
Authorization: Bearer <user_access_token>
Content-Type: application/json
```

**Response** (200 OK):
```json
{
  "url": "https://billing.stripe.com/session/1234567890"
}
```

**Error Responses**:
- `401 Unauthorized`: Missing or invalid token
- `404 Not Found`: No Stripe customer ID (never subscribed)
- `500 Internal Server Error`: Stripe API error

**Implementation Notes**:
- Lookup `stripe_customer_id` from `profiles` table
- Return 404 if no customer ID exists
- Set `return_url` to user dashboard

---

### 3. Webhook Endpoint
**Purpose**: Receive and process Stripe webhook events

```
POST /api/billing/webhook
```

**Request Headers**:
```
Stripe-Signature: t=1234567890,v1=signature_hash
Content-Type: application/json
```

**Request Body**: Stripe Event object (varies by event type)

**Response**: `200 OK` (empty body)

**Event Types Handled**:
- `checkout.session.completed`: Store customer/subscription IDs
- `invoice.paid`: Provision tier access
- `invoice.payment_failed`: Handle failed payment
- `customer.subscription.updated`: Update subscription status
- `customer.subscription.deleted`: Downgrade to free tier

**Implementation Notes**:
- **CRITICAL**: Verify webhook signature before processing
- Parse `event.type` to determine handler
- Log all events for audit trail
- Implement idempotency (check if event already processed)
- Return 200 even if event not handled (acknowledged)

---

### 4. Get Subscription Status
**Purpose**: Get current subscription status for authenticated user

```
GET /api/billing/subscription-status
```

**Headers**:
```
Authorization: Bearer <user_access_token>
```

**Response** (200 OK):
```json
{
  "has_subscription": true,
  "tier": "basic",
  "status": "active",
  "current_period_end": "2025-12-19T00:00:00Z",
  "cancel_at_period_end": false,
  "customer_id": "cus_1234567890",
  "subscription_id": "sub_1234567890"
}
```

**Error Responses**:
- `401 Unauthorized`: Missing or invalid token
- `404 Not Found`: No subscription found

**Implementation Notes**:
- Query `profiles` table for subscription data
- Return null values if no subscription
- Include period end date for renewal display

---

## Database Schema

### Migration: `014_add_stripe_integration.sql`

```sql
-- ============================================================================
-- STRIPE INTEGRATION SCHEMA
-- ============================================================================
-- Add Stripe-related columns to profiles table
-- Author: GitHub Copilot
-- Date: 2025-11-19

-- Add Stripe customer and subscription tracking columns
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT UNIQUE,
ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT,
ADD COLUMN IF NOT EXISTS subscription_status TEXT 
    CHECK (subscription_status IN (
        'active',           -- Subscription is active
        'past_due',         -- Payment failed, in grace period
        'canceled',         -- Subscription canceled
        'incomplete',       -- Initial payment pending
        'incomplete_expired', -- Initial payment failed
        'trialing',         -- In trial period
        'unpaid'            -- Multiple payment failures
    )),
ADD COLUMN IF NOT EXISTS subscription_current_period_end TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS subscription_grace_period_end TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS cancel_at_period_end BOOLEAN DEFAULT false;

-- Add indexes for fast Stripe lookups
CREATE INDEX IF NOT EXISTS idx_profiles_stripe_customer_id 
    ON public.profiles(stripe_customer_id);
    
CREATE INDEX IF NOT EXISTS idx_profiles_stripe_subscription_id 
    ON public.profiles(stripe_subscription_id);

CREATE INDEX IF NOT EXISTS idx_profiles_subscription_status 
    ON public.profiles(subscription_status) 
    WHERE subscription_status IS NOT NULL;

-- Add RLS policies for Stripe fields
-- Users can view their own Stripe data
CREATE POLICY IF NOT EXISTS "Users can view own Stripe subscription data"
    ON public.profiles FOR SELECT
    USING (auth.uid() = id);

-- Only service role can update Stripe fields (via webhooks)
-- Regular users cannot modify Stripe data directly
DROP POLICY IF EXISTS "Only service role can update Stripe data" ON public.profiles;
CREATE POLICY "Service role can update Stripe data"
    ON public.profiles FOR UPDATE
    USING (auth.role() = 'service_role');

-- Add comment for documentation
COMMENT ON COLUMN public.profiles.stripe_customer_id IS 
    'Stripe customer ID for subscription management';
COMMENT ON COLUMN public.profiles.stripe_subscription_id IS 
    'Active Stripe subscription ID (null if no active subscription)';
COMMENT ON COLUMN public.profiles.subscription_status IS 
    'Current subscription status from Stripe webhook events';
COMMENT ON COLUMN public.profiles.subscription_current_period_end IS 
    'Timestamp when current billing period ends';
COMMENT ON COLUMN public.profiles.subscription_grace_period_end IS 
    'Timestamp when grace period ends for past_due subscriptions';
COMMENT ON COLUMN public.profiles.cancel_at_period_end IS 
    'True if subscription is set to cancel at period end';
```

### Updated `user_tier_info` View

```sql
-- Update view to include subscription status
CREATE OR REPLACE VIEW public.user_tier_info AS
SELECT 
    u.id,
    u.email,
    COALESCE(p.display_name, split_part(u.email, '@', 1)) AS display_name,
    COALESCE(p.account_tier, 'free') AS account_tier,
    COALESCE(p.role, 'user') AS role,
    COALESCE(q.quiz_count, 0) AS current_quiz_count,
    CASE 
        WHEN COALESCE(p.account_tier, 'free') = 'free' THEN 5
        WHEN COALESCE(p.account_tier, 'free') = 'basic' THEN 100
        WHEN COALESCE(p.account_tier, 'free') = 'educator' THEN 500
        ELSE 5
    END AS quota_limit,
    CASE 
        WHEN COALESCE(p.account_tier, 'free') = 'free' THEN COALESCE(q.quiz_count, 0) >= 5
        WHEN COALESCE(p.account_tier, 'free') = 'basic' THEN COALESCE(q.quiz_count, 0) >= 100
        WHEN COALESCE(p.account_tier, 'free') = 'educator' THEN COALESCE(q.quiz_count, 0) >= 500
        ELSE COALESCE(q.quiz_count, 0) >= 5
    END AS quota_exceeded,
    -- Stripe subscription fields
    p.stripe_customer_id,
    p.stripe_subscription_id,
    p.subscription_status,
    p.subscription_current_period_end,
    p.subscription_grace_period_end,
    p.cancel_at_period_end
FROM auth.users u
LEFT JOIN public.profiles p ON u.id = p.id
LEFT JOIN (
    SELECT 
        user_id,
        COUNT(*) AS quiz_count
    FROM public.quizzes
    WHERE deleted_at IS NULL
        AND created_at >= date_trunc('month', CURRENT_TIMESTAMP)
    GROUP BY user_id
) q ON u.id = q.user_id;
```

---

## Configuration (`config.py`)

### Add Stripe Configuration Class

```python
# ============================================================================
# Stripe Configuration
# ============================================================================

# Stripe API keys
STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY: str = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")

# Stripe Price IDs (created in Stripe Dashboard)
STRIPE_PRICE_BASIC_MONTHLY: str = os.getenv("STRIPE_PRICE_BASIC_MONTHLY", "")
STRIPE_PRICE_BASIC_ANNUAL: str = os.getenv("STRIPE_PRICE_BASIC_ANNUAL", "")
STRIPE_PRICE_EDUCATOR_MONTHLY: str = os.getenv("STRIPE_PRICE_EDUCATOR_MONTHLY", "")
STRIPE_PRICE_EDUCATOR_ANNUAL: str = os.getenv("STRIPE_PRICE_EDUCATOR_ANNUAL", "")

# Stripe configuration validation
@classmethod
def get_stripe_price_ids(cls) -> dict[str, str]:
    """Get all Stripe price IDs as a dictionary"""
    return {
        "basic_monthly": cls.STRIPE_PRICE_BASIC_MONTHLY,
        "basic_annual": cls.STRIPE_PRICE_BASIC_ANNUAL,
        "educator_monthly": cls.STRIPE_PRICE_EDUCATOR_MONTHLY,
        "educator_annual": cls.STRIPE_PRICE_EDUCATOR_ANNUAL,
    }

@classmethod
def validate_stripe_price_id(cls, price_id: str) -> bool:
    """Validate if price_id is in allowed list"""
    return price_id in cls.get_stripe_price_ids().values()

@classmethod
def get_tier_from_price_id(cls, price_id: str) -> str:
    """Map Stripe price ID to account tier"""
    price_to_tier = {
        cls.STRIPE_PRICE_BASIC_MONTHLY: "basic",
        cls.STRIPE_PRICE_BASIC_ANNUAL: "basic",
        cls.STRIPE_PRICE_EDUCATOR_MONTHLY: "educator",
        cls.STRIPE_PRICE_EDUCATOR_ANNUAL: "educator",
    }
    return price_to_tier.get(price_id, "free")
```

---

## Pydantic Schemas

### Request/Response Models

```python
# schemas/billing.py

from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime

# ============================================================================
# Checkout Session Schemas
# ============================================================================

class CheckoutSessionRequest(BaseModel):
    """Request to create a Stripe Checkout Session"""
    price_id: str = Field(
        ...,
        description="Stripe price ID for the subscription plan",
        example="price_1234567890"
    )
    tier: Literal["basic", "educator"] = Field(
        ...,
        description="Target tier for the subscription"
    )

class CheckoutSessionResponse(BaseModel):
    """Response containing Checkout Session URL"""
    session_id: str = Field(
        ...,
        description="Stripe Checkout Session ID"
    )
    url: str = Field(
        ...,
        description="URL to redirect user to for checkout"
    )

# ============================================================================
# Customer Portal Schemas
# ============================================================================

class PortalSessionResponse(BaseModel):
    """Response containing Customer Portal URL"""
    url: str = Field(
        ...,
        description="URL to redirect user to for portal"
    )

# ============================================================================
# Subscription Status Schemas
# ============================================================================

class SubscriptionStatusResponse(BaseModel):
    """User's current subscription status"""
    has_subscription: bool = Field(
        ...,
        description="Whether user has an active subscription"
    )
    tier: Literal["free", "basic", "educator"] = Field(
        ...,
        description="Current account tier"
    )
    status: Optional[str] = Field(
        None,
        description="Stripe subscription status (active, past_due, canceled, etc)"
    )
    current_period_end: Optional[datetime] = Field(
        None,
        description="Timestamp when current billing period ends"
    )
    cancel_at_period_end: bool = Field(
        False,
        description="True if subscription is set to cancel at period end"
    )
    customer_id: Optional[str] = Field(
        None,
        description="Stripe customer ID"
    )
    subscription_id: Optional[str] = Field(
        None,
        description="Stripe subscription ID"
    )
    grace_period_end: Optional[datetime] = Field(
        None,
        description="Grace period end for past_due subscriptions"
    )

# ============================================================================
# Webhook Event Schemas
# ============================================================================

class WebhookEventMetadata(BaseModel):
    """Metadata stored in Stripe events"""
    user_id: str = Field(..., description="Quizify user ID (UUID)")
    tier: str = Field(..., description="Account tier (basic/educator)")
```

---

## Service Layer Pattern

### Billing Service (`services/billing_service.py`)

```python
from typing import Optional, Dict, Any
import stripe
from datetime import datetime, timedelta
from config import config
from services.logger import app_logger as logger

class BillingService:
    """Service for managing Stripe subscriptions and billing"""
    
    def __init__(self):
        stripe.api_key = config.STRIPE_SECRET_KEY
    
    async def get_or_create_customer(
        self, 
        user_id: str, 
        email: str
    ) -> str:
        """
        Get existing Stripe customer ID or create new customer
        
        Args:
            user_id: Quizify user ID (UUID)
            email: User's email address
            
        Returns:
            Stripe customer ID (cus_xxx)
        """
        # Check if customer exists in database
        result = await supabase.table("profiles")\
            .select("stripe_customer_id")\
            .eq("id", user_id)\
            .single()
        
        if result.data and result.data.get("stripe_customer_id"):
            return result.data["stripe_customer_id"]
        
        # Create new Stripe customer
        customer = stripe.Customer.create(
            email=email,
            metadata={"quizify_user_id": user_id}
        )
        
        # Store customer ID
        await supabase.table("profiles")\
            .update({"stripe_customer_id": customer.id})\
            .eq("id", user_id)\
            .execute()
        
        logger.info(f"Created Stripe customer {customer.id} for user {user_id}")
        return customer.id
    
    async def create_checkout_session(
        self,
        user_id: str,
        email: str,
        price_id: str,
        tier: str
    ) -> Dict[str, str]:
        """
        Create a Stripe Checkout Session
        
        Args:
            user_id: Quizify user ID
            email: User's email
            price_id: Stripe price ID
            tier: Target tier (basic/educator)
            
        Returns:
            Dict with session_id and url
        """
        # Validate price ID
        if not config.validate_stripe_price_id(price_id):
            raise ValueError(f"Invalid price ID: {price_id}")
        
        # Get or create customer
        customer_id = await self.get_or_create_customer(user_id, email)
        
        # Create checkout session
        session = stripe.checkout.Session.create(
            customer=customer_id,
            mode="subscription",
            billing_mode="flexible",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{config.FRONTEND_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{config.FRONTEND_URL}/billing/canceled",
            metadata={
                "user_id": user_id,
                "tier": tier
            },
            subscription_data={
                "metadata": {
                    "user_id": user_id,
                    "tier": tier
                }
            }
        )
        
        logger.info(f"Created checkout session {session.id} for user {user_id}")
        return {
            "session_id": session.id,
            "url": session.url
        }
    
    async def create_portal_session(
        self,
        user_id: str
    ) -> Dict[str, str]:
        """
        Create a Stripe Customer Portal Session
        
        Args:
            user_id: Quizify user ID
            
        Returns:
            Dict with url
        """
        # Get customer ID
        result = await supabase.table("profiles")\
            .select("stripe_customer_id")\
            .eq("id", user_id)\
            .single()
        
        if not result.data or not result.data.get("stripe_customer_id"):
            raise ValueError("No Stripe customer found")
        
        customer_id = result.data["stripe_customer_id"]
        
        # Create portal session
        portal_session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{config.FRONTEND_URL}/dashboard"
        )
        
        logger.info(f"Created portal session for user {user_id}")
        return {"url": portal_session.url}
    
    async def provision_subscription(
        self,
        user_id: str,
        tier: str,
        subscription_id: str,
        status: str,
        current_period_end: datetime
    ):
        """
        Provision subscription access by updating user tier
        
        Args:
            user_id: Quizify user ID
            tier: Account tier to provision
            subscription_id: Stripe subscription ID
            status: Subscription status
            current_period_end: End of current period
        """
        await supabase.table("profiles").update({
            "account_tier": tier,
            "stripe_subscription_id": subscription_id,
            "subscription_status": status,
            "subscription_current_period_end": current_period_end.isoformat(),
            "subscription_grace_period_end": None,
            "cancel_at_period_end": False
        }).eq("id", user_id).execute()
        
        logger.info(
            f"Provisioned {tier} subscription for user {user_id} "
            f"(subscription: {subscription_id}, status: {status})"
        )
    
    async def handle_failed_payment(
        self,
        user_id: str,
        grace_days: int = 7
    ):
        """
        Handle failed payment by setting grace period
        
        Args:
            user_id: Quizify user ID
            grace_days: Days until grace period expires
        """
        grace_period_end = datetime.utcnow() + timedelta(days=grace_days)
        
        await supabase.table("profiles").update({
            "subscription_status": "past_due",
            "subscription_grace_period_end": grace_period_end.isoformat()
        }).eq("id", user_id).execute()
        
        logger.warning(
            f"User {user_id} payment failed - grace period until {grace_period_end}"
        )
        
        # TODO: Send email notification
    
    async def cancel_subscription(
        self,
        user_id: str
    ):
        """
        Cancel subscription and downgrade to free tier
        
        Args:
            user_id: Quizify user ID
        """
        await supabase.table("profiles").update({
            "account_tier": "free",
            "stripe_subscription_id": None,
            "subscription_status": "canceled",
            "subscription_current_period_end": None,
            "subscription_grace_period_end": None,
            "cancel_at_period_end": False
        }).eq("id", user_id).execute()
        
        logger.info(f"Canceled subscription for user {user_id}")
```

---

## Code Patterns & Best Practices

### 1. Webhook Signature Verification

```python
import stripe
from fastapi import HTTPException, Request

async def verify_webhook_signature(
    payload: bytes,
    signature: str,
    webhook_secret: str
) -> stripe.Event:
    """
    Verify Stripe webhook signature
    
    Args:
        payload: Raw request body bytes
        signature: Stripe-Signature header value
        webhook_secret: Webhook secret from Stripe Dashboard
        
    Returns:
        Verified Stripe Event object
        
    Raises:
        HTTPException: If signature verification fails
    """
    try:
        event = stripe.Webhook.construct_event(
            payload, signature, webhook_secret
        )
        return event
    except ValueError:
        # Invalid payload
        logger.error("Invalid webhook payload")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        # Invalid signature
        logger.error("Invalid webhook signature")
        raise HTTPException(status_code=400, detail="Invalid signature")
```

### 2. Idempotency Pattern (Redis)

```python
from services.redis.client import get_redis

async def is_event_processed(event_id: str) -> bool:
    """Check if webhook event already processed"""
    redis = get_redis()
    key = f"stripe:event:{event_id}"
    return await redis.exists(key) > 0

async def mark_event_processed(event_id: str):
    """Mark webhook event as processed (24hr TTL)"""
    redis = get_redis()
    key = f"stripe:event:{event_id}"
    await redis.setex(key, 86400, "processed")
```

### 3. Error Handling Pattern

```python
from fastapi import HTTPException
import stripe

async def handle_stripe_api_call(func, *args, **kwargs):
    """
    Wrapper for Stripe API calls with error handling
    
    Usage:
        result = await handle_stripe_api_call(
            stripe.Checkout.Session.create,
            **session_params
        )
    """
    try:
        return func(*args, **kwargs)
    except stripe.error.CardError as e:
        # Card declined
        logger.warning(f"Card declined: {e.user_message}")
        raise HTTPException(status_code=400, detail=e.user_message)
    except stripe.error.InvalidRequestError as e:
        # Invalid parameters
        logger.error(f"Invalid Stripe request: {e}")
        raise HTTPException(status_code=400, detail="Invalid request")
    except stripe.error.AuthenticationError as e:
        # Authentication failed
        logger.error(f"Stripe authentication failed: {e}")
        raise HTTPException(status_code=500, detail="Payment service error")
    except stripe.error.APIConnectionError as e:
        # Network error
        logger.error(f"Stripe API connection error: {e}")
        raise HTTPException(status_code=503, detail="Payment service unavailable")
    except stripe.error.StripeError as e:
        # Generic Stripe error
        logger.error(f"Stripe error: {e}")
        raise HTTPException(status_code=500, detail="Payment processing error")
    except Exception as e:
        # Unexpected error
        logger.error(f"Unexpected error in Stripe API call: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
```

---

## Environment Variables Reference

### Development (`.env`)
```bash
# Stripe Test Keys
STRIPE_SECRET_KEY=sk_test_51...
STRIPE_PUBLISHABLE_KEY=pk_test_51...
STRIPE_WEBHOOK_SECRET=whsec_...

# Stripe Price IDs (Test Mode)
STRIPE_PRICE_BASIC_MONTHLY=price_test_basic_monthly
STRIPE_PRICE_BASIC_ANNUAL=price_test_basic_annual
STRIPE_PRICE_EDUCATOR_MONTHLY=price_test_educator_monthly
STRIPE_PRICE_EDUCATOR_ANNUAL=price_test_educator_annual
```

### Production (Railway)
```bash
# Stripe Live Keys
STRIPE_SECRET_KEY=sk_live_51...
STRIPE_PUBLISHABLE_KEY=pk_live_51...
STRIPE_WEBHOOK_SECRET=whsec_...

# Stripe Price IDs (Live Mode)
STRIPE_PRICE_BASIC_MONTHLY=price_live_basic_monthly
STRIPE_PRICE_BASIC_ANNUAL=price_live_basic_annual
STRIPE_PRICE_EDUCATOR_MONTHLY=price_live_educator_monthly
STRIPE_PRICE_EDUCATOR_ANNUAL=price_live_educator_annual
```

---

## Testing Reference

### Stripe Test Cards

| Scenario | Card Number | CVC | Date |
|----------|-------------|-----|------|
| Success | 4242 4242 4242 4242 | Any | Future |
| Requires Auth | 4000 0025 0000 3155 | Any | Future |
| Decline (generic) | 4000 0000 0000 0002 | Any | Future |
| Insufficient funds | 4000 0000 0000 9995 | Any | Future |
| Expired card | 4000 0000 0000 0069 | Any | Future |
| Incorrect CVC | 4000 0000 0000 0127 | Any | Future |

### Stripe CLI Commands

```bash
# Forward webhooks to localhost
stripe listen --forward-to localhost:8000/api/billing/webhook

# Trigger specific events
stripe trigger checkout.session.completed
stripe trigger invoice.paid
stripe trigger invoice.payment_failed
stripe trigger customer.subscription.deleted

# View webhook logs
stripe logs tail
```

---

**Last Updated**: 2025-11-19  
**Next**: Review Epic 1 for implementation details
