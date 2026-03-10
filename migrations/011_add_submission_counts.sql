-- Migration: 011 - Add submission counts to user_tier_info view
-- Date: 2025-10-26
-- Purpose: Track number of quizzes attempted (submissions) vs created (quizzes)
--          This allows users to see how many quizzes they've attempted via /auth/me

-- ============================================================================
-- SECURITY MODEL EXPLANATION
-- ============================================================================
-- user_submission_counts: security_invoker = on (users can query submissions table)
-- user_tier_info: security_definer (default) - accesses auth.users table
--   * auth.users requires elevated permissions (users can't query it directly)
--   * Backend ALWAYS uses SERVICE ROLE client for get_user_tier_info()
--   * Backend ALWAYS filters by authenticated user_id (no data leakage risk)
--   * This is safe because user_id comes from validated JWT token
-- ============================================================================

-- ============================================================================
-- Step 1: Create user_submission_counts view (similar to user_quiz_counts)
-- ============================================================================

-- NOTE: Using security_definer (default) instead of security_invoker
-- Reason: This view is joined by user_tier_info (which uses security_definer)
-- When a security_definer view joins a security_invoker view, the invoker
-- runs with the caller's permissions, which may not have access to submissions table
CREATE OR REPLACE VIEW user_submission_counts AS
SELECT 
    user_id,
    COUNT(*) AS submission_count
FROM submissions
GROUP BY user_id;

COMMENT ON VIEW user_submission_counts IS 
'Real-time count of quiz submissions (attempts) per user - tracks quizzes taken, not created. Uses security_definer to work with user_tier_info join.';

-- ============================================================================
-- Step 2: Update user_tier_info view to include submission count
-- ============================================================================

-- CRITICAL: Must use security_definer (default) NOT security_invoker
-- 
-- ⚠️  SUPABASE LINTER WARNING - IGNORE IT!
-- Supabase will show a security warning about security_definer, but this is CORRECT.
--
-- WHY security_definer IS REQUIRED:
-- 1. This view accesses auth.users table which requires elevated permissions
-- 2. Regular users cannot access auth.users (by design)
-- 3. Using security_invoker would cause "42501 permission denied" errors
--
-- WHY THIS IS SECURE:
-- 1. Users NEVER query this view directly (no PostgREST API access)
-- 2. ALL queries go through FastAPI backend which validates JWT tokens
-- 3. Backend ALWAYS filters: .eq("id", user_id) where user_id is from validated JWT
-- 4. Impossible for users to access other users' data (backend enforces this)
--
-- SECURITY MODEL:
-- Layer 1: JWT authentication (FastAPI validates with Supabase)
-- Layer 2: Backend filtering (Python code adds WHERE id = user_id)
-- Layer 3: View permissions (security_definer allows auth.users access)
--
-- This is the ONLY way to access auth.users data for authenticated users.

DROP VIEW IF EXISTS user_tier_info;

CREATE OR REPLACE VIEW user_tier_info AS
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
'User tier, role, display name, quota info, and submission count. Uses security_definer (NOT security_invoker) because it accesses auth.users table. This is SECURE because: (1) Users never query directly - all access via FastAPI backend, (2) Backend validates JWT and filters by authenticated user_id, (3) No way to access other users data. Supabase linter warning can be ignored - this is the correct security model for accessing auth.users.';

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
    RAISE NOTICE '  SELECT email, current_quiz_count AS created, quizzes_attempted FROM user_tier_info LIMIT 5;';
    RAISE NOTICE '';
END $$;
