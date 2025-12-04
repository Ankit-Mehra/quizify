-- Migration: 027_add_generation_mode_to_quizzes.sql
-- Purpose: Track whether quiz was generated using standard or enhanced (RAG) mode
-- Date: 2025-12-04
--
-- This allows frontend to:
-- 1. Display appropriate UI for enhanced quiz features (bloom_level, difficulty, concepts)
-- 2. Show "Enhanced" or "Standard" badge on quizzes
-- 3. Filter quizzes by generation mode
-- ============================================================================

-- Add generation_mode column to quizzes table
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'quizzes' 
        AND column_name = 'generation_mode'
    ) THEN
        ALTER TABLE public.quizzes 
        ADD COLUMN generation_mode TEXT 
        DEFAULT 'standard' 
        CHECK (generation_mode IN ('standard', 'enhanced'));
        
        COMMENT ON COLUMN public.quizzes.generation_mode IS 
            'Quiz generation mode: standard (fast) or enhanced (RAG with Bloom taxonomy)';
    END IF;
END $$;

-- Optional: Backfill existing quizzes
-- Quizzes with questions that have concept_id or bloom_level are likely enhanced mode
-- UPDATE public.quizzes q
-- SET generation_mode = 'enhanced'
-- WHERE EXISTS (
--     SELECT 1 FROM public.questions qq 
--     WHERE qq.quiz_id = q.id 
--     AND (qq.concept_id IS NOT NULL OR qq.bloom_level IS NOT NULL)
-- )
-- AND q.generation_mode IS NULL;
