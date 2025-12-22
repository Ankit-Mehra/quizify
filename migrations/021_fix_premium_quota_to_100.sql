-- Migration: Fix Premium tier quota from 50 to 100
-- Purpose: Premium tier should have 100 quizzes, matching original basic tier quota
-- Date: 2025-11-28
--
-- This migration fixes the user_tier_info view to use 100 quizzes for Premium tier
-- Run this if migration 020_rename_basic_to_premium.sql was already applied with 50 quota

-- Recreate the user_tier_info view with corrected quota
DROP VIEW IF EXISTS user_tier_info;

CREATE VIEW user_tier_info AS
SELECT 
    u.id,
    u.email,
    COALESCE(p.account_tier, 'free') as account_tier,
    COALESCE(p.display_name, '') as display_name,
    p.stripe_customer_id,
    p.stripe_subscription_id,
    p.subscription_status,
    p.current_period_end,
    p.google_refresh_token IS NOT NULL as google_connected,
    p.google_connected_at,
    (
        SELECT COUNT(*) 
        FROM quizzes q 
        WHERE q.created_by = u.id
    ) as current_quiz_count,
    (
        SELECT COUNT(*) 
        FROM submissions s 
        WHERE s.user_id = u.id
    ) as quizzes_attempted,
    CASE 
        WHEN COALESCE(p.account_tier, 'free') = 'free' THEN 5
        WHEN COALESCE(p.account_tier, 'free') = 'premium' THEN 100
        WHEN COALESCE(p.account_tier, 'free') = 'pro' THEN -1  -- Unlimited
        ELSE 5
    END as quota_limit,
    CASE 
        WHEN COALESCE(p.account_tier, 'free') = 'pro' THEN FALSE
        WHEN COALESCE(p.account_tier, 'free') = 'premium' THEN (
            SELECT COUNT(*) FROM quizzes q WHERE q.created_by = u.id
        ) >= 100
        ELSE (
            SELECT COUNT(*) FROM quizzes q WHERE q.created_by = u.id
        ) >= 5
    END as quota_exceeded
FROM auth.users u
LEFT JOIN profiles p ON u.id = p.id;

-- Grant access to the view
GRANT SELECT ON user_tier_info TO authenticated;
GRANT SELECT ON user_tier_info TO service_role;

-- Verification query (run manually to confirm)
-- SELECT account_tier, quota_limit FROM user_tier_info LIMIT 5;
