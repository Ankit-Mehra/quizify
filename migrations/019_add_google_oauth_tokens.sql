-- Migration: Add Google OAuth token storage to profiles
-- Purpose: Store Google refresh tokens for Google Forms export feature
-- Epic: QUIZ-002 Google Forms Export

-- Add columns for Google OAuth tokens
ALTER TABLE profiles 
ADD COLUMN IF NOT EXISTS google_refresh_token TEXT,
ADD COLUMN IF NOT EXISTS google_connected_at TIMESTAMPTZ;

-- Add comment for documentation
COMMENT ON COLUMN profiles.google_refresh_token IS 'Google OAuth2 refresh token for Forms API access';
COMMENT ON COLUMN profiles.google_connected_at IS 'Timestamp when user connected their Google account';

-- Create index for quick lookup of connected users
CREATE INDEX IF NOT EXISTS idx_profiles_google_connected 
ON profiles(id) WHERE google_refresh_token IS NOT NULL;

-- Update user_tier_info view to include Google connection status
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
        WHEN COALESCE(p.account_tier, 'free') = 'basic' THEN 50
        WHEN COALESCE(p.account_tier, 'free') = 'pro' THEN -1  -- Unlimited
        ELSE 5
    END as quota_limit,
    CASE 
        WHEN COALESCE(p.account_tier, 'free') = 'pro' THEN FALSE
        WHEN COALESCE(p.account_tier, 'free') = 'basic' THEN (
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

