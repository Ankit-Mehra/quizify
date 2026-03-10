-- Migration: 040_add_flashcard_enhanced_fields.sql
-- Description: Add enhanced mode fields to flashcards table for RAG-based generation
-- Date: 2024-12-25
-- 
-- This migration adds support for enhanced flashcard generation with:
-- - concept_name: The concept this card tests (from concept extraction)
-- - bloom_level: Bloom's taxonomy level (remember, understand, apply, analyze)
-- - difficulty_score: Difficulty score from 0.0 to 1.0
-- - source_chunk_id: Reference to RAG chunk for traceability
-- - generation_mode: Whether card was generated with standard or enhanced mode

-- =============================================================================
-- PART 1: Add enhanced fields to flashcards table
-- =============================================================================

-- Add concept name field
ALTER TABLE public.flashcards
ADD COLUMN IF NOT EXISTS concept_name TEXT;

COMMENT ON COLUMN public.flashcards.concept_name IS 'Concept this card tests (enhanced mode only)';

-- Add Bloom's taxonomy level
ALTER TABLE public.flashcards
ADD COLUMN IF NOT EXISTS bloom_level TEXT CHECK (
    bloom_level IS NULL OR 
    bloom_level IN ('remember', 'understand', 'apply', 'analyze', 'evaluate', 'create')
);

COMMENT ON COLUMN public.flashcards.bloom_level IS 'Bloom taxonomy level: remember, understand, apply, analyze (enhanced mode only)';

-- Add difficulty score (0.0 to 1.0)
ALTER TABLE public.flashcards
ADD COLUMN IF NOT EXISTS difficulty_score DECIMAL(3,2) CHECK (
    difficulty_score IS NULL OR 
    (difficulty_score >= 0.0 AND difficulty_score <= 1.0)
);

COMMENT ON COLUMN public.flashcards.difficulty_score IS 'Difficulty score 0.0-1.0 (enhanced mode only)';

-- Add source chunk reference for RAG traceability
ALTER TABLE public.flashcards
ADD COLUMN IF NOT EXISTS source_chunk_id UUID;

COMMENT ON COLUMN public.flashcards.source_chunk_id IS 'Reference to RAG chunk used for generation (enhanced mode only)';

-- =============================================================================
-- PART 2: Add generation_mode to flashcard_decks for tracking
-- =============================================================================

ALTER TABLE public.flashcard_decks
ADD COLUMN IF NOT EXISTS generation_mode TEXT DEFAULT 'standard' CHECK (
    generation_mode IN ('standard', 'enhanced')
);

COMMENT ON COLUMN public.flashcard_decks.generation_mode IS 'Mode used for deck generation: standard (1 credit) or enhanced (2 credits)';

-- =============================================================================
-- PART 3: Add indexes for enhanced fields
-- =============================================================================

-- Index for filtering by concept
CREATE INDEX IF NOT EXISTS idx_flashcards_concept_name 
ON public.flashcards(concept_name) 
WHERE concept_name IS NOT NULL;

-- Index for filtering by Bloom level
CREATE INDEX IF NOT EXISTS idx_flashcards_bloom_level 
ON public.flashcards(bloom_level) 
WHERE bloom_level IS NOT NULL;

-- Index for filtering by difficulty
CREATE INDEX IF NOT EXISTS idx_flashcards_difficulty 
ON public.flashcards(difficulty_score) 
WHERE difficulty_score IS NOT NULL;

-- =============================================================================
-- Done!
-- =============================================================================
