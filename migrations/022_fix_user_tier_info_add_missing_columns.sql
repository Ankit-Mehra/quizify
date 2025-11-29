-- Migration 022: Fix user_tier_info view to include current_period_start and subscription_canceled_at
-- Issue: API returns null for current_period_start because the view was missing this column
-- The profiles table has these columns, but they weren't included in the view
-- Date: 2025-11-28

-- Drop the existing view first
DROP VIEW IF EXISTS user_tier_info;

-- Recreate the view with all billing-related columns
CREATE VIEW user_tier_info AS
SELECT 
    u.id,
    u.email,
    COALESCE(p.account_tier, 'free') AS account_tier,
    COALESCE(p.display_name, '') AS display_name,
    p.stripe_customer_id,
    p.stripe_subscription_id,
    p.subscription_status,
    p.current_period_start,  -- ADDED: Was missing from view
    p.current_period_end,
    p.subscription_canceled_at,  -- ADDED: Was missing from view
    p.google_refresh_token IS NOT NULL AS google_connected,
    p.google_connected_at,
    (SELECT COUNT(*) FROM quizzes q WHERE q.created_by = u.id) AS current_quiz_count,
    (SELECT COUNT(*) FROM submissions s WHERE s.user_id = u.id) AS quizzes_attempted,
    CASE
        WHEN COALESCE(p.account_tier, 'free') = 'free' THEN 5
        WHEN COALESCE(p.account_tier, 'free') = 'premium' THEN 100
        WHEN COALESCE(p.account_tier, 'free') = 'pro' THEN -1
        ELSE 5
    END AS quota_limit,
    CASE
        WHEN COALESCE(p.account_tier, 'free') = 'pro' THEN false
        WHEN COALESCE(p.account_tier, 'free') = 'premium' THEN 
            (SELECT COUNT(*) FROM quizzes q WHERE q.created_by = u.id) >= 100
        ELSE 
            (SELECT COUNT(*) FROM quizzes q WHERE q.created_by = u.id) >= 5
    END AS quota_exceeded
FROM auth.users u
LEFT JOIN profiles p ON u.id = p.id;

-- Add comment for documentation
COMMENT ON VIEW user_tier_info IS 'Combined view of user authentication and billing tier information. Includes Stripe subscription details, quota tracking, and Google OAuth status.';
