-- Migration: 034 - Fix user_tier_info view permissions
-- Date: 2025-12-13
-- Purpose: Fix "permission denied for table users" error when accessing view via service_role
--
-- Root Cause: The view was created with `security_invoker = true` in migration 033.
-- This means the view runs with the CALLER's permissions, not the view owner's.
-- When service_role queries the view via PostgREST, it doesn't have direct access 
-- to auth.users table, causing the permission denied error.
--
-- Fix: Recreate the view WITHOUT security_invoker (defaults to SECURITY DEFINER behavior)
-- which runs with the view OWNER's permissions (postgres), which CAN access auth.users.
--
-- All 25 columns preserved exactly as they were:
-- id, email, display_name, avatar_url, account_tier, role, available_units,
-- available_credits, monthly_credits, purchased_credits, subscription_units_remaining,
-- free_units_remaining, purchased_units, current_period_start, period_end,
-- stripe_customer_id, stripe_subscription_id, subscription_status, billing_plan,
-- current_quiz_count, quizzes_attempted, quota_limit, quota_exceeded, created_at, updated_at

-- Step 1: Drop the existing view
DROP VIEW IF EXISTS public.user_tier_info;

-- Step 2: Recreate the view WITHOUT security_invoker (uses SECURITY DEFINER by default)
CREATE VIEW public.user_tier_info AS
SELECT 
    u.id,
    u.email,
    p.display_name,
    p.avatar_url,
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

-- Step 3: Grant SELECT to service_role only (backend access)
-- Revoke from anon and authenticated for security (prevents direct API access to all user data)
REVOKE ALL ON public.user_tier_info FROM anon;
REVOKE ALL ON public.user_tier_info FROM authenticated;
GRANT SELECT ON public.user_tier_info TO service_role;

-- Step 4: Add comment
COMMENT ON VIEW public.user_tier_info IS 
'Unified view of user tier, quota, Stripe subscription, credits, and avatar. Service role access only. Uses SECURITY DEFINER to access auth.users.';

-- Step 5: Verification - check security_invoker is NOT set
-- This should return NULL or empty reloptions (no security_invoker=true)
SELECT relname, reloptions 
FROM pg_class 
WHERE relname = 'user_tier_info' AND relkind = 'v';
