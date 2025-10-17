-- Migration: 007 - Add RLS policies for answers and profiles tables
-- Date: 2025-10-17
-- Purpose: Add RLS policies for answers (user_answers) and profiles tables

-- ============================================================================
-- Step 1: Check column types for type-safe policies
-- ============================================================================

DO $$
DECLARE
    answers_exists BOOLEAN;
    profiles_user_id_col TEXT;
    submissions_user_id_type TEXT;
BEGIN
    -- Check if answers table exists (it might be named 'answers' or 'user_answers')
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = 'answers'
    ) INTO answers_exists;
    
    IF NOT answers_exists THEN
        RAISE WARNING 'Table "answers" does not exist yet. Skipping answers RLS policy.';
    ELSE
        RAISE NOTICE 'Found table "answers". Will add RLS policy.';
    END IF;
    
    -- Check profiles table user column name (might be 'id' or 'user_id')
    SELECT column_name INTO profiles_user_id_col
    FROM information_schema.columns
    WHERE table_name = 'profiles' AND column_name IN ('id', 'user_id')
    LIMIT 1;
    
    IF profiles_user_id_col IS NULL THEN
        RAISE WARNING 'Table "profiles" does not have id or user_id column. Skipping profiles RLS policy.';
    ELSE
        RAISE NOTICE 'Found profiles table with column: %', profiles_user_id_col;
    END IF;
    
    -- Check submissions.user_id type for answers policy
    SELECT data_type INTO submissions_user_id_type
    FROM information_schema.columns
    WHERE table_name = 'submissions' AND column_name = 'user_id';
    
    RAISE NOTICE '============================================';
    RAISE NOTICE 'Column Types:';
    RAISE NOTICE 'submissions.user_id: %', COALESCE(submissions_user_id_type, 'NOT FOUND');
    RAISE NOTICE '============================================';
END $$;

-- ============================================================================
-- Step 2: Add RLS policy for answers table
-- ============================================================================

-- Enable RLS on answers table
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'answers') THEN
        ALTER TABLE answers ENABLE ROW LEVEL SECURITY;
        RAISE NOTICE '✅ RLS enabled on answers table';
    END IF;
END $$;

DROP POLICY IF EXISTS answers_user_policy ON answers;

-- Policy: Users can only see and manage their own answers (via submission)
-- This uses a subquery to check if the submission belongs to the user
DO $$
DECLARE
    col_type TEXT;
BEGIN
    -- Skip if answers table doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'answers') THEN
        RAISE NOTICE '⚠️  Skipping answers policy - table does not exist';
        RETURN;
    END IF;
    
    -- Check submissions.user_id column type
    SELECT data_type INTO col_type
    FROM information_schema.columns
    WHERE table_name = 'submissions' AND column_name = 'user_id';
    
    IF col_type = 'uuid' THEN
        -- UUID type: compare directly
        EXECUTE 'CREATE POLICY answers_user_policy ON answers FOR ALL TO authenticated ' ||
                'USING (EXISTS (SELECT 1 FROM submissions WHERE submissions.id = answers.submission_id AND submissions.user_id = auth.uid())) ' ||
                'WITH CHECK (EXISTS (SELECT 1 FROM submissions WHERE submissions.id = answers.submission_id AND submissions.user_id = auth.uid()))';
        RAISE NOTICE '✅ answers_user_policy created for UUID type';
    ELSIF col_type IN ('text', 'character varying') THEN
        -- TEXT type: cast auth.uid() to text
        EXECUTE 'CREATE POLICY answers_user_policy ON answers FOR ALL TO authenticated ' ||
                'USING (EXISTS (SELECT 1 FROM submissions WHERE submissions.id = answers.submission_id AND submissions.user_id = auth.uid()::text)) ' ||
                'WITH CHECK (EXISTS (SELECT 1 FROM submissions WHERE submissions.id = answers.submission_id AND submissions.user_id = auth.uid()::text))';
        RAISE NOTICE '✅ answers_user_policy created for TEXT type';
    ELSE
        RAISE EXCEPTION 'Unexpected column type for submissions.user_id: %', col_type;
    END IF;
END $$;

-- Add comment for documentation
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'answers') THEN
        EXECUTE 'COMMENT ON POLICY answers_user_policy ON answers IS ' ||
                '''Users can manage answers only for their own submissions (via submission ownership)''';
    END IF;
END $$;

-- ============================================================================
-- Step 3: Add RLS policy for profiles table
-- ============================================================================

-- Enable RLS on profiles table
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS profiles_user_policy ON profiles;
DROP POLICY IF EXISTS profiles_admin_policy ON profiles;

-- Policy 1: Users can view and update their own profile
DO $$
DECLARE
    col_type TEXT;
BEGIN
    SELECT data_type INTO col_type
    FROM information_schema.columns
    WHERE table_name = 'profiles' AND column_name = 'id';
    
    IF col_type = 'uuid' THEN
        -- UUID type: compare directly
        EXECUTE 'CREATE POLICY profiles_user_policy ON profiles FOR ALL TO authenticated ' ||
                'USING (id = auth.uid()) ' ||
                'WITH CHECK (id = auth.uid())';
        RAISE NOTICE '✅ profiles_user_policy created for UUID type';
    ELSIF col_type IN ('text', 'character varying') THEN
        -- TEXT type: cast auth.uid() to text
        EXECUTE 'CREATE POLICY profiles_user_policy ON profiles FOR ALL TO authenticated ' ||
                'USING (id = auth.uid()::text) ' ||
                'WITH CHECK (id = auth.uid()::text)';
        RAISE NOTICE '✅ profiles_user_policy created for TEXT type';
    ELSE
        RAISE EXCEPTION 'Unexpected column type for profiles.id: %', col_type;
    END IF;
END $$;

COMMENT ON POLICY profiles_user_policy ON profiles IS 
'Users can view and update their own profile';

-- Policy 2: Admins can view all profiles (for admin panel)
-- This policy only allows SELECT for admins, not UPDATE/DELETE
CREATE POLICY profiles_admin_policy ON profiles 
FOR SELECT 
TO authenticated
USING (public.is_user_admin(auth.uid()));

COMMENT ON POLICY profiles_admin_policy ON profiles IS 
'Admins can view all user profiles (SELECT only)';

-- ============================================================================
-- Verification
-- ============================================================================

DO $$
DECLARE
    policy_count INTEGER;
    answers_policy_exists BOOLEAN;
    profiles_policy_count INTEGER;
BEGIN
    -- Check answers policy (if table exists)
    SELECT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'answers' AND policyname = 'answers_user_policy'
    ) INTO answers_policy_exists;
    
    IF answers_policy_exists THEN
        RAISE NOTICE '✅ answers_user_policy created';
    ELSE
        RAISE NOTICE '⚠️  answers_user_policy not created (table may not exist)';
    END IF;
    
    -- Check profiles policies
    SELECT COUNT(*) INTO profiles_policy_count
    FROM pg_policies 
    WHERE tablename = 'profiles' AND policyname IN ('profiles_user_policy', 'profiles_admin_policy');
    
    IF profiles_policy_count >= 2 THEN
        RAISE NOTICE '✅ profiles policies created (user + admin)';
    ELSE
        RAISE WARNING '⚠️  Expected 2 profiles policies, found %', profiles_policy_count;
    END IF;
    
    -- Total count of all user-related RLS policies
    SELECT COUNT(*) INTO policy_count
    FROM pg_policies 
    WHERE tablename IN ('quizzes', 'user_files', 'submissions', 'questions', 'quiz_metadata', 'answers', 'profiles')
    AND schemaname = 'public';

    RAISE NOTICE '============================================';
    RAISE NOTICE 'Migration 007 completed!';
    RAISE NOTICE 'Total RLS policies across all tables: %', policy_count;
    RAISE NOTICE '============================================';
END $$;

-- Show final policy summary
SELECT 
    tablename,
    policyname,
    roles,
    cmd,
    CASE 
        WHEN policyname LIKE '%admin%' THEN 'Admin access'
        WHEN policyname LIKE '%user%' THEN 'User ownership'
        ELSE 'Other'
    END as policy_type
FROM pg_policies 
WHERE schemaname = 'public' 
AND tablename IN ('quizzes', 'user_files', 'submissions', 'questions', 'quiz_metadata', 'answers', 'profiles', 'role_audit_log')
ORDER BY tablename, policyname;
