-- Migration: 025 - Secure user_tier_info view
-- Date: 2025-12-03
-- Purpose: Fix security issue where user_tier_info exposes auth.users data to all users
-- 
-- Issue: Supabase security advisor flagged that the view "user_tier_info" in public schema
-- may expose auth.users data to anon or authenticated roles, potentially compromising
-- user data security (emails, Stripe info, etc. of ALL users).
--
-- Fix: 
-- 1. Revoke all privileges from anon and authenticated on the view
-- 2. Create a SECURITY DEFINER function that only returns the current user's data
--
-- Note: Backend code uses service_role which bypasses RLS, so this doesn't affect
-- existing functionality. This only prevents direct PostgREST API access to the view.

-- Step 1: Revoke all privileges from anon and authenticated on the view
REVOKE ALL ON public.user_tier_info FROM anon;
REVOKE ALL ON public.user_tier_info FROM authenticated;

-- Step 2: Create a secure function that only returns the current user's tier info
-- This can be used by frontend if needed, as an alternative to the view
CREATE OR REPLACE FUNCTION public.get_my_tier_info()
RETURNS TABLE (
    id UUID,
    email TEXT,
    account_tier TEXT,
    display_name TEXT,
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
        u.id,
        u.email::TEXT,
        COALESCE(p.account_tier, 'free')::TEXT AS account_tier,
        COALESCE(p.display_name, '')::TEXT AS display_name,
        p.stripe_customer_id,
        p.stripe_subscription_id,
        p.subscription_status,
        p.current_period_start,
        p.current_period_end,
        p.subscription_canceled_at,
        (p.google_refresh_token IS NOT NULL) AS google_connected,
        p.google_connected_at,
        (SELECT count(*) FROM quizzes q WHERE q.created_by = u.id) AS current_quiz_count,
        (SELECT count(*) FROM submissions s WHERE s.user_id = u.id) AS quizzes_attempted,
        CASE
            WHEN COALESCE(p.account_tier, 'free') = 'free' THEN 5
            WHEN COALESCE(p.account_tier, 'free') = 'premium' THEN 100
            WHEN COALESCE(p.account_tier, 'free') = 'pro' THEN -1
            ELSE 5
        END AS quota_limit,
        CASE
            WHEN COALESCE(p.account_tier, 'free') = 'pro' THEN false
            WHEN COALESCE(p.account_tier, 'free') = 'premium' THEN 
                ((SELECT count(*) FROM quizzes q WHERE q.created_by = u.id) >= 100)
            ELSE 
                ((SELECT count(*) FROM quizzes q WHERE q.created_by = u.id) >= 5)
        END AS quota_exceeded
    FROM auth.users u
    LEFT JOIN profiles p ON u.id = p.id
    WHERE u.id = auth.uid();  -- Only return current user's data
$$;

-- Grant execute to authenticated users only (not anon)
GRANT EXECUTE ON FUNCTION public.get_my_tier_info() TO authenticated;

-- Add comment documenting security
COMMENT ON FUNCTION public.get_my_tier_info() IS 'Securely returns tier info for the current authenticated user only. Uses SECURITY DEFINER to access auth.users safely.';
