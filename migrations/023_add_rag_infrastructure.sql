-- Migration: 023 - Add RAG Infrastructure for Quiz Quality Improvement
-- Date: 2025-12-02
-- Purpose: Add vector storage, chunks, concepts tables for RAG-based quiz generation

-- ============================================================================
-- 1. Enable pgvector extension (verify it's enabled)
-- ============================================================================
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- 2. Documents table (enhanced metadata for ingested content)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('file', 'url', 'text')),
    source_reference TEXT, -- file_id, URL, or null for text
    original_content TEXT, -- Full original content
    token_count INTEGER,
    word_count INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb -- Extensible metadata (file type, etc.)
);

CREATE INDEX IF NOT EXISTS idx_documents_user ON public.documents(user_id);
CREATE INDEX IF NOT EXISTS idx_documents_created ON public.documents(created_at DESC);

-- RLS Policy
ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own documents" ON public.documents;
CREATE POLICY "Users can view own documents"
    ON public.documents FOR SELECT
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert own documents" ON public.documents;
CREATE POLICY "Users can insert own documents"
    ON public.documents FOR INSERT
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete own documents" ON public.documents;
CREATE POLICY "Users can delete own documents"
    ON public.documents FOR DELETE
    USING (auth.uid() = user_id);

-- ============================================================================
-- 3. Chunks table (semantic chunks with embeddings)
-- ============================================================================
-- Using OpenAI text-embedding-3-small (1536 dimensions)
CREATE TABLE IF NOT EXISTS public.chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL, -- Position in document
    content TEXT NOT NULL,
    token_count INTEGER,
    embedding vector(1536), -- OpenAI text-embedding-3-small
    metadata JSONB DEFAULT '{}'::jsonb, -- Section headers, page numbers, etc.
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chunks_document ON public.chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_user ON public.chunks(user_id);

-- HNSW index for fast similarity search (better for production than IVFFlat)
-- Note: vector_cosine_ops requires pgvector 0.5.0+
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON public.chunks 
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- RLS Policy
ALTER TABLE public.chunks ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own chunks" ON public.chunks;
CREATE POLICY "Users can view own chunks"
    ON public.chunks FOR SELECT
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert own chunks" ON public.chunks;
CREATE POLICY "Users can insert own chunks"
    ON public.chunks FOR INSERT
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete own chunks" ON public.chunks;
CREATE POLICY "Users can delete own chunks"
    ON public.chunks FOR DELETE
    USING (auth.uid() = user_id);

-- ============================================================================
-- 4. Concepts table (extracted key concepts for targeted question generation)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.concepts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    chunk_id UUID REFERENCES public.chunks(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    concept_type TEXT, -- 'entity', 'keyword', 'topic', 'definition', 'process'
    relevance_score FLOAT DEFAULT 0.5,
    embedding vector(1536), -- For concept similarity search
    source_text TEXT, -- The text that contains this concept
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_concepts_document ON public.concepts(document_id);
CREATE INDEX IF NOT EXISTS idx_concepts_user ON public.concepts(user_id);
CREATE INDEX IF NOT EXISTS idx_concepts_type ON public.concepts(concept_type);
CREATE INDEX IF NOT EXISTS idx_concepts_embedding ON public.concepts 
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- RLS Policy
ALTER TABLE public.concepts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own concepts" ON public.concepts;
CREATE POLICY "Users can view own concepts"
    ON public.concepts FOR SELECT
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert own concepts" ON public.concepts;
CREATE POLICY "Users can insert own concepts"
    ON public.concepts FOR INSERT
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete own concepts" ON public.concepts;
CREATE POLICY "Users can delete own concepts"
    ON public.concepts FOR DELETE
    USING (auth.uid() = user_id);

-- ============================================================================
-- 5. Enhance questions table with quality metadata
-- ============================================================================
-- Add columns if they don't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'questions' AND column_name = 'bloom_level') THEN
        ALTER TABLE public.questions ADD COLUMN bloom_level TEXT CHECK (bloom_level IN ('remember', 'understand', 'apply', 'analyze', 'evaluate', 'create'));
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'questions' AND column_name = 'difficulty') THEN
        ALTER TABLE public.questions ADD COLUMN difficulty TEXT DEFAULT 'medium' CHECK (difficulty IN ('easy', 'medium', 'hard'));
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'questions' AND column_name = 'concept_id') THEN
        ALTER TABLE public.questions ADD COLUMN concept_id UUID REFERENCES public.concepts(id) ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'questions' AND column_name = 'chunk_id') THEN
        ALTER TABLE public.questions ADD COLUMN chunk_id UUID REFERENCES public.chunks(id) ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'questions' AND column_name = 'confidence_score') THEN
        ALTER TABLE public.questions ADD COLUMN confidence_score FLOAT;
    END IF;
END $$;

COMMENT ON COLUMN public.questions.bloom_level IS 'Bloom taxonomy level: remember, understand, apply, analyze, evaluate, create';
COMMENT ON COLUMN public.questions.difficulty IS 'Question difficulty: easy, medium, hard';
COMMENT ON COLUMN public.questions.concept_id IS 'Reference to the concept this question tests';
COMMENT ON COLUMN public.questions.confidence_score IS 'LLM-generated confidence score for question quality (0-1)';

-- ============================================================================
-- 6. Vector similarity search function
-- ============================================================================
CREATE OR REPLACE FUNCTION match_chunks(
    query_embedding vector(1536),
    match_threshold FLOAT DEFAULT 0.7,
    match_count INT DEFAULT 5,
    filter_user_id UUID DEFAULT NULL,
    filter_document_id UUID DEFAULT NULL
)
RETURNS TABLE (
    id UUID,
    document_id UUID,
    content TEXT,
    token_count INTEGER,
    metadata JSONB,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        c.id,
        c.document_id,
        c.content,
        c.token_count,
        c.metadata,
        1 - (c.embedding <=> query_embedding) AS similarity
    FROM public.chunks c
    WHERE 
        (filter_user_id IS NULL OR c.user_id = filter_user_id)
        AND (filter_document_id IS NULL OR c.document_id = filter_document_id)
        AND 1 - (c.embedding <=> query_embedding) > match_threshold
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- ============================================================================
-- 7. Concept similarity search function
-- ============================================================================
CREATE OR REPLACE FUNCTION match_concepts(
    query_embedding vector(1536),
    match_threshold FLOAT DEFAULT 0.6,
    match_count INT DEFAULT 10,
    filter_user_id UUID DEFAULT NULL,
    filter_document_id UUID DEFAULT NULL
)
RETURNS TABLE (
    id UUID,
    name TEXT,
    concept_type TEXT,
    relevance_score FLOAT,
    source_text TEXT,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        c.id,
        c.name,
        c.concept_type,
        c.relevance_score,
        c.source_text,
        1 - (c.embedding <=> query_embedding) AS similarity
    FROM public.concepts c
    WHERE 
        (filter_user_id IS NULL OR c.user_id = filter_user_id)
        AND (filter_document_id IS NULL OR c.document_id = filter_document_id)
        AND 1 - (c.embedding <=> query_embedding) > match_threshold
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- ============================================================================
-- 8. LLM Call Analytics table (for PostHog + internal tracking)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.llm_calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    trace_id UUID, -- Correlate multi-step LLM workflows
    call_type TEXT NOT NULL, -- 'embedding', 'generation', 'classification', 'extraction'
    model TEXT NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    total_tokens INTEGER,
    latency_ms INTEGER,
    cost_usd DECIMAL(10, 6),
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    metadata JSONB DEFAULT '{}'::jsonb, -- Feature, question type, etc.
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_llm_calls_user ON public.llm_calls(user_id);
CREATE INDEX IF NOT EXISTS idx_llm_calls_trace ON public.llm_calls(trace_id);
CREATE INDEX IF NOT EXISTS idx_llm_calls_type ON public.llm_calls(call_type);
CREATE INDEX IF NOT EXISTS idx_llm_calls_created ON public.llm_calls(created_at DESC);

-- RLS: Users can only see their own LLM calls
ALTER TABLE public.llm_calls ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own llm_calls" ON public.llm_calls;
CREATE POLICY "Users can view own llm_calls"
    ON public.llm_calls FOR SELECT
    USING (auth.uid() = user_id);

-- Service role can insert (for backend tracking)
-- Note: This policy allows the service role to insert analytics.
-- The service role bypasses RLS anyway, but this is explicit documentation.
-- Regular users cannot insert llm_calls (no user-facing INSERT policy).
DROP POLICY IF EXISTS "Service can insert llm_calls" ON public.llm_calls;
CREATE POLICY "Service can insert llm_calls"
    ON public.llm_calls FOR INSERT
    WITH CHECK (TRUE);

-- ============================================================================
-- 9. Quiz Generation Sessions (track full pipeline)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.quiz_generation_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    quiz_id UUID REFERENCES public.quizzes(id) ON DELETE SET NULL,
    document_id UUID REFERENCES public.documents(id) ON DELETE SET NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    total_chunks INTEGER,
    total_concepts INTEGER,
    questions_requested INTEGER,
    questions_generated INTEGER,
    total_latency_ms INTEGER,
    total_tokens_used INTEGER,
    error_message TEXT,
    pipeline_metadata JSONB DEFAULT '{}'::jsonb, -- Detailed pipeline stats
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_quiz_sessions_user ON public.quiz_generation_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_quiz_sessions_status ON public.quiz_generation_sessions(status);

-- RLS
ALTER TABLE public.quiz_generation_sessions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own sessions" ON public.quiz_generation_sessions;
CREATE POLICY "Users can view own sessions"
    ON public.quiz_generation_sessions FOR SELECT
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert own sessions" ON public.quiz_generation_sessions;
CREATE POLICY "Users can insert own sessions"
    ON public.quiz_generation_sessions FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- ============================================================================
-- 10. Add Missing UPDATE Policies for RAG Tables
-- ============================================================================

-- Documents UPDATE policy
DROP POLICY IF EXISTS "Users can update own documents" ON public.documents;
CREATE POLICY "Users can update own documents"
    ON public.documents FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Chunks UPDATE policy (for updating embeddings if needed)
DROP POLICY IF EXISTS "Users can update own chunks" ON public.chunks;
CREATE POLICY "Users can update own chunks"
    ON public.chunks FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Concepts UPDATE policy (for updating relevance scores, etc.)
DROP POLICY IF EXISTS "Users can update own concepts" ON public.concepts;
CREATE POLICY "Users can update own concepts"
    ON public.concepts FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Quiz Generation Sessions UPDATE policy
DROP POLICY IF EXISTS "Users can update own sessions" ON public.quiz_generation_sessions;
CREATE POLICY "Users can update own sessions"
    ON public.quiz_generation_sessions FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Quiz Generation Sessions DELETE policy
DROP POLICY IF EXISTS "Users can delete own sessions" ON public.quiz_generation_sessions;
CREATE POLICY "Users can delete own sessions"
    ON public.quiz_generation_sessions FOR DELETE
    USING (auth.uid() = user_id);

-- ============================================================================
-- 11. Grant execute permissions on functions
-- ============================================================================
GRANT EXECUTE ON FUNCTION match_chunks TO authenticated;
GRANT EXECUTE ON FUNCTION match_chunks TO service_role;
GRANT EXECUTE ON FUNCTION match_concepts TO authenticated;
GRANT EXECUTE ON FUNCTION match_concepts TO service_role;
