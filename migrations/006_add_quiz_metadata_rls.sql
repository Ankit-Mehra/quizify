-- Migration: 006 - Add quiz_metadata RLS policy
-- Date: 2025-10-17
-- Description: Add RLS policy for quiz_metadata table to allow authenticated users to insert/read their own metadata
-- Note: This complements migration 005 which added policies for quizzes, user_files, submissions, and questions
-- Fixed: Use proper UUID type casting for auth.uid()

-- ============================================================================
-- Enable RLS on quiz_metadata table
-- ============================================================================

ALTER TABLE quiz_metadata ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- Create quiz_metadata RLS policy
-- ============================================================================

DROP POLICY IF EXISTS quiz_metadata_user_policy ON quiz_metadata;

-- Policy: Users can only see and create their own quiz metadata
-- Note: created_by is TEXT type, so we cast auth.uid() to text
CREATE POLICY quiz_metadata_user_policy 
ON quiz_metadata FOR ALL 
TO authenticated
USING (created_by = auth.uid()::text)
WITH CHECK (created_by = auth.uid()::text);

COMMENT ON POLICY quiz_metadata_user_policy ON quiz_metadata IS 
'Users can SELECT/UPDATE/DELETE their own quiz metadata (USING) and INSERT new metadata as themselves (WITH CHECK)';

-- ============================================================================
-- Verification - Check all RLS policies are in place
-- ============================================================================

DO $$
DECLARE
    policy_count INTEGER;
BEGIN
    -- Check quiz_metadata policy
    IF EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'quiz_metadata' 
        AND policyname = 'quiz_metadata_user_policy'
    ) THEN
        RAISE NOTICE '✅ quiz_metadata_user_policy created successfully';
    ELSE
        RAISE EXCEPTION '❌ Failed to create quiz_metadata_user_policy';
    END IF;

    RAISE NOTICE '============================================';
    RAISE NOTICE 'Verifying all RLS policies from migrations 005 & 006:';
    RAISE NOTICE '============================================';

    -- Verify quizzes policy
    IF EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'quizzes' 
        AND policyname = 'quizzes_user_policy'
    ) THEN
        RAISE NOTICE '✅ quizzes_user_policy exists';
    ELSE
        RAISE WARNING '⚠️  quizzes_user_policy missing - run migration 005';
    END IF;

    -- Verify user_files policy
    IF EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'user_files' 
        AND policyname = 'user_files_user_policy'
    ) THEN
        RAISE NOTICE '✅ user_files_user_policy exists';
    ELSE
        RAISE WARNING '⚠️  user_files_user_policy missing - run migration 005';
    END IF;

    -- Verify submissions policy
    IF EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'submissions' 
        AND policyname = 'submissions_user_policy'
    ) THEN
        RAISE NOTICE '✅ submissions_user_policy exists';
    ELSE
        RAISE WARNING '⚠️  submissions_user_policy missing - run migration 005';
    END IF;

    -- Verify questions policy
    IF EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'questions' 
        AND policyname = 'questions_user_policy'
    ) THEN
        RAISE NOTICE '✅ questions_user_policy exists';
    ELSE
        RAISE WARNING '⚠️  questions_user_policy missing - run migration 005';
    END IF;

    -- Verify quiz_metadata policy
    IF EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'quiz_metadata' 
        AND policyname = 'quiz_metadata_user_policy'
    ) THEN
        RAISE NOTICE '✅ quiz_metadata_user_policy exists';
    ELSE
        RAISE EXCEPTION '❌ quiz_metadata_user_policy missing';
    END IF;

    -- Count total policies
    SELECT COUNT(*) INTO policy_count
    FROM pg_policies 
    WHERE tablename IN ('quizzes', 'user_files', 'submissions', 'questions', 'quiz_metadata')
    AND policyname LIKE '%_user_policy';

    RAISE NOTICE '============================================';
    RAISE NOTICE 'Total RLS policies found: %', policy_count;
    
    IF policy_count >= 5 THEN
        RAISE NOTICE '✅ All required RLS policies are in place';
    ELSE
        RAISE WARNING '⚠️  Expected 5 policies, found %', policy_count;
    END IF;

    RAISE NOTICE '============================================';
    RAISE NOTICE 'Migration 006 completed successfully';
    RAISE NOTICE 'quiz_metadata table now has RLS enabled';
    RAISE NOTICE 'Authenticated users can create their own metadata';
    RAISE NOTICE '============================================';
END $$;

-- ============================================================================
-- Display all current RLS policies for verification
-- ============================================================================

SELECT 
    schemaname,
    tablename,
    policyname,
    roles,
    cmd,
    qual AS using_expression,
    with_check AS with_check_expression
FROM pg_policies 
WHERE schemaname = 'public' 
AND tablename IN ('quizzes', 'user_files', 'submissions', 'questions', 'quiz_metadata')
ORDER BY tablename, policyname;
