-- Migration: 039_add_flashcard_support.sql
-- Description: Add support for flashcard decks and cards
-- Date: 2025-12-22
--
-- This migration creates the database schema for flashcards following
-- the implementation plan:
-- - decks table: Contains flashcard decks (similar to quizzes)
-- - flashcards table: Contains individual flashcard cards
-- - RLS policies for user data isolation
--
-- We chose to create separate tables (Option B from the plan) because:
-- 1. Flashcards have different fields than quiz questions
-- 2. Spaced repetition requires card-specific tracking
-- 3. Cleaner separation of concerns for future features

-- =============================================================================
-- PART 1: Create flashcard_decks table
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.flashcard_decks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_by UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    
    -- Content source tracking (same pattern as quizzes)
    content_source_type TEXT CHECK (content_source_type IN ('text', 'file', 'url')),
    content_source_reference TEXT,
    
    -- Statistics
    card_count INTEGER DEFAULT 0,
    
    -- Study tracking
    last_studied TIMESTAMPTZ,
    total_study_sessions INTEGER DEFAULT 0,
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add index for user lookups
CREATE INDEX IF NOT EXISTS idx_flashcard_decks_created_by ON public.flashcard_decks(created_by);
CREATE INDEX IF NOT EXISTS idx_flashcard_decks_created_at ON public.flashcard_decks(created_at DESC);

-- Add comment
COMMENT ON TABLE public.flashcard_decks IS 'Flashcard decks created by users for studying';

-- =============================================================================
-- PART 2: Create flashcards table
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.flashcards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deck_id UUID NOT NULL REFERENCES public.flashcard_decks(id) ON DELETE CASCADE,
    
    -- Card content
    front TEXT NOT NULL,
    back TEXT NOT NULL,
    hint TEXT,
    
    -- Position in deck
    position INTEGER DEFAULT 0,
    
    -- Spaced Repetition fields (for future Leitner/SM2 implementation)
    status TEXT DEFAULT 'new' CHECK (status IN ('new', 'learning', 'review', 'mastered')),
    ease_factor DECIMAL(3,2) DEFAULT 2.50,  -- SM2 ease factor (typically 1.3 to 2.5+)
    interval_days INTEGER DEFAULT 0,         -- Days until next review
    repetitions INTEGER DEFAULT 0,           -- Successful repetitions in a row
    next_review TIMESTAMPTZ,                 -- Next scheduled review date
    last_reviewed TIMESTAMPTZ,               -- Last time card was studied
    
    -- Statistics
    times_correct INTEGER DEFAULT 0,
    times_incorrect INTEGER DEFAULT 0,
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add indexes
CREATE INDEX IF NOT EXISTS idx_flashcards_deck_id ON public.flashcards(deck_id);
CREATE INDEX IF NOT EXISTS idx_flashcards_status ON public.flashcards(status);
CREATE INDEX IF NOT EXISTS idx_flashcards_next_review ON public.flashcards(next_review) WHERE next_review IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_flashcards_position ON public.flashcards(deck_id, position);

-- Add comment
COMMENT ON TABLE public.flashcards IS 'Individual flashcards within decks';

-- =============================================================================
-- PART 3: Create study_sessions table (for tracking study progress)
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.flashcard_study_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deck_id UUID NOT NULL REFERENCES public.flashcard_decks(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    
    -- Session statistics
    cards_studied INTEGER DEFAULT 0,
    cards_correct INTEGER DEFAULT 0,
    cards_incorrect INTEGER DEFAULT 0,
    time_spent_seconds INTEGER DEFAULT 0,
    
    -- Session metadata
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    is_completed BOOLEAN DEFAULT FALSE
);

-- Add indexes
CREATE INDEX IF NOT EXISTS idx_study_sessions_user ON public.flashcard_study_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_study_sessions_deck ON public.flashcard_study_sessions(deck_id);
CREATE INDEX IF NOT EXISTS idx_study_sessions_started ON public.flashcard_study_sessions(started_at DESC);

-- Add comment
COMMENT ON TABLE public.flashcard_study_sessions IS 'Tracks individual study sessions for flashcard decks';

-- =============================================================================
-- PART 4: RLS Policies
-- =============================================================================

-- Enable RLS
ALTER TABLE public.flashcard_decks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.flashcards ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.flashcard_study_sessions ENABLE ROW LEVEL SECURITY;

-- Flashcard Decks Policies
-- Users can view their own decks
CREATE POLICY "Users can view own decks" ON public.flashcard_decks
    FOR SELECT USING (auth.uid() = created_by);

-- Users can insert their own decks
CREATE POLICY "Users can create decks" ON public.flashcard_decks
    FOR INSERT WITH CHECK (auth.uid() = created_by);

-- Users can update their own decks
CREATE POLICY "Users can update own decks" ON public.flashcard_decks
    FOR UPDATE USING (auth.uid() = created_by);

-- Users can delete their own decks
CREATE POLICY "Users can delete own decks" ON public.flashcard_decks
    FOR DELETE USING (auth.uid() = created_by);

-- Flashcards Policies (access through deck ownership)
-- Users can view cards in their own decks
CREATE POLICY "Users can view cards in own decks" ON public.flashcards
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM public.flashcard_decks d 
            WHERE d.id = flashcards.deck_id 
            AND d.created_by = auth.uid()
        )
    );

-- Users can insert cards into their own decks
CREATE POLICY "Users can create cards in own decks" ON public.flashcards
    FOR INSERT WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.flashcard_decks d 
            WHERE d.id = flashcards.deck_id 
            AND d.created_by = auth.uid()
        )
    );

-- Users can update cards in their own decks
CREATE POLICY "Users can update cards in own decks" ON public.flashcards
    FOR UPDATE USING (
        EXISTS (
            SELECT 1 FROM public.flashcard_decks d 
            WHERE d.id = flashcards.deck_id 
            AND d.created_by = auth.uid()
        )
    );

-- Users can delete cards from their own decks
CREATE POLICY "Users can delete cards from own decks" ON public.flashcards
    FOR DELETE USING (
        EXISTS (
            SELECT 1 FROM public.flashcard_decks d 
            WHERE d.id = flashcards.deck_id 
            AND d.created_by = auth.uid()
        )
    );

-- Study Sessions Policies
-- Users can view their own study sessions
CREATE POLICY "Users can view own study sessions" ON public.flashcard_study_sessions
    FOR SELECT USING (auth.uid() = user_id);

-- Users can create their own study sessions
CREATE POLICY "Users can create study sessions" ON public.flashcard_study_sessions
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Users can update their own study sessions
CREATE POLICY "Users can update own study sessions" ON public.flashcard_study_sessions
    FOR UPDATE USING (auth.uid() = user_id);

-- =============================================================================
-- PART 5: Trigger to update card_count automatically
-- =============================================================================

-- Function to update deck card count
CREATE OR REPLACE FUNCTION update_deck_card_count()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE public.flashcard_decks 
        SET card_count = card_count + 1,
            updated_at = NOW()
        WHERE id = NEW.deck_id;
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE public.flashcard_decks 
        SET card_count = card_count - 1,
            updated_at = NOW()
        WHERE id = OLD.deck_id;
        RETURN OLD;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create trigger
DROP TRIGGER IF EXISTS trigger_update_deck_card_count ON public.flashcards;
CREATE TRIGGER trigger_update_deck_card_count
    AFTER INSERT OR DELETE ON public.flashcards
    FOR EACH ROW
    EXECUTE FUNCTION update_deck_card_count();

-- =============================================================================
-- PART 6: Trigger to update timestamps
-- =============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_flashcard_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create triggers for updated_at
DROP TRIGGER IF EXISTS trigger_flashcard_decks_updated ON public.flashcard_decks;
CREATE TRIGGER trigger_flashcard_decks_updated
    BEFORE UPDATE ON public.flashcard_decks
    FOR EACH ROW
    EXECUTE FUNCTION update_flashcard_timestamp();

DROP TRIGGER IF EXISTS trigger_flashcards_updated ON public.flashcards;
CREATE TRIGGER trigger_flashcards_updated
    BEFORE UPDATE ON public.flashcards
    FOR EACH ROW
    EXECUTE FUNCTION update_flashcard_timestamp();

-- =============================================================================
-- PART 7: Service role policies for backend operations
-- =============================================================================

-- Allow service role full access (for backend operations)
CREATE POLICY "Service role has full access to decks" ON public.flashcard_decks
    FOR ALL USING (auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "Service role has full access to flashcards" ON public.flashcards
    FOR ALL USING (auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "Service role has full access to study sessions" ON public.flashcard_study_sessions
    FOR ALL USING (auth.jwt() ->> 'role' = 'service_role');

-- =============================================================================
-- VERIFICATION
-- =============================================================================

-- Verify tables were created
DO $$
BEGIN
    ASSERT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'flashcard_decks'), 
        'flashcard_decks table was not created';
    ASSERT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'flashcards'), 
        'flashcards table was not created';
    ASSERT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'flashcard_study_sessions'), 
        'flashcard_study_sessions table was not created';
    
    RAISE NOTICE '✅ Migration 039: Flashcard support tables created successfully';
END $$;
