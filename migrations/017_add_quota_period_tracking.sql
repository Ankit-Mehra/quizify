-- ============================================================================
-- Migration 017: Add Quota Period Tracking
-- ============================================================================
-- Purpose: Implement monthly/billing-cycle quota resets
-- Created: 2025-11-19 (Epic 1: Infrastructure Setup - Quota Fix)
-- 
-- This migration adds period tracking columns to profiles and updates the
-- user_tier_info view to count quizzes only within the current period.
-- 
-- Logic:
-- - Free Tier: Resets on 1st of calendar month (default behavior)
-- - Paid Tiers: Resets on billing cycle start (synced from Stripe)
-- ============================================================================

-- 1. Add period tracking columns to profiles
ALTER TABLE public.profiles
ADD COLUMN IF NOT EXISTS current_period_start TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS current_period_end TIMESTAMPTZ;

COMMENT ON COLUMN public.profiles.current_period_start IS 
'Start of current billing period (or month for free tier). Quotas count from this date.';

COMMENT ON COLUMN public.profiles.current_period_end IS 
'End of current billing period. Used for display purposes.';

-- 2. Update user_tier_info view to use period-based counting
DROP VIEW IF EXISTS public.user_tier_info;

CREATE OR REPLACE VIEW public.user_tier_info AS
SELECT 
    u.id,
    u.email,
    p.display_name,
    p.account_tier,
    -- Stripe subscription fields
    p.stripe_customer_id,
    p.stripe_subscription_id,
    p.subscription_status,
    p.subscription_canceled_at,
    p.current_period_start,
    p.current_period_end,
    -- Calculate if subscription is in grace period (canceled but still valid)
    CASE 
        WHEN p.subscription_status = 'canceled' 
             AND p.subscription_canceled_at IS NOT NULL 
             AND (p.subscription_canceled_at + INTERVAL '30 days') > NOW()
        THEN TRUE
        ELSE FALSE
    END AS in_grace_period,
    -- Quiz count (filtered by current period)
    -- For free tier (null start): defaults to start of current month
    -- For paid tier (set start): uses billing period start
    COALESCE(COUNT(q.id), 0)::INTEGER AS current_quiz_count,
    CASE 
        WHEN p.account_tier = 'free' THEN 5
        WHEN p.account_tier = 'basic' THEN 100
        WHEN p.account_tier = 'pro' THEN 2147483647    -- Unlimited (INT max)
        ELSE 5
    END AS quota_limit,
    -- Quota exceeded flag
    CASE 
        WHEN p.account_tier = 'pro' THEN FALSE     -- Pro tier never exceeds quota
        WHEN COALESCE(COUNT(q.id), 0) >= 
            CASE 
                WHEN p.account_tier = 'free' THEN 5
                WHEN p.account_tier = 'basic' THEN 100
                ELSE 5
            END
        THEN TRUE
        ELSE FALSE
    END AS quota_exceeded,
    -- Billing status indicator
    CASE
        WHEN p.account_tier = 'free' THEN 'no_subscription'
        WHEN p.subscription_status = 'active' THEN 'active'
        WHEN p.subscription_status = 'trialing' THEN 'trialing'
        WHEN p.subscription_status = 'past_due' THEN 'payment_failed'
        WHEN p.subscription_status = 'canceled' 
             AND (p.subscription_canceled_at + INTERVAL '30 days') > NOW() THEN 'grace_period'
        WHEN p.subscription_status = 'canceled' THEN 'expired'
        WHEN p.subscription_status = 'incomplete' THEN 'incomplete'
        ELSE 'unknown'
    END AS billing_status
FROM auth.users u
LEFT JOIN public.profiles p ON u.id = p.id
-- CRITICAL FIX: Filter quizzes by current period start
-- If current_period_start is NULL (free tier), use start of current month
-- Optimization: Use CASE for explicit logic instead of COALESCE
LEFT JOIN public.quizzes q ON u.id = q.created_by 
    AND q.created_at >= (
        CASE 
            WHEN p.current_period_start IS NOT NULL THEN p.current_period_start
            ELSE date_trunc('month', now())
        END
    )
GROUP BY 
    u.id, 
    u.email, 
    p.display_name,
    p.account_tier, 
    p.stripe_customer_id,
    p.stripe_subscription_id,
    p.subscription_status,
    p.subscription_canceled_at,
    p.current_period_start,
    p.current_period_end;

-- Grant permissions
GRANT SELECT ON public.user_tier_info TO authenticated;

COMMENT ON VIEW public.user_tier_info IS 
'Unified view of user tier, quota, and Stripe subscription status. Quotas reset monthly/periodically.';

-- ============================================================================
-- Verification
-- ============================================================================
-- 1. Check free tier (should count from 1st of month):
-- SELECT current_quiz_count FROM user_tier_info WHERE account_tier = 'free';
--
-- 2. Check paid tier (should count from current_period_start):
-- SELECT current_quiz_count FROM user_tier_info WHERE account_tier = 'basic';
