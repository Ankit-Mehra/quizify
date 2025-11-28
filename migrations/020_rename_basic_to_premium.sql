-- Migration: Rename 'basic' tier to 'premium'
-- Purpose: Align database tier naming with new pricing structure
-- Date: 2025-11-27
--
-- Tier Structure:
-- - Free: $0/mo - 5 quizzes
-- - Premium: $7/mo - 50 quizzes (was 'basic')
-- - Pro: Coming soon - Unlimited + LMS exports
--
-- IMPORTANT: Steps must be in this order to avoid constraint violations

-- Step 1: Drop the CHECK constraint FIRST (before any data changes)
ALTER TABLE profiles DROP CONSTRAINT IF EXISTS profiles_account_tier_check;

-- Step 2: Update all existing 'basic' tier users to 'premium'
UPDATE profiles 
SET account_tier = 'premium' 
WHERE account_tier = 'basic';

-- Step 3: Add new CHECK constraint with updated tier names
ALTER TABLE profiles ADD CONSTRAINT profiles_account_tier_check 
CHECK (account_tier IN ('free', 'premium', 'pro'));

-- Step 3: Update the user_tier_info view with new tier names
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
        WHEN COALESCE(p.account_tier, 'free') = 'premium' THEN 50
        WHEN COALESCE(p.account_tier, 'free') = 'pro' THEN -1  -- Unlimited
        ELSE 5
    END as quota_limit,
    CASE 
        WHEN COALESCE(p.account_tier, 'free') = 'pro' THEN FALSE
        WHEN COALESCE(p.account_tier, 'free') = 'premium' THEN (
            SELECT COUNT(*) FROM quizzes q WHERE q.created_by = u.id
        ) >= 50
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
-- SELECT account_tier, COUNT(*) FROM profiles GROUP BY account_tier;
-- SELECT * FROM user_tier_info LIMIT 5;
