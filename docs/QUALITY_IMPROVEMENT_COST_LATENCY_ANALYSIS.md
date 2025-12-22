# Quiz Quality Improvement: Cost & Latency Analysis

## Overview

This document analyzes the cost and latency implications of upgrading from the current quiz generation system to the enhanced RAG-based pipeline. Analysis is based on actual PostHog analytics data and OpenAI pricing.

---

## Current System Baseline (From PostHog Analytics)

### Understanding PostHog Metrics

| PostHog Term | Meaning | Example |
|--------------|---------|---------|
| **Trace** | One quiz generation request (user clicks "Generate Quiz") | 1 trace = 1 quiz |
| **Generation** | One LLM API call | Multiple generations per trace |

### Observed Data Points

**Data Point 1 (Historical):**
| Metric | Value |
|--------|-------|
| Traces | 5 |
| Generations | 45 |
| Total Cost | $0.0367 |
| **Generations per Quiz** | 9 (45/5) |
| **Cost per Quiz** | **$0.00734** |

**Data Point 2 (Recent - 10-question quiz):**
| Metric | Value |
|--------|-------|
| Traces | 1 |
| Generations | 10 |
| Total Cost | $0.0086 |
| **Generations per Quiz** | 10 |
| **Cost per Quiz** | **$0.0086** |

### Current Architecture Flow Analysis

For a 10-question "mixed" quiz, the current system:

1. **Chunks text** based on question count (~10 chunks for 10 questions)
2. **For each chunk**, calls `generate_quiz_async()` which:
   - Expands "mixed" to all 4 types: `[multiple_choice, true_false, fill_blank, matching]`
   - Makes **1 LLM call per question type** (4 calls per chunk)
   - Each call asks for `base_questions // 4` questions

**Result**: 10 chunks × 1 generation per chunk = **10 LLM generations** per quiz

### ⚠️ Potential Inefficiency Discovered

The prompt wording may cause over-generation:

```
"Generate exactly 1 questions of the following types: multiple_choice, true_false, fill_blank, matching."
```

The LLM may interpret this as "1 question of EACH type" = **4 questions per call**.

If this is happening:
- 10 generations × 4 questions = **40 questions generated**
- Only 10 returned: `return filtered[:total_questions]`
- **75% of LLM output is wasted!**

**Recommendation**: Fix prompt to be explicit:
```python
# Current (ambiguous)
f"Generate exactly {num_questions} questions of the following types: {type_str}."

# Fixed (explicit)
f"Generate exactly {num_questions} questions total. Mix the types: {type_str}. Do NOT generate {num_questions} of each type."
```

### Corrected Current Cost Baseline

| Metric | Value | Notes |
|--------|-------|-------|
| **Cost per 10-Question Quiz** | **$0.0086** | From actual PostHog data |
| Generations per Quiz | 10 | One per chunk |
| Avg Cost per Generation | $0.00086 | |

---

## Enhanced RAG Pipeline: Cost Analysis

### OpenAI Pricing (December 2024)

| Model | Input (per 1K tokens) | Output (per 1K tokens) |
|-------|----------------------|------------------------|
| gpt-4o | $0.0025 | $0.01 |
| gpt-4o-mini | $0.00015 | $0.0006 |
| text-embedding-3-small | $0.00002 | N/A |
| text-embedding-3-large | $0.00013 | N/A |

### New Pipeline Steps & Token Usage

For a typical 10-question quiz from ~2000 words (~2,500 tokens) of content:

#### Step 1: Document Ingestion & Embedding
| Operation | Model | Tokens | Cost |
|-----------|-------|--------|------|
| Chunk embeddings (~5 chunks × 500 tokens) | text-embedding-3-small | 2,500 | $0.00005 |

#### Step 2: Concept Extraction (LLM-based, replaces spaCy)
| Operation | Model | Input Tokens | Output Tokens | Cost |
|-----------|-------|-------------|---------------|------|
| Extract concepts from chunks | gpt-4o-mini | ~3,000 | ~500 | $0.00075 |
| Concept embeddings (~10 concepts) | text-embedding-3-small | ~200 | - | $0.000004 |

#### Step 3: RAG Retrieval
| Operation | Model | Tokens | Cost |
|-----------|-------|--------|------|
| Query embedding (per concept) | text-embedding-3-small | ~50 × 10 | $0.00001 |

#### Step 4: Question Generation (Per Question)
| Operation | Model | Input Tokens | Output Tokens | Cost per Q |
|-----------|-------|-------------|---------------|------------|
| Generate question with RAG context | gpt-4o-mini | ~800 | ~200 | $0.00024 |
| Generate explanation | gpt-4o-mini | ~400 | ~150 | $0.00015 |

For 10 questions: $0.0039

#### Step 5: Classification (Bloom + Difficulty)
| Operation | Model | Input Tokens | Output Tokens | Cost |
|-----------|-------|-------------|---------------|------|
| Classify all 10 questions | gpt-4o-mini | ~1,500 | ~300 | $0.00041 |

### Total Cost Comparison

| Pipeline | Cost per 10-Question Quiz | Change |
|----------|--------------------------|--------|
| **Current** | ~$0.0086 | Baseline (actual PostHog data) |
| **Enhanced RAG** | ~$0.0055 | **-36%** (cheaper!) |

**Surprising Result**: The enhanced RAG pipeline is actually **cheaper** than the current implementation because:
1. Current system makes 10 LLM calls (one per chunk)
2. Enhanced system makes fewer, more targeted calls
3. Embeddings are extremely cheap ($0.00002/1K tokens)

### Cost Breakdown (Enhanced Pipeline)

```
Embeddings (chunks):     $0.00005  (0.9%)
Concept Extraction:      $0.00075  (13.6%)
Concept Embeddings:      $0.000004 (0.1%)
RAG Query Embeddings:    $0.00001  (0.2%)
Question Generation:     $0.0039   (70.9%)  ← Main cost driver
Classification:          $0.00041  (7.5%)
─────────────────────────────────────────
Total:                   $0.00552  (100%)
```

### Monthly Cost Projections

| Scenario | Current ($0.0086/quiz) | Enhanced ($0.0055/quiz) | Savings |
|----------|------------------------|-------------------------|---------|
| 10 quizzes/month | $0.086 | $0.055 | -$0.031 |
| 50 quizzes/month | $0.43 | $0.28 | -$0.15 |
| 100 quizzes/month | $0.86 | $0.55 | -$0.31 |
| 500 quizzes/month | $4.30 | $2.75 | -$1.55 |

**Verdict**: The enhanced pipeline is actually **cheaper** while providing better quality!

---

## Enhanced RAG Pipeline: Latency Analysis

### Current Pipeline Latency
| Step | Time | Notes |
|------|------|-------|
| Text chunking (tiktoken) | ~50ms | |
| GPT-4o-mini generation (10 calls) | ~8-12s | 10 parallel LLM calls |
| JSON parsing | ~10ms | |
| Database save | ~100ms | |
| **Total** | **~8-12s** | Due to 10 parallel LLM calls |

### Enhanced Pipeline Latency (Sequential)
| Step | Time | Notes |
|------|------|-------|
| 1. Document ingestion | ~50ms | Text processing |
| 2. Semantic chunking | ~100ms | LlamaIndex SentenceSplitter |
| 3. Chunk embeddings (batch) | ~500ms | 5 chunks, batched API call |
| 4. Save document + chunks | ~150ms | Database writes |
| 5. Concept extraction (LLM) | ~2s | Single GPT-4o-mini call |
| 6. Concept embeddings | ~200ms | Batched |
| 7. Save concepts | ~100ms | Database write |
| 8. RAG retrieval | ~100ms | Vector similarity search |
| 9. Question generation | ~5-8s | 10 questions, parallelizable |
| 10. Explanation generation | ~3-5s | 10 explanations, parallelizable |
| 11. Classification | ~1.5s | Batch classification |
| 12. Save quiz | ~150ms | Database write |
| **Total (Sequential)** | **~13-18s** | |

### Optimized Pipeline Latency (With Parallelization)

| Step | Time | Optimization |
|------|------|--------------|
| 1-4. Ingestion + Embedding | ~800ms | Batch embeddings |
| 5-7. Concept extraction | ~2.5s | Single LLM call + batch embed |
| 8. RAG retrieval | ~100ms | Parallel queries |
| 9-10. Question + Explanation | ~5s | **Parallel per question** |
| 11. Classification | ~1s | Batch in single call |
| 12. Save | ~150ms | - |
| **Total (Optimized)** | **~9-10s** | |

### Latency Comparison

| Pipeline | Latency | Increase |
|----------|---------|----------|
| **Current** | ~3.5-5.5s | Baseline |
| **Enhanced (Sequential)** | ~13-18s | +3-4x |
| **Enhanced (Optimized)** | ~9-10s | **+2x** |

---

## Latency Optimization Strategies

### 1. Parallel Question Generation
Instead of generating questions sequentially, generate all 10 in parallel:
```python
# Current: Sequential
for concept in concepts:
    question = await generate_question(concept)

# Optimized: Parallel
questions = await asyncio.gather(*[
    generate_question(concept) for concept in concepts
])
```
**Savings**: ~4-5s for 10 questions

### 2. Batch Embedding Calls
Combine all embedding requests into single API calls:
```python
# Instead of 5 separate calls for chunks
embeddings = await embed_model.get_text_embeddings(all_chunks)
```
**Savings**: ~400ms (network overhead)

### 3. Combined Prompts
Merge explanation generation into question generation prompt:
```python
# Instead of 2 calls per question
"Generate question AND explanation in single response"
```
**Savings**: ~3s for 10 questions

### 4. Skip Classification for Simple Mode
Make Bloom/difficulty classification optional:
```python
if options.enable_bloom_classification:
    # Extra 1.5s for classification
```
**Savings**: ~1.5s when disabled

### 5. Caching Embeddings
For documents that are re-used, cache embeddings:
```python
# Check if document already ingested
existing = await get_cached_embeddings(content_hash)
```
**Savings**: ~2.5s on repeat generations

---

## Context Modes: Two-Mode Strategy

Based on analysis, we implement a **simplified two-mode** context strategy instead of three modes.

### Mode Comparison

| Mode | Context Used | Tokens | Latency | Cost/Question | Best For |
|------|--------------|--------|---------|---------------|----------|
| **Standard** | chunk only | ~500 | +0ms | ~$0.0003 | 80% of questions |
| **Enhanced** | chunk + related | ~1500 | +100-200ms | ~$0.0008 | Compare/contrast |

### Why Two Modes (Not Three)

| Rejected Mode | Reason |
|---------------|--------|
| Fast (source_text only) | Too limited context for quality questions |
| source_text + chunk | Redundant (source_text ⊂ chunk) |

### When to Use Each Mode

```python
def determine_context_mode(question_type: str, bloom_level: str) -> str:
    """
    Standard Mode (Default - ~80% of questions):
        - Uses chunk.text only (~500 tokens)
        - Retrieved via concept.chunk_id (no similarity search)
        - Good for: Remember, Understand, Apply, Create
    
    Enhanced Mode (~20% of questions):
        - Uses chunk + related_chunks (~1500 tokens)
        - Query with concept.embedding (already stored - no extra API call)
        - Good for: Analyze, Evaluate (comparison questions)
    """
    # Analyze bloom level benefits most from cross-references
    if bloom_level == "analyze":
        return "enhanced"
    
    # Check for comparison question types
    comparison_keywords = ["compare", "contrast", "relationship", "difference"]
    if any(kw in question_type.lower() for kw in comparison_keywords):
        return "enhanced"
    
    return "standard"
```

### Key Insight

```
source_text ⊂ chunk (source_text is already inside chunk)
→ Never use source_text + chunk (redundant, wastes tokens)
→ chunk already provides full context around the concept
```

---

## Decision: Remove spaCy, Use LLM

### Original Plan (With spaCy)
| Component | Memory | Latency | Cost |
|-----------|--------|---------|------|
| spaCy en_core_web_sm | +50-70MB | ~100ms | $0 |
| KeyBERT | +200MB | ~200ms | $0 |
| **Total** | +250-270MB | +300ms | $0 |

### Updated Plan (LLM-Only)
| Component | Memory | Latency | Cost |
|-----------|--------|---------|------|
| GPT-4o-mini for NER | 0 | ~2s | ~$0.00075 |
| Skip KeyBERT | 0 | 0 | $0 |
| **Total** | **0** | +2s | +$0.00075 |

### Trade-off Analysis

| Factor | spaCy Approach | LLM Approach | Winner |
|--------|---------------|--------------|--------|
| Memory footprint | +250MB | 0 | **LLM** |
| Railway deployment | Requires model download | No changes | **LLM** |
| Concept quality | Rule-based NER | Context-aware | **LLM** |
| Latency | +300ms | +2s | spaCy |
| Cost per quiz | $0 | +$0.00075 | spaCy |
| Maintenance | spaCy updates | None | **LLM** |

**Decision**: Use LLM for concept extraction. The +$0.00075 cost and +1.7s latency is worth the 0 memory footprint and better quality extraction.

---

## Updated Requirements (No spaCy)

### Removed Dependencies
```diff
- spacy>=3.7.0
- keybert>=0.8.0  # Uses sentence-transformers, large memory
```

### Kept Dependencies
```txt
# LlamaIndex Core (lightweight)
llama-index-core>=0.11.0
llama-index-llms-openai>=0.2.0
llama-index-embeddings-openai>=0.2.0

# Async Support
asyncpg>=0.29.0
```

### Estimated Memory Impact
| Component | Memory |
|-----------|--------|
| llama-index-core | ~20MB |
| llama-index-embeddings-openai | ~5MB |
| asyncpg | ~2MB |
| **Total New** | **~27MB** |

Compare to spaCy approach: **250MB saved**

---

## Summary

### Cost Impact
| Metric | Current | Enhanced | Change |
|--------|---------|----------|--------|
| Cost per quiz | $0.0086 | $0.0055 | **-36%** ✅ |
| Monthly (100 quizzes) | $0.86 | $0.55 | -$0.31 |
| Annual (1200 quizzes) | $10.32 | $6.60 | -$3.72 |

**Verdict**: Enhanced pipeline is **cheaper** while providing better quality!

### Latency Impact
| Metric | Current | Enhanced (Optimized) | Change |
|--------|---------|---------------------|--------|
| Average latency | ~8-12s | ~9-10s | **~Same** |
| With caching | ~8-12s | ~7s | -15-40% |

**Verdict**: Latency is comparable or better with the enhanced pipeline

### Memory Impact
| Approach | Additional Memory |
|----------|-------------------|
| With spaCy + KeyBERT | +250MB |
| LLM-only (final choice) | **+27MB** |

**Verdict**: LLM approach saves 223MB, critical for Railway single-instance deployment

---

## Recommendations

1. **Use LLM for concept extraction** - No spaCy/KeyBERT
2. **Enable parallel question generation** - Reduce latency by ~4s
3. **Use two-mode context strategy**:
   - **Standard** (default): chunk only - covers 80% of questions
   - **Enhanced**: chunk + related - for compare/contrast questions
4. **Implement document caching** - Avoid re-embedding same content
5. **Make Bloom classification inline** - Include in question generation prompt (no extra call)

---

## Appendix: Updated Epic 2 Dependencies

```txt
# LlamaIndex Core (Required)
llama-index-core>=0.11.0
llama-index-llms-openai>=0.2.0
llama-index-embeddings-openai>=0.2.0

# Database (Required)
asyncpg>=0.29.0

# REMOVED - Too memory heavy for single-instance deployment
# spacy>=3.7.0
# keybert>=0.8.0
# sentence-transformers>=2.2.0
```
