-- Migration: 010 - Update user_tier_info view to include display_name
-- Date: 2025-10-23
-- Purpose: Add display_name field to user_tier_info view after adding it to profiles table

-- ============================================================================
-- Update user_tier_info view to include display_name
-- ============================================================================

DROP VIEW IF EXISTS user_tier_info;

CREATE OR REPLACE VIEW user_tier_info AS
SELECT 
    u.id,
    u.email,
    p.display_name,  -- NEW: Include display name from profiles
    COALESCE(p.account_tier, 'free') AS account_tier,
    COALESCE(p.role, 'user') AS role,
    COALESCE(q.quiz_count, 0) AS current_quiz_count,
    CASE 
        WHEN COALESCE(p.account_tier, 'free') = 'free' THEN 5
        WHEN COALESCE(p.account_tier, 'free') = 'basic' THEN 100
        WHEN COALESCE(p.account_tier, 'free') = 'educator' THEN 500
        ELSE 5
    END AS quota_limit,
    CASE 
        WHEN COALESCE(p.account_tier, 'free') = 'free' THEN COALESCE(q.quiz_count, 0) >= 5
        WHEN COALESCE(p.account_tier, 'free') = 'basic' THEN COALESCE(q.quiz_count, 0) >= 100
        WHEN COALESCE(p.account_tier, 'free') = 'educator' THEN COALESCE(q.quiz_count, 0) >= 500
        ELSE true
    END AS quota_exceeded,
    p.created_at,
    p.updated_at
FROM auth.users u
LEFT JOIN public.profiles p ON u.id = p.id
LEFT JOIN user_quiz_counts q ON u.id = q.user_id;

COMMENT ON VIEW user_tier_info IS 
'User tier, role, and display name information with quota status for enforcement and admin panel';

-- ============================================================================
-- Verification
-- ============================================================================

-- Check view structure
SELECT 
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'public' 
AND table_name = 'user_tier_info'
ORDER BY ordinal_position;

-- Sample data
SELECT 
    id,
    email,
    display_name,
    account_tier,
    role,
    current_quiz_count,
    quota_limit,
    quota_exceeded
FROM user_tier_info
LIMIT 3;

-- ============================================================================
-- Notes
-- ============================================================================
-- After this migration:
-- 1. user_tier_info view now includes display_name field
-- 2. GET /auth/me endpoint will return user's display name
-- 3. Admin panel can display user names instead of just emails
-- ============================================================================
