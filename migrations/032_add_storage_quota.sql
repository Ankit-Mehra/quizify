-- Migration: 032 - Add Storage Quota Tracking (SAFE VERSION)
-- Description: Adds per-user storage quota limits based on billing plan
--              Free: 250 MB, Pay-as-you-go: 2 GB, Pro: 5 GB
-- Date: 2025-12-10
-- Updated: 2025-12-21 - Made safe to not regress existing view/trigger functionality
--
-- SAFETY NOTES:
-- - Uses CREATE OR REPLACE for functions (safe, won't fail if exists)
-- - Uses ADD COLUMN IF NOT EXISTS (safe, won't fail if exists)
-- - Uses CREATE INDEX IF NOT EXISTS (safe)
-- - Recreates user_tier_info view (DROP + CREATE) preserving avatar_url, quizzes_attempted
-- - Recreates handle_new_user trigger preserving OAuth metadata sync
-- - NOTE: View/trigger definitions fully replaced; this version includes all required columns

-- ============================================================================
-- SECTION 1: Storage Quota Constants
-- ============================================================================
-- Storage limits in bytes:
-- Free plan:         250 MB = 262,144,000 bytes
-- Pay-as-you-go:       2 GB = 2,147,483,648 bytes (has purchased credits, no Pro sub)
-- Pro subscription:    5 GB = 5,368,709,120 bytes

-- ============================================================================
-- SECTION 2: Add storage quota columns to profiles
-- ============================================================================

-- Add storage_quota_bytes column to track per-user limits
-- Defaults to free tier limit (250 MB)
ALTER TABLE public.profiles
ADD COLUMN IF NOT EXISTS storage_quota_bytes BIGINT NOT NULL DEFAULT 262144000;

COMMENT ON COLUMN public.profiles.storage_quota_bytes IS 
'Storage quota in bytes. Free=262144000 (250MB), PayAsYouGo=2147483648 (2GB), Pro=5368709120 (5GB)';


-- ============================================================================
-- SECTION 3: Backfill existing users based on billing plan
-- ============================================================================

-- Pro users get 5GB
UPDATE public.profiles
SET storage_quota_bytes = 5368709120  -- 5 GB
WHERE billing_plan = 'pro' 
  AND (subscription_status = 'active' OR subscription_status = 'trialing');

-- Pay-as-you-go users (free plan but has purchased credits) get 2GB
UPDATE public.profiles
SET storage_quota_bytes = 2147483648  -- 2 GB
WHERE billing_plan = 'free' 
  AND credit_units_purchased > 0;

-- Free users stay at 250MB (default)
-- No update needed since DEFAULT is already 262144000


-- ============================================================================
-- SECTION 4: Create function to calculate user's storage quota limit
-- ============================================================================

CREATE OR REPLACE FUNCTION public.get_storage_quota_limit(p_user_id UUID)
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_billing_plan TEXT;
    v_subscription_status TEXT;
    v_purchased_units INT;
BEGIN
    -- Fetch user's billing info
    SELECT 
        COALESCE(billing_plan, 'free'),
        subscription_status,
        COALESCE(credit_units_purchased, 0)
    INTO v_billing_plan, v_subscription_status, v_purchased_units
    FROM public.profiles
    WHERE id = p_user_id;
    
    -- Pro users with active subscription get 5GB
    IF v_billing_plan = 'pro' AND v_subscription_status IN ('active', 'trialing') THEN
        RETURN 5368709120;  -- 5 GB
    END IF;
    
    -- Users who have purchased credits (pay-as-you-go) get 2GB
    IF v_purchased_units > 0 THEN
        RETURN 2147483648;  -- 2 GB
    END IF;
    
    -- Free users get 250MB
    RETURN 262144000;  -- 250 MB
END;
$$;

COMMENT ON FUNCTION public.get_storage_quota_limit IS 
'Returns storage quota in bytes based on billing plan. Pro=5GB, PayAsYouGo=2GB, Free=250MB';


-- ============================================================================
-- SECTION 5: Create function to get user's current storage usage
-- ============================================================================

CREATE OR REPLACE FUNCTION public.get_storage_usage(p_user_id UUID)
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_total_bytes BIGINT;
BEGIN
    SELECT COALESCE(SUM(file_size_bytes), 0)
    INTO v_total_bytes
    FROM public.user_files
    WHERE user_id = p_user_id;
    
    RETURN v_total_bytes;
END;
$$;

COMMENT ON FUNCTION public.get_storage_usage IS 
'Returns total storage used by user in bytes (sum of all file sizes)';


-- ============================================================================
-- SECTION 6: Create function to check if file upload would exceed quota
-- ============================================================================

CREATE OR REPLACE FUNCTION public.check_storage_quota(
    p_user_id UUID,
    p_file_size_bytes BIGINT
)
RETURNS TABLE(
    allowed BOOLEAN,
    current_usage_bytes BIGINT,
    quota_limit_bytes BIGINT,
    remaining_bytes BIGINT,
    would_use_bytes BIGINT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_current_usage BIGINT;
    v_quota_limit BIGINT;
    v_remaining BIGINT;
    v_would_use BIGINT;
    v_allowed BOOLEAN;
BEGIN
    -- Get current usage and quota limit
    v_current_usage := public.get_storage_usage(p_user_id);
    v_quota_limit := public.get_storage_quota_limit(p_user_id);
    v_remaining := GREATEST(0, v_quota_limit - v_current_usage);
    v_would_use := v_current_usage + p_file_size_bytes;
    v_allowed := v_would_use <= v_quota_limit;
    
    RETURN QUERY SELECT v_allowed, v_current_usage, v_quota_limit, v_remaining, v_would_use;
END;
$$;

COMMENT ON FUNCTION public.check_storage_quota IS 
'Checks if uploading a file of given size would exceed user storage quota. Returns allowance status and usage details.';


-- ============================================================================
-- SECTION 7: Update user_tier_info view to include storage info
-- SAFE VERSION: Preserves avatar_url and quizzes_attempted columns
-- ============================================================================

-- Drop and recreate view with ALL existing columns PLUS new storage columns
DROP VIEW IF EXISTS user_tier_info;

CREATE OR REPLACE VIEW user_tier_info AS
SELECT 
    u.id,
    u.email,
    p.display_name,
    p.avatar_url,  -- PRESERVED from existing view
    
    -- Map billing_plan to account_tier for backward compatibility
    COALESCE(p.billing_plan, 'free') AS account_tier,
    COALESCE(p.role, 'user') AS role,
    
    -- Credit fields (3-bucket system: subscription + free + purchased)
    (COALESCE(p.credit_units_remaining, 0) + 
     COALESCE(p.credit_units_purchased, 0) + 
     COALESCE(p.free_credit_units_remaining, 0)) AS available_units,
    
    (COALESCE(p.credit_units_remaining, 0) + 
     COALESCE(p.credit_units_purchased, 0) + 
     COALESCE(p.free_credit_units_remaining, 0))::numeric / 2.0 AS available_credits,
    
    -- Monthly allowance: Pro gets subscription (60) + free (6), Free users get just free (6)
    -- NOTE: Using 60 to match existing production view (not 80)
    CASE 
        WHEN COALESCE(p.billing_plan, 'free') = 'pro' 
        THEN (COALESCE(p.credit_units_monthly, 60) + COALESCE(p.free_credit_units_monthly, 6))::numeric / 2.0
        ELSE COALESCE(p.free_credit_units_monthly, 6)::numeric / 2.0
    END AS monthly_credits,
    
    COALESCE(p.credit_units_purchased, 0)::numeric / 2.0 AS purchased_credits,
    
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
    
    -- Storage quota info (NEW)
    COALESCE(p.storage_quota_bytes, 262144000) AS storage_quota_bytes,
    public.get_storage_usage(u.id) AS storage_used_bytes,
    
    -- Legacy fields for backward compatibility
    (SELECT count(*) FROM quizzes q WHERE q.created_by = u.id)::integer AS current_quiz_count,
    (SELECT count(*) FROM submissions s WHERE s.user_id = u.id)::integer AS quizzes_attempted,  -- PRESERVED
    
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
'User billing info with 3-bucket credit status, storage quota tracking, avatar_url, and quizzes_attempted.';


-- ============================================================================
-- SECTION 8: Update handle_new_user trigger to set storage quota
-- SAFE VERSION: Preserves OAuth metadata sync (display_name, avatar_url)
-- ============================================================================

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  v_display_name TEXT;
  v_avatar_url TEXT;
BEGIN
  -- Extract OAuth metadata (Google, GitHub, etc.)
  v_display_name := COALESCE(
    NEW.raw_user_meta_data->>'full_name',
    NEW.raw_user_meta_data->>'name',
    NULL
  );

  v_avatar_url := COALESCE(
    NEW.raw_user_meta_data->>'avatar_url',
    NEW.raw_user_meta_data->>'picture',
    NULL
  );

  INSERT INTO public.profiles (
    id,
    account_tier,
    billing_plan,
    credit_units_monthly,
    credit_units_remaining,
    credit_units_purchased,
    free_credit_units_monthly,
    free_credit_units_remaining,
    storage_quota_bytes,
    current_period_start,
    current_period_end,
    display_name,
    avatar_url,
    created_at,
    updated_at
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
    262144000,                                       -- Storage quota: 250 MB for free users
    date_trunc('month', now()),                      -- Period starts at beginning of current month
    date_trunc('month', now()) + interval '1 month', -- Period ends at beginning of next month
    v_display_name,                                  -- OAuth display name
    v_avatar_url,                                    -- OAuth avatar URL
    COALESCE(NEW.created_at, now()),
    now()
  )
  ON CONFLICT (id) DO UPDATE
  SET
    display_name = COALESCE(EXCLUDED.display_name, public.profiles.display_name),
    avatar_url = COALESCE(EXCLUDED.avatar_url, public.profiles.avatar_url),
    current_period_start = COALESCE(public.profiles.current_period_start, EXCLUDED.current_period_start),
    current_period_end = COALESCE(public.profiles.current_period_end, EXCLUDED.current_period_end),
    -- Set storage_quota_bytes only if not already set (preserve upgrades)
    storage_quota_bytes = COALESCE(public.profiles.storage_quota_bytes, EXCLUDED.storage_quota_bytes),
    updated_at = now();

  RETURN NEW;
EXCEPTION
  WHEN others THEN
    RAISE WARNING 'Failed to create/update profile for user %: %', NEW.id, SQLERRM;
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION public.handle_new_user IS 
'Initializes new user profile with 3-bucket credit system, storage quota, and OAuth metadata. Triggered on auth.users INSERT.';


-- ============================================================================
-- SECTION 9: Create trigger to update storage quota on credit purchase
-- ============================================================================

CREATE OR REPLACE FUNCTION public.update_storage_quota_on_credit_purchase()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    -- If user purchased credits and was on free tier, upgrade to pay-as-you-go storage
    IF NEW.credit_units_purchased > 0 AND OLD.credit_units_purchased = 0 THEN
        -- Only upgrade if not already Pro
        IF NEW.billing_plan = 'free' OR NEW.billing_plan IS NULL THEN
            NEW.storage_quota_bytes := 2147483648;  -- 2 GB
        END IF;
    END IF;
    
    RETURN NEW;
END;
$$;

-- Drop existing trigger if exists
DROP TRIGGER IF EXISTS trigger_update_storage_quota_on_purchase ON public.profiles;

-- Create trigger
CREATE TRIGGER trigger_update_storage_quota_on_purchase
BEFORE UPDATE ON public.profiles
FOR EACH ROW
WHEN (OLD.credit_units_purchased IS DISTINCT FROM NEW.credit_units_purchased)
EXECUTE FUNCTION public.update_storage_quota_on_credit_purchase();

COMMENT ON FUNCTION public.update_storage_quota_on_credit_purchase IS 
'Automatically upgrades storage quota from Free (250MB) to PayAsYouGo (2GB) when user purchases credits.';


-- ============================================================================
-- SECTION 10: Add index for efficient storage usage queries
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_user_files_user_size 
ON public.user_files(user_id, file_size_bytes);

COMMENT ON INDEX idx_user_files_user_size IS 
'Index for efficient storage usage calculation per user';
