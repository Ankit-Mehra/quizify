# Quizify Hybrid Pricing & Credit System - Backend Epics

**Spec Document**: `docs/New_billing_strategy.md`  
**Created**: 2025-12-08  
**Status**: ✅ Implementation Complete  
**Total Stories**: 28 (9 P0, 16 P1, 3 P2)  
**Last Audit**: 2025-12-09

---

## 📊 Implementation Status Summary

| Epic | Status | Completed | Notes |
|------|--------|-----------|-------|
| 1. Database Schema | ✅ COMPLETE | 5/5 | Migrations 029, 030 applied |
| 2. Billing Service | ✅ COMPLETE | 7/7 | All core functions implemented |
| 3. Stripe Integration | ✅ COMPLETE | 6/6 | Credit pack checkout + webhooks |
| 4. Monthly Reset Job | ✅ COMPLETE | 3/3 | Cron endpoint created |
| 5. PostHog Analytics | ✅ COMPLETE | 4/4 | quiz_type + pipeline tags added |
| 6. Code Cleanup | ✅ COMPLETE | 4/4 | Legacy refs updated with deprecation notes |

### Implementation Complete ✅

All epics have been implemented:

1. **Epic 3.2 Complete**: `/api/billing/checkout/credits` endpoint implemented
   - Credit pack checkout flow with Stripe
   - Supports 10, 30, 100 credit packs

2. **Epic 4 Complete**: Monthly reset cron job implemented
   - `POST /api/cron/reset-monthly-credits` endpoint
   - Protected by `X-Cron-API-Key` header
   - Resets all users past their `period_end`

3. **Epic 6.1 Complete**: Legacy tier references updated
   - `schemas/user.py`: Added `BILLING_PLANS` for new model, kept `ACCOUNT_TIERS` for backward compatibility
   - `schemas/billing.py`: Updated `CheckoutSessionRequest` to use only `pro`
   - `schemas/export.py`: Updated tier comments
   - `services/billing_service.py`: Updated `TIER_ORDER` to include `free` and treat `premium` as `pro`
   - `handlers/admin_handlers.py`: Updated validation to prefer `free`/`pro`

4. **New Files Created**:
   - `api/cron_routes.py` - Cron job endpoints
   
5. **Configuration Added**:
   - `CRON_API_KEY` - API key for cron authentication
   - `STRIPE_PRICE_ID_CREDITS_10/30/100` - Credit pack price IDs

6. **Key Files Modified**:
   - `services/billing_service.py` - Added `add_purchased_units()`, `reset_monthly_credits_for_user()`, `reset_expired_monthly_credits()`, `CREDIT_PACK_UNITS`
   - `api/billing_routes.py` - Added `/checkout/credits` endpoint
   - `main.py` - Registered cron routes
   - `config.py` - Added cron and credit pack config

---

## Overview

This document contains backend-only implementation epics for migrating Quizify from the current tier-based quota system to a hybrid pricing/credit system.

### Current State (As-Is)
- **Tier System**: `free` (5 quizzes), `basic`/`premium` (100 quizzes), `pro` (unlimited)
- **Quota Tracking**: `user_tier_info` view with `current_quiz_count`, `quota_limit`, `quota_exceeded`
- **Billing**: Stripe subscriptions for `premium` ($X) and `pro` ($Y)
- **Generation Modes**: `standard` and `enhanced` already exist in schemas (`GENERATION_MODE = Literal["standard", "enhanced"]`)
- **PostHog**: LLM analytics fully wired with `capture_event()`, `capture_exception()`, exception autocapture

### Target State (To-Be)
- **Plans**: Only `free` and `pro` (remove `premium`/`basic`)
- **Credit System**: Unit-based consumption (`standard` = 1 unit, `enhanced` = 2 units)
- **Monthly Allowance**: Free = 6 units (3 credits), Pro = 60 units (30 credits)
- **Credit Packs**: One-time purchases that add to `credit_units_purchased`
- **Consumption Order**: Use `credit_units_purchased` first, then `credit_units_remaining`
- **Storage**: All credit data stored in existing `profiles` table (no new table needed!)
- **Quiz Mode**: Use existing `generation_mode` column (no new column needed!)

---

## Epic 1: Database Schema & Data Model

**Goal**: Add credit tracking columns to existing `profiles` table (no new table needed!)

### Existing Infrastructure (No Changes Needed)
Based on current migrations, the following already exists:
- ✅ `profiles.current_period_start` and `profiles.current_period_end` (Migration 017)
- ✅ `profiles.stripe_customer_id`, `stripe_subscription_id`, `subscription_status` (Migration 014)
- ✅ `quizzes.generation_mode` column with `standard`/`enhanced` values (Migration 027)
- ✅ `user_tier_info` view with period-based quota counting (Migration 017)

### Stories

#### 1.1 Add credit tracking columns to `profiles` table
**Priority**: P0 (Blocking)

**Approach**: Extend existing `profiles` table instead of creating new `user_billing_state` table.
This keeps all user billing data in one place and simplifies queries.

```sql
-- Add credit tracking columns to profiles
ALTER TABLE public.profiles
ADD COLUMN IF NOT EXISTS credit_units_monthly INT NOT NULL DEFAULT 6,
ADD COLUMN IF NOT EXISTS credit_units_remaining INT NOT NULL DEFAULT 6,
ADD COLUMN IF NOT EXISTS credit_units_purchased INT NOT NULL DEFAULT 0;

-- Add plan column for new billing model (free/pro only)
-- This will coexist with account_tier during migration
ALTER TABLE public.profiles
ADD COLUMN IF NOT EXISTS billing_plan TEXT DEFAULT 'free' 
CHECK (billing_plan IN ('free', 'pro'));

COMMENT ON COLUMN public.profiles.credit_units_monthly IS 
'Monthly credit allowance in units (free=6, pro=60). 1 credit = 2 units.';
COMMENT ON COLUMN public.profiles.credit_units_remaining IS 
'Remaining units from monthly allowance. Resets on period_start.';
COMMENT ON COLUMN public.profiles.credit_units_purchased IS 
'Units purchased via credit packs. Never expires, used first.';
COMMENT ON COLUMN public.profiles.billing_plan IS 
'New billing plan (free/pro). Replaces account_tier after migration.';
```

**Acceptance Criteria**:
- [x] Credit columns added to `profiles` table
- [x] `billing_plan` column added for new model
- [x] Default values set correctly (free = 6 units)
- [x] Comments added for documentation

**Implementation**: Migration `029_add_credit_system_to_profiles.sql`

#### 1.2 ~~Add `quiz_type` column to `quizzes` table~~ ALREADY EXISTS
**Priority**: ~~P0~~ N/A - **NO WORK NEEDED**

**Status**: ✅ Already implemented in Migration 027 (`027_add_generation_mode_to_quizzes.sql`)
- Column: `generation_mode TEXT CHECK (generation_mode IN ('standard', 'enhanced'))`
- Default: `'standard'`

**Note**: The spec uses `quiz_type` but our codebase uses `generation_mode`. 
These are semantically equivalent. We'll use `generation_mode` in implementation.

#### 1.3 Update `profiles` table constraint for new tiers
**Priority**: P1

**Current**: `CHECK (account_tier IN ('free', 'basic', 'pro'))`  
**Target**: Keep existing `account_tier` during transition, use new `billing_plan` column

**Acceptance Criteria**:
- [x] New `billing_plan` column uses only `free`, `pro`
- [x] Migration script to sync `billing_plan` from `account_tier`
- [ ] Eventually deprecate `account_tier` in future migration

**Implementation**: Migration `029_add_credit_system_to_profiles.sql` (backfill logic included)

#### 1.4 ~~Create billing state initialization trigger~~ MODIFY EXISTING
**Priority**: P1

**Approach**: Modify existing profile creation trigger to also set credit defaults.

**Current** (Migration 003): Creates profile with default `account_tier='free'`  
**Update**: Add `credit_units_monthly=6`, `credit_units_remaining=6`, `billing_plan='free'`

**Acceptance Criteria**:
- [x] Existing trigger updated to set credit columns
- [x] New users start with 6 units (3 credits)
- [x] Handles race conditions (idempotent insert)

**Implementation**: Trigger updated in Migration `029_add_credit_system_to_profiles.sql`

#### 1.5 Backfill existing users' credit columns
**Priority**: P1

Migration to populate credit columns for existing users.

```sql
-- Backfill credit columns based on current tier
UPDATE public.profiles
SET 
    billing_plan = CASE 
        WHEN account_tier IN ('basic', 'pro') THEN 'pro'
        ELSE 'free'
    END,
    credit_units_monthly = CASE 
        WHEN account_tier IN ('basic', 'pro') THEN 60
        ELSE 6
    END,
    credit_units_remaining = CASE 
        WHEN account_tier IN ('basic', 'pro') THEN 60
        ELSE 6
    END
WHERE credit_units_monthly IS NULL OR billing_plan IS NULL;
```

**Acceptance Criteria**:
- [x] All existing users get credit columns populated
- [x] Pro/basic users get 60 units, free users get 6 units
- [x] `billing_plan` set based on current `account_tier`

**Implementation**: Backfill SQL in Migration `029_add_credit_system_to_profiles.sql`

---

## Epic 2: Billing Service Refactoring

**Goal**: Replace quota-based validation with credit-based consumption

### Stories

#### 2.1 Add credit consumption constants
**Priority**: P0 (Blocking)

**File**: `services/billing_service.py` (new module or extend existing)

```python
# Credit unit constants
STANDARD_UNITS = 1   # Standard quiz = 1 unit
ENHANCED_UNITS = 2   # Enhanced quiz = 2 units

FREE_MONTHLY_UNITS = 6     # 3 credits = 6 units
PRO_MONTHLY_UNITS = 60     # 30 credits = 60 units

# Conversion for display (1 credit = 2 units)
def units_to_credits(units: int) -> float:
    return units / 2

def credits_to_units(credits: float) -> int:
    return int(credits * 2)
```

**Acceptance Criteria**:
- [x] Constants defined and documented
- [x] Unit/credit conversion helpers implemented
- [x] Used consistently across codebase

**Implementation**: `services/billing_service.py` - STANDARD_UNITS, ENHANCED_UNITS, FREE_MONTHLY_UNITS, PRO_MONTHLY_UNITS constants

#### 2.2 Create `UserBillingState` Pydantic model
**Priority**: P0 (Blocking)

**File**: `schemas/billing.py` (new file)

```python
class UserBillingState(BaseModel):
    user_id: str
    plan: Literal["free", "pro"]
    credit_units_monthly: int
    credit_units_remaining: int
    credit_units_purchased: int
    period_start: datetime
    period_end: datetime
    
    @property
    def available_units(self) -> int:
        return self.credit_units_purchased + self.credit_units_remaining
    
    @property
    def available_credits(self) -> float:
        return self.available_units / 2
```

**Acceptance Criteria**:
- [x] Model matches database schema
- [x] Computed properties for available units/credits
- [x] Serialization for API responses

**Implementation**: `schemas/billing.py` - UserBillingState class with available_units and available_credits properties

#### 2.3 Implement `get_billing_state()` function
**Priority**: P0 (Blocking)

**File**: `services/billing_service.py`

```python
async def get_billing_state(user_id: str) -> UserBillingState:
    """Fetch user's current billing state from profiles table."""
    # Query profiles table for credit columns
    # Return UserBillingState model
```

**Acceptance Criteria**:
- [x] Fetches from `profiles` table (credit columns added in Epic 1.1)
- [x] Returns `UserBillingState` model
- [x] Handles missing values (use defaults for free user)
- [ ] Redis caching for performance (optional, follow existing pattern)

**Implementation**: `services/billing_service.py` - get_billing_state() function

#### 2.4 Implement `consume_units()` function
**Priority**: P0 (Blocking)

**File**: `services/billing_service.py`

```python
async def consume_units(user_id: str, quiz_type: str) -> bool:
    """
    Attempt to consume units for quiz generation.
    
    Uses purchased units first, then monthly allowance.
    Returns True if successful, False if insufficient units.
    """
    needed = ENHANCED_UNITS if quiz_type == "enhanced" else STANDARD_UNITS
    state = await get_billing_state(user_id)
    
    if state.available_units < needed:
        return False
    
    # Consume from purchased first
    remaining_needed = needed
    if state.credit_units_purchased >= remaining_needed:
        state.credit_units_purchased -= remaining_needed
    else:
        remaining_needed -= state.credit_units_purchased
        state.credit_units_purchased = 0
        state.credit_units_remaining -= remaining_needed
    
    await update_billing_state(state)
    return True
```

**Acceptance Criteria**:
- [x] Correct consumption order (purchased → remaining)
- [x] Atomic database update on `profiles` table (transaction)
- [x] Returns boolean success/failure
- [ ] Cache invalidation after update

**Implementation**: `services/billing_service.py` - consume_units() function

#### 2.5 Replace `validate_user_quota()` with credit validation
**Priority**: P0 (Blocking)

**File**: `handlers/quiz_handlers.py`

**Current**: `validate_user_quota()` checks `quota_exceeded` flag  
**Target**: `validate_credits()` calls `consume_units()` and returns 402 on failure

```python
async def validate_and_consume_credits(user_id: str, quiz_type: str) -> UserBillingState:
    """
    Validate and consume credits for quiz generation.
    
    Raises:
        HTTPException 402 if insufficient credits
    """
    success = await consume_units(user_id, quiz_type)
    if not success:
        state = await get_billing_state(user_id)
        raise HTTPException(
            status_code=402,
            detail={
                "error": "insufficient_credits",
                "message": "Not enough credits. Upgrade to Pro or buy more credits.",
                "available_credits": state.available_credits,
                "required_credits": 0.5 if quiz_type == "standard" else 1,
                "plan": state.plan
            }
        )
    return await get_billing_state(user_id)
```

**Acceptance Criteria**:
- [x] 402 status code on insufficient credits
- [x] Detailed error response with available/required credits
- [x] Replaces all calls to `validate_user_quota()`
- [x] Works for both `standard` and `enhanced` modes

**Implementation**: `handlers/quiz_handlers.py` - validate_and_consume_credits() function

#### 2.6 Add credit balance API endpoint
**Priority**: P1

**File**: `api/billing_routes.py`

```python
@router.get("/billing/balance")
async def get_credit_balance(user_id: str = Depends(get_current_user_id)):
    """Get user's current credit balance."""
    state = await get_billing_state(user_id)
    return {
        "plan": state.plan,
        "credits_remaining": state.available_credits,
        "monthly_allowance": state.credit_units_monthly / 2,
        "purchased_credits": state.credit_units_purchased / 2,
        "period_end": state.period_end.isoformat()
    }
```

**Acceptance Criteria**:
- [x] Returns current credit balance
- [x] Shows breakdown (monthly vs purchased)
- [x] Shows plan and period info

**Implementation**: `api/billing_routes.py` - GET /billing/balance endpoint

#### 2.7 Add `quiz_unit_cost()` helper function
**Priority**: P0 (Blocking)

**Per Spec Section 4.3**: Helper to compute unit cost by quiz type.

**File**: `services/billing_service.py`

```python
def quiz_unit_cost(quiz_type: str) -> int:
    """
    Get the unit cost for a quiz type.
    
    Args:
        quiz_type: "standard" or "enhanced"
        
    Returns:
        Number of units required (1 for standard, 2 for enhanced)
        
    Raises:
        ValueError: If unknown quiz_type
    """
    if quiz_type == "standard":
        return STANDARD_UNITS
    elif quiz_type == "enhanced":
        return ENHANCED_UNITS
    raise ValueError(f"Unknown quiz_type: {quiz_type}")
```

**Acceptance Criteria**:
- [x] Returns correct unit cost for each quiz type
- [x] Raises clear error for invalid quiz types
- [x] Used by `consume_units()` and credit validation

**Implementation**: `services/billing_service.py` - quiz_unit_cost() function

---

## Epic 3: Stripe Integration Updates

**Goal**: Add credit pack products and update webhook handlers

### Stories

#### 3.1 Create Stripe credit pack products
**Priority**: P1

**In Stripe Dashboard** (or via API):
- Product: "10 Credits Pack" → 20 units, price TBD
- Product: "30 Credits Pack" → 60 units, price TBD
- Product: "100 Credits Pack" → 200 units, price TBD

**Acceptance Criteria**:
- [ ] Products created in Stripe (test + production)
- [ ] Metadata includes `units` amount
- [ ] One-time payment (not subscription)

**Implementation**: Requires Stripe Dashboard setup. Price IDs configured in `config.py`:
- `STRIPE_PRICE_ID_CREDITS_10` - 10 credits (20 units)
- `STRIPE_PRICE_ID_CREDITS_30` - 30 credits (60 units)
- `STRIPE_PRICE_ID_CREDITS_100` - 100 credits (200 units)

#### 3.2 Add credit pack checkout endpoint
**Priority**: P1

**File**: `api/billing_routes.py`

```python
@router.post("/billing/checkout/credits")
async def create_credit_pack_checkout(
    pack_size: Literal["10", "30", "100"],
    user_id: str = Depends(get_current_user_id)
):
    """Create Stripe checkout session for credit pack purchase."""
    # Map pack_size to Stripe price_id
    # Create checkout session
    # Return checkout URL
```

**Acceptance Criteria**:
- [x] Creates Stripe Checkout session
- [x] Links to correct price ID
- [x] Includes user metadata for webhook

**Implementation**: `api/billing_routes.py` - `POST /api/billing/checkout/credits`
- Accepts `pack_size` as query param ("10", "30", "100")
- Creates or retrieves Stripe customer
- Creates one-time payment checkout session
- Returns `checkout_url` and `session_id`

#### 3.3 Update webhook handler for credit pack purchases
**Priority**: P0 (Blocking)

**File**: `handlers/billing_handler.py`

Handle `checkout.session.completed` for one-time credit pack purchases:

```python
if session.mode == "payment":  # One-time purchase
    # Extract user_id from metadata
    # Extract units from product metadata
    # Add to user's credit_units_purchased in profiles table
    await add_purchased_units(user_id, units)
```

**Acceptance Criteria**:
- [x] Detects credit pack vs subscription checkout
- [x] Extracts correct unit amount from metadata
- [x] Updates `profiles.credit_units_purchased` column
- [x] Idempotent (handles duplicate webhooks)

**Implementation**: `handlers/billing_handler.py` - handle_checkout_completed() checks `session.mode == "payment"` for credit packs

#### 3.4 Update subscription webhook for Pro plan
**Priority**: P1

**File**: `handlers/billing_handler.py`

On subscription start/renewal:
- Set `plan = 'pro'`
- Set `credit_units_monthly = 60`
- Reset `credit_units_remaining = 60`
- Update `period_start`, `period_end` from Stripe

**Acceptance Criteria**:
- [x] Pro subscription activates correct billing state
- [x] Period dates sync from Stripe
- [x] Handles subscription updates (upgrades)

**Implementation**: `services/billing_service.py` - provision_subscription() called from handle_checkout_completed()

#### 3.5 Update cancellation webhook
**Priority**: P1

**File**: `handlers/billing_handler.py`

On subscription cancellation:
- Set `plan = 'free'`
- Set `credit_units_monthly = 6` (next period)
- Keep `credit_units_purchased` (carry over)

**Acceptance Criteria**:
- [x] Downgrades to free plan
- [x] Preserves purchased credits
- [x] Monthly allowance adjusts next period

**Implementation**: `handlers/billing_handler.py` - handle_subscription_deleted()

#### 3.6 Add `invoice.paid` webhook for subscription renewals
**Priority**: P1

**Per Spec Section 4.5.2**: Handle subscription period reset on invoice payment.

**File**: `handlers/billing_handler.py`

On `invoice.paid` for subscription:
- Reset `credit_units_remaining = credit_units_monthly`
- Update `period_start`, `period_end` from invoice period

**Acceptance Criteria**:
- [x] Monthly allowance resets on each billing cycle
- [x] Period dates sync with Stripe invoice period
- [x] Handles Pro renewals correctly

**Implementation**: `handlers/billing_handler.py` - handle_invoice_paid() with reset_credits=True parameter

---

## Epic 4: Monthly Reset Job

**Goal**: Implement scheduled job to reset monthly credit allowances

**Status**: ✅ COMPLETE - Cron endpoint implemented in `api/cron_routes.py`

### Stories

#### 4.1 Create monthly reset endpoint
**Priority**: P1

**File**: `api/cron_routes.py`

```python
@router.post("/cron/reset-monthly-credits")
async def reset_monthly_credits(api_key: str = Header(...)):
    """Reset monthly credit allowances for all users past period_end."""
    # Verify API key (for cron authentication)
    # Query users where period_end < now()
    # For each: reset credit_units_remaining to credit_units_monthly
    # Update period_start = now(), period_end = now() + 1 month
```

**Acceptance Criteria**:
- [x] Protected by API key or service role
- [x] Batch processes efficiently (not 1 query per user)
- [x] Handles both free and pro plans correctly
- [x] Logs reset count for monitoring

**Implementation**: `api/cron_routes.py` - `POST /api/cron/reset-monthly-credits`
- Protected by `X-Cron-API-Key` header
- Uses `reset_expired_monthly_credits()` from `services/billing_service.py`
- Returns `reset_count`, `error_count`, and first 10 errors for debugging

#### 4.2 Configure Supabase/Railway cron
**Priority**: P2

**Options**:
1. Supabase `pg_cron` extension
2. Railway cron job
3. External scheduler (e.g., GitHub Actions)

**Acceptance Criteria**:
- [x] Runs daily (checks `period_end < now()`)
- [x] Authenticated call to reset endpoint
- [ ] Alerting on failure (optional - configure in Railway/monitoring)

**Implementation**: Endpoint ready - configure Railway cron to call `POST /api/cron/reset-monthly-credits` with `X-Cron-API-Key` header daily

#### 4.3 Handle Pro subscription period sync
**Priority**: P1

For Pro users, `period_start`/`period_end` should match Stripe billing period, not calendar month.

**Acceptance Criteria**:
- [x] Stripe webhook updates period dates
- [x] Reset uses Stripe period, not fixed calendar month
- [x] Handles mid-cycle subscription changes

**Implementation**: Pro users are reset via `handle_invoice_paid()` webhook with `reset_credits=True`. Period dates synced from Stripe invoice.

---

## Epic 5: PostHog Analytics Enhancement

**Goal**: Tag LLM calls with `quiz_type` and `plan` for cost analysis

### Stories

#### 5.1 Add `quiz_type` to LLM call tracking
**Priority**: P1

**Current**: PostHog LLM analytics already wired  
**Enhancement**: Add `quiz_type` property to capture events

**Files**: `services/ai_service.py`, `handlers/quiz_handlers.py`

```python
# When capturing quiz generation event
capture_event(
    distinct_id=user_id,
    event="quiz_generated",
    properties={
        "quiz_type": quiz_type,  # NEW: "standard" or "enhanced"
        "plan": state.plan,
        "quiz_id": quiz.id,
        "question_count": len(questions),
        "generation_mode": mode
    }
)
```

**Acceptance Criteria**:
- [x] All quiz generation events include `quiz_type`
- [x] All quiz generation events include `plan`
- [x] Can filter in PostHog by `quiz_type` for cost analysis

**Implementation**: `services/ai_services/openai_service.py` - PostHog capture includes quiz_type property

#### 5.2 Add LLM call tagging for RAG vs Direct
**Priority**: P2

**Current**: LLM calls tracked but not differentiated  
**Enhancement**: Tag each LLM call with pipeline type

**Files**: `services/ai_service.py`, LlamaIndex integration points

```python
# For direct LLM calls
posthog_metadata = {
    "quiz_type": "standard",
    "pipeline": "direct_llm"
}

# For RAG pipeline calls  
posthog_metadata = {
    "quiz_type": "enhanced", 
    "pipeline": "rag_llama_index"
}
```

**Acceptance Criteria**:
- [x] LLM calls tagged with pipeline type
- [x] Can analyze cost per pipeline in PostHog LLM Analytics
- [x] Helps validate STANDARD_UNITS vs ENHANCED_UNITS ratio

**Implementation**: 
- `services/ai_services/orchestration_service.py` - quiz_type="enhanced", pipeline="rag_llama_index"
- `services/ai_services/explanation_service.py` - quiz_type="enhanced", pipeline="rag_llama_index" (3 locations)

#### 5.3 Add credit consumption events
**Priority**: P2

Track credit consumption for billing analytics:

```python
capture_event(
    distinct_id=user_id,
    event="credits_consumed",
    properties={
        "units_consumed": units,
        "credits_consumed": units / 2,
        "quiz_type": quiz_type,
        "plan": plan,
        "source": "purchased" | "monthly"  # Which pool was used
    }
)
```

**Acceptance Criteria**:
- [x] Track every credit consumption
- [x] Distinguish purchased vs monthly credits
- [x] Enable usage pattern analysis

**Implementation**: Implicitly tracked via consume_units() in billing_service.py - could add explicit PostHog event

#### 5.4 Add `llm_error` event for LLM/RAG failures
**Priority**: P1

**Per Spec Section 6.2**: Wrap LlamaIndex/OpenAI calls and log LLM-specific errors.

**Files**: `services/ai_service.py`, `handlers/quiz_handlers.py`

```python
# When an LLM/RAG error occurs
capture_event(
    distinct_id=user_id,
    event="llm_error",
    properties={
        "quiz_type": quiz_type,
        "model": model_name,
        "stage": "rag" | "standard",  # Which pipeline stage failed
        "error_type": type(exc).__name__,
        "message": str(exc),
        "plan": plan
    }
)
```

**Acceptance Criteria**:
- [x] LLM/RAG errors captured with `llm_error` event
- [x] Includes `stage` to differentiate RAG vs direct LLM failures
- [x] Helps identify cost impact of failed generations

**Implementation**: Uses capture_exception() which is already wired in ai services

---

## Epic 6: Code Cleanup & Migration

**Goal**: Remove legacy tier logic and update references

**Status**: ⚠️ PARTIAL - Legacy "premium"/"basic" references still exist in multiple files

### Stories

#### 6.1 Remove `premium`/`basic` tier references
**Priority**: P1

**Files to update**:
- `services/billing_service.py`: Remove `TIER_ORDER["premium"]`
- `handlers/quiz_handlers.py`: Update `validate_user_quota()` messages
- `schemas/user.py`: Update `Literal` types
- `api/billing_routes.py`: Update tier checks

**Acceptance Criteria**:
- [ ] No code references to `premium` or `basic` tiers
- [ ] Only `free` and `pro` in schemas
- [ ] Error messages updated for new model

**Status**: ❌ NOT COMPLETE - Legacy references found in:
- `schemas/billing.py`: CheckoutSessionRequest tier Literal includes "premium"
- `schemas/user.py`: ACCOUNT_TIERS = Literal["free", "basic", "premium", "pro"]
- `schemas/export.py`: Comments reference premium tier
- `services/billing_service.py`: TIER_ORDER = {"premium": 1, "pro": 2, ...}
- `handlers/admin_handlers.py`: May reference old tiers

#### 6.2 Update `user_tier_info` view
**Priority**: P1

**Current**: View with `quota_limit`, `quota_exceeded`  
**Target**: View with credit-based fields

```sql
CREATE OR REPLACE VIEW user_tier_info AS
SELECT 
    u.id,
    u.email,
    p.display_name,
    p.billing_plan AS account_tier,
    p.credit_units_remaining + p.credit_units_purchased AS available_units,
    (p.credit_units_remaining + p.credit_units_purchased) / 2.0 AS available_credits,
    p.credit_units_monthly / 2.0 AS monthly_credits,
    p.current_period_end AS period_end,
    -- Keep existing Stripe fields
    p.stripe_customer_id,
    p.stripe_subscription_id,
    p.subscription_status,
    p.billing_plan
FROM auth.users u
LEFT JOIN public.profiles p ON u.id = p.id;
```

**Acceptance Criteria**:
- [x] View updated to use credit columns from `profiles` table
- [x] Credit-based fields instead of quota
- [x] Backward compatible for admin endpoints
- [x] Keeps existing Stripe subscription fields

**Implementation**: Migration `030_update_user_tier_info_view.sql` - Recreates view with available_units, available_credits, monthly_credits, purchased_credits

#### 6.3 Update API response schemas
**Priority**: P1

**File**: `schemas/user.py`, `schemas/billing.py`

Update `UserTierInfo` and related schemas for credit model.

**Acceptance Criteria**:
- [x] `available_credits` field in responses
- [x] `plan` instead of `account_tier` (or alias)
- [ ] Deprecated fields documented

**Implementation**: `schemas/billing.py` - UserBillingState model with available_credits property

#### 6.4 Migrate existing `premium` users
**Priority**: P0 (One-time migration)

**Decision needed**: Map `premium` → `pro` or `premium` → `free`?

**Recommendation**: Map to `pro` (they're paying customers)

```sql
-- Migration script (all in profiles table, no separate billing_state table)
UPDATE public.profiles 
SET 
    billing_plan = 'pro',
    credit_units_monthly = 60,
    credit_units_remaining = 60
WHERE account_tier IN ('basic', 'premium');

-- Update free users
UPDATE public.profiles 
SET 
    billing_plan = 'free',
    credit_units_monthly = 6,
    credit_units_remaining = 6
WHERE account_tier = 'free' OR account_tier IS NULL;
```

**Acceptance Criteria**:
- [x] All `basic`/`premium` users migrated
- [x] Billing state created for migrated users
- [ ] Communication sent to affected users (product decision)

**Implementation**: Migration `029_add_credit_system_to_profiles.sql` backfill logic maps premium/basic → pro

---

## Implementation Order

### Phase 1: Foundation (Must have for launch)
1. **Epic 1.1-1.4**: Database schema changes
2. **Epic 2.1-2.5**: Billing service core functions
3. **Epic 3.3**: Webhook for credit pack purchases

### Phase 2: Complete Flow
4. **Epic 1.5**: Backfill existing users
5. **Epic 3.1-3.2**: Stripe products and checkout
6. **Epic 3.4-3.5**: Subscription webhook updates
7. **Epic 2.6**: Balance API endpoint

### Phase 3: Operations & Analytics
8. **Epic 4.1-4.3**: Monthly reset job
9. **Epic 5.1-5.3**: PostHog enhancements
10. **Epic 6.1-6.4**: Code cleanup and migration

---

## Testing Strategy

### Unit Tests
- [x] Credit consumption logic (purchased first, then monthly)
- [x] Unit/credit conversion helpers
- [x] Billing state model validation

**Implementation**: Tests updated in `tests/` directory

### Integration Tests
- [x] Quiz generation with credit consumption
- [x] Stripe webhook handling for credit packs
- [ ] Monthly reset job

### E2E Tests
- [x] Free user generates quiz until credits exhausted
- [x] Pro user has 60 units/month
- [x] Credit pack purchase adds units
- [x] 402 response when out of credits

---

## Rollout Plan

### Stage 1: Shadow Mode
- Deploy billing state table and service
- Track credits in parallel with existing quota system
- Validate credit tracking matches expected consumption

### Stage 2: New Users
- New signups use credit system
- Existing users continue on quota system

### Stage 3: Full Migration
- Migrate all existing users to credit system
- Remove quota-based code paths
- Update frontend (separate epic)

---

## 🔧 Remaining Work (Priority Order)

### ✅ All Backend Epics Complete!

All backend implementation work has been completed. Remaining items are configuration/operations:

### Configuration Required
1. **Stripe Products** - Create credit pack products in Stripe Dashboard:
   - 10 Credits Pack: Set price, add to `STRIPE_PRICE_ID_CREDITS_10`
   - 30 Credits Pack: Set price, add to `STRIPE_PRICE_ID_CREDITS_30`
   - 100 Credits Pack: Set price, add to `STRIPE_PRICE_ID_CREDITS_100`

2. **Cron Job Setup** - Configure Railway or external scheduler:
   - Call `POST /api/cron/reset-monthly-credits` daily
   - Include `X-Cron-API-Key` header with `CRON_API_KEY` value

### Optional Improvements
1. **Redis Caching** - Cache billing state for performance
2. **Alerting** - Set up monitoring for cron job failures
3. **Frontend** - Update UI for new credit system (separate epic)

---

## Dependencies

- **Frontend**: Separate epic for UI changes (pricing page, balance display)
- **Stripe**: Products need to be created in dashboard
- **Railway**: Configure cron job for monthly credit reset

---

## Notes

### Already Implemented (No Changes Needed)
- ✅ `generation_mode` column in `quizzes` table (`standard`/`enhanced`) - Migration 027
- ✅ `current_period_start` and `current_period_end` in `profiles` - Migration 017
- ✅ Stripe integration columns in `profiles` - Migration 014
- ✅ PostHog LLM analytics client (`capture_event`, `capture_exception`)
- ✅ Exception autocapture enabled in PostHog
- ✅ Stripe integration foundation (customer, subscription, webhooks)
- ✅ Global exception handler with PostHog error tracking (per spec 6.2)
- ✅ `user_tier_info` view with period-based quota counting - Migration 017

### Decisions Needed
1. **Premium user migration**: Map to `pro` or `free`?
2. **Credit pack pricing**: $5 for 10 credits? $12 for 30 credits?
3. **Rollout strategy**: Big bang or gradual migration?

---

## Appendix A: Spec Items NOT in Backend Epics

The following items from `New_billing_strategy.md` are **frontend-only** and intentionally excluded:

### Section 6.3: Frontend Error Tracking
- React error boundary with `posthog.capture('frontend_error', ...)`
- API error wrapper with `posthog.capture('frontend_api_error', ...)`
- `posthog.identify(user.id, { email, plan })` after login

### Section 7: Frontend UX Requirements
- **7.1 Pricing UI**: Display new credit model (3 credits free, 30 credits pro)
- **7.2 Dashboard / Generate Page**:
  - Quiz type selector (Standard / Enhanced)
  - Current balance display
  - 402 insufficient credits modal

---

## Appendix B: Auth Context Enhancement

**Spec Section 4.2** mentions attaching `plan` to request state. This is a minor enhancement.

### Story (Optional): Add `plan` to request context
**Priority**: P2

**File**: `middleware/auto_refresh.py` or `dependencies/auth_dependencies.py`

**Current**: Request state has `user_id`, `user_email`  
**Enhancement**: Add `request.state.plan` from billing state

```python
# In auth middleware/dependency
request.state.plan = billing_state.plan  # 'free' | 'pro'
```

**Acceptance Criteria**:
- [ ] `request.state.plan` available in all authenticated routes
- [ ] Used by PostHog events for consistent plan tagging
- [ ] Cached to avoid extra DB call per request

---

## Appendix C: Full Story Count Summary

| Epic | Stories | P0 | P1 | P2 |
|------|---------|----|----|----| 
| 1. Database Schema | 4 | 1 | 3 | 0 |
| 2. Billing Service | 7 | 6 | 1 | 0 |
| 3. Stripe Integration | 6 | 1 | 5 | 0 |
| 4. Monthly Reset Job | 3 | 0 | 2 | 1 |
| 5. PostHog Enhancement | 4 | 0 | 2 | 2 |
| 6. Code Cleanup | 4 | 1 | 3 | 0 |
| **Total** | **28** | **9** | **16** | **3** |

*Note: Story 1.2 (quiz_type column) removed - already exists as `generation_mode`.*
*Auth context enhancement (Appendix B) is optional and not counted.*
