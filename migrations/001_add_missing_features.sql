-- Migration: 001 - Add Missing Features for Comprehensive Quiz Generation
-- Date: 2025-10-03
-- Purpose: Add tier management, content source tracking, file size validation, and search indexes

-- ============================================================================
-- 1. Profiles table setup (for account_tier)
-- ============================================================================

-- Note: Supabase auth.users is locked down, so we use public.profiles
-- The profiles table should already exist in your Supabase project
-- This section verifies it exists and has the required structure

-- Verify profiles table exists
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables 
                   WHERE table_schema = 'public' AND table_name = 'profiles') THEN
        RAISE EXCEPTION 'profiles table does not exist. Please create it first via Supabase Dashboard.';
    END IF;
END $$;

-- Ensure account_tier column exists in profiles (should already be there)
-- IMPORTANT: These values MUST match schemas/user.py -> Literal["free", "basic", "pro"]
-- If you modify tier options, update BOTH this migration AND the schema file
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema = 'public' 
                   AND table_name = 'profiles' 
                   AND column_name = 'account_tier') THEN
        ALTER TABLE public.profiles 
        ADD COLUMN account_tier TEXT DEFAULT 'free' 
        CHECK (account_tier IN ('free', 'basic', 'pro'));
        
        CREATE INDEX idx_profiles_tier ON public.profiles(account_tier);
    END IF;
END $$;

-- ============================================================================
-- 2. Add content source tracking to quizzes
-- ============================================================================

-- Track whether quiz was generated from file or web URL
-- IMPORTANT: These values MUST match schemas/quiz.py -> Literal["file", "url", "text"]
-- If you modify source types, update BOTH this migration AND the schema file
ALTER TABLE quizzes 
ADD COLUMN IF NOT EXISTS content_source_type TEXT DEFAULT 'file'
CHECK (content_source_type IN ('file', 'url', 'text'));

-- Store file_id (UUID) or URL (text) or 'manual' for text input
ALTER TABLE quizzes 
ADD COLUMN IF NOT EXISTS content_source_reference TEXT;

COMMENT ON COLUMN quizzes.content_source_type IS 'Source of quiz content: file (uploaded doc), url (web scraping), text (manual input)';
COMMENT ON COLUMN quizzes.content_source_reference IS 'Reference to source: file_id for file, URL for url, null for text';

-- Index for filtering by source type
CREATE INDEX IF NOT EXISTS idx_quizzes_source_type ON quizzes(content_source_type);

-- ============================================================================
-- 3. Add file size validation column
-- ============================================================================

-- Track file size for 10MB limit enforcement
ALTER TABLE user_files 
ADD COLUMN IF NOT EXISTS file_size_bytes INTEGER;

COMMENT ON COLUMN user_files.file_size_bytes IS 'File size in bytes (max 10MB = 10485760 bytes)';

-- ============================================================================
-- 4. Add search capabilities for quizzes
-- ============================================================================

-- Enable trigram extension for fuzzy text search
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- GIN index for title search (case-insensitive partial matching)
CREATE INDEX IF NOT EXISTS idx_quizzes_title_search 
ON quizzes USING gin(to_tsvector('english', title));

-- Additional index for ILIKE queries on title
CREATE INDEX IF NOT EXISTS idx_quizzes_title_trgm 
ON quizzes USING gin(title gin_trgm_ops);

-- ============================================================================
-- 5. Ensure required indexes exist for performance
-- ============================================================================

-- Quiz indexes (should already exist, but adding IF NOT EXISTS for safety)
CREATE INDEX IF NOT EXISTS idx_quizzes_user ON quizzes(created_by);
CREATE INDEX IF NOT EXISTS idx_quizzes_created_at ON quizzes(created_at);
CREATE INDEX IF NOT EXISTS idx_quizzes_user_created_at ON quizzes(created_by, created_at DESC);

-- File indexes
CREATE INDEX IF NOT EXISTS idx_user_files_user ON user_files(user_id);
CREATE INDEX IF NOT EXISTS idx_user_files_uploaded_at ON user_files(uploaded_at);

-- Question indexes (for quiz retrieval optimization)
CREATE INDEX IF NOT EXISTS idx_questions_quiz ON questions(quiz_id);

-- Submission indexes
CREATE INDEX IF NOT EXISTS idx_submissions_user ON submissions(user_id);
CREATE INDEX IF NOT EXISTS idx_submissions_quiz ON submissions(quiz_id);
CREATE INDEX IF NOT EXISTS idx_submissions_submitted_at ON submissions(submitted_at);

-- ============================================================================
-- 6. Add helpful views for quota management
-- ============================================================================

-- View to track user quiz counts (for quota enforcement)
CREATE OR REPLACE VIEW user_quiz_counts AS
SELECT 
    created_by AS user_id,
    COUNT(*) AS quiz_count
FROM quizzes
GROUP BY created_by;

COMMENT ON VIEW user_quiz_counts IS 'Real-time count of quizzes per user for quota enforcement';

-- View to join users with their tier limits (using profiles table)
CREATE OR REPLACE VIEW user_tier_info AS
SELECT 
    u.id,
    u.email,
    COALESCE(p.account_tier, 'free') AS account_tier,
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
    END AS quota_exceeded
FROM auth.users u
LEFT JOIN public.profiles p ON u.id = p.id
LEFT JOIN user_quiz_counts q ON u.id = q.user_id;

COMMENT ON VIEW user_tier_info IS 'User tier information with quota status for easy enforcement (using profiles table)';

-- ============================================================================
-- 7. Add policies for row-level security (if not already set)
-- ============================================================================

-- Enable RLS on quizzes table
ALTER TABLE quizzes ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only see their own quizzes
DROP POLICY IF EXISTS quizzes_user_policy ON quizzes;
CREATE POLICY quizzes_user_policy 
ON quizzes FOR ALL 
USING (created_by = auth.uid());

-- Policy: Users can only see their own files
ALTER TABLE user_files ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS user_files_user_policy ON user_files;
CREATE POLICY user_files_user_policy 
ON user_files FOR ALL 
USING (user_id = auth.uid());

-- Policy: Users can only see their own submissions
ALTER TABLE submissions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS submissions_user_policy ON submissions;
CREATE POLICY submissions_user_policy 
ON submissions FOR ALL 
USING (user_id = auth.uid());

-- ============================================================================
-- Migration Complete
-- ============================================================================

-- Verify migration success
DO $$
BEGIN
    RAISE NOTICE 'Migration 001 completed successfully';
    RAISE NOTICE 'Verified: profiles table exists with account_tier column';
    RAISE NOTICE 'Added: content_source_type and content_source_reference to quizzes';
    RAISE NOTICE 'Added: file_size_bytes to user_files';
    RAISE NOTICE 'Added: search indexes for quiz titles';
    RAISE NOTICE 'Created: user_quiz_counts and user_tier_info views';
END $$;
