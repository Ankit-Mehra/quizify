import json
import time
import asyncio
from typing import List, Dict, Any, Optional
from uuid import uuid4

from services.ai_services.openai_service import get_openai_client, _build_posthog_kwargs
from services.logger import ai_logger as logger
from services.db_services.supabase_concepts import create_concepts
from services.db_services.supabase_llm_analytics import track_llm_call
from services.posthog_service import capture_exception
from services.ai_services.pricing import calculate_cost
from config import config


# Configuration for batch extraction optimization
# Process multiple chunks per LLM call to minimize API latency overhead
# Smaller batches = more focused extraction = better quality concepts
# 8 chunks × ~512 tokens = ~4K tokens per call (well within nano model's 128K context)
CHUNKS_PER_BATCH = 8

# Maximum parallel batches - run all batches in parallel for fastest completion
# For gpt-4.1-nano with your tier limits, 8-10 is safe
MAX_PARALLEL_BATCHES = 10

# For medium-sized docs (<= 150k chars), a single LLM call is faster than many batched calls
# This eliminates network round trips and decoding passes
# Threshold set to 150k to safely stay within nano model's 128K token context (with prompt overhead)
DOC_SINGLE_CALL_CHAR_THRESHOLD = 150_000

# Compact per-batch concept limits to keep responses small and fast
# Example: 8 concepts/batch × 10 batches = 80 raw concepts, deduped to ~50 final
# Actual batch count varies by document size (num_chunks / CHUNKS_PER_BATCH)
MAX_CONCEPTS_PER_BATCH = 8

# Hard cap on LLM response size for concept extraction
# With 8 concepts × ~80 tokens each = ~640, cap at 800 for safety
MAX_OUTPUT_TOKENS_PER_BATCH = 800


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


# Batch extraction prompt - processes multiple sections in one call
# This dramatically reduces API latency overhead (1 call vs N calls)
BATCH_CONCEPT_EXTRACTION_PROMPT = """
Analyze the following document sections and extract key concepts that would be good for quiz questions.

For each concept, identify:
1. name: The concept name (1-4 words)
2. type: One of [entity, keyword, topic, definition, process]
3. relevance: Score from 0.0 to 1.0 based on importance for understanding the material
4. source_text: A short phrase (max 15 words) from the original text that best illustrates this concept
5. section: Which section number (1-{num_sections}) this concept came from

Document Sections:
{sections_text}

Return JSON format:
{{
  "concepts": [
    {{"name": "...", "type": "...", "relevance": 0.8, "source_text": "...", "section": 1}}
  ]
}}

Extract at most {max_concepts} high-quality, non-duplicate concepts across all sections combined. Prioritize:
- Key terms and definitions that are central to the material
- Named entities (people, places, organizations, tools)
- Important processes, methods, or frameworks
- Central themes and important relationships between concepts

If multiple sections mention the same concept, include it only once with the highest relevance score.
"""


class ConceptExtractionService:
    """
    Service for extracting key concepts from document chunks using LLM.
    
    This replaces heavy NLP libraries (spaCy, KeyBERT) with LLM-based extraction
    for zero memory overhead and better context-aware results.
    """
    
    def __init__(self):
        # Single PostHog-wrapped client for all operations
        # PostHog automatically tracks token usage and latency
        self.client = get_openai_client()
    
    async def _get_embeddings(self, texts: List[str], user_id: str, trace_id: str) -> List[List[float]]:
        """Generate embeddings using OpenAI client (with PostHog tracking)."""
        embeddings = []
        
        # Process in batches
        batch_size = config.EMBEDDING_BATCH_SIZE
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            start_time = time.time()
            
            try:
                # Use the wrapped client for PostHog analytics
                response = await self.client.embeddings.create(
                    input=batch,
                    model=config.EMBEDDING_MODEL,
                    dimensions=config.EMBEDDING_DIMENSIONS
                )
                
                # Extract embeddings (ensure order is preserved)
                batch_embeddings = [data.embedding for data in response.data]
                embeddings.extend(batch_embeddings)
                
                # Track analytics (Supabase)
                latency_ms = int((time.time() - start_time) * 1000)
                track_llm_call(
                    user_id=user_id,
                    trace_id=trace_id,
                    call_type="embedding",
                    model=config.EMBEDDING_MODEL,
                    input_tokens=response.usage.prompt_tokens,
                    output_tokens=0,
                    latency_ms=latency_ms,
                    cost_usd=calculate_cost(config.EMBEDDING_MODEL, response.usage.prompt_tokens, 0)
                )
                
            except Exception as e:
                logger.error(f"Embedding generation failed: {str(e)}")
                raise
                
        return embeddings

    async def extract_concepts(
        self,
        chunks: List[Dict[str, Any]],
        user_id: str,
        user_token: str,
        document_id: str,
        trace_id: Optional[str] = None,
        content_source_type: str = "text"
    ) -> List[Dict[str, Any]]:
        """
        Extract concepts from chunks using optimized batch processing.
        
        Architecture: Instead of 1 chunk → 1 LLM call (slow due to API latency),
        we batch multiple chunks per call to minimize round-trips.
        
        Performance comparison (79 chunks):
        - Old: 20 chunks × 1 call each = 20 calls in 2 rounds = ~22 seconds
        - New: 79 chunks ÷ 8 per batch = 10 calls in 1 round = ~2-3 seconds
        
        Args:
            chunks: List of chunk dicts from ingestion
            user_id: UUID of the user
            user_token: JWT token for RLS enforcement
            document_id: UUID of the parent document
            trace_id: Optional trace ID for analytics
            content_source_type: Source type for analytics (text, file, url)
            
        Returns:
            List of stored concept records
        """
        trace_id = trace_id or str(uuid4())
        total_chunks = len(chunks)
        
        logger.info(f"Extracting concepts from {total_chunks} chunks for doc {document_id}")
        
        # Estimate total document size for this concept extraction
        total_chars = sum(len(c.get("content", "")) for c in chunks)
        logger.info(f"[BATCH] Total content length: {total_chars} characters")
        
        # Fast path: for medium-sized docs, run a single batch call over all chunks
        # This avoids multiple LLM calls and significantly reduces wall-clock time
        if total_chars <= DOC_SINGLE_CALL_CHAR_THRESHOLD:
            logger.info(
                f"[BATCH] Using single-call extraction for doc {document_id} "
                f"(chars={total_chars} <= {DOC_SINGLE_CALL_CHAR_THRESHOLD})"
            )
            raw_concepts = await self._extract_from_batch(
                chunks=chunks,
                batch_idx=0,
                user_id=user_id,
                document_id=document_id,
                trace_id=trace_id,
                content_source_type=content_source_type,
                is_single_call=True,
            )
            extracted_concepts_data = raw_concepts or []
            successful_batches = 1 if extracted_concepts_data else 0
            logger.info(
                f"[BATCH] {successful_batches}/1 batches succeeded, "
                f"extracted {len(extracted_concepts_data)} raw concepts"
            )
            return await self._post_process_and_store_concepts(
                extracted_concepts_data,
                user_id,
                user_token,
                document_id,
                trace_id,
            )
        
        # Multi-batch path for very large documents
        logger.info("[BATCH] Using multi-batch extraction (doc too large for single call)")
        
        # Group chunks into batches for efficient processing
        # Each batch is processed in a single LLM call
        batches = []
        for i in range(0, total_chunks, CHUNKS_PER_BATCH):
            batch = chunks[i:i + CHUNKS_PER_BATCH]
            batches.append(batch)
        
        num_batches = len(batches)
        logger.info(f"[BATCH] Processing {total_chunks} chunks in {num_batches} batches ({CHUNKS_PER_BATCH} chunks/batch)")
        
        # Process batches with staggered starts to avoid OpenAI burst rate limiting
        # OpenAI throttles response times when hit with many simultaneous requests
        semaphore = asyncio.Semaphore(MAX_PARALLEL_BATCHES)
        batch_start_times = {}
        batch_end_times = {}
        global_start = time.time()
        
        async def process_batch(batch: List[Dict], batch_idx: int):
            async with semaphore:
                batch_start_times[batch_idx] = time.time() - global_start
                logger.info(f"[BATCH {batch_idx}] Starting at +{batch_start_times[batch_idx]:.2f}s")
                result = await self._extract_from_batch(
                    batch, batch_idx, user_id, document_id, trace_id, content_source_type, is_single_call=False
                )
                batch_end_times[batch_idx] = time.time() - global_start
                logger.info(f"[BATCH {batch_idx}] Finished at +{batch_end_times[batch_idx]:.2f}s (took {batch_end_times[batch_idx] - batch_start_times[batch_idx]:.2f}s)")
                return result
        
        start_time = time.time()
        # Create tasks immediately (schedule in event loop) - crucial for true parallelism
        tasks = [asyncio.create_task(process_batch(batch, idx)) for idx, batch in enumerate(batches)]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        batch_time = time.time() - start_time
        
        # Accurate parallelism diagnostic: compare total time to max individual batch duration
        if num_batches > 0 and batch_start_times and batch_end_times:
            durations = [
                batch_end_times[i] - batch_start_times[i]
                for i in batch_end_times.keys()
                if i in batch_start_times
            ]
            avg_per_batch = sum(durations) / len(durations) if durations else 0
            max_batch_duration = max(durations) if durations else 0
            logger.info(
                f"[BATCH] All {num_batches} batches completed in {batch_time:.2f}s "
                f"(avg {avg_per_batch:.2f}s/batch, max {max_batch_duration:.2f}s)"
            )
            # If total time >> max single batch, parallelism is limited
            if batch_time > max_batch_duration * 1.5:
                logger.warning(
                    f"[BATCH] ⚠️ Limited parallelism detected "
                    f"(total {batch_time:.2f}s vs max single-batch {max_batch_duration:.2f}s)"
                )
        else:
            logger.info(f"[BATCH] All {num_batches} batches completed in {batch_time:.2f}s")
        
        # Flatten results, skip failures
        extracted_concepts_data = []
        successful_batches = 0
        for batch_idx, result in enumerate(results):
            if isinstance(result, list):
                extracted_concepts_data.extend(result)
                successful_batches += 1
            elif isinstance(result, Exception):
                logger.error(f"Batch {batch_idx} extraction failed: {result}")
        
        logger.info(f"[BATCH] {successful_batches}/{num_batches} batches succeeded, extracted {len(extracted_concepts_data)} raw concepts")
        
        return await self._post_process_and_store_concepts(
            extracted_concepts_data,
            user_id,
            user_token,
            document_id,
            trace_id,
        )
    
    async def _post_process_and_store_concepts(
        self,
        extracted_concepts_data: List[Dict[str, Any]],
        user_id: str,
        user_token: str,
        document_id: str,
        trace_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Deduplicate, embed, and store extracted concepts.
        
        Shared by both single-call and multi-batch extraction paths.
        """
        if not extracted_concepts_data:
            logger.warning(f"No concepts extracted for document {document_id}")
            return []

        # Sort by relevance BEFORE deduplication to ensure highest-relevance instance is kept
        extracted_concepts_data.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        
        # Deduplicate concepts by name (batch extraction may have overlaps)
        # For unnamed concepts, deduplicate by source_text to avoid similar content
        seen_names = set()
        seen_source_texts = set()
        unique_concepts: List[Dict[str, Any]] = []
        
        for concept in extracted_concepts_data:
            name_lower = concept.get("name", "").lower().strip()
            if name_lower:
                # Named concept - deduplicate by name
                if name_lower not in seen_names:
                    seen_names.add(name_lower)
                    unique_concepts.append(concept)
            else:
                # Unnamed concept - deduplicate by source_text to avoid duplicate content
                source_text = concept.get("source_text", "").strip()
                if source_text and source_text not in seen_source_texts:
                    seen_source_texts.add(source_text)
                    unique_concepts.append(concept)
                # Skip concepts with no name and no source_text (malformed)
        
        logger.info(f"[BATCH] After deduplication: {len(unique_concepts)} unique concepts")
        
        # Limit total concepts and sort by relevance
        max_concepts = config.MAX_CONCEPTS_PER_DOCUMENT
        if len(unique_concepts) > max_concepts:
            unique_concepts.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
            unique_concepts = unique_concepts[:max_concepts]

        # Generate embeddings for concepts (batch async)
        concept_names = [c["name"] for c in unique_concepts]
        if concept_names:
            embeddings = await self._get_embeddings(concept_names, user_id, trace_id)
            for i, concept in enumerate(unique_concepts):
                concept["embedding"] = embeddings[i]
        
        # Store in DB (with user_token for RLS)
        stored_concepts = create_concepts(unique_concepts, user_token)
        logger.info(f"Stored {len(stored_concepts)} concepts for document {document_id}")
        
        return stored_concepts
    
    async def _extract_from_batch(
        self,
        chunks: List[Dict[str, Any]],
        batch_idx: int,
        user_id: str,
        document_id: str,
        trace_id: str,
        content_source_type: str = "text",
        is_single_call: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Extract concepts from a batch of chunks in a single LLM call.
        
        This is the key optimization: by sending multiple chunks per call,
        we amortize the API latency (~500-800ms) across more content.
        
        Args:
            chunks: List of up to 8 chunk dicts (last batch may have fewer)
            batch_idx: Index of this batch (for logging)
            user_id: UUID of the user
            document_id: UUID of the parent document
            trace_id: Trace ID for analytics
            content_source_type: Source type for analytics
            is_single_call: True if processing entire document in one call, False for multi-batch mode
            
        Returns:
            List of formatted concept dicts ready for DB storage
        """
        start_time = time.time()
        # Use nano model for fastest concept extraction (~5s per batch vs 25-50s with mini)
        model = config.LLM_MODEL_NANO
        num_chunks = len(chunks)
        
        # Build sections text with numbered headers
        sections_parts = []
        chunk_id_map = {}  # section_num -> chunk_id for later reference
        
        for i, chunk in enumerate(chunks):
            section_num = i + 1
            chunk_id_map[section_num] = chunk.get("id")
            content = chunk.get("content", "").strip()
            if not content:
                continue  # Skip empty chunks to avoid malformed section headers
            sections_parts.append(f"--- Section {section_num} ---\n{content}")
        
        sections_text = "\n\n".join(sections_parts)
        
        try:
            # Build PostHog kwargs for tracking (distinct_id, trace_id, properties)
            posthog_kwargs = _build_posthog_kwargs(
                user_id=user_id,
                trace_id=trace_id,
                properties={
                    "generation_mode": "concept_extraction",
                    "batch_idx": batch_idx,
                    "chunks_in_batch": num_chunks,
                    "document_id": document_id,
                }
            )
            
            # Calculate max concepts and tokens based on mode
            # Single-call: entire document -> request config.MAX_CONCEPTS_PER_DOCUMENT, allow 6000 tokens
            # Multi-batch: each batch -> request MAX_CONCEPTS_PER_BATCH (or num_chunks if smaller), cap at 800 tokens
            if is_single_call:
                max_concepts_for_batch = config.MAX_CONCEPTS_PER_DOCUMENT
                max_output_tokens = 6000
            else:
                max_concepts_for_batch = min(MAX_CONCEPTS_PER_BATCH, num_chunks)
                max_output_tokens = MAX_OUTPUT_TOKENS_PER_BATCH
            
            # PostHog-wrapped client automatically tracks tokens and latency
            response = await self.client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert educational content analyzer. Extract key concepts that would make excellent quiz questions."
                    },
                    {
                        "role": "user",
                        "content": BATCH_CONCEPT_EXTRACTION_PROMPT.format(
                            num_sections=num_chunks,
                            sections_text=sections_text,
                            max_concepts=max_concepts_for_batch,
                        )
                    },
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=max_output_tokens,
                **posthog_kwargs
            )
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            # Parse response
            content = response.choices[0].message.content
            usage = response.usage
            
            try:
                data = json.loads(content)
                concepts = data.get("concepts", [])
            except json.JSONDecodeError:
                logger.error(f"Batch {batch_idx}: Failed to parse JSON: {content[:100]}...")
                concepts = []
            
            # Track analytics
            cost = calculate_cost(model, usage.prompt_tokens, usage.completion_tokens)
            track_llm_call(
                user_id=user_id,
                trace_id=trace_id,
                call_type="extraction_batch",
                model=model,
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
                latency_ms=latency_ms,
                cost_usd=cost,
                metadata={
                    "batch_idx": batch_idx,
                    "chunks_in_batch": num_chunks,
                    "document_id": document_id,
                    "concepts_extracted": len(concepts)
                }
            )
            
            logger.debug("Batch %s: extracted %s concepts in %sms", batch_idx, len(concepts), latency_ms)
            
            # Format concepts for DB storage
            formatted_concepts = []
            for c in concepts:
                # Map section number back to chunk_id (fallback to section 1 if invalid)
                section_num = c.get("section", 1)
                chunk_id = chunk_id_map.get(section_num, chunk_id_map.get(1, chunks[0].get("id") if chunks else None))
                
                formatted_concepts.append({
                    "document_id": document_id,
                    "user_id": user_id,
                    "chunk_id": chunk_id,
                    "name": c.get("name", "Unknown"),
                    "concept_type": c.get("type", "keyword"),
                    "relevance_score": float(c.get("relevance", 0.5)),
                    "source_text": c.get("source_text", ""),
                    "metadata": {"batch_idx": batch_idx}
                })
            
            return formatted_concepts
            
        except Exception as e:
            logger.error(f"Batch {batch_idx}: Error extracting concepts: {str(e)}")
            # Track failure
            track_llm_call(
                user_id=user_id,
                trace_id=trace_id,
                call_type="extraction_batch",
                model=model,
                input_tokens=0,
                output_tokens=0,
                latency_ms=int((time.time() - start_time) * 1000),
                success=False,
                error_message=str(e),
                metadata={"batch_idx": batch_idx, "chunks_in_batch": num_chunks}
            )
            capture_exception(
                exception=e,
                distinct_id=user_id,
                properties={
                    "generation_mode": "enhanced",
                    "stage": "concept_extraction_batch",
                    "model": model,
                    "batch_idx": batch_idx,
                    "content_source_type": content_source_type,
                    "trace_id": trace_id,
                }
            )
            return []
