import json
import time
import asyncio
from typing import List, Dict, Any, Optional
from uuid import uuid4

from services.ai_services.openai_service import get_openai_client, get_batch_openai_client, _build_posthog_kwargs
from services.logger import ai_logger as logger
from services.db_services.supabase_concepts import create_concepts
from services.db_services.supabase_llm_analytics import track_llm_call
from services.posthog_service import capture_exception
from services.ai_services.pricing import calculate_cost
from config import config


# Configuration for batch extraction optimization
# Process multiple chunks per LLM call to minimize API latency overhead
# Smaller batches = more focused extraction = better quality concepts
# 8 chunks × ~512 tokens = ~4K tokens per call (well within mini model's 128K context)
CHUNKS_PER_BATCH = 8

# Maximum parallel batches - with httpx connection limits fixed, these run truly parallel
# 10 batches × 8 chunks = 80 chunks processed simultaneously
# Your Tier 1 limits: 500 RPM, 200K TPM - plenty of headroom for 10 parallel requests
MAX_PARALLEL_BATCHES = 10


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
4. source_text: A key sentence or phrase containing this concept
5. section: Which section number (1-{num_sections}) this concept came from

Document Sections:
{sections_text}

Return JSON format:
{{
  "concepts": [
    {{"name": "...", "type": "...", "relevance": 0.8, "source_text": "...", "section": 1}}
  ]
}}

Extract 30-50 high-quality concepts total across all sections (aim for 4-6 per section). Prioritize:
- Key terms and definitions that are central to the material
- Named entities (people, places, organizations, tools)
- Important processes, methods, or frameworks
- Central themes and relationships between concepts
- Avoid duplicates - if a concept appears in multiple sections, include it once with highest relevance
"""


class ConceptExtractionService:
    """
    Service for extracting key concepts from document chunks using LLM.
    
    This replaces heavy NLP libraries (spaCy, KeyBERT) with LLM-based extraction
    for zero memory overhead and better context-aware results.
    """
    
    def __init__(self):
        # Regular client for embeddings (PostHog tracking is fine, not parallelized heavily)
        self.client = get_openai_client()
        # Dedicated batch client for parallel extraction (bypasses PostHog to enable true parallelism)
        self.batch_client = get_batch_openai_client()
    
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
        
        # Group chunks into batches for efficient processing
        # Each batch is processed in a single LLM call
        batches = []
        for i in range(0, total_chunks, CHUNKS_PER_BATCH):
            batch = chunks[i:i + CHUNKS_PER_BATCH]
            batches.append(batch)
        
        num_batches = len(batches)
        logger.info(f"[BATCH] Processing {total_chunks} chunks in {num_batches} batches ({CHUNKS_PER_BATCH} chunks/batch)")
        
        # Process all batches in parallel with rate limiting
        # CRITICAL: Use asyncio.create_task() to schedule tasks immediately in the event loop
        # Without this, OpenAI SDK's async calls may execute sequentially despite httpx settings
        semaphore = asyncio.Semaphore(MAX_PARALLEL_BATCHES)
        
        async def process_batch(batch: List[Dict], batch_idx: int):
            async with semaphore:
                return await self._extract_from_batch(
                    batch, batch_idx, user_id, document_id, trace_id, content_source_type
                )
        
        start_time = time.time()
        # Create tasks immediately (schedule in event loop) - crucial for true parallelism
        tasks = [asyncio.create_task(process_batch(batch, idx)) for idx, batch in enumerate(batches)]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        batch_time = time.time() - start_time
        
        # Log diagnostic: if batches are parallel, batch_time should be ~= time for slowest batch (~5-7s)
        # If sequential, batch_time ~= num_batches * avg_batch_time (~55s for 10 batches)
        avg_per_batch = batch_time / num_batches if num_batches > 0 else 0
        logger.info(f"[BATCH] All {num_batches} batches completed in {batch_time:.2f}s (avg {avg_per_batch:.2f}s/batch)")
        if batch_time > (avg_per_batch * 2):
            logger.warning(f"[BATCH] ⚠️  Batches appear to be running SEQUENTIALLY (expected ~{avg_per_batch:.2f}s if parallel, got {batch_time:.2f}s)")
        
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
        
        if not extracted_concepts_data:
            logger.warning(f"No concepts extracted for document {document_id}")
            return []

        # Sort by relevance BEFORE deduplication to ensure highest-relevance instance is kept
        # (per prompt instruction: "include it once with highest relevance")
        extracted_concepts_data.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        
        # Deduplicate concepts by name (batch extraction may have overlaps)
        seen_names = set()
        unique_concepts = []
        for concept in extracted_concepts_data:
            name_lower = concept.get("name", "").lower().strip()
            if name_lower and name_lower not in seen_names:
                seen_names.add(name_lower)
                unique_concepts.append(concept)
        
        logger.info(f"[BATCH] After deduplication: {len(unique_concepts)} unique concepts")
        
        # Limit total concepts and sort by relevance
        if len(unique_concepts) > config.MAX_CONCEPTS_PER_DOCUMENT:
            unique_concepts.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
            unique_concepts = unique_concepts[:config.MAX_CONCEPTS_PER_DOCUMENT]

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
        content_source_type: str = "text"
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
            
        Returns:
            List of formatted concept dicts ready for DB storage
        """
        start_time = time.time()
        model = config.LLM_MODEL_MINI
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
        
        # Note: We use batch_client here (bypasses PostHog) for true parallel execution
        # PostHog tracking is done manually via track_llm_call() below
        
        try:
            response = await self.batch_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are an expert educational content analyzer. Extract key concepts that would make excellent quiz questions."},
                    {"role": "user", "content": BATCH_CONCEPT_EXTRACTION_PROMPT.format(
                        num_sections=num_chunks,
                        sections_text=sections_text
                    )}
                ],
                response_format={"type": "json_object"},
                temperature=0.3
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
