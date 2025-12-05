# Quiz Quality Improvement Implementation Plan

## Executive Summary

This document outlines a comprehensive plan to upgrade Quizify's quiz generation system from the current basic prompting approach to a sophisticated RAG-based (Retrieval Augmented Generation) pipeline using **LlamaIndex**, **Supabase pgvector**, and enhanced **OpenAI GPT-4** orchestration. The goal is to produce higher-quality, contextually accurate quiz questions with proper concept extraction, Bloom's taxonomy classification, and difficulty leveling.

---

## Current State Analysis

### Existing Architecture

| Component | Current Implementation | Limitations |
|-----------|----------------------|-------------|
| **Text Chunking** | `tiktoken`-based token splitting (`chunking_service.py`) | No semantic awareness, chunks may break mid-concept |
| **Quiz Generation** | Direct GPT-4o/GPT-4o-mini prompting | No RAG, no concept-aware generation, no fact verification |
| **Question Types** | MCQ, True/False, Fill-blank, Matching | No Bloom's taxonomy, no difficulty classification |
| **LLM Analytics** | PostHog integration via wrapper | ✅ Already integrated - must preserve |
| **Database** | Supabase (PostgreSQL) | No vector storage, no embeddings |
| **Content Sources** | Text, PDF, DOCX, URL scraping | Content stored but not chunked/indexed |

### Current Code Flow
```
User Input → File/Text Extraction → Token Chunking → GPT-4 Prompt → JSON Parse → Save to DB
```

### ⚠️ Known Issues in Current Implementation

#### Issue 1: Ambiguous Prompt Causing Over-Generation (HIGH PRIORITY)

**Location**: `services/ai_services/prompts.py` - `build_quiz_prompt_mixed()`

**Problem**: The current prompt wording is ambiguous:
```python
f"Generate exactly {num_questions} questions of the following types: {type_str}."
# Where type_str = "multiple_choice, true_false, fill_blank, matching"
```

The LLM interprets this as "generate {num_questions} of EACH type" instead of "{num_questions} total".

**Impact**:
- For a 10-question quiz with "mixed" types, the LLM generates **40 questions** (10 × 4 types)
- Code then truncates: `return filtered[:total_questions]` - discarding 75% of output
- **Wasting ~75% of LLM costs** ($0.0086 per quiz instead of ~$0.002)

**Resolution**: Fixed by new concept-based pipeline (1 question per concept, explicit type assignment)

#### Issue 2: Inefficient Chunking Strategy

**Location**: `services/ai_services/chunking_service.py`

**Problem**: Current system creates one chunk per question, resulting in 10 LLM calls for a 10-question quiz.

**Impact**: High latency (~8-12s) and cost due to multiple API calls.

**Fix**: Will be addressed in Epic 3 (Semantic Chunking with LlamaIndex)

### Key Files to Modify
- `services/ai_services/chunking_service.py` - Replace with LlamaIndex ingestion
- `services/ai_services/openai_service.py` - Add LLM orchestration layer
- `services/ai_services/prompts.py` - Enhance with Bloom's taxonomy
- `services/ai_services/prompt_smart.py` - Add concept-aware prompts
- `handlers/quiz_handlers.py` - Integrate new pipeline
- `schemas/quiz.py` - Add difficulty, Bloom level fields

---

## Known Issues in Current Implementation

> These issues are **resolved by the new RAG pipeline** - no separate fixes needed.

### Issue 1: Per-Chunk Question Type Bug (75% Cost Waste)

**File**: `services/ai_services/prompts.py`

**Problem**:
```python
# Current prompt (sent to LLM for EACH chunk):
"Generate exactly 1 questions of the following types: multiple_choice, true_false, fill_blank, matching."

# What LLM does: Generates 1 question of EACH type = 4 questions per chunk
# What we wanted: Generate 1 question total from ANY of those types

# For 10-question quiz:
# - Creates 10 chunks (one per question requested)
# - Each chunk generates 4 questions (1 per type)
# - Total: 40 questions generated, truncated to 10
# - Result: 75% of LLM output wasted!
```

**Resolution**: New pipeline generates 1 question per concept with explicit type assignment.

### Issue 2: No Semantic Awareness in Chunking

**File**: `services/ai_services/chunking_service.py`

**Problem**: Token-based chunking splits text at arbitrary boundaries, potentially breaking mid-sentence or mid-concept.

**Resolution**: New pipeline uses LlamaIndex `SentenceSplitter` for semantic-aware chunking.

---

## Question Distribution Strategy (New Pipeline)

> The new concept-based pipeline inherently fixes the above issues by generating exactly 1 question per concept.

### Old vs New Approach

| Aspect | Old (Current) | New (RAG Pipeline) |
|--------|---------------|-------------------|
| Unit of generation | Chunk | Concept |
| Questions per unit | 1 (but buggy: generates 4) | 1 |
| Type assignment | All 4 types per chunk | 1 type per concept |
| LLM calls | 10 calls for 10 questions | 10 calls for 10 questions |
| Waste | 75% (40 generated, 10 used) | 0% (10 generated, 10 used) |
| Cost per 10-question quiz | ~$0.0086 | ~$0.0055 |

### Frontend Question Type Options

Users can select from these options in the frontend:

| User Selection | Backend Receives | Example |
|----------------|------------------|---------|
| "Mixed" | `"mixed"` | All 4 types, LLM chooses |
| Single type | `"multiple_choice"` | All questions are MCQ |
| Multiple types | `["multiple_choice", "true_false"]` | Cycle through selected types |

**Note**: Frontend does NOT support exact count distribution (e.g., "4 MCQ, 3 T/F"). 
Types are distributed evenly across concepts using round-robin.

### New Pipeline Question Distribution

```
┌─────────────────────────────────────────────────────────────┐
│              CONCEPT-BASED GENERATION                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  INPUT:                                                      │
│     - num_questions: 10                                      │
│     - question_types: "mixed" | "multiple_choice" |          │
│                       ["mcq", "tf"] | ["mcq", "tf", "fb"]    │
│                                                              │
│  STEP 1: Ingest & Chunk Document                            │
│     - Semantic chunking (~500 tokens each)                  │
│     - Store with embeddings                                  │
│                                                              │
│  STEP 2: Extract Concepts                                   │
│     - LLM extracts 3-8 concepts per chunk                   │
│     - Rank by relevance                                      │
│     - Select top N concepts (where N ≥ num_questions)       │
│                                                              │
│  STEP 3: Assign Question Types                              │
│                                                              │
│     IF question_types == "mixed":                           │
│         → LLM chooses best type per concept                 │
│         → Natural fit: definitions→MCQ, terms→fill_blank    │
│                                                              │
│     ELIF question_types == "multiple_choice" (single type): │
│         → All 10 questions are that type                    │
│                                                              │
│     ELIF question_types == ["mcq", "tf"] (multiple types):  │
│         → Round-robin: concept1→mcq, concept2→tf,           │
│           concept3→mcq, concept4→tf, ...                    │
│         → Even distribution across selected types           │
│                                                              │
│  STEP 4: Generate Questions                                 │
│     - 1 question per selected concept                       │
│     - Use chunk context (standard mode)                     │
│     - Or chunk + related (enhanced mode for compare)        │
│                                                              │
│  RESULT: 10 concepts → 10 questions (no waste!)             │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Type Assignment Implementation

```python
from typing import List, Union

def assign_question_types(
    concepts: List[dict],
    question_types: Union[str, List[str]]
) -> List[tuple]:
    """
    Assign question types to concepts based on user selection.
    
    Args:
        concepts: List of extracted concepts
        question_types: 
            - "mixed": LLM chooses best type (return None, let LLM decide)
            - "multiple_choice": Single type - all questions same type
            - ["multiple_choice", "true_false"]: Multiple types - round-robin
    
    Returns:
        List of (concept, question_type) tuples
    """
    # Option 1: Mixed - let LLM choose per concept
    if question_types == "mixed":
        return [(c, None) for c in concepts]  # None = LLM decides
    
    # Option 2: Single type - all questions same type
    if isinstance(question_types, str):
        return [(c, question_types) for c in concepts]
    
    # Option 3: List of types - round-robin distribution
    if isinstance(question_types, list):
        return [(c, question_types[i % len(question_types)]) 
                for i, c in enumerate(concepts)]
    
    raise ValueError(f"Invalid question_types: {question_types}")
```

### Distribution Examples

**Example 1: Mixed (10 questions)**
```
User selects: "Mixed"
Result: LLM picks best type per concept
  - concept1 (definition) → multiple_choice
  - concept2 (term) → fill_blank
  - concept3 (fact) → true_false
  - ... (LLM decides based on concept nature)
```

**Example 2: Single Type (10 questions)**
```
User selects: "Multiple Choice"
Result: All 10 questions are MCQ
  - concept1 → multiple_choice
  - concept2 → multiple_choice
  - ... (all same type)
```

**Example 3: Two Types (10 questions)**
```
User selects: ["Multiple Choice", "True/False"]
Result: Round-robin (5 MCQ, 5 T/F)
  - concept1 → multiple_choice
  - concept2 → true_false
  - concept3 → multiple_choice
  - concept4 → true_false
  - ... (alternating)
```

**Example 4: Three Types (10 questions)**
```
User selects: ["MCQ", "T/F", "Fill Blank"]
Result: Round-robin (4 MCQ, 3 T/F, 3 FB)
  - concept1 → multiple_choice
  - concept2 → true_false
  - concept3 → fill_blank
  - concept4 → multiple_choice
  - ... (cycling through types)
```

---

## Epic 1: Database Schema Evolution

### 1.1 Enable pgvector Extension ✅
**Status**: Already enabled per user confirmation


### 1.2 Create New Tables for RAG Pipeline

#### Migration: `023_add_rag_infrastructure.sql`

```sql
-- Migration: 023 - Add RAG Infrastructure for Quiz Quality Improvement
-- Date: 2025-12-XX
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

CREATE INDEX idx_documents_user ON public.documents(user_id);
CREATE INDEX idx_documents_created ON public.documents(created_at DESC);

-- RLS Policy
ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own documents"
    ON public.documents FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own documents"
    ON public.documents FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete own documents"
    ON public.documents FOR DELETE
    USING (auth.uid() = user_id);

-- ============================================================================
-- 3. Chunks table (semantic chunks with embeddings)
-- ============================================================================
-- Using OpenAI text-embedding-3-small (1536 dimensions) or text-embedding-3-large (3072)
-- We'll use 1536 dimensions for cost efficiency
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

CREATE INDEX idx_chunks_document ON public.chunks(document_id);
CREATE INDEX idx_chunks_user ON public.chunks(user_id);

-- HNSW index for fast similarity search (better for production than IVFFlat)
CREATE INDEX idx_chunks_embedding ON public.chunks 
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- RLS Policy
ALTER TABLE public.chunks ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own chunks"
    ON public.chunks FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own chunks"
    ON public.chunks FOR INSERT
    WITH CHECK (auth.uid() = user_id);

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

CREATE INDEX idx_concepts_document ON public.concepts(document_id);
CREATE INDEX idx_concepts_user ON public.concepts(user_id);
CREATE INDEX idx_concepts_type ON public.concepts(concept_type);
CREATE INDEX idx_concepts_embedding ON public.concepts 
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- RLS Policy
ALTER TABLE public.concepts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own concepts"
    ON public.concepts FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own concepts"
    ON public.concepts FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete own concepts"
    ON public.concepts FOR DELETE
    USING (auth.uid() = user_id);

-- ============================================================================
-- 5. Enhance questions table with quality metadata
-- ============================================================================
ALTER TABLE public.questions 
ADD COLUMN IF NOT EXISTS bloom_level TEXT 
    CHECK (bloom_level IN ('remember', 'understand', 'apply', 'analyze', 'evaluate', 'create'));

ALTER TABLE public.questions 
ADD COLUMN IF NOT EXISTS difficulty TEXT DEFAULT 'medium'
    CHECK (difficulty IN ('easy', 'medium', 'hard'));

ALTER TABLE public.questions 
ADD COLUMN IF NOT EXISTS concept_id UUID REFERENCES public.concepts(id) ON DELETE SET NULL;

ALTER TABLE public.questions 
ADD COLUMN IF NOT EXISTS chunk_id UUID REFERENCES public.chunks(id) ON DELETE SET NULL;

ALTER TABLE public.questions 
ADD COLUMN IF NOT EXISTS confidence_score FLOAT; -- LLM confidence in question quality

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

CREATE INDEX idx_llm_calls_user ON public.llm_calls(user_id);
CREATE INDEX idx_llm_calls_trace ON public.llm_calls(trace_id);
CREATE INDEX idx_llm_calls_type ON public.llm_calls(call_type);
CREATE INDEX idx_llm_calls_created ON public.llm_calls(created_at DESC);

-- RLS: Users can only see their own LLM calls
ALTER TABLE public.llm_calls ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own llm_calls"
    ON public.llm_calls FOR SELECT
    USING (auth.uid() = user_id);

-- Service role can insert (for backend tracking)
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

CREATE INDEX idx_quiz_sessions_user ON public.quiz_generation_sessions(user_id);
CREATE INDEX idx_quiz_sessions_status ON public.quiz_generation_sessions(status);

-- RLS
ALTER TABLE public.quiz_generation_sessions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own sessions"
    ON public.quiz_generation_sessions FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own sessions"
    ON public.quiz_generation_sessions FOR INSERT
    WITH CHECK (auth.uid() = user_id);
```

### 1.3 Schema Changes Summary

| Table | Status | Purpose |
|-------|--------|---------|
| `documents` | NEW | Store ingested document metadata |
| `chunks` | NEW | Store semantic chunks with embeddings |
| `concepts` | NEW | Store extracted concepts for targeted questions |
| `questions` | MODIFY | Add bloom_level, difficulty, concept_id, chunk_id |
| `llm_calls` | NEW | Internal LLM analytics (complements PostHog) |
| `quiz_generation_sessions` | NEW | Track full pipeline execution |

---

## Epic 2: New Dependencies

### 2.1 Add to `requirements.txt`

```txt
# LlamaIndex Core
llama-index-core>=0.11.0
llama-index-llms-openai>=0.2.0
llama-index-embeddings-openai>=0.2.0

# Async Database Support
asyncpg>=0.29.0  # For direct Supabase connection
```

### 2.2 Removed Dependencies (Memory Optimization)

The following dependencies were **intentionally excluded** to minimize memory footprint on Railway single-instance deployment:

```txt
# ❌ REMOVED - Too memory heavy (~250MB combined)
# spacy>=3.7.0           # +50-70MB RAM when loaded
# keybert>=0.8.0         # Requires sentence-transformers
# sentence-transformers>=2.2.0  # +200MB RAM
```

**Rationale**: See `docs/QUALITY_IMPROVEMENT_COST_LATENCY_ANALYSIS.md` for full analysis.

**Alternative**: Concept extraction is performed using GPT-4o-mini, which:
- Adds 0 memory overhead
- Provides better context-aware extraction than rule-based NER
- Costs ~$0.00075 per document (negligible)
- Adds ~2s latency (acceptable for quality improvement)

---

## Epic 3: Ingestion & Preprocessing Module

### 3.1 New Service: `services/ai_services/ingestion_service.py`

**Responsibilities:**
- Accept text, PDF, URL content
- Clean and preprocess text
- Chunk using LlamaIndex's `SentenceSplitter` (semantic-aware)
- Generate embeddings via OpenAI `text-embedding-3-small`
- Store chunks in Supabase `chunks` table

**Key Features:**
- Semantic chunking (respects sentence boundaries)
- Overlap between chunks for context continuity
- Metadata attachment (source, page number, section)
- Batch embedding generation for efficiency
- PostHog analytics integration for embedding calls

### 3.2 Architecture

```python
# services/ai_services/ingestion_service.py

from llama_index.core import Document, Settings
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.openai import OpenAIEmbedding
from services.posthog_service import is_posthog_wrapper_active, get_posthog_client

class IngestionService:
    def __init__(self):
        self.embed_model = OpenAIEmbedding(
            model="text-embedding-3-small",
            dimensions=1536
        )
        self.splitter = SentenceSplitter(
            chunk_size=512,
            chunk_overlap=50,
            paragraph_separator="\n\n"
        )
    
    async def ingest_content(
        self,
        content: str,
        source_type: str,
        source_reference: str,
        user_id: str,
        user_token: str,
        trace_id: str = None
    ) -> dict:
        """
        Full ingestion pipeline:
        1. Create document record
        2. Chunk content semantically
        3. Generate embeddings
        4. Store chunks with embeddings
        5. Return document_id and chunk_ids
        """
        pass
```

---

## Epic 4: Concept & Topic Extraction Module (LLM-Based)

### 4.1 New Service: `services/ai_services/concept_extraction_service.py`

**Responsibilities:**
- Extract key concepts, entities, and topics from chunks using GPT-4o-mini
- Identify concept types (entity, keyword, topic, definition, process)
- Rank concepts by relevance and frequency
- Store in `concepts` table with embeddings

**Key Features:**
- **LLM-based extraction** (replaces spaCy + KeyBERT for 0 memory overhead)
- Context-aware concept identification
- Concept deduplication across chunks
- Relevance scoring based on frequency and position
- PostHog analytics for extraction LLM calls

### 4.2 Architecture

```python
# services/ai_services/concept_extraction_service.py

from typing import List, Dict, Optional
from services.ai_services.openai_service import get_openai_client, _build_posthog_kwargs
from services.logger import ai_logger as logger

CONCEPT_EXTRACTION_PROMPT = """
Analyze the following text and extract key concepts that would be good for quiz questions.

For each concept, identify:
1. name: The concept name (1-4 words)
2. type: One of [entity, keyword, topic, definition, process]
3. relevance: Score from 0.0 to 1.0 based on importance
4. source_text: The sentence containing this concept

Text:
\"\"\"
{chunk_text}
\"\"\"

Return JSON format:
{{
  "concepts": [
    {{"name": "...", "type": "...", "relevance": 0.8, "source_text": "..."}}
  ]
}}

Extract 3-8 high-quality concepts. Prioritize:
- Key terms and definitions
- Named entities (people, places, organizations)
- Important processes or methods
- Central themes and topics
"""

class ConceptExtractionService:
    def __init__(self):
        self.client = None  # Lazy load
    
    async def extract_concepts(
        self,
        document_id: str,
        chunks: List[Dict],
        user_id: str,
        trace_id: str = None
    ) -> List[Dict]:
        """
        Extract concepts from all chunks using GPT-4o-mini:
        1. LLM-based extraction (single call per chunk batch)
        2. Deduplicate across chunks
        3. Rank by frequency and relevance
        4. Generate embeddings for similarity search
        5. Store in concepts table
        
        Cost: ~$0.00075 per document
        Latency: ~2s
        Memory: 0 (no model loading)
        """
        pass
    
    async def _extract_from_chunk(
        self,
        chunk_text: str,
        user_id: str,
        trace_id: str
    ) -> List[Dict]:
        """Extract concepts from a single chunk using GPT-4o-mini."""
        if not self.client:
            self.client = get_openai_client()
        
        posthog_kwargs = _build_posthog_kwargs(
            user_id=user_id,
            trace_id=trace_id,
            properties={
                "feature": "concept_extraction",
                "content_length": len(chunk_text)
            }
        )
        
        response = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": CONCEPT_EXTRACTION_PROMPT.format(chunk_text=chunk_text)
            }],
            response_format={"type": "json_object"},
            **posthog_kwargs
        )
        
        # Parse and return concepts
        import json
        result = json.loads(response.choices[0].message.content)
        return result.get("concepts", [])
```

---

## Epic 5: LLM Orchestration Layer

### 5.1 Context Strategy: Two Modes

Based on analysis, we implement a **simplified two-mode** context strategy:

```
┌─────────────────────────────────────────────────────────────┐
│              CONTEXT STRATEGY: TWO MODES                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  mode: Literal["standard", "enhanced"]                      │
│                                                              │
│  STANDARD MODE (Default - 80% of questions):                │
│     └─> context = chunk.text (~500 tokens)                  │
│     └─> Retrieved via concept.chunk_id                      │
│     └─> Good for: Remember, Understand, Apply, Create       │
│     └─> Cost: ~$0.0003/question                             │
│     └─> Latency: +0ms (no similarity search)                │
│                                                              │
│  ENHANCED MODE (Compare/Contrast questions):                │
│     └─> context = chunk + related_chunks (~1500 tokens)     │
│     └─> Query with concept.embedding (already stored!)      │
│     └─> Exclude concept.chunk_id (avoid duplicate)          │
│     └─> Good for: Analyze, Evaluate (comparison questions)  │
│     └─> Cost: ~$0.0008/question                             │
│     └─> Latency: +100-200ms (similarity search)             │
│                                                              │
│  KEY INSIGHT:                                                │
│     source_text ⊂ chunk (source_text is inside chunk)       │
│     → Never use source_text + chunk (redundant!)            │
│     → chunk already provides full context around concept    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

#### When to Use Each Mode

| Question Type | Mode | Reason |
|---------------|------|--------|
| Define/recall | Standard | Chunk has enough context |
| Explain concept | Standard | Chunk has enough context |
| Apply to scenario | Standard | LLM creativity, not more data |
| **Compare X and Y** | **Enhanced** | Need chunks about both topics |
| **Relationship between A and B** | **Enhanced** | Need cross-references |
| Design/create | Standard | Creativity, not more data |

### 5.2 Enhance: `services/ai_services/openai_service.py`

**New Responsibilities:**
- Add LlamaIndex-based prompt orchestration
- Multi-step prompting (concept → question → distractors → explanation)
- **Two-mode context retrieval** (standard vs enhanced)
- Bloom's taxonomy classification
- Difficulty assessment
- **Preserve existing PostHog integration**

### 5.3 Context Retrieval Implementation

```python
# services/ai_services/context_service.py

from typing import Literal, List
from services.database_service import get_supabase

class ContextService:
    """
    Manages context retrieval for question generation.
    Two modes: standard (chunk only) and enhanced (chunk + related).
    """
    
    async def get_context_for_concept(
        self,
        concept: dict,
        mode: Literal["standard", "enhanced"] = "standard"
    ) -> str:
        """
        Get context for question generation based on mode.
        
        Standard: Just the chunk where concept was found (~500 tokens)
        Enhanced: Chunk + related chunks for cross-referencing (~1500 tokens)
        """
        supabase = get_supabase()
        
        # Always get the source chunk (contains the concept)
        chunk_result = await supabase.table("chunks") \
            .select("text") \
            .eq("id", concept["chunk_id"]) \
            .single() \
            .execute()
        
        chunk_text = chunk_result.data["text"]
        
        if mode == "standard":
            return chunk_text
        
        # Enhanced mode: find related chunks using stored embedding
        if mode == "enhanced":
            # Use the stored concept embedding (no extra API call!)
            related_result = await supabase.rpc(
                "match_chunks",
                {
                    "query_embedding": concept["embedding"],
                    "match_count": 2,
                    "match_threshold": 0.7,
                    "filter_user_id": concept["user_id"],
                    "filter_document_id": concept["document_id"]
                }
            ).execute()
            
            # Filter out the source chunk (avoid redundancy)
            related_chunks = [
                r["text"] for r in related_result.data 
                if r["id"] != concept["chunk_id"]
            ]
            
            # Combine: source chunk + related chunks
            if related_chunks:
                return f"{chunk_text}\n\n---\nRelated Context:\n" + \
                       "\n---\n".join(related_chunks)
            else:
                return chunk_text  # Fallback to standard if no related found
    
    def should_use_enhanced_mode(self, question_type: str, bloom_level: str) -> bool:
        """
        Determine if enhanced mode is beneficial for this question.
        
        Enhanced mode helps with comparison/relationship questions.
        """
        comparison_indicators = [
            "compare", "contrast", "relationship", "difference", 
            "similarity", "versus", "distinguish"
        ]
        
        # Analyze bloom level benefits most from cross-references
        if bloom_level == "analyze":
            return True
        
        # Check if question type suggests comparison
        if any(indicator in question_type.lower() for indicator in comparison_indicators):
            return True
        
        return False
```

### 5.4 Quiz Orchestration Engine

```python
# Add to openai_service.py or create orchestration_service.py

from llama_index.core import PromptTemplate
from typing import Literal

class QuizOrchestrationEngine:
    """
    LlamaIndex-based quiz generation with:
    - Two-mode context retrieval (standard/enhanced)
    - Multi-step LLM chaining
    - Bloom's taxonomy enforcement
    - PostHog analytics at each step
    """
    
    def __init__(self):
        self.context_service = ContextService()
    
    QUESTION_PROMPT = PromptTemplate(
        "Based on the following concept and supporting passage, create a {bloom_level} level "
        "{question_type} question.\n\n"
        "Concept: {concept}\n\n"
        "Supporting Text:\n{context_str}\n\n"
        "Requirements:\n"
        "- Bloom Level: {bloom_level} (questions should test {bloom_description})\n"
        "- Difficulty: {difficulty}\n"
        "- 1 correct answer + 3 plausible distractors\n"
        "- Include explanation referencing the source text"
    )
    
    async def generate_question(
        self,
        concept: dict,
        bloom_level: str,
        difficulty: str,
        question_type: str,
        user_id: str,
        trace_id: str,
        mode: Literal["standard", "enhanced"] = "standard"
    ) -> dict:
        """
        Generate a single high-quality question.
        
        Args:
            concept: Concept dict with name, chunk_id, embedding
            bloom_level: Target Bloom's taxonomy level
            difficulty: easy/medium/hard
            question_type: multiple_choice, true_false, etc.
            user_id: For PostHog tracking
            trace_id: For PostHog tracking
            mode: "standard" (chunk only) or "enhanced" (chunk + related)
        
        Returns:
            Generated question dict
        """
        # Get context based on mode
        context = await self.context_service.get_context_for_concept(
            concept=concept,
            mode=mode
        )
        
        # Generate question with context
        # ... (LLM call with PostHog tracking)
        pass

### 5.3 Bloom's Taxonomy Integration

```python
BLOOM_LEVELS = {
    "remember": "recall of facts and basic concepts",
    "understand": "explaining ideas or concepts",
    "apply": "using information in new situations",
    "analyze": "drawing connections among ideas",
    "evaluate": "justifying a decision or course of action",
    "create": "producing new or original work"
}

BLOOM_QUESTION_STARTERS = {
    "remember": ["What is...", "Define...", "List...", "Name..."],
    "understand": ["Explain...", "Describe...", "Summarize...", "Compare..."],
    "apply": ["How would you use...", "What would happen if...", "Demonstrate..."],
    "analyze": ["Why did...", "What is the relationship between...", "Differentiate..."],
    "evaluate": ["Do you agree that...", "What is the best approach to...", "Justify..."],
    "create": ["Design...", "Propose...", "What would you create to...", "Formulate..."]
}
```

---

## Epic 6: Explanation & Postprocessing Module

### 6.1 New Service: `services/ai_services/explanation_service.py`

**Responsibilities:**
- Generate detailed answer explanations
- Explain why distractors are incorrect
- Fact-check against source chunks (RAG verification)
- Filter inappropriate/low-quality questions

### 6.2 Architecture

```python
class ExplanationService:
    async def generate_explanation(
        self,
        question: dict,
        correct_answer: str,
        distractors: list,
        source_chunks: list,
        user_id: str,
        trace_id: str
    ) -> dict:
        """
        Generate comprehensive explanation:
        1. Why correct answer is right
        2. Why each distractor is wrong
        3. Reference to source text
        4. Fact verification via RAG
        """
        pass
    
    async def verify_factual_accuracy(
        self,
        question: dict,
        source_chunks: list
    ) -> tuple[bool, float]:
        """
        Verify question against source material.
        Returns (is_accurate, confidence_score)
        """
        pass
```

---

## Epic 7: Bloom & Difficulty Classification Module

### 7.1 New Service: `services/ai_services/classification_service.py`

**Responsibilities:**
- Classify generated questions by Bloom's level
- Assign difficulty (easy/medium/hard)
- Ensure balanced distribution in quiz

### 7.2 Architecture

```python
class ClassificationService:
    async def classify_question(
        self,
        question_text: str,
        options: list,
        correct_answer: str,
        user_id: str,
        trace_id: str
    ) -> dict:
        """
        Classify question:
        - bloom_level: remember|understand|apply|analyze|evaluate|create
        - difficulty: easy|medium|hard
        - confidence_score: 0-1
        """
        pass
    
    async def balance_quiz(
        self,
        questions: list,
        target_distribution: dict
    ) -> list:
        """
        Reorder/filter questions to match target Bloom/difficulty distribution.
        """
        pass
```

---

## Epic 8: Updated Quiz Generation Pipeline

### 8.1 New Handler Flow

```
User Request
    ↓
1. Ingest Content (IngestionService)
    - Create document record
    - Semantic chunking
    - Generate & store embeddings
    ↓
2. Extract Concepts (ConceptExtractionService)
    - LLM-based extraction (GPT-4o-mini)
    - Rank by relevance
    - Store with chunk_id + embeddings
    ↓
3. Select Concepts for Quiz
    - Based on num_questions
    - Ensure topic coverage
    ↓
4. For Each Concept:
    a. Determine Mode:
       - "standard" (default): Use chunk.text only
       - "enhanced": If comparison/relationship question detected
    b. Get Context (via chunk_id, optionally + related chunks)
    c. Generate Question (QuizOrchestrationEngine)
    d. Classify (Bloom + Difficulty in same call)
    e. Track LLM call (PostHog + llm_calls table)
    ↓
5. Balance Quiz
    - Ensure Bloom distribution
    - Ensure difficulty distribution
    ↓
6. Save to Database
    - questions with bloom_level, difficulty, concept_id, chunk_id
    - quiz_generation_session record
    ↓
7. Return Response
```

### 8.2 Mode Selection Logic

```python
def determine_context_mode(
    question_type: str,
    bloom_level: str = None,
    user_preference: str = None
) -> Literal["standard", "enhanced"]:
    """
    Determine whether to use standard or enhanced context mode.
    
    Standard Mode (~80% of questions):
        - Faster (no similarity search)
        - Cheaper (~$0.0003/question)
        - Uses: chunk.text only (~500 tokens)
        - Good for: define, explain, apply, create questions
    
    Enhanced Mode (~20% of questions):
        - Slower (+100-200ms for similarity search)
        - More expensive (~$0.0008/question)
        - Uses: chunk + related_chunks (~1500 tokens)
        - Good for: compare, contrast, relationship questions
    """
    # User can force enhanced mode
    if user_preference == "enhanced":
        return "enhanced"
    
    # Analyze bloom level - "analyze" often needs cross-references
    if bloom_level == "analyze":
        return "enhanced"
    
    # Check question type for comparison indicators
    comparison_keywords = ["compare", "contrast", "versus", "difference", 
                          "similarity", "relationship", "distinguish"]
    if any(kw in question_type.lower() for kw in comparison_keywords):
        return "enhanced"
    
    # Default to standard (covers 80% of cases well)
    return "standard"
```

### 8.3 Updated Handler: `handlers/quiz_handlers.py`

```python
async def generate_quiz_from_text_v2(
    data: TextQuizRequest,
    current_user_id: str,
    user_token: str
):
    """
    Enhanced quiz generation with RAG pipeline.
    """
    trace_id = str(uuid4())
    
    # 1. Create generation session
    session = await create_generation_session(current_user_id, trace_id)
    
    try:
        # 2. Ingest content
        ingestion_result = await ingestion_service.ingest_content(
            content=data.content,
            source_type="text",
            user_id=current_user_id,
            user_token=user_token,
            trace_id=trace_id
        )
        
        # 3. Extract concepts
        concepts = await concept_service.extract_concepts(
            document_id=ingestion_result["document_id"],
            chunks=ingestion_result["chunks"],
            user_id=current_user_id,
            trace_id=trace_id
        )
        
        # 4. Generate questions with RAG
        questions = await orchestration_engine.generate_quiz(
            concepts=concepts[:data.num_questions],
            question_types=data.question_type,
            user_id=current_user_id,
            trace_id=trace_id
        )
        
        # 5. Balance and classify
        balanced_questions = await classification_service.balance_quiz(
            questions=questions,
            target_distribution={
                "bloom": {"understand": 0.4, "apply": 0.3, "analyze": 0.3},
                "difficulty": {"easy": 0.3, "medium": 0.5, "hard": 0.2}
            }
        )
        
        # 6. Save quiz
        quiz_id, saved_questions = save_quiz_to_database_v2(...)
        
        # 7. Update session
        await complete_generation_session(session.id, quiz_id, len(saved_questions))
        
        return QuizGenerationResponse(...)
        
    except Exception as e:
        await fail_generation_session(session.id, str(e))
        raise
```

---

## Epic 9: LLM Analytics Integration

### 9.1 Preserve Existing PostHog Integration

The current implementation already has PostHog analytics. We need to:

1. **Keep existing `posthog_service.py`** unchanged
2. **Keep PostHog kwargs pattern** in all LLM calls
3. **Add analytics to new services** (ingestion, concept extraction, etc.)

### 9.2 Enhanced Analytics Tracking

```python
# Add to all new LLM-calling services

async def _track_llm_call(
    user_id: str,
    trace_id: str,
    call_type: str,  # 'embedding', 'generation', 'classification', 'extraction'
    model: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    success: bool = True,
    error_message: str = None,
    metadata: dict = None
):
    """
    Track LLM call in both PostHog (via existing wrapper) and llm_calls table.
    """
    # PostHog is already tracked via the wrapper in openai_service.py
    
    # Also save to llm_calls table for internal analytics
    supabase = get_supabase()
    await supabase.table("llm_calls").insert({
        "user_id": user_id,
        "trace_id": trace_id,
        "call_type": call_type,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "latency_ms": latency_ms,
        "cost_usd": calculate_cost(model, input_tokens, output_tokens),
        "success": success,
        "error_message": error_message,
        "metadata": metadata or {}
    }).execute()
```

### 9.3 Cost Calculation

```python
# Model pricing (per 1K tokens as of Dec 2024)
LLM_PRICING = {
    "gpt-4o": {"input": 0.0025, "output": 0.01},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "text-embedding-3-small": {"input": 0.00002, "output": 0},
    "text-embedding-3-large": {"input": 0.00013, "output": 0}
}

def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = LLM_PRICING.get(model, {"input": 0, "output": 0})
    return (input_tokens * pricing["input"] / 1000) + (output_tokens * pricing["output"] / 1000)
```

---

## Epic 10: Schema Updates

### 10.1 New Pydantic Models: `schemas/quiz.py`

```python
# Add to schemas/quiz.py

class BloomLevel(str, Enum):
    REMEMBER = "remember"
    UNDERSTAND = "understand"
    APPLY = "apply"
    ANALYZE = "analyze"
    EVALUATE = "evaluate"
    CREATE = "create"

class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"

class EnhancedQuestion(BaseModel):
    """Enhanced question with quality metadata"""
    id: Optional[UUID] = None
    quiz_id: Optional[UUID] = None
    type: Literal["multiple_choice", "true_false", "fill_blank", "matching"]
    question: str
    options: Optional[List[str]] = None
    correct_answer: Union[str, bool, List[int]]
    explanation: str
    source: str
    bloom_level: BloomLevel
    difficulty: Difficulty
    concept_id: Optional[UUID] = None
    chunk_id: Optional[UUID] = None
    confidence_score: Optional[float] = None

class QuizGenerationOptions(BaseModel):
    """Options for quiz generation"""
    bloom_distribution: Optional[Dict[BloomLevel, float]] = None
    difficulty_distribution: Optional[Dict[Difficulty, float]] = None
    enable_rag: bool = True
    enable_fact_check: bool = True
```

### 10.2 New Request/Response Models

```python
class EnhancedTextQuizRequest(BaseModel):
    title: str
    content: str
    question_type: List[Literal["multiple_choice", "true_false", "fill_blank", "matching", "mixed"]] = ["mixed"]
    num_questions: int = Field(10, gt=0, le=50)
    options: Optional[QuizGenerationOptions] = None

class EnhancedQuizGenerationResponse(BaseModel):
    quiz_id: str
    title: str
    message: str
    questions: List[EnhancedQuestion]
    generation_stats: Dict[str, Any]  # Chunks, concepts, tokens used, etc.
    source_url: Optional[str] = None
    file_id: Optional[str] = None
```

---

## Epic 11: API Routes Updates

### 11.1 New Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v2/quiz/text` | POST | Enhanced quiz from text |
| `/api/v2/quiz/file/{file_id}` | POST | Enhanced quiz from file |
| `/api/v2/quiz/url` | POST | Enhanced quiz from URL |
| `/api/quiz/{quiz_id}/concepts` | GET | Get concepts for a quiz |
| `/api/quiz/{quiz_id}/chunks` | GET | Get source chunks for a quiz |
| `/api/analytics/generation/{session_id}` | GET | Get generation session stats |

### 11.2 Backward Compatibility

Keep existing `/api/quiz/*` endpoints working with current behavior. New pipeline accessible via `/api/v2/quiz/*`.

---

## Epic 12: Configuration Updates

### 12.1 New Environment Variables

```env
# LlamaIndex Settings
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
CHUNK_SIZE=512
CHUNK_OVERLAP=50

# Quality Settings
ENABLE_RAG_PIPELINE=true
ENABLE_CONCEPT_EXTRACTION=true
ENABLE_BLOOM_CLASSIFICATION=true
ENABLE_FACT_CHECK=true

# Performance
MAX_CHUNKS_PER_DOCUMENT=100
MAX_CONCEPTS_PER_DOCUMENT=50
EMBEDDING_BATCH_SIZE=20
```

### 12.2 Config Updates: `config.py`

```python
class Config:
    # ... existing config ...
    
    # LlamaIndex
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    EMBEDDING_DIMENSIONS: int = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "512"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "50"))
    
    # Quality Pipeline
    ENABLE_RAG_PIPELINE: bool = os.getenv("ENABLE_RAG_PIPELINE", "true").lower() == "true"
    ENABLE_CONCEPT_EXTRACTION: bool = os.getenv("ENABLE_CONCEPT_EXTRACTION", "true").lower() == "true"
```

---

## Implementation Order & Timeline

### Phase 1: Foundation (Week 1-2)
1. Database migration (Epic 1)
2. Add new dependencies (Epic 2)
3. Ingestion service with embeddings (Epic 3)
4. Update schemas (Epic 10)

### Phase 2: Core Pipeline (Week 3-4)
5. Concept extraction service (Epic 4)
6. LLM orchestration layer (Epic 5)
7. LLM analytics integration (Epic 9)

### Phase 3: Quality Enhancement (Week 5-6)
8. Explanation service (Epic 6)
9. Classification service (Epic 7)
10. Updated handlers (Epic 8)

### Phase 4: API & Polish (Week 7-8)
11. New API routes (Epic 11)
12. Configuration updates (Epic 12)
13. Testing & documentation
14. Performance optimization

---

## Testing Strategy

### Unit Tests
- Test each service in isolation
- Mock external dependencies (OpenAI, Supabase)
- Verify PostHog analytics calls

### Integration Tests
- Full pipeline end-to-end
- Vector similarity search accuracy
- Bloom classification accuracy

### Performance Tests
- Embedding generation latency
- RAG retrieval latency
- Full quiz generation time

---

## Rollback Plan

1. **Feature Flag**: Use `ENABLE_RAG_PIPELINE=false` to disable new pipeline
2. **Endpoint Versioning**: Keep `/api/quiz/*` working, new features on `/api/v2/quiz/*`
3. **Database**: New tables are additive, no breaking changes to existing schema

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Question relevance score | N/A | >0.8 |
| Bloom accuracy | N/A | >85% |
| Distractor quality | Basic | Plausible |
| User satisfaction | Baseline | +20% |
| Generation time | ~5s | <10s |
| Token efficiency | N/A | Track & optimize |

---

## Appendix: File Structure After Implementation

```
services/
├── ai_services/
│   ├── __init__.py
│   ├── chunking_service.py       # DEPRECATED (keep for backward compat)
│   ├── classification_service.py # NEW
│   ├── concept_extraction_service.py # NEW (LLM-based, no spaCy)
│   ├── doc_service.py            # KEEP
│   ├── embedding_service.py      # NEW
│   ├── explanation_service.py    # NEW
│   ├── gemini_service.py         # KEEP
│   ├── ingestion_service.py      # NEW
│   ├── openai_service.py         # ENHANCE
│   ├── orchestration_service.py  # NEW
│   ├── prompt_smart.py           # ENHANCE
│   └── prompts.py                # ENHANCE
├── db_services/
│   ├── supabase_chunks.py        # NEW
│   ├── supabase_concepts.py      # NEW
│   ├── supabase_documents.py     # NEW
│   ├── supabase_file.py          # KEEP
│   ├── supabase_llm_analytics.py # NEW
│   └── supabase_quiz.py          # ENHANCE
```

---

## References

- [LlamaIndex Documentation](https://docs.llamaindex.ai/)
- [Supabase pgvector Guide](https://supabase.com/docs/guides/ai/vector-columns)
- [OpenAI Embeddings](https://platform.openai.com/docs/guides/embeddings)
- [Bloom's Taxonomy](https://cft.vanderbilt.edu/guides-sub-pages/blooms-taxonomy/)
- [PostHog LLM Analytics](https://posthog.com/docs/ai-engineering)
- [Cost & Latency Analysis](./QUALITY_IMPROVEMENT_COST_LATENCY_ANALYSIS.md)
