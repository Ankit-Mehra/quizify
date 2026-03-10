# Epic 1: Infrastructure Setup (Days 1-2)

**Status**: Not Started  
**Duration**: 2 days  
**Priority**: Critical (Blocking)  
**Dependencies**: None

---

## Overview

Set up foundational infrastructure for Stripe integration including SDK installation, configuration management, database schema, and initial service structure.

---

## Tasks Breakdown

### Task 1.1: Install Dependencies (30 minutes)
**File**: `requirements.txt`

**Action**: Add Stripe Python SDK

```bash
# Add to requirements.txt
stripe==8.0.0  # Latest stable version as of Epic creation
```

**Installation**:
```bash
pip install -r requirements.txt
```

**Verification**:
```python
# Test import in Python shell
import stripe
print(stripe.api_version)  # Should print API version
```

---

### Task 1.2: Update Configuration (1 hour)
**File**: `config.py`

**Action**: Add Stripe configuration class

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

# Frontend URL for redirects
FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")

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

### Task 1.3: Update Environment Variables (30 minutes)

**File**: `.env.example`

**Action**: Add Stripe configuration documentation

```bash
# ============================================================================
# Stripe Configuration (Epic 1)
# ============================================================================

# Stripe API Keys
# Get these from: https://dashboard.stripe.com/test/apikeys
# SECURITY: Use test keys (sk_test_, pk_test_) in development
#           Use live keys (sk_live_, pk_live_) in production ONLY
STRIPE_SECRET_KEY=sk_test_YOUR_SECRET_KEY_HERE
STRIPE_PUBLISHABLE_KEY=pk_test_YOUR_PUBLISHABLE_KEY_HERE

# Stripe Webhook Secret
# Get this from: https://dashboard.stripe.com/test/webhooks
# After creating webhook endpoint for /api/billing/webhook
STRIPE_WEBHOOK_SECRET=whsec_YOUR_WEBHOOK_SECRET_HERE

# Stripe Price IDs
# Create these in Stripe Dashboard: Products > Add Product > Add Price
# Copy the price ID (starts with "price_") for each plan
STRIPE_PRICE_BASIC_MONTHLY=price_YOUR_BASIC_MONTHLY_ID
STRIPE_PRICE_BASIC_ANNUAL=price_YOUR_BASIC_ANNUAL_ID
STRIPE_PRICE_EDUCATOR_MONTHLY=price_YOUR_EDUCATOR_MONTHLY_ID
STRIPE_PRICE_EDUCATOR_ANNUAL=price_YOUR_EDUCATOR_ANNUAL_ID

# Frontend URL (for Stripe redirects)
FRONTEND_URL=http://localhost:3000  # Development
# FRONTEND_URL=https://app.quizify.ca  # Production
```

**File**: `.env` (local development)

**Action**: Copy from `.env.example` and add test values

```bash
# Copy example file
cp .env.example .env

# Open .env and add your test keys from Stripe Dashboard
# https://dashboard.stripe.com/test/apikeys
```

---

### Task 1.4: Create Database Migration (2 hours)

**File**: `migrations/014_add_stripe_integration.sql`

**Action**: Create migration with Stripe columns

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

**Apply Migration**:
```bash
# Connect to Supabase database
psql -h <supabase-host> -U postgres -d postgres

# Run migration
\i migrations/014_add_stripe_integration.sql

# Verify columns added
\d public.profiles
```

---

### Task 1.5: Update `user_tier_info` View (1 hour)

**File**: `migrations/015_update_user_tier_info_with_stripe.sql`

**Action**: Update view to include subscription fields

```sql
-- ============================================================================
-- UPDATE USER_TIER_INFO VIEW WITH STRIPE FIELDS
-- ============================================================================
-- Add Stripe subscription fields to user_tier_info view
-- Author: GitHub Copilot
-- Date: 2025-11-19

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

-- Grant SELECT on view
GRANT SELECT ON public.user_tier_info TO authenticated;
GRANT SELECT ON public.user_tier_info TO anon;

-- Add comment
COMMENT ON VIEW public.user_tier_info IS 
    'Combined view of user tier, quota, and Stripe subscription status';
```

**Apply Migration**:
```bash
psql -h <supabase-host> -U postgres -d postgres
\i migrations/015_update_user_tier_info_with_stripe.sql

# Test query
SELECT * FROM user_tier_info LIMIT 5;
```

---

### Task 1.6: Create Pydantic Schemas (1 hour)

**File**: `schemas/billing.py` (NEW)

**Action**: Create request/response models

```python
"""
Billing and Stripe Subscription Schemas
Author: GitHub Copilot
Date: 2025-11-19
"""

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
        example="price_1234567890",
        min_length=1
    )
    tier: Literal["basic", "educator"] = Field(
        ...,
        description="Target tier for the subscription"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "price_id": "price_1QBxyz123ABC",
                "tier": "basic"
            }
        }

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

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "cs_test_a1b2c3d4e5f6g7h8i9j0",
                "url": "https://checkout.stripe.com/pay/cs_test_a1b2c3d4e5f6g7h8i9j0"
            }
        }

# ============================================================================
# Customer Portal Schemas
# ============================================================================

class PortalSessionResponse(BaseModel):
    """Response containing Customer Portal URL"""
    url: str = Field(
        ...,
        description="URL to redirect user to for portal"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://billing.stripe.com/session/live_abcdef123456"
            }
        }

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

    class Config:
        json_schema_extra = {
            "example": {
                "has_subscription": True,
                "tier": "basic",
                "status": "active",
                "current_period_end": "2025-12-19T00:00:00Z",
                "cancel_at_period_end": False,
                "customer_id": "cus_ABC123xyz",
                "subscription_id": "sub_DEF456uvw",
                "grace_period_end": None
            }
        }

# ============================================================================
# Webhook Event Schemas
# ============================================================================

class WebhookEventMetadata(BaseModel):
    """Metadata stored in Stripe events"""
    user_id: str = Field(..., description="Quizify user ID (UUID)")
    tier: str = Field(..., description="Account tier (basic/educator)")
```

---

### Task 1.7: Create Service Structure (1 hour)

**File**: `services/billing_service.py` (NEW)

**Action**: Create skeleton service with core methods

```python
"""
Billing Service for Stripe Integration
Author: GitHub Copilot
Date: 2025-11-19
"""

from typing import Optional, Dict, Any
import stripe
from datetime import datetime, timedelta
from config import config
from services.logger import app_logger as logger
from services.supabase_client import get_supabase

class BillingService:
    """Service for managing Stripe subscriptions and billing"""
    
    def __init__(self):
        """Initialize Stripe with API key"""
        stripe.api_key = config.STRIPE_SECRET_KEY
        if not stripe.api_key:
            logger.warning("STRIPE_SECRET_KEY not configured")
    
    # ========================================================================
    # Customer Management
    # ========================================================================
    
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
        # TODO: Implement in Epic 2
        raise NotImplementedError("Implemented in Epic 2")
    
    # ========================================================================
    # Checkout Flow
    # ========================================================================
    
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
        # TODO: Implement in Epic 2
        raise NotImplementedError("Implemented in Epic 2")
    
    # ========================================================================
    # Customer Portal
    # ========================================================================
    
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
        # TODO: Implement in Epic 4
        raise NotImplementedError("Implemented in Epic 4")
    
    # ========================================================================
    # Subscription Provisioning
    # ========================================================================
    
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
        # TODO: Implement in Epic 3
        raise NotImplementedError("Implemented in Epic 3")
    
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
        # TODO: Implement in Epic 3
        raise NotImplementedError("Implemented in Epic 3")
    
    async def cancel_subscription(
        self,
        user_id: str
    ):
        """
        Cancel subscription and downgrade to free tier
        
        Args:
            user_id: Quizify user ID
        """
        # TODO: Implement in Epic 3
        raise NotImplementedError("Implemented in Epic 3")

# Singleton instance
billing_service = BillingService()
```

---

### Task 1.8: Create API Route Skeleton (30 minutes)

**File**: `api/billing_routes.py` (NEW)

**Action**: Create route structure

```python
"""
Billing API Routes
Author: GitHub Copilot
Date: 2025-11-19
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Dict
from schemas.billing import (
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    PortalSessionResponse,
    SubscriptionStatusResponse
)
from dependencies.auth_dependencies import get_current_user
from services.logger import app_logger as logger

router = APIRouter(prefix="/api/billing", tags=["billing"])

# ============================================================================
# Checkout Session
# ============================================================================

@router.post(
    "/create-checkout-session",
    response_model=CheckoutSessionResponse,
    summary="Create Stripe Checkout Session",
    description="Create a new Stripe Checkout Session for subscription purchase"
)
async def create_checkout_session(
    request: CheckoutSessionRequest,
    current_user: Dict = Depends(get_current_user)
):
    """
    Create Stripe Checkout Session for subscription purchase
    
    **Implemented in Epic 2**
    """
    # TODO: Implement in Epic 2
    raise HTTPException(
        status_code=501,
        detail="Checkout session creation not yet implemented (Epic 2)"
    )

# ============================================================================
# Customer Portal
# ============================================================================

@router.post(
    "/create-portal-session",
    response_model=PortalSessionResponse,
    summary="Create Stripe Customer Portal Session",
    description="Create a Customer Portal Session for subscription management"
)
async def create_portal_session(
    current_user: Dict = Depends(get_current_user)
):
    """
    Create Stripe Customer Portal Session
    
    **Implemented in Epic 4**
    """
    # TODO: Implement in Epic 4
    raise HTTPException(
        status_code=501,
        detail="Customer portal not yet implemented (Epic 4)"
    )

# ============================================================================
# Subscription Status
# ============================================================================

@router.get(
    "/subscription-status",
    response_model=SubscriptionStatusResponse,
    summary="Get Subscription Status",
    description="Get current subscription status for authenticated user"
)
async def get_subscription_status(
    current_user: Dict = Depends(get_current_user)
):
    """
    Get current subscription status
    
    **Implemented in Epic 5**
    """
    # TODO: Implement in Epic 5
    raise HTTPException(
        status_code=501,
        detail="Subscription status not yet implemented (Epic 5)"
    )

# ============================================================================
# Webhook Handler
# ============================================================================

@router.post(
    "/webhook",
    summary="Stripe Webhook Handler",
    description="Receive and process Stripe webhook events",
    include_in_schema=False  # Hidden from OpenAPI docs
)
async def stripe_webhook(request: Request):
    """
    Stripe webhook event handler
    
    **Implemented in Epic 3**
    """
    # TODO: Implement in Epic 3
    raise HTTPException(
        status_code=501,
        detail="Webhook handling not yet implemented (Epic 3)"
    )
```

---

### Task 1.9: Register Billing Routes (15 minutes)

**File**: `main.py`

**Action**: Import and include billing router

```python
# Add import at top
from api.billing_routes import router as billing_router

# Add route registration after other routers
app.include_router(billing_router)
```

---

### Task 1.10: Create Stripe Products in Dashboard (1 hour)

**Platform**: Stripe Dashboard (https://dashboard.stripe.com)

**Actions**:

1. **Switch to Test Mode** (toggle in top-right)

2. **Create Products**:
   - Go to: Products → Add Product
   - Create 2 products:

**Product 1: Basic Plan**
- Name: `Quizify Basic`
- Description: `100 quizzes per month - Perfect for individual users`
- Pricing:
  - **Monthly**: $9.99 USD, recurring monthly → Copy price ID to `STRIPE_PRICE_BASIC_MONTHLY`
  - **Annual**: $99.99 USD, recurring yearly (2 months free) → Copy price ID to `STRIPE_PRICE_BASIC_ANNUAL`

**Product 2: Educator Plan**
- Name: `Quizify Educator`
- Description: `500 quizzes per month - Designed for teachers and trainers`
- Pricing:
  - **Monthly**: $19.99 USD, recurring monthly → Copy price ID to `STRIPE_PRICE_EDUCATOR_MONTHLY`
  - **Annual**: $199.99 USD, recurring yearly (2 months free) → Copy price ID to `STRIPE_PRICE_EDUCATOR_ANNUAL`

3. **Update `.env` file** with the 4 price IDs

---

## Verification Checklist

### Code Verification
- [ ] `stripe` package installed and importable
- [ ] Config class has all Stripe variables
- [ ] `.env.example` has Stripe documentation
- [ ] `.env` has test values configured
- [ ] Database migration applied successfully
- [ ] `user_tier_info` view updated with Stripe fields
- [ ] `billing.py` schema created with all models
- [ ] `billing_service.py` created with skeleton methods
- [ ] `billing_routes.py` created with placeholder endpoints
- [ ] Billing routes registered in `main.py`

### Stripe Dashboard Verification
- [ ] Test mode enabled
- [ ] 2 products created (Basic, Educator)
- [ ] 4 prices created (2 monthly, 2 annual)
- [ ] Price IDs copied to `.env`

### Database Verification
```sql
-- Run these queries to verify schema
\d public.profiles  -- Should show new Stripe columns

SELECT * FROM user_tier_info LIMIT 1;  -- Should include subscription fields
```

### API Verification
```bash
# Start FastAPI server
uvicorn main:app --reload

# Visit OpenAPI docs
open http://localhost:8000/docs

# Verify billing endpoints exist (should return 501 Not Implemented)
```

---

## Common Issues & Troubleshooting

### Issue 1: `stripe` Import Error
**Symptom**: `ModuleNotFoundError: No module named 'stripe'`

**Solution**:
```bash
pip install stripe==8.0.0
pip freeze | grep stripe  # Verify installation
```

### Issue 2: Migration Fails (Column Already Exists)
**Symptom**: `ERROR: column "stripe_customer_id" already exists`

**Solution**: Migration is idempotent, error can be ignored. Verify with:
```sql
SELECT column_name FROM information_schema.columns 
WHERE table_name = 'profiles' AND column_name LIKE 'stripe%';
```

### Issue 3: Stripe API Key Not Working
**Symptom**: `stripe.error.AuthenticationError: Invalid API Key`

**Solution**:
1. Verify test mode is enabled in Stripe Dashboard
2. Check key starts with `sk_test_` (not `sk_live_`)
3. Regenerate key in Dashboard if needed
4. Ensure no extra spaces in `.env` file

### Issue 4: Price IDs Not Found
**Symptom**: `config.STRIPE_PRICE_BASIC_MONTHLY` is empty string

**Solution**:
1. Create products in Stripe Dashboard first
2. Copy price IDs (start with `price_`)
3. Add to `.env` file
4. Restart FastAPI server to reload config

---

## Next Steps

Once all tasks complete:
1. ✅ Verify all checklist items
2. ✅ Commit changes with message: `feat: add Stripe infrastructure setup (Epic 1)`
3. ✅ Push to feature branch: `git push origin feat/stripe-integration`
4. ➡️ Proceed to **Epic 2: Checkout Flow Implementation**

---

**Epic Owner**: GitHub Copilot  
**Last Updated**: 2025-11-19  
**Status**: Ready for Implementation
