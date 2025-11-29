-- Migration 022: Fix user_tier_info view to include Google OAuth status columns
-- Issue: API needs google_connected and google_connected_at for OAuth feature
-- IMPORTANT: This migration preserves the period-based quota logic from migration 017
-- Date: 2025-11-28

-- Drop the existing view first
DROP VIEW IF EXISTS public.user_tier_info;

-- Recreate the view with all columns including Google OAuth status
-- CRITICAL: Uses period-based quiz counting from migration 017
CREATE OR REPLACE VIEW public.user_tier_info AS
SELECT 
    u.id,
    u.email,
    p.display_name,
    COALESCE(p.account_tier, 'free') AS account_tier,
    -- Stripe subscription fields
    p.stripe_customer_id,
    p.stripe_subscription_id,
    p.subscription_status,
    p.subscription_canceled_at,
    p.current_period_start,
    p.current_period_end,
    -- Google OAuth status (ADDED)
    p.google_refresh_token IS NOT NULL AS google_connected,
    p.google_connected_at,
    -- Calculate if subscription is in grace period (canceled but still valid)
    CASE 
        WHEN p.subscription_status = 'canceled' 
             AND p.subscription_canceled_at IS NOT NULL 
             AND (p.subscription_canceled_at + INTERVAL '30 days') > NOW()
        THEN TRUE
        ELSE FALSE
    END AS in_grace_period,
    -- Quiz count (filtered by current period) - PRESERVED FROM MIGRATION 017
    -- For free tier (null start): defaults to start of current month
    -- For paid tier (set start): uses billing period start
    COALESCE(COUNT(q.id), 0)::INTEGER AS current_quiz_count,
    COALESCE(s.submission_count, 0)::INTEGER AS quizzes_attempted,
    CASE 
        WHEN COALESCE(p.account_tier, 'free') = 'free' THEN 5
        WHEN COALESCE(p.account_tier, 'free') = 'premium' THEN 100
        WHEN COALESCE(p.account_tier, 'free') = 'pro' THEN -1  -- Unlimited
        ELSE 5
    END AS quota_limit,
    -- Quota exceeded flag
    CASE 
        WHEN COALESCE(p.account_tier, 'free') = 'pro' THEN FALSE  -- Pro tier never exceeds quota
        WHEN COALESCE(COUNT(q.id), 0) >= 
            CASE 
                WHEN COALESCE(p.account_tier, 'free') = 'free' THEN 5
                WHEN COALESCE(p.account_tier, 'free') = 'premium' THEN 100
                ELSE 5
            END
        THEN TRUE
        ELSE FALSE
    END AS quota_exceeded,
    -- Billing status indicator
    CASE
        WHEN COALESCE(p.account_tier, 'free') = 'free' THEN 'no_subscription'
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
LEFT JOIN public.user_submission_counts s ON u.id = s.user_id
-- CRITICAL FIX: Filter quizzes by current period start (preserved from migration 017)
-- If current_period_start is NULL (free tier), use start of current month
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
    p.current_period_end,
    p.google_refresh_token,
    p.google_connected_at,
    s.submission_count;

-- Grant permissions
GRANT SELECT ON public.user_tier_info TO authenticated;

-- Add comment for documentation
COMMENT ON VIEW public.user_tier_info IS 'Unified view of user tier, quota, Stripe subscription, and Google OAuth status. Quotas reset monthly/periodically.';
