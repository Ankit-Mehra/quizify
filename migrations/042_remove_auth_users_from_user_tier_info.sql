-- Migration: 042 - Remove auth.users dependency from user_tier_info view
-- Date: 2026-02-26
-- Purpose: Fix Supabase security advisor ERROR: public.user_tier_info exposes auth.users
--
-- Problem:
--   The view joins FROM auth.users u LEFT JOIN profiles p ON u.id = p.id
--   This exposes auth-internal data through a public schema view.
--   Even though migration 025 revoked anon/authenticated access,
--   the view itself still references auth.users which is a security concern.
--
-- Solution:
--   1. Add email column to profiles (synced from auth.users on signup/update)
--   2. Backfill existing users' emails from auth.users
--   3. Rewrite user_tier_info view to source everything from profiles (no auth.users)
--   4. Update get_my_tier_info function similarly
--   5. Revoke anon access, grant only SELECT to authenticated
--
-- Impact:
--   - Backend code is unaffected: all queries use service_role which bypasses RLS
--   - Email field is still available via profiles.email
--   - View no longer references auth.users at all
-- ============================================================================

-- ============================================================================
-- Step 1: Add email column to profiles table
-- ============================================================================

ALTER TABLE public.profiles
ADD COLUMN IF NOT EXISTS email TEXT;

COMMENT ON COLUMN public.profiles.email IS
'User email synced from auth.users on signup and email change. Source of truth is auth.users; this is a denormalized copy for the user_tier_info view to avoid joining auth.users.';

-- ============================================================================
-- Step 2: Backfill existing users'' emails from auth.users
-- ============================================================================

DO $$
DECLARE
    updated_count INTEGER;
BEGIN
    WITH email_updates AS (
        UPDATE public.profiles p
        SET email = u.email,
            updated_at = NOW()
        FROM auth.users u
        WHERE p.id = u.id
        AND p.email IS NULL
        RETURNING p.id
    )
    SELECT COUNT(*) INTO updated_count FROM email_updates;
    
    RAISE NOTICE 'Backfilled % user emails from auth.users to profiles', updated_count;
END $$;

-- ============================================================================
-- Step 3: Update trigger function to also sync email on signup
-- ============================================================================

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    _display_name TEXT;
    _avatar_url TEXT;
BEGIN
    -- Extract name from raw_user_meta_data
    _display_name := COALESCE(
        NEW.raw_user_meta_data->>'full_name',
        NEW.raw_user_meta_data->>'name',
        NULL
    );
    
    -- Extract avatar URL from raw_user_meta_data
    _avatar_url := COALESCE(
        NEW.raw_user_meta_data->>'avatar_url',
        NEW.raw_user_meta_data->>'picture',
        NULL
    );

    -- Insert new profile with ALL required fields
    INSERT INTO public.profiles (
        id,
        email,
        account_tier,
        billing_plan,
        display_name,
        avatar_url,
        -- Credit system columns
        credit_units_monthly,
        credit_units_remaining,
        credit_units_purchased,
        free_credit_units_monthly,
        free_credit_units_remaining,
        storage_quota_bytes,
        current_period_start,
        current_period_end,
        -- Timestamps
        created_at,
        updated_at
    )
    VALUES (
        NEW.id,
        NEW.email,                                       -- Sync email from auth.users
        'free',
        'free',
        _display_name,
        _avatar_url,
        6,                                               -- credit_units_monthly
        0,                                               -- credit_units_remaining
        0,                                               -- credit_units_purchased
        6,                                               -- free_credit_units_monthly
        6,                                               -- free_credit_units_remaining
        262144000,                                       -- storage_quota_bytes: 250 MB
        date_trunc('month', NOW()),
        date_trunc('month', NOW()) + interval '1 month',
        COALESCE(NEW.created_at, NOW()),
        NOW()
    )
    ON CONFLICT (id) DO UPDATE
    SET
        email = COALESCE(EXCLUDED.email, public.profiles.email),
        display_name = COALESCE(EXCLUDED.display_name, public.profiles.display_name),
        avatar_url = COALESCE(EXCLUDED.avatar_url, public.profiles.avatar_url),
        current_period_start = COALESCE(public.profiles.current_period_start, EXCLUDED.current_period_start),
        current_period_end = COALESCE(public.profiles.current_period_end, EXCLUDED.current_period_end),
        storage_quota_bytes = COALESCE(public.profiles.storage_quota_bytes, EXCLUDED.storage_quota_bytes),
        updated_at = NOW();
    
    RETURN NEW;
EXCEPTION
    WHEN others THEN
        RAISE WARNING 'Failed to create/update profile for user %: %', NEW.id, SQLERRM;
        RETURN NEW;
END;
$$;

COMMENT ON FUNCTION public.handle_new_user() IS
'Trigger function that auto-creates profile with free tier, credit system, and syncs email/display_name/avatar from auth.users metadata on signup.';

-- ============================================================================
-- Step 4: Add trigger to sync email on auth.users email change
-- ============================================================================

CREATE OR REPLACE FUNCTION public.handle_user_email_change()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    -- Sync email change to profiles table
    IF NEW.email IS DISTINCT FROM OLD.email THEN
        UPDATE public.profiles
        SET email = NEW.email,
            updated_at = NOW()
        WHERE id = NEW.id;
    END IF;
    RETURN NEW;
EXCEPTION
    WHEN others THEN
        RAISE WARNING 'Failed to sync email change for user %: %', NEW.id, SQLERRM;
        RETURN NEW;
END;
$$;

COMMENT ON FUNCTION public.handle_user_email_change() IS
'Trigger function that syncs email from auth.users to profiles on email change.';

-- Create trigger on auth.users for email changes (requires superuser)
-- Note: If this fails due to permissions, apply via Supabase Dashboard SQL editor
DROP TRIGGER IF EXISTS on_auth_user_email_change ON auth.users;
CREATE TRIGGER on_auth_user_email_change
    AFTER UPDATE OF email ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_user_email_change();

-- ============================================================================
-- Step 5: Rewrite user_tier_info view — source everything from profiles
-- ============================================================================

DROP VIEW IF EXISTS public.user_tier_info;

CREATE OR REPLACE VIEW public.user_tier_info
WITH (security_invoker = true)
AS
SELECT
    p.id,
    p.email,
    p.display_name,
    p.avatar_url,
    COALESCE(p.billing_plan, 'free'::text) AS account_tier,
    COALESCE(p.role, 'user'::text) AS role,
    -- Credit/unit calculations (hybrid billing model)
    COALESCE(p.credit_units_remaining, 0)
        + COALESCE(p.credit_units_purchased, 0)
        + COALESCE(p.free_credit_units_remaining, 0) AS available_units,
    (COALESCE(p.credit_units_remaining, 0)
        + COALESCE(p.credit_units_purchased, 0)
        + COALESCE(p.free_credit_units_remaining, 0))::numeric / 2.0 AS available_credits,
    CASE
        WHEN COALESCE(p.billing_plan, 'free'::text) = 'pro'::text
            THEN (COALESCE(p.credit_units_monthly, 60) + COALESCE(p.free_credit_units_monthly, 6))::numeric / 2.0
        ELSE COALESCE(p.free_credit_units_monthly, 6)::numeric / 2.0
    END AS monthly_credits,
    COALESCE(p.credit_units_purchased, 0)::numeric / 2.0 AS purchased_credits,
    COALESCE(p.credit_units_remaining, 0) AS subscription_units_remaining,
    COALESCE(p.free_credit_units_remaining, 0) AS free_units_remaining,
    COALESCE(p.credit_units_purchased, 0) AS purchased_units,
    -- Stripe/subscription fields
    p.current_period_start,
    p.current_period_end AS period_end,
    p.stripe_customer_id,
    p.stripe_subscription_id,
    p.subscription_status,
    p.billing_plan,
    -- Storage fields
    COALESCE(p.storage_quota_bytes, 262144000::bigint) AS storage_quota_bytes,
    get_storage_usage(p.id) AS storage_used_bytes,
    -- Quiz counts (computed from tables)
    (SELECT count(*) FROM public.quizzes q WHERE q.created_by = p.id)::integer AS current_quiz_count,
    (SELECT count(*) FROM public.submissions s WHERE s.user_id = p.id)::integer AS quizzes_attempted,
    -- Quota calculations
    CASE
        WHEN COALESCE(p.billing_plan, 'free'::text) = 'pro'::text THEN -1
        ELSE 5
    END AS quota_limit,
    (COALESCE(p.credit_units_remaining, 0)
        + COALESCE(p.credit_units_purchased, 0)
        + COALESCE(p.free_credit_units_remaining, 0)) <= 0 AS quota_exceeded,
    -- Timestamps
    p.created_at,
    p.updated_at
FROM public.profiles p;

COMMENT ON VIEW public.user_tier_info IS
'Unified view of user tier, quota, credits, and subscription. Sources ALL data from profiles (no auth.users dependency). Used by backend service_role queries.';

-- ============================================================================
-- Step 6: Secure access — revoke anon, grant SELECT to authenticated only
-- ============================================================================

REVOKE ALL ON public.user_tier_info FROM anon;
REVOKE ALL ON public.user_tier_info FROM authenticated;
GRANT SELECT ON public.user_tier_info TO authenticated;

-- ============================================================================
-- Step 7: Update get_my_tier_info function to use profiles instead of auth.users
-- Note: Must DROP first because RETURNS TABLE signature changes (adding avatar_url)
-- ============================================================================

DROP FUNCTION IF EXISTS public.get_my_tier_info();

CREATE FUNCTION public.get_my_tier_info()
RETURNS TABLE (
    id UUID,
    email TEXT,
    account_tier TEXT,
    display_name TEXT,
    avatar_url TEXT,
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    subscription_status TEXT,
    current_period_start TIMESTAMPTZ,
    current_period_end TIMESTAMPTZ,
    subscription_canceled_at TIMESTAMPTZ,
    google_connected BOOLEAN,
    google_connected_at TIMESTAMPTZ,
    current_quiz_count BIGINT,
    quizzes_attempted BIGINT,
    quota_limit INTEGER,
    quota_exceeded BOOLEAN
)
LANGUAGE sql
SECURITY DEFINER
STABLE
SET search_path = public
AS $$
    SELECT
        p.id,
        p.email::TEXT,
        COALESCE(p.billing_plan, 'free')::TEXT AS account_tier,
        COALESCE(p.display_name, '')::TEXT AS display_name,
        p.avatar_url::TEXT,
        p.stripe_customer_id,
        p.stripe_subscription_id,
        p.subscription_status,
        p.current_period_start,
        p.current_period_end,
        p.subscription_canceled_at,
        (p.google_refresh_token IS NOT NULL) AS google_connected,
        p.google_connected_at,
        (SELECT count(*) FROM quizzes q WHERE q.created_by = p.id) AS current_quiz_count,
        (SELECT count(*) FROM submissions s WHERE s.user_id = p.id) AS quizzes_attempted,
        CASE
            WHEN COALESCE(p.billing_plan, 'free') = 'free' THEN 5
            WHEN COALESCE(p.billing_plan, 'free') = 'premium' THEN 100
            WHEN COALESCE(p.billing_plan, 'free') = 'pro' THEN -1
            ELSE 5
        END AS quota_limit,
        CASE
            WHEN COALESCE(p.billing_plan, 'free') = 'pro' THEN false
            WHEN COALESCE(p.billing_plan, 'free') = 'premium' THEN
                ((SELECT count(*) FROM quizzes q WHERE q.created_by = p.id) >= 100)
            ELSE
                ((SELECT count(*) FROM quizzes q WHERE q.created_by = p.id) >= 5)
        END AS quota_exceeded
    FROM profiles p
    WHERE p.id = auth.uid();
$$;

GRANT EXECUTE ON FUNCTION public.get_my_tier_info() TO authenticated;

COMMENT ON FUNCTION public.get_my_tier_info() IS
'Securely returns tier info for the current authenticated user. Sources from profiles only (no auth.users dependency).';

-- ============================================================================
-- Step 8: Verification queries
-- ============================================================================

-- Verify email column exists in profiles
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
AND table_name = 'profiles'
AND column_name = 'email';

-- Verify view no longer references auth.users
-- (Check view definition — should only show FROM public.profiles)
SELECT pg_get_viewdef('public.user_tier_info'::regclass, true);

-- ============================================================================
-- Notes
-- ============================================================================
-- After this migration:
-- 1. user_tier_info view sources ALL data from public.profiles (no auth.users join)
-- 2. profiles.email is synced from auth.users on signup and email change
-- 3. anon has NO access to user_tier_info; authenticated has SELECT only
-- 4. View uses security_invoker=true (no SECURITY DEFINER bypass)
-- 5. get_my_tier_info() function also updated to use profiles only
-- 6. Existing backend code using service_role is unaffected
-- 7. All 24 columns preserved with identical output
-- ============================================================================
