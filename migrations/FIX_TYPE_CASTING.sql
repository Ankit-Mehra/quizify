-- Fix type casting issues in RLS policies
-- This script checks column types and recreates policies with correct casting
-- Run this if you get "operator does not exist: uuid = text" errors

-- ============================================================================
-- Step 1: Check column types for all tables
-- ============================================================================

DO $$
DECLARE
    quizzes_created_by_type TEXT;
    user_files_user_id_type TEXT;
    quiz_metadata_created_by_type TEXT;
    submissions_user_id_type TEXT;
BEGIN
    -- Check quizzes.created_by type
    SELECT data_type INTO quizzes_created_by_type
    FROM information_schema.columns
    WHERE table_name = 'quizzes' AND column_name = 'created_by';
    
    -- Check user_files.user_id type
    SELECT data_type INTO user_files_user_id_type
    FROM information_schema.columns
    WHERE table_name = 'user_files' AND column_name = 'user_id';
    
    -- Check quiz_metadata.created_by type
    SELECT data_type INTO quiz_metadata_created_by_type
    FROM information_schema.columns
    WHERE table_name = 'quiz_metadata' AND column_name = 'created_by';
    
    -- Check submissions.user_id type
    SELECT data_type INTO submissions_user_id_type
    FROM information_schema.columns
    WHERE table_name = 'submissions' AND column_name = 'user_id';
    
    RAISE NOTICE '============================================';
    RAISE NOTICE 'Column Types:';
    RAISE NOTICE 'quizzes.created_by: %', quizzes_created_by_type;
    RAISE NOTICE 'user_files.user_id: %', user_files_user_id_type;
    RAISE NOTICE 'quiz_metadata.created_by: %', quiz_metadata_created_by_type;
    RAISE NOTICE 'submissions.user_id: %', submissions_user_id_type;
    RAISE NOTICE '============================================';
END $$;

-- ============================================================================
-- Step 2: Fix quizzes table policy
-- ============================================================================

DROP POLICY IF EXISTS quizzes_user_policy ON quizzes;

-- Check if created_by is UUID or TEXT and create appropriate policy
DO $$
DECLARE
    col_type TEXT;
BEGIN
    SELECT data_type INTO col_type
    FROM information_schema.columns
    WHERE table_name = 'quizzes' AND column_name = 'created_by';
    
    IF col_type = 'uuid' THEN
        -- UUID type: compare directly without casting
        EXECUTE 'CREATE POLICY quizzes_user_policy ON quizzes FOR ALL TO authenticated ' ||
                'USING (created_by = auth.uid()) ' ||
                'WITH CHECK (created_by = auth.uid())';
        RAISE NOTICE '✅ quizzes_user_policy created for UUID type';
    ELSIF col_type IN ('text', 'character varying') THEN
        -- TEXT type: cast auth.uid() to text
        EXECUTE 'CREATE POLICY quizzes_user_policy ON quizzes FOR ALL TO authenticated ' ||
                'USING (created_by = auth.uid()::text) ' ||
                'WITH CHECK (created_by = auth.uid()::text)';
        RAISE NOTICE '✅ quizzes_user_policy created for TEXT type';
    ELSE
        RAISE EXCEPTION 'Unexpected column type for quizzes.created_by: %', col_type;
    END IF;
END $$;

-- ============================================================================
-- Step 3: Fix user_files table policy
-- ============================================================================

DROP POLICY IF EXISTS user_files_user_policy ON user_files;

DO $$
DECLARE
    col_type TEXT;
BEGIN
    SELECT data_type INTO col_type
    FROM information_schema.columns
    WHERE table_name = 'user_files' AND column_name = 'user_id';
    
    IF col_type = 'uuid' THEN
        EXECUTE 'CREATE POLICY user_files_user_policy ON user_files FOR ALL TO authenticated ' ||
                'USING (user_id = auth.uid()) ' ||
                'WITH CHECK (user_id = auth.uid())';
        RAISE NOTICE '✅ user_files_user_policy created for UUID type';
    ELSIF col_type IN ('text', 'character varying') THEN
        EXECUTE 'CREATE POLICY user_files_user_policy ON user_files FOR ALL TO authenticated ' ||
                'USING (user_id = auth.uid()::text) ' ||
                'WITH CHECK (user_id = auth.uid()::text)';
        RAISE NOTICE '✅ user_files_user_policy created for TEXT type';
    ELSE
        RAISE EXCEPTION 'Unexpected column type for user_files.user_id: %', col_type;
    END IF;
END $$;

-- ============================================================================
-- Step 4: Fix quiz_metadata table policy
-- ============================================================================

DROP POLICY IF EXISTS quiz_metadata_user_policy ON quiz_metadata;

DO $$
DECLARE
    col_type TEXT;
BEGIN
    SELECT data_type INTO col_type
    FROM information_schema.columns
    WHERE table_name = 'quiz_metadata' AND column_name = 'created_by';
    
    IF col_type = 'uuid' THEN
        EXECUTE 'CREATE POLICY quiz_metadata_user_policy ON quiz_metadata FOR ALL TO authenticated ' ||
                'USING (created_by = auth.uid()) ' ||
                'WITH CHECK (created_by = auth.uid())';
        RAISE NOTICE '✅ quiz_metadata_user_policy created for UUID type';
    ELSIF col_type IN ('text', 'character varying') THEN
        EXECUTE 'CREATE POLICY quiz_metadata_user_policy ON quiz_metadata FOR ALL TO authenticated ' ||
                'USING (created_by = auth.uid()::text) ' ||
                'WITH CHECK (created_by = auth.uid()::text)';
        RAISE NOTICE '✅ quiz_metadata_user_policy created for TEXT type';
    ELSE
        RAISE EXCEPTION 'Unexpected column type for quiz_metadata.created_by: %', col_type;
    END IF;
END $$;

-- ============================================================================
-- Step 5: Fix submissions table policy
-- ============================================================================

DROP POLICY IF EXISTS submissions_user_policy ON submissions;

DO $$
DECLARE
    col_type TEXT;
BEGIN
    SELECT data_type INTO col_type
    FROM information_schema.columns
    WHERE table_name = 'submissions' AND column_name = 'user_id';
    
    IF col_type = 'uuid' THEN
        EXECUTE 'CREATE POLICY submissions_user_policy ON submissions FOR ALL TO authenticated ' ||
                'USING (user_id = auth.uid()) ' ||
                'WITH CHECK (user_id = auth.uid())';
        RAISE NOTICE '✅ submissions_user_policy created for UUID type';
    ELSIF col_type IN ('text', 'character varying') THEN
        EXECUTE 'CREATE POLICY submissions_user_policy ON submissions FOR ALL TO authenticated ' ||
                'USING (user_id = auth.uid()::text) ' ||
                'WITH CHECK (user_id = auth.uid()::text)';
        RAISE NOTICE '✅ submissions_user_policy created for TEXT type';
    ELSE
        RAISE EXCEPTION 'Unexpected column type for submissions.user_id: %', col_type;
    END IF;
END $$;

-- ============================================================================
-- Step 6: Fix questions table policy (references quizzes)
-- ============================================================================

ALTER TABLE questions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS questions_user_policy ON questions;

DO $$
DECLARE
    col_type TEXT;
BEGIN
    SELECT data_type INTO col_type
    FROM information_schema.columns
    WHERE table_name = 'quizzes' AND column_name = 'created_by';
    
    IF col_type = 'uuid' THEN
        EXECUTE 'CREATE POLICY questions_user_policy ON questions FOR ALL TO authenticated ' ||
                'USING (EXISTS (SELECT 1 FROM quizzes WHERE quizzes.id = questions.quiz_id AND quizzes.created_by = auth.uid())) ' ||
                'WITH CHECK (EXISTS (SELECT 1 FROM quizzes WHERE quizzes.id = questions.quiz_id AND quizzes.created_by = auth.uid()))';
        RAISE NOTICE '✅ questions_user_policy created for UUID type';
    ELSIF col_type IN ('text', 'character varying') THEN
        EXECUTE 'CREATE POLICY questions_user_policy ON questions FOR ALL TO authenticated ' ||
                'USING (EXISTS (SELECT 1 FROM quizzes WHERE quizzes.id = questions.quiz_id AND quizzes.created_by = auth.uid()::text)) ' ||
                'WITH CHECK (EXISTS (SELECT 1 FROM quizzes WHERE quizzes.id = questions.quiz_id AND quizzes.created_by = auth.uid()::text))';
        RAISE NOTICE '✅ questions_user_policy created for TEXT type';
    ELSE
        RAISE EXCEPTION 'Unexpected column type for quizzes.created_by: %', col_type;
    END IF;
END $$;

-- ============================================================================
-- Verification
-- ============================================================================

DO $$
DECLARE
    policy_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO policy_count
    FROM pg_policies 
    WHERE tablename IN ('quizzes', 'user_files', 'submissions', 'questions', 'quiz_metadata')
    AND policyname LIKE '%_user_policy';

    RAISE NOTICE '============================================';
    RAISE NOTICE 'Fix completed!';
    RAISE NOTICE 'Total RLS policies: %', policy_count;
    
    IF policy_count >= 5 THEN
        RAISE NOTICE '✅ All required RLS policies are in place';
    ELSE
        RAISE WARNING '⚠️  Expected 5 policies, found %', policy_count;
    END IF;
    RAISE NOTICE '============================================';
END $$;

-- Show final policy details
SELECT 
    tablename,
    policyname,
    roles,
    cmd
FROM pg_policies 
WHERE schemaname = 'public' 
AND tablename IN ('quizzes', 'user_files', 'submissions', 'questions', 'quiz_metadata')
ORDER BY tablename, policyname;
