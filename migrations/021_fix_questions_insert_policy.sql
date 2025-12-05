-- Migration: 021 - Fix missing INSERT policy on questions table
-- Date: 2025-12-01
-- Purpose: Add INSERT/UPDATE/DELETE policies that were dropped in migration 019
-- 
-- Issue: Migration 019 replaced questions_user_policy (FOR ALL) with only
-- questions_select_policy (FOR SELECT), which blocked quiz generation.

-- ============================================================================
-- 1. Add INSERT policy for questions table
-- ============================================================================

-- Policy: Users can insert questions into quizzes they own
CREATE POLICY questions_insert_policy 
ON questions FOR INSERT 
TO authenticated
WITH CHECK (
    quiz_id IN (
        SELECT id FROM quizzes 
        WHERE created_by = auth.uid()
    )
);

COMMENT ON POLICY questions_insert_policy ON questions IS 
'Users can add questions only to quizzes they own';

-- ============================================================================
-- 2. Add UPDATE policy for questions table
-- ============================================================================

-- Policy: Users can update questions in quizzes they own
CREATE POLICY questions_update_policy 
ON questions FOR UPDATE 
TO authenticated
USING (
    quiz_id IN (
        SELECT id FROM quizzes 
        WHERE created_by = auth.uid()
    )
)
WITH CHECK (
    quiz_id IN (
        SELECT id FROM quizzes 
        WHERE created_by = auth.uid()
    )
);

COMMENT ON POLICY questions_update_policy ON questions IS 
'Users can update questions only in quizzes they own';

-- ============================================================================
-- 3. Add DELETE policy for questions table
-- ============================================================================

-- Policy: Users can delete questions from quizzes they own
CREATE POLICY questions_delete_policy 
ON questions FOR DELETE 
TO authenticated
USING (
    quiz_id IN (
        SELECT id FROM quizzes 
        WHERE created_by = auth.uid()
    )
);

COMMENT ON POLICY questions_delete_policy ON questions IS 
'Users can delete questions only from quizzes they own';

-- ============================================================================
-- 4. Verification
-- ============================================================================

DO $$
DECLARE
    policy_count INT;
BEGIN
    SELECT COUNT(*) INTO policy_count
    FROM pg_policies
    WHERE tablename = 'questions' 
    AND policyname IN ('questions_select_policy', 'questions_insert_policy', 
                       'questions_update_policy', 'questions_delete_policy');
    
    IF policy_count >= 4 THEN
        RAISE NOTICE '✅ All 4 questions policies created successfully';
        RAISE NOTICE '   - questions_select_policy (SELECT)';
        RAISE NOTICE '   - questions_insert_policy (INSERT)';
        RAISE NOTICE '   - questions_update_policy (UPDATE)';
        RAISE NOTICE '   - questions_delete_policy (DELETE)';
    ELSE
        RAISE WARNING '⚠️  Only % of 4 policies found for questions table', policy_count;
    END IF;
END $$;
