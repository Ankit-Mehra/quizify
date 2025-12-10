-- Migration: 029 - Hybrid Credit System for Billing
-- Description: Implements the 3-bucket credit system (subscription, free, purchased)
--              with proper period tracking and billing plan support
-- Date: 2025-12-09
-- Consolidated from: 029, 030, 031

-- ============================================================================
-- SECTION 1: Schema Changes - Add all credit tracking columns
-- ============================================================================

-- 1.1 Add basic credit tracking columns
ALTER TABLE public.profiles
ADD COLUMN IF NOT EXISTS credit_units_monthly INT NOT NULL DEFAULT 6,
ADD COLUMN IF NOT EXISTS credit_units_remaining INT NOT NULL DEFAULT 6,
ADD COLUMN IF NOT EXISTS credit_units_purchased INT NOT NULL DEFAULT 0;

-- 1.2 Add billing_plan column for new billing model (free/pro only)
ALTER TABLE public.profiles
ADD COLUMN IF NOT EXISTS billing_plan TEXT DEFAULT 'free' 
CHECK (billing_plan IN ('free', 'pro'));

-- 1.3 Add dedicated columns for FREE credits (separate from subscription credits)
-- This implements the 3-bucket system: subscription + free + purchased
ALTER TABLE public.profiles
ADD COLUMN IF NOT EXISTS free_credit_units_monthly INT NOT NULL DEFAULT 6,
ADD COLUMN IF NOT EXISTS free_credit_units_remaining INT NOT NULL DEFAULT 6;

-- 1.4 Add column comments for documentation
COMMENT ON COLUMN public.profiles.credit_units_monthly IS 
'Monthly SUBSCRIPTION credit allowance in units (pro=60). Legacy column - defaults to 6 for backward compat but free users use free_credit_units_* columns instead.';
COMMENT ON COLUMN public.profiles.credit_units_remaining IS 
'Remaining units from SUBSCRIPTION allowance. Pro users only (set to 0 for free users). Resets on invoice.paid.';
COMMENT ON COLUMN public.profiles.credit_units_purchased IS 
'Units purchased via credit packs. Never expires, consumed FIRST.';
COMMENT ON COLUMN public.profiles.billing_plan IS 
'Billing plan: free or pro. Determines subscription credits.';
COMMENT ON COLUMN public.profiles.free_credit_units_monthly IS 
'Monthly FREE credit allowance in units (always 6 for all users). 1 credit = 2 units.';
COMMENT ON COLUMN public.profiles.free_credit_units_remaining IS 
'Remaining units from FREE allowance. Resets monthly via cron (free) or invoice.paid (pro).';


-- ============================================================================
-- SECTION 2: Data Backfill - Migrate existing users to new credit system
-- ============================================================================

-- 2.1 Map existing Pro/Premium/Basic users to 'pro' plan with 60 subscription units
UPDATE public.profiles
SET 
    billing_plan = 'pro',
    credit_units_monthly = 60,
    credit_units_remaining = 60,
    free_credit_units_monthly = 6,
    free_credit_units_remaining = 6
WHERE account_tier IN ('basic', 'premium', 'pro');

-- 2.2 Map Free users (or null) to 'free' plan
-- Free users get 0 subscription credits, 6 free credits
UPDATE public.profiles
SET 
    billing_plan = 'free',
    credit_units_monthly = 6,  -- Legacy column (kept for compatibility)
    credit_units_remaining = 0, -- No subscription credits for free users
    free_credit_units_monthly = 6,
    free_credit_units_remaining = 6
WHERE account_tier = 'free' OR account_tier IS NULL;

-- 2.3 Ensure every profile has an active period window for cron resets
-- Uses calendar month boundaries for consistency
UPDATE public.profiles
SET
    current_period_start = COALESCE(current_period_start, date_trunc('month', now())),
    current_period_end = COALESCE(current_period_end, date_trunc('month', now()) + interval '1 month')
WHERE current_period_start IS NULL OR current_period_end IS NULL;


-- ============================================================================
-- SECTION 3: Trigger - Initialize new users with credit system
-- ============================================================================

-- Create or replace the handle_new_user trigger function
-- SECURITY: Uses SECURITY DEFINER because this runs as an auth trigger
--           when the user doesn't exist in profiles yet (RLS can't apply)
-- SAFE because: No user input, only uses NEW.id from auth, SET search_path = ''
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
  INSERT INTO public.profiles (
    id,
    account_tier,
    billing_plan,
    credit_units_monthly,
    credit_units_remaining,
    credit_units_purchased,
    free_credit_units_monthly,
    free_credit_units_remaining,
    current_period_start,
    current_period_end
  )
  VALUES (
    NEW.id,
    'free',                                          -- Legacy tier
    'free',                                          -- Billing plan
    6,                                               -- Legacy monthly (kept for compatibility)
    0,                                               -- Subscription bucket (empty for free users)
    0,                                               -- Purchased credits
    6,                                               -- Free monthly allowance
    6,                                               -- Free credits remaining
    date_trunc('month', now()),                      -- Period starts at beginning of current month
    date_trunc('month', now()) + interval '1 month'  -- Period ends at beginning of next month
  )
  ON CONFLICT (id) DO NOTHING;

  RETURN NEW;
END;
$$;

COMMENT ON FUNCTION public.handle_new_user IS 
'Initializes new user profile with 3-bucket credit system. Triggered on auth.users INSERT.';


-- ============================================================================
-- SECTION 4: View - User tier info with credit status
-- ============================================================================

-- Drop and recreate the view with all credit bucket information
DROP VIEW IF EXISTS user_tier_info;

CREATE OR REPLACE VIEW user_tier_info AS
SELECT 
    u.id,
    u.email,
    p.display_name,
    
    -- Map billing_plan to account_tier for backward compatibility
    COALESCE(p.billing_plan, 'free') AS account_tier,
    COALESCE(p.role, 'user') AS role,
    
    -- Credit fields (3-bucket system: subscription + free + purchased)
    (COALESCE(p.credit_units_remaining, 0) + 
     COALESCE(p.credit_units_purchased, 0) + 
     COALESCE(p.free_credit_units_remaining, 0)) AS available_units,
    
    (COALESCE(p.credit_units_remaining, 0) + 
     COALESCE(p.credit_units_purchased, 0) + 
     COALESCE(p.free_credit_units_remaining, 0)) / 2.0 AS available_credits,
    
    -- Monthly allowance: Pro gets subscription (60) + free (6), Free users get just free (6)
    CASE 
        WHEN COALESCE(p.billing_plan, 'free') = 'pro' 
        THEN (COALESCE(p.credit_units_monthly, 60) + COALESCE(p.free_credit_units_monthly, 6)) / 2.0
        ELSE COALESCE(p.free_credit_units_monthly, 6) / 2.0
    END AS monthly_credits,
    
    COALESCE(p.credit_units_purchased, 0) / 2.0 AS purchased_credits,
    
    -- Individual bucket visibility (for debugging/admin)
    COALESCE(p.credit_units_remaining, 0) AS subscription_units_remaining,
    COALESCE(p.free_credit_units_remaining, 0) AS free_units_remaining,
    COALESCE(p.credit_units_purchased, 0) AS purchased_units,
    
    -- Period info
    p.current_period_start,
    p.current_period_end AS period_end,
    
    -- Stripe info
    p.stripe_customer_id,
    p.stripe_subscription_id,
    p.subscription_status,
    p.billing_plan,
    
    -- Legacy fields for backward compatibility
    (SELECT count(*) FROM quizzes q WHERE q.created_by = u.id) AS current_quiz_count,
    
    -- Quota limit (legacy): 5 for free, -1 (unlimited) for pro
    CASE 
        WHEN COALESCE(p.billing_plan, 'free') = 'pro' THEN -1
        ELSE 5
    END AS quota_limit,
    
    -- Quota exceeded: Check if total credits <= 0
    ((COALESCE(p.credit_units_remaining, 0) + 
      COALESCE(p.credit_units_purchased, 0) + 
      COALESCE(p.free_credit_units_remaining, 0)) <= 0) AS quota_exceeded,
    
    p.created_at,
    p.updated_at

FROM auth.users u
LEFT JOIN public.profiles p ON u.id = p.id;

COMMENT ON VIEW user_tier_info IS 
'User billing info with 3-bucket credit status: subscription + free + purchased.';
