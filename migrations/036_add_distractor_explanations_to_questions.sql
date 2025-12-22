-- Migration: 036 - Add distractor_explanations column to questions table
-- Date: 2025-12-16
-- Purpose: Store structured distractor explanations for MCQ and fill_blank questions
-- Context: Frontend already implements distractor_explanations display, but the field
--          was not being saved to database. This migration adds the column to persist it.
--
-- IMPORTANT: This is a backward-compatible, non-breaking change:
-- - Column is nullable (existing questions get NULL)
-- - No CHECK constraints (any valid JSONB is accepted)
-- - No foreign keys or dependencies on other tables
-- - RLS policies already cover all questions columns via SELECT *

-- ============================================================================
-- 1. Add distractor_explanations column to questions table
-- ============================================================================

-- The distractor_explanations field stores a JSON object mapping incorrect options
-- to their explanations. Example for MCQ:
-- {
--   "Paris": "Paris is the capital of France, not Germany",
--   "Madrid": "Madrid is the capital of Spain, not Germany",
--   "Rome": "Rome is the capital of Italy, not Germany"
-- }
--
-- For true_false and matching questions, this will be NULL.
-- For fill_blank questions, this contains explanations for wrong fill options.

DO $$
BEGIN
    -- Check if column already exists to make migration idempotent
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'questions' 
        AND column_name = 'distractor_explanations'
    ) THEN
        ALTER TABLE public.questions 
        ADD COLUMN distractor_explanations JSONB DEFAULT NULL;
        
        RAISE NOTICE 'Added distractor_explanations column to questions table';
    ELSE
        RAISE NOTICE 'Column distractor_explanations already exists, skipping';
    END IF;
END $$;

-- ============================================================================
-- 2. Add comment for documentation
-- ============================================================================

COMMENT ON COLUMN public.questions.distractor_explanations IS 
    'JSON object mapping incorrect options to explanations. '
    'Populated for multiple_choice and fill_blank questions. '
    'NULL for true_false and matching questions. '
    'Example: {"Paris": "Paris is the capital of France, not Germany"}';

-- ============================================================================
-- 3. Verification Query (for manual testing)
-- ============================================================================

-- Run this after migration to verify:
-- SELECT column_name, data_type, is_nullable, column_default
-- FROM information_schema.columns 
-- WHERE table_schema = 'public' AND table_name = 'questions'
-- ORDER BY ordinal_position;

-- ============================================================================
-- Note: No index needed for this column
-- ============================================================================
-- We don't add an index because:
-- 1. This column is never used in WHERE clauses
-- 2. It's only retrieved as part of SELECT * when fetching questions
-- 3. Adding an index would slow down INSERT operations unnecessarily
