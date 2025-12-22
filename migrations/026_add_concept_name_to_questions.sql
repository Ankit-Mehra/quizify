-- Migration: 026_add_concept_name_to_questions.sql
-- Purpose: Add concept_name column to questions table for denormalized access
-- Date: 2025-12-04
-- 
-- Background:
-- The questions table has concept_id (FK to concepts table) but retrieving
-- concept_name required a JOIN. Adding concept_name as a denormalized column
-- provides faster reads and simpler queries.
--
-- This is nullable because:
-- 1. Standard mode questions don't have concepts (concept_id = NULL)
-- 2. Existing questions won't have this data populated
-- ============================================================================

-- Add concept_name column to questions table
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'questions' 
        AND column_name = 'concept_name'
    ) THEN
        ALTER TABLE public.questions ADD COLUMN concept_name TEXT;
        COMMENT ON COLUMN public.questions.concept_name IS 'Denormalized concept name for display (from concepts.name)';
    END IF;
END $$;

-- Optional: Backfill existing questions with concept_name from concepts table
-- Only run this if you want to populate existing data
-- UPDATE public.questions q
-- SET concept_name = c.name
-- FROM public.concepts c
-- WHERE q.concept_id = c.id
-- AND q.concept_name IS NULL;
