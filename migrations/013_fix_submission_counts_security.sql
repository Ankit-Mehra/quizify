-- Migration: 013 - Fix user_submission_counts security model
-- Date: 2025-10-27
-- Purpose: Fix user_submission_counts to use security_definer (not security_invoker)
-- Issue: When user_tier_info (security_definer) joins user_submission_counts (security_invoker),
--        the join fails because there's no user context to run security_invoker with.
-- Result: quizzes_attempted always returns 0 even when submissions exist

-- ============================================================================
-- Recreate user_submission_counts with security_definer (default)
-- ============================================================================

DROP VIEW IF EXISTS user_submission_counts CASCADE;

CREATE OR REPLACE VIEW user_submission_counts AS
SELECT 
    user_id,
    COUNT(*) AS submission_count
FROM submissions
GROUP BY user_id;

COMMENT ON VIEW user_submission_counts IS 
'Real-time count of quiz submissions (attempts) per user. Uses security_definer (like user_quiz_counts) to work properly when joined by user_tier_info view.';

-- Grant permissions
GRANT SELECT ON user_submission_counts TO authenticated;
GRANT SELECT ON user_submission_counts TO anon;

-- ============================================================================
-- Recreate user_tier_info to pick up the change (views may cache dependencies)
-- ============================================================================

DROP VIEW IF EXISTS user_tier_info CASCADE;

CREATE OR REPLACE VIEW user_tier_info AS
SELECT 
    u.id,
    u.email,
    p.display_name,
    COALESCE(p.account_tier, 'free') AS account_tier,
    COALESCE(p.role, 'user') AS role,
    COALESCE(q.quiz_count, 0) AS current_quiz_count,
    COALESCE(s.submission_count, 0) AS quizzes_attempted,
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
LEFT JOIN user_submission_counts s ON u.id = s.user_id;

COMMENT ON VIEW user_tier_info IS 
'User tier, role, display name, quota info, and submission count. Uses security_definer to access auth.users. All joined views (user_quiz_counts, user_submission_counts) also use security_definer for consistent behavior.';

-- Grant permissions
GRANT SELECT ON user_tier_info TO authenticated;
GRANT SELECT ON user_tier_info TO anon;

-- ============================================================================
-- Verification
-- ============================================================================

DO $$
DECLARE
    test_user_id uuid := '760602fe-b19f-472a-b65e-060f9e195529';
    quiz_count_direct bigint;
    submission_count_direct bigint;
    quiz_count_view bigint;
    submission_count_view bigint;
BEGIN
    -- Get counts directly from tables
    SELECT COUNT(*) INTO quiz_count_direct FROM quizzes WHERE created_by = test_user_id;
    SELECT COUNT(*) INTO submission_count_direct FROM submissions WHERE user_id = test_user_id;
    
    -- Get counts from view
    SELECT current_quiz_count, quizzes_attempted 
    INTO quiz_count_view, submission_count_view
    FROM user_tier_info 
    WHERE id = test_user_id;
    
    -- Compare
    RAISE NOTICE '';
    RAISE NOTICE '=================================================================';
    RAISE NOTICE 'Migration 013 - Verification for user: %', test_user_id;
    RAISE NOTICE '=================================================================';
    RAISE NOTICE '';
    RAISE NOTICE 'Direct table counts:';
    RAISE NOTICE '  Quizzes created: %', quiz_count_direct;
    RAISE NOTICE '  Submissions: %', submission_count_direct;
    RAISE NOTICE '';
    RAISE NOTICE 'View counts:';
    RAISE NOTICE '  current_quiz_count: %', quiz_count_view;
    RAISE NOTICE '  quizzes_attempted: %', submission_count_view;
    RAISE NOTICE '';
    
    IF quiz_count_direct = quiz_count_view AND submission_count_direct = submission_count_view THEN
        RAISE NOTICE '✅ SUCCESS: View counts match table counts!';
    ELSE
        RAISE WARNING '❌ MISMATCH: View counts do not match table counts';
        RAISE WARNING 'This may indicate RLS policies blocking the view queries';
    END IF;
    
    RAISE NOTICE '';
    RAISE NOTICE '=================================================================';
    RAISE NOTICE 'Migration 013 completed!';
    RAISE NOTICE '=================================================================';
    RAISE NOTICE '';
END $$;
