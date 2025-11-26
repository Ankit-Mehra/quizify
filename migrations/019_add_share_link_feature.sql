-- Migration: 019 - Add Share Link Feature
-- Date: 2025-01-18
-- Purpose: Add columns for public quiz sharing via unique slugs

-- ============================================================================
-- 1. Add share link columns to quizzes table
-- ============================================================================

-- Add is_public flag to control quiz visibility
ALTER TABLE quizzes 
ADD COLUMN IF NOT EXISTS is_public BOOLEAN DEFAULT FALSE NOT NULL;

-- Add public_slug for shareable URL path (e.g., /quiz/abc123xyz)
-- Slug should be unique across all public quizzes
ALTER TABLE quizzes 
ADD COLUMN IF NOT EXISTS public_slug TEXT;

-- Add shared_at timestamp to track when quiz was made public
ALTER TABLE quizzes 
ADD COLUMN IF NOT EXISTS shared_at TIMESTAMPTZ;

COMMENT ON COLUMN quizzes.is_public IS 'Whether quiz is publicly accessible via share link';
COMMENT ON COLUMN quizzes.public_slug IS 'Unique URL slug for public access (e.g., abc123xyz)';
COMMENT ON COLUMN quizzes.shared_at IS 'Timestamp when quiz was first made public';

-- ============================================================================
-- 2. Add indexes for efficient public quiz lookup
-- ============================================================================

-- Unique index on public_slug (only for non-null values)
-- This allows multiple NULL values but enforces uniqueness for actual slugs
CREATE UNIQUE INDEX IF NOT EXISTS idx_quizzes_public_slug 
ON quizzes(public_slug) WHERE public_slug IS NOT NULL;

-- Index for finding public quizzes efficiently
CREATE INDEX IF NOT EXISTS idx_quizzes_is_public 
ON quizzes(is_public) WHERE is_public = TRUE;

-- Composite index for public quiz retrieval by slug
CREATE INDEX IF NOT EXISTS idx_quizzes_public_lookup 
ON quizzes(public_slug, is_public) WHERE is_public = TRUE;

-- ============================================================================
-- 3. Update RLS policies to allow public quiz access
-- ============================================================================

-- Drop existing quiz policy and recreate with public access
DROP POLICY IF EXISTS quizzes_user_policy ON quizzes;

-- Policy: Users can see their own quizzes OR public quizzes
CREATE POLICY quizzes_select_policy 
ON quizzes FOR SELECT 
USING (
    created_by = auth.uid()  -- User's own quizzes
    OR is_public = TRUE      -- Public quizzes
);

-- Policy: Users can only INSERT their own quizzes
CREATE POLICY quizzes_insert_policy 
ON quizzes FOR INSERT 
WITH CHECK (created_by = auth.uid());

-- Policy: Users can only UPDATE their own quizzes
CREATE POLICY quizzes_update_policy 
ON quizzes FOR UPDATE 
USING (created_by = auth.uid())
WITH CHECK (created_by = auth.uid());

-- Policy: Users can only DELETE their own quizzes
CREATE POLICY quizzes_delete_policy 
ON quizzes FOR DELETE 
USING (created_by = auth.uid());

-- ============================================================================
-- 4. Allow anonymous access for public quiz viewing
-- ============================================================================

-- Create policy for anonymous users to view public quizzes
-- Note: This requires anon role to have SELECT permission on quizzes table
DROP POLICY IF EXISTS quizzes_anon_public_policy ON quizzes;
CREATE POLICY quizzes_anon_public_policy 
ON quizzes FOR SELECT 
TO anon
USING (is_public = TRUE);

-- ============================================================================
-- 5. Update questions table RLS for public quiz access
-- ============================================================================

-- Drop existing questions policy if it exists
DROP POLICY IF EXISTS questions_user_policy ON questions;

-- Policy: Users can see questions for their own quizzes or public quizzes
CREATE POLICY questions_select_policy 
ON questions FOR SELECT 
USING (
    quiz_id IN (
        SELECT id FROM quizzes 
        WHERE created_by = auth.uid() OR is_public = TRUE
    )
);

-- Policy for anonymous users to view questions of public quizzes
DROP POLICY IF EXISTS questions_anon_public_policy ON questions;
CREATE POLICY questions_anon_public_policy 
ON questions FOR SELECT 
TO anon
USING (
    quiz_id IN (SELECT id FROM quizzes WHERE is_public = TRUE)
);

-- ============================================================================
-- 6. Create helper function to generate unique slugs
-- ============================================================================

-- Function to generate a random slug (8 characters, alphanumeric)
CREATE OR REPLACE FUNCTION generate_quiz_slug() 
RETURNS TEXT AS $$
DECLARE
    chars TEXT := 'abcdefghijklmnopqrstuvwxyz0123456789';
    result TEXT := '';
    i INTEGER;
BEGIN
    FOR i IN 1..8 LOOP
        result := result || substr(chars, floor(random() * length(chars) + 1)::int, 1);
    END LOOP;
    RETURN result;
END;
$$ LANGUAGE plpgsql;

-- Function to generate a unique slug (retries if collision)
CREATE OR REPLACE FUNCTION generate_unique_quiz_slug() 
RETURNS TEXT AS $$
DECLARE
    new_slug TEXT;
    slug_exists BOOLEAN;
BEGIN
    LOOP
        new_slug := generate_quiz_slug();
        SELECT EXISTS(SELECT 1 FROM quizzes WHERE public_slug = new_slug) INTO slug_exists;
        EXIT WHEN NOT slug_exists;
    END LOOP;
    RETURN new_slug;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Migration Complete
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE 'Migration 019 completed successfully';
    RAISE NOTICE 'Added: is_public, public_slug, shared_at columns to quizzes';
    RAISE NOTICE 'Added: Unique index on public_slug, index on is_public';
    RAISE NOTICE 'Updated: RLS policies for public quiz access';
    RAISE NOTICE 'Added: Anonymous user access for public quizzes';
    RAISE NOTICE 'Added: Helper functions for slug generation';
END $$;
