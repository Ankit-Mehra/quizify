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
    """
    Service for extracting key concepts from document chunks using GPT-4o-mini.
    
    This replaces heavy NLP libraries (spaCy, KeyBERT) with LLM-based extraction
    for zero memory overhead and better context-aware results.
    """
    
    def __init__(self):
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
        Extract concepts from chunks and store them.
        
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
        
        logger.info(f"Extracting concepts from {len(chunks)} chunks for doc {document_id}")
        
        # Limit chunks to process - use smaller limit for faster quiz generation
        # Most quizzes need 10-20 questions, so 20 chunks is plenty
        max_chunks_for_extraction = min(20, config.MAX_CHUNKS_PER_DOCUMENT)
        if len(chunks) > max_chunks_for_extraction:
            logger.info(f"Limiting chunk processing from {len(chunks)} to {max_chunks_for_extraction} for faster extraction")
            chunks = chunks[:max_chunks_for_extraction]
        
        # Process chunks in parallel with rate limiting
        # Increased from 5 to 10 for faster processing (gpt-4o-mini handles it well)
        semaphore = asyncio.Semaphore(10)
        
        async def process_chunk(chunk):
            async with semaphore:
                return await self._extract_from_chunk(chunk, user_id, document_id, trace_id, content_source_type)

        tasks = [process_chunk(chunk) for chunk in chunks]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Flatten results, skip failures
        extracted_concepts_data = []
        for result in results:
            if isinstance(result, list):
                extracted_concepts_data.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"Chunk extraction failed: {result}")
            
        if not extracted_concepts_data:
            logger.warning(f"No concepts extracted for document {document_id}")
            return []

        # Limit total concepts
        if len(extracted_concepts_data) > config.MAX_CONCEPTS_PER_DOCUMENT:
            # Sort by relevance and take top N
            extracted_concepts_data.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
            extracted_concepts_data = extracted_concepts_data[:config.MAX_CONCEPTS_PER_DOCUMENT]

        # Generate embeddings for concepts (batch async)
        concept_names = [c["name"] for c in extracted_concepts_data]
        if concept_names:
            embeddings = await self._get_embeddings(concept_names, user_id, trace_id)
            for i, concept in enumerate(extracted_concepts_data):
                concept["embedding"] = embeddings[i]
        
        # Store in DB (with user_token for RLS)
        stored_concepts = create_concepts(extracted_concepts_data, user_token)
        logger.info(f"Stored {len(stored_concepts)} concepts for document {document_id}")
        
        return stored_concepts
    
    async def _extract_from_chunk(
        self,
        chunk: Dict[str, Any],
        user_id: str,
        document_id: str,
        trace_id: str,
        content_source_type: str = "text"
    ) -> List[Dict[str, Any]]:
        """Extract concepts from a single chunk using GPT-4o-mini."""
        start_time = time.time()
        model = "gpt-4o-mini"
        
        # Build PostHog tracking kwargs
        posthog_kwargs = _build_posthog_kwargs(
            user_id=user_id,
            trace_id=trace_id,
            properties={
                "call_type": "concept_extraction",
                "document_id": document_id,
                "generation_mode": "enhanced",
                "content_source_type": content_source_type,
                "feature": "quiz_generation",
            }
        )
        
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are an expert educational content analyzer."},
                    {"role": "user", "content": CONCEPT_EXTRACTION_PROMPT.format(chunk_text=chunk["content"])}
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
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
                logger.error(f"Failed to parse JSON from concept extraction: {content[:100]}...")
                concepts = []
                
            # Track analytics (sync, fire-and-forget)
            cost = calculate_cost(model, usage.prompt_tokens, usage.completion_tokens)
            track_llm_call(
                user_id=user_id,
                trace_id=trace_id,
                call_type="extraction",
                model=model,
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
                latency_ms=latency_ms,
                cost_usd=cost,
                metadata={"chunk_id": chunk.get("id"), "document_id": document_id}
            )
            
            # Format for DB
            formatted_concepts = []
            for c in concepts:
                formatted_concepts.append({
                    "document_id": document_id,
                    "user_id": user_id,
                    "chunk_id": chunk.get("id"),
                    "name": c.get("name", "Unknown"),
                    "concept_type": c.get("type", "keyword"),
                    "relevance_score": float(c.get("relevance", 0.5)),
                    "source_text": c.get("source_text", ""),
                    "metadata": {}
                })
                
            return formatted_concepts
            
        except Exception as e:
            logger.error(f"Error extracting concepts from chunk: {str(e)}")
            # Track failure to Supabase (sync)
            track_llm_call(
                user_id=user_id,
                trace_id=trace_id,
                call_type="extraction",
                model=model,
                input_tokens=0,
                output_tokens=0,
                latency_ms=int((time.time() - start_time) * 1000),
                success=False,
                error_message=str(e)
            )
            # Capture to PostHog Error Tracking for proper stack traces
            capture_exception(
                exception=e,
                distinct_id=user_id,
                properties={
                    "quiz_type": "enhanced",
                    "stage": "concept_extraction",
                    "model": model,
                    "content_source_type": content_source_type,
                    "trace_id": trace_id,
                }
            )
            return []
