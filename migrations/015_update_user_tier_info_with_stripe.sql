-- ============================================================================
-- Migration 015: Update user_tier_info View with Stripe Fields
-- ============================================================================
-- Purpose: Add Stripe subscription fields to user_tier_info view
-- Created: 2025-01-XX (Epic 1: Infrastructure Setup)
-- 
-- This migration updates the user_tier_info view to include Stripe subscription
-- data, enabling quota enforcement and billing status checks in one query.
-- ============================================================================

-- Drop existing view (required for schema changes)
DROP VIEW IF EXISTS public.user_tier_info;

-- Recreate view with Stripe fields
CREATE OR REPLACE VIEW public.user_tier_info AS
SELECT 
    u.id,
    u.email,
    p.name,
    p.account_tier,
    -- Stripe subscription fields
    p.stripe_customer_id,
    p.stripe_subscription_id,
    p.subscription_status,
    p.subscription_canceled_at,
    -- Calculate if subscription is in grace period (canceled but still valid)
    CASE 
        WHEN p.subscription_status = 'canceled' 
             AND p.subscription_canceled_at IS NOT NULL 
             AND (p.subscription_canceled_at + INTERVAL '30 days') > NOW()
        THEN TRUE
        ELSE FALSE
    END AS in_grace_period,
    -- Quiz count and quota
    COALESCE(COUNT(q.id), 0)::INTEGER AS current_quiz_count,
    CASE 
        WHEN p.account_tier = 'free' THEN 5
        WHEN p.account_tier = 'basic' THEN 100
        WHEN p.account_tier = 'educator' THEN 500
        ELSE 5
    END AS quota_limit,
    -- Quota exceeded flag (considers grace period)
    CASE 
        WHEN COALESCE(COUNT(q.id), 0) >= 
            CASE 
                WHEN p.account_tier = 'free' THEN 5
                WHEN p.account_tier = 'basic' THEN 100
                WHEN p.account_tier = 'educator' THEN 500
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
LEFT JOIN public.quizzes q ON u.id = q.user_id
GROUP BY 
    u.id, 
    u.email, 
    p.name,
    p.account_tier, 
    p.stripe_customer_id,
    p.stripe_subscription_id,
    p.subscription_status,
    p.subscription_canceled_at;

-- ============================================================================
-- Grant Permissions
-- ============================================================================

-- Allow authenticated users to query the view (RLS enforced at profiles level)
GRANT SELECT ON public.user_tier_info TO authenticated;

-- ============================================================================
-- Comments for Documentation
-- ============================================================================

COMMENT ON VIEW public.user_tier_info IS 
'Unified view of user tier, quota, and Stripe subscription status for quota enforcement';

COMMENT ON COLUMN public.user_tier_info.in_grace_period IS 
'True if subscription is canceled but user still has access (within 30 days of cancellation)';

COMMENT ON COLUMN public.user_tier_info.billing_status IS 
'Billing status: no_subscription, active, trialing, payment_failed, grace_period, expired, incomplete, unknown';

-- ============================================================================
-- Verification Queries (Run these to verify migration success)
-- ============================================================================

-- Check view structure
-- SELECT column_name, data_type 
-- FROM information_schema.columns 
-- WHERE table_schema = 'public' 
-- AND table_name = 'user_tier_info'
-- ORDER BY ordinal_position;

-- Test query (replace with real user ID)
-- SELECT * FROM public.user_tier_info WHERE id = 'your-user-uuid-here';

-- Test grace period calculation (should show users in grace period)
-- SELECT id, email, account_tier, subscription_status, subscription_canceled_at, in_grace_period, billing_status
-- FROM public.user_tier_info
-- WHERE subscription_status = 'canceled'
-- ORDER BY subscription_canceled_at DESC;
