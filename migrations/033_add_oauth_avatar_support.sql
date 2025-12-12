-- Migration: 033 - Add OAuth Avatar Support
-- Date: 2025-12-12
-- Purpose: Store user avatar URL from OAuth providers (Google, etc.) in profiles table

-- ============================================================================
-- Step 1: Add avatar_url column to profiles table
-- ============================================================================

ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS avatar_url TEXT;

COMMENT ON COLUMN public.profiles.avatar_url IS 
'User avatar/profile picture URL from OAuth providers (Google, GitHub, etc.)';

-- ============================================================================
-- Step 2: Update trigger function to extract avatar from OAuth metadata
-- Note: Preserves existing behavior for account_tier, display_name
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
    -- Google OAuth uses 'full_name' or 'name'
    -- Other providers may use 'name'
    _display_name := COALESCE(
        NEW.raw_user_meta_data->>'full_name',
        NEW.raw_user_meta_data->>'name',
        NULL
    );
    
    -- Extract avatar URL from raw_user_meta_data
    -- Google OAuth uses 'avatar_url' or 'picture'
    -- Other providers may use 'avatar_url'
    _avatar_url := COALESCE(
        NEW.raw_user_meta_data->>'avatar_url',
        NEW.raw_user_meta_data->>'picture',
        NULL
    );

    -- Insert new profile with defaults matching table schema
    INSERT INTO public.profiles (
        id, 
        account_tier,
        billing_plan,
        display_name, 
        avatar_url, 
        created_at, 
        updated_at
    )
    VALUES (
        NEW.id, 
        'free',      -- default account_tier
        'free',      -- default billing_plan
        _display_name,
        _avatar_url,
        COALESCE(NEW.created_at, NOW()),
        NOW()
    )
    ON CONFLICT (id) DO UPDATE
    SET 
        display_name = COALESCE(EXCLUDED.display_name, public.profiles.display_name),
        avatar_url = COALESCE(EXCLUDED.avatar_url, public.profiles.avatar_url),
        updated_at = NOW();
    
    RETURN NEW;
EXCEPTION
    WHEN others THEN
        -- Log error but don't fail user signup
        RAISE WARNING 'Failed to create/update profile for user %: %', NEW.id, SQLERRM;
        RETURN NEW;
END;
$$;

COMMENT ON FUNCTION public.handle_new_user() IS 
'Trigger function that auto-creates profile with free tier, extracts display name and avatar URL from OAuth user metadata on signup';

-- ============================================================================
-- Step 3: Backfill existing users' avatars from auth.users metadata
-- ============================================================================

DO $$
DECLARE
    updated_count INTEGER;
BEGIN
    -- Update existing profiles with avatars from auth.users metadata
    WITH avatar_updates AS (
        UPDATE public.profiles p
        SET avatar_url = COALESCE(
            u.raw_user_meta_data->>'avatar_url',
            u.raw_user_meta_data->>'picture'
        ),
        updated_at = NOW()
        FROM auth.users u
        WHERE p.id = u.id 
        AND p.avatar_url IS NULL  -- Only update if not already set
        AND (
            u.raw_user_meta_data->>'avatar_url' IS NOT NULL 
            OR u.raw_user_meta_data->>'picture' IS NOT NULL
        )
        RETURNING p.id
    )
    SELECT COUNT(*) INTO updated_count FROM avatar_updates;
    
    RAISE NOTICE 'Backfilled % user avatars from metadata to profiles', updated_count;
END $$;

-- ============================================================================
-- Step 4: Update user_tier_info view to include avatar_url
-- ============================================================================
-- IMPORTANT: Preserving ALL existing columns and logic from the current view
-- Only adding avatar_url column after display_name

DROP VIEW IF EXISTS public.user_tier_info;

CREATE OR REPLACE VIEW public.user_tier_info
WITH (security_invoker = true)
AS
SELECT 
    u.id,
    u.email,
    p.display_name,
    p.avatar_url,  -- NEW: Avatar URL from OAuth providers
    COALESCE(p.billing_plan, 'free'::text) AS account_tier,
    COALESCE(p.role, 'user'::text) AS role,
    -- Credit/unit calculations (hybrid billing model)
    COALESCE(p.credit_units_remaining, 0) + COALESCE(p.credit_units_purchased, 0) + COALESCE(p.free_credit_units_remaining, 0) AS available_units,
    (COALESCE(p.credit_units_remaining, 0) + COALESCE(p.credit_units_purchased, 0) + COALESCE(p.free_credit_units_remaining, 0))::numeric / 2.0 AS available_credits,
    CASE
        WHEN COALESCE(p.billing_plan, 'free'::text) = 'pro'::text THEN (COALESCE(p.credit_units_monthly, 60) + COALESCE(p.free_credit_units_monthly, 6))::numeric / 2.0
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
    -- Quiz counts (computed from tables)
    (SELECT count(*) FROM public.quizzes q WHERE q.created_by = u.id)::integer AS current_quiz_count,
    (SELECT count(*) FROM public.submissions s WHERE s.user_id = u.id)::integer AS quizzes_attempted,
    -- Quota calculations
    CASE
        WHEN COALESCE(p.billing_plan, 'free'::text) = 'pro'::text THEN -1
        ELSE 5
    END AS quota_limit,
    (COALESCE(p.credit_units_remaining, 0) + COALESCE(p.credit_units_purchased, 0) + COALESCE(p.free_credit_units_remaining, 0)) <= 0 AS quota_exceeded,
    -- Timestamps
    p.created_at,
    p.updated_at
FROM auth.users u
LEFT JOIN public.profiles p ON u.id = p.id;

COMMENT ON VIEW public.user_tier_info IS 
'Unified view of user tier, quota, Stripe subscription, credits, and avatar. Used by /auth/me endpoint.';

-- ============================================================================
-- Step 5: Verification
-- ============================================================================

-- Verify avatar_url column exists in profiles
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' 
AND table_name = 'profiles'
AND column_name = 'avatar_url';

-- Verify avatar_url column exists in view
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public' 
AND table_name = 'user_tier_info'
AND column_name = 'avatar_url';

-- ============================================================================
-- Notes
-- ============================================================================
-- After this migration:
-- 1. New OAuth signups will automatically have their avatar saved to profiles.avatar_url
-- 2. Existing users' avatars will be backfilled from auth.users.raw_user_meta_data
-- 3. The avatar_url field is optional (NULL allowed) for email/password signups
-- 4. Google OAuth provides avatar via 'avatar_url' or 'picture' in metadata
-- 5. user_tier_info view now includes avatar_url for frontend display
-- 6. ALL existing columns and logic preserved in user_tier_info view
-- ============================================================================
    p.avatar_url,
    p.account_tier,
    u.email
FROM public.profiles p
LEFT JOIN auth.users u ON p.id = u.id
WHERE p.avatar_url IS NOT NULL
LIMIT 5;

-- ============================================================================
-- Notes
-- ============================================================================
-- After this migration:
-- 1. New OAuth signups will automatically have their avatar saved to profiles.avatar_url
-- 2. Existing users' avatars will be backfilled from auth.users.raw_user_meta_data
-- 3. The avatar_url field is optional (NULL allowed) for email/password signups
-- 4. Google OAuth provides avatar via 'avatar_url' or 'picture' in metadata
-- 5. user_tier_info view now includes avatar_url for frontend display
-- ============================================================================
