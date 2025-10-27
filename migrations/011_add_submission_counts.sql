-- Migration: 011 - Add submission counts to user_tier_info view
-- Date: 2025-10-26
-- Purpose: Track number of quizzes attempted (submissions) vs created (quizzes)
--          This allows users to see how many quizzes they've attempted via /auth/me

-- ============================================================================
-- Step 1: Create user_submission_counts view (similar to user_quiz_counts)
-- ============================================================================

-- Use security_invoker = on to enforce RLS policies
-- This ensures users only see their own submission counts (respects RLS on submissions table)
CREATE OR REPLACE VIEW user_submission_counts 
WITH (security_invoker = on) AS
SELECT 
    user_id,
    COUNT(*) AS submission_count
FROM submissions
GROUP BY user_id;

COMMENT ON VIEW user_submission_counts IS 
'Real-time count of quiz submissions (attempts) per user - tracks quizzes taken, not created. Uses security_invoker to enforce RLS.';

-- ============================================================================
-- Step 2: Update user_tier_info view to include submission count
-- ============================================================================

-- NOTE: user_tier_info joins auth.users which is already protected by Supabase
-- The view automatically filters to show only the authenticated user's data
-- because auth.users is restricted by Supabase's built-in RLS

DROP VIEW IF EXISTS user_tier_info;

CREATE OR REPLACE VIEW user_tier_info 
WITH (security_invoker = on) AS
SELECT 
    u.id,
    u.email,
    p.display_name,
    COALESCE(p.account_tier, 'free') AS account_tier,
    COALESCE(p.role, 'user') AS role,
    COALESCE(q.quiz_count, 0) AS current_quiz_count,  -- Quizzes CREATED
    COALESCE(s.submission_count, 0) AS quizzes_attempted,  -- Quizzes ATTEMPTED (NEW)
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
LEFT JOIN user_quiz_counts q ON u.id = q.user_id
LEFT JOIN user_submission_counts s ON u.id = s.user_id;  -- NEW: Join submission counts

COMMENT ON VIEW user_tier_info IS 
'User tier, role, display name, quota info, and submission count (quizzes attempted vs created). Uses security_invoker to enforce RLS.';

-- ============================================================================
-- Step 3: Grant permissions
-- ============================================================================

GRANT SELECT ON user_submission_counts TO authenticated;
GRANT SELECT ON user_tier_info TO authenticated;

-- ============================================================================
-- Verification Queries
-- ============================================================================

DO $$
BEGIN
    -- Verify user_submission_counts view exists
    IF EXISTS (SELECT 1 FROM pg_views WHERE viewname = 'user_submission_counts') THEN
        RAISE NOTICE '✅ user_submission_counts view created successfully';
    ELSE
        RAISE EXCEPTION '❌ Failed to create user_submission_counts view';
    END IF;

    -- Verify user_tier_info has quizzes_attempted column
    IF EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'user_tier_info' 
        AND column_name = 'quizzes_attempted'
    ) THEN
        RAISE NOTICE '✅ user_tier_info.quizzes_attempted column added successfully';
    ELSE
        RAISE EXCEPTION '❌ Failed to add quizzes_attempted to user_tier_info';
    END IF;

    RAISE NOTICE '';
    RAISE NOTICE '=================================================================';
    RAISE NOTICE 'Migration 011 completed successfully!';
    RAISE NOTICE '=================================================================';
    RAISE NOTICE '';
    RAISE NOTICE 'Changes:';
    RAISE NOTICE '  ✅ Created user_submission_counts view';
    RAISE NOTICE '  ✅ Updated user_tier_info to include quizzes_attempted';
    RAISE NOTICE '';
    RAISE NOTICE 'Sample query to test:';
    RAISE NOTICE '  SELECT email, current_quiz_count AS created, quizzes_attempted';
    RAISE NOTICE '  FROM user_tier_info LIMIT 5;';
    RAISE NOTICE '';
END $$;
