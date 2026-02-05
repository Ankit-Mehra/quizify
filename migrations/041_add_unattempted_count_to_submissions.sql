-- Migration: Add unattempted_count column to submissions table
-- Description: Tracks questions that users skipped/didn't answer separately from wrong answers
-- Author: Copilot
-- Date: 2026-02-05

-- ============================================================================
-- Step 1: Add unattempted_count column to submissions table
-- ============================================================================
-- This column tracks questions where the user didn't provide an answer.
-- It's separate from wrong_count which tracks attempted-but-incorrect answers.
-- Default to 0 for backward compatibility with existing submissions.

ALTER TABLE submissions
ADD COLUMN IF NOT EXISTS unattempted_count INTEGER NOT NULL DEFAULT 0;

-- Add a check constraint to ensure unattempted_count is non-negative
ALTER TABLE submissions
ADD CONSTRAINT submissions_unattempted_count_check CHECK (unattempted_count >= 0);

-- ============================================================================
-- Step 2: Add comment for documentation
-- ============================================================================

COMMENT ON COLUMN submissions.unattempted_count IS 
'Number of questions the user skipped/did not answer. Separate from wrong_count which tracks attempted-but-incorrect answers.';

-- ============================================================================
-- Step 3: Verify the change
-- ============================================================================

DO $$
DECLARE
    column_exists BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'submissions' 
        AND column_name = 'unattempted_count'
    ) INTO column_exists;
    
    IF column_exists THEN
        RAISE NOTICE '✅ SUCCESS: unattempted_count column added to submissions table';
    ELSE
        RAISE EXCEPTION '❌ FAILED: unattempted_count column was not created';
    END IF;
END $$;

-- ============================================================================
-- Rollback Instructions
-- ============================================================================
-- To rollback this migration:
-- ALTER TABLE submissions DROP CONSTRAINT IF EXISTS submissions_unattempted_count_check;
-- ALTER TABLE submissions DROP COLUMN IF EXISTS unattempted_count;
