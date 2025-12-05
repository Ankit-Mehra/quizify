-- Migration: Fix RLS policies to allow INSERT operations with authenticated clients
-- Date: 2025-10-16
-- Description: Add WITH CHECK clause to RLS policies so authenticated users can insert their own data

-- ============================================================================
-- Fix quizzes table RLS policy
-- ============================================================================

DROP POLICY IF EXISTS quizzes_user_policy ON quizzes;

-- Policy: Users can only see and create their own quizzes
CREATE POLICY quizzes_user_policy 
ON quizzes FOR ALL 
USING (created_by = auth.uid())
WITH CHECK (created_by = auth.uid());

COMMENT ON POLICY quizzes_user_policy ON quizzes IS 
'Users can SELECT/UPDATE/DELETE their own quizzes (USING) and INSERT new quizzes as themselves (WITH CHECK)';

-- ============================================================================
-- Fix user_files table RLS policy
-- ============================================================================

DROP POLICY IF EXISTS user_files_user_policy ON user_files;

-- Policy: Users can only see and create their own files
CREATE POLICY user_files_user_policy 
ON user_files FOR ALL 
USING (user_id = auth.uid())
WITH CHECK (user_id = auth.uid());

COMMENT ON POLICY user_files_user_policy ON user_files IS 
'Users can SELECT/UPDATE/DELETE their own files (USING) and INSERT new files as themselves (WITH CHECK)';

-- ============================================================================
-- Fix submissions table RLS policy
-- ============================================================================

DROP POLICY IF EXISTS submissions_user_policy ON submissions;

-- Policy: Users can only see and create their own submissions
CREATE POLICY submissions_user_policy 
ON submissions FOR ALL 
USING (user_id = auth.uid())
WITH CHECK (user_id = auth.uid());

COMMENT ON POLICY submissions_user_policy ON submissions IS 
'Users can SELECT/UPDATE/DELETE their own submissions (USING) and INSERT new submissions as themselves (WITH CHECK)';

-- ============================================================================
-- Fix questions table RLS policy (if exists)
-- ============================================================================

-- Enable RLS on questions table if not already enabled
ALTER TABLE questions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS questions_user_policy ON questions;

-- Policy: Users can see questions from their own quizzes
-- For INSERT: Allow if the quiz belongs to the user
CREATE POLICY questions_user_policy 
ON questions FOR ALL 
USING (
    EXISTS (
        SELECT 1 FROM quizzes 
        WHERE quizzes.id = questions.quiz_id 
        AND quizzes.created_by = auth.uid()
    )
)
WITH CHECK (
    EXISTS (
        SELECT 1 FROM quizzes 
        WHERE quizzes.id = questions.quiz_id 
        AND quizzes.created_by = auth.uid()
    )
);

COMMENT ON POLICY questions_user_policy ON questions IS 
'Users can manage questions only for quizzes they created';

-- ============================================================================
-- Verification
-- ============================================================================

DO $$
BEGIN
    -- Verify quizzes policy
    IF EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'quizzes' 
        AND policyname = 'quizzes_user_policy'
    ) THEN
        RAISE NOTICE '✅ quizzes_user_policy updated with WITH CHECK clause';
    ELSE
        RAISE EXCEPTION '❌ Failed to create quizzes_user_policy';
    END IF;

    -- Verify user_files policy
    IF EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'user_files' 
        AND policyname = 'user_files_user_policy'
    ) THEN
        RAISE NOTICE '✅ user_files_user_policy updated with WITH CHECK clause';
    ELSE
        RAISE EXCEPTION '❌ Failed to create user_files_user_policy';
    END IF;

    -- Verify submissions policy
    IF EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'submissions' 
        AND policyname = 'submissions_user_policy'
    ) THEN
        RAISE NOTICE '✅ submissions_user_policy updated with WITH CHECK clause';
    ELSE
        RAISE EXCEPTION '❌ Failed to create submissions_user_policy';
    END IF;

    -- Verify questions policy
    IF EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'questions' 
        AND policyname = 'questions_user_policy'
    ) THEN
        RAISE NOTICE '✅ questions_user_policy created with WITH CHECK clause';
    ELSE
        RAISE EXCEPTION '❌ Failed to create questions_user_policy';
    END IF;

    RAISE NOTICE '============================================';
    RAISE NOTICE 'Migration 005 completed successfully';
    RAISE NOTICE 'All RLS policies now support INSERT operations';
    RAISE NOTICE 'Authenticated users can create their own data';
    RAISE NOTICE '============================================';
END $$;
