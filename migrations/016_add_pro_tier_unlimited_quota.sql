-- ============================================================================
-- Migration 016: Add Pro Tier with Unlimited Quota
-- ============================================================================
-- Purpose: Introduce "pro" tier with unlimited quota, aligned with pricing analysis
-- Created: 2025-11-19 (Epic 1: Infrastructure Setup - Pricing Alignment)
-- 
-- This migration adds the "pro" tier to replace the planned "educator" tier
-- with better pricing ($15/mo for unlimited quizzes vs $19.99/mo for 500).
-- 
-- Pricing Structure (from COST_BREAKDOWN.md analysis):
-- - Free: $0/mo - 5 quizzes
-- - Basic: $5/mo - 100 quizzes (97% profit margin)
-- - Pro: $15/mo - Unlimited quizzes (97% profit margin)
-- 
-- Note: Existing "educator" tier (500 quizzes) remains for backward compatibility
-- but new subscriptions will use "pro" tier.
-- ============================================================================

-- Update the user_tier_info view to support "pro" tier with unlimited quota
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
        WHEN p.account_tier = 'educator' THEN 500  -- Legacy tier
        WHEN p.account_tier = 'pro' THEN 2147483647    -- Unlimited (INT max)
        ELSE 5
    END AS quota_limit,
    -- Quota exceeded flag (pro tier never exceeds)
    CASE 
        WHEN p.account_tier = 'pro' THEN FALSE     -- Pro tier never exceeds quota
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
LEFT JOIN public.quizzes q ON u.id = q.created_by
GROUP BY 
    u.id, 
    u.email, 
    p.display_name,
    p.account_tier, 
    p.stripe_customer_id,
    p.stripe_subscription_id,
    p.subscription_status,
    p.subscription_canceled_at;

-- Grant permissions
GRANT SELECT ON public.user_tier_info TO authenticated;

-- Add comment explaining pro tier
COMMENT ON VIEW public.user_tier_info IS 
'Unified view of user tier, quota, and Stripe subscription status. Pro tier has unlimited quota (INT_MAX).';

-- ============================================================================
-- Migration Notes
-- ============================================================================
-- 
-- 1. Pro tier uses quota_limit = 2147483647 (INT_MAX, effectively unlimited)
-- 2. Pro tier users will never hit quota_exceeded = true
-- 3. Educator tier (500 quizzes) remains for backward compatibility
-- 4. New Stripe subscriptions will create "pro" tier users
-- 5. Existing educator users are not migrated (no breaking changes)
-- 6. Frontend can offer "Upgrade to Pro" for unlimited quizzes
-- 
-- To migrate existing educator users to pro tier (optional, run separately):
-- UPDATE public.profiles SET account_tier = 'pro' WHERE account_tier = 'educator';
-- 
-- ============================================================================

-- Verification Queries
-- 
-- Check pro tier quota calculation:
-- SELECT account_tier, quota_limit, quota_exceeded 
-- FROM user_tier_info 
-- WHERE account_tier = 'pro';
-- 
-- Check all tier quotas:
-- SELECT account_tier, COUNT(*) as user_count, MIN(quota_limit) as quota 
-- FROM user_tier_info 
-- GROUP BY account_tier 
-- ORDER BY quota;
