"""
Flashcard Generation Service.

This service handles AI-powered flashcard generation from content.
It uses the ContentIngestionService for input processing and the
ILLMProvider abstraction for generation (supports OpenAI, Gemini, Groq).

Supports two generation modes:
- Standard: Fast, direct LLM generation (1 credit)
- Enhanced: RAG-based with concept extraction and context retrieval (2 credits)
"""

import time
import json
from typing import Optional, List, Dict, Any
from uuid import uuid4

from pydantic import ValidationError

from services.content.models import IngestedContent
from services.ai_services.prompts import build_flashcard_prompt_with_difficulty
from services.llm import get_llm_provider, LLMGenerationRequest, ILLMProvider
from services.logger import ai_logger as logger
from schemas.flashcard import (
    GeneratedFlashcard,
    FlashcardGenerationConfig,
)


# Constants
DEFAULT_CARDS_PER_100_WORDS = 1  # ~1 card per 100 words of content
MIN_CARDS = 3  # Minimum cards to generate
MAX_CARDS_PER_REQUEST = 50  # Maximum cards per single LLM request
MAX_CONTENT_TOKENS = 6000  # Max tokens to send to LLM in single request


class FlashcardGenerationError(Exception):
    """Raised when flashcard generation fails."""
    
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        self.message = message
        self.original_error = original_error
        super().__init__(self.message)


class FlashcardParseError(FlashcardGenerationError):
    """Raised when AI response cannot be parsed into flashcards."""
    
    def __init__(self, message: str, raw_response: Optional[str] = None):
        super().__init__(message)
        self.raw_response = raw_response


class FlashcardGenerationService:
    """
    Service for generating flashcards using AI.
    
    This service takes ingested content and generates flashcards using
    the configured LLM provider (OpenAI, Gemini, or Groq) via the
    ILLMProvider abstraction layer.
    
    Example usage:
        service = FlashcardGenerationService()
        
        # Generate from content
        content = await ingestion_service.ingest_text("Educational content...")
        flashcards = await service.generate(content, config)
        
        # Or with custom parameters
        flashcards = await service.generate(
            content,
            config=FlashcardGenerationConfig(
                num_cards=20,
                card_style="mixed",
                include_hints=True
            ),
            user_id="user-123",
            trace_id="trace-456"
        )
        
        # Or with a specific provider
        service = FlashcardGenerationService(provider_name="gemini")
    """
    
    def __init__(self, provider_name: Optional[str] = None):
        """
        Initialize the flashcard generation service.
        
        Args:
            provider_name: LLM provider to use (default: config.DEFAULT_LLM_PROVIDER).
                          Supported: "openai", "gemini", "groq"
        """
        self.provider: ILLMProvider = get_llm_provider(provider_name)
    
    async def generate(
        self,
        content: IngestedContent,
        generation_config: Optional[FlashcardGenerationConfig] = None,
        user_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> List[GeneratedFlashcard]:
        """
        Generate flashcards from ingested content.
        
        Args:
            content: The ingested content to generate flashcards from
            generation_config: Configuration for generation (card count, style, etc.)
            user_id: User ID for analytics tracking
            trace_id: Trace ID for request correlation
            
        Returns:
            List of GeneratedFlashcard objects
            
        Raises:
            FlashcardGenerationError: If generation fails
            FlashcardParseError: If AI response cannot be parsed
        """
        start_time = time.time()
        trace_id = trace_id or str(uuid4())
        generation_config = generation_config or FlashcardGenerationConfig()
        
        logger.info(
            "Starting flashcard generation for user %s, trace: %s, word_count: %d",
            user_id[:8] if user_id else "unknown",
            trace_id[:8],
            content.word_count
        )
        
        # Calculate number of cards to generate
        num_cards = self._calculate_card_count(content, generation_config)
        logger.debug("Calculated %d cards to generate", num_cards)
        
        # Check if content needs chunking
        if content.word_count > 3000:  # ~3000 words is roughly 4k tokens
            logger.info("Content is long (%d words), using chunked generation", content.word_count)
            flashcards = await self._generate_chunked(
                content, num_cards, generation_config, user_id, trace_id
            )
        else:
            flashcards = await self._generate_single(
                content.text, num_cards, generation_config, user_id, trace_id
            )
        
        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.info(
            "Flashcard generation completed: %d cards in %dms",
            len(flashcards), elapsed_ms
        )
        
        return flashcards
    
    async def _generate_single(
        self,
        text: str,
        num_cards: int,
        generation_config: FlashcardGenerationConfig,
        user_id: Optional[str],
        trace_id: str,
    ) -> List[GeneratedFlashcard]:
        """
        Generate flashcards from a single text chunk.
        
        Args:
            text: Text content to generate from
            num_cards: Number of cards to generate
            generation_config: Generation configuration
            user_id: User ID for tracking
            trace_id: Trace ID for correlation
            
        Returns:
            List of generated flashcards
        """
        # Build the prompt
        prompt = build_flashcard_prompt_with_difficulty(
            text=text,
            num_cards=num_cards,
            difficulty=generation_config.difficulty,
            card_style=generation_config.card_style,
            include_hints=generation_config.include_hints,
        )
        
        # Build analytics properties
        properties = {
            "feature": "flashcard_generation",
            "num_cards": num_cards,
            "content_length": len(text),
            "difficulty": generation_config.difficulty,
            "card_style": generation_config.card_style,
            "model": self.provider.default_model,
            "provider": self.provider.provider_name,
        }
        
        # Create system message for flashcard generation
        system_message = "You are a flashcard generation expert. Always respond with valid JSON only, no additional text."
        
        # Call the LLM with retry logic via provider abstraction
        try:
            response = await self.provider.generate(LLMGenerationRequest(
                prompt=prompt,
                system_message=system_message,
                response_format="json_object",
                temperature=0.7,
                max_tokens=4000,
                user_id=user_id,
                trace_id=trace_id,
                properties=properties,
            ))
        except Exception as e:  # noqa: BLE001
            logger.error("LLM call failed for flashcard generation: %s", str(e))
            raise FlashcardGenerationError(
                message=f"Failed to generate flashcards: {str(e)}",
                original_error=e
            ) from e
        
        # Parse the response
        raw_content = response.content
        flashcards = self._parse_response(raw_content)
        
        # Log token usage for analytics
        if response.usage:
            logger.debug(
                "Token usage - input: %d, output: %d, total: %d",
                response.usage.get("prompt_tokens", 0),
                response.usage.get("completion_tokens", 0),
                response.usage.get("total_tokens", 0)
            )
        
        return flashcards
    
    async def _generate_chunked(
        self,
        content: IngestedContent,
        total_cards: int,
        config: FlashcardGenerationConfig,
        user_id: Optional[str],
        trace_id: str,
    ) -> List[GeneratedFlashcard]:
        """
        Generate flashcards from long content by processing in chunks.
        
        Args:
            content: Full ingested content
            total_cards: Total number of cards to generate
            config: Generation configuration
            user_id: User ID for tracking
            trace_id: Trace ID for correlation
            
        Returns:
            Combined list of flashcards from all chunks
        """
        # Split content into chunks
        chunks = self._split_into_chunks(content.text)
        logger.info("Split content into %d chunks", len(chunks))
        
        # Calculate cards per chunk (distribute evenly)
        cards_per_chunk = max(MIN_CARDS, total_cards // len(chunks))
        remainder = total_cards % len(chunks)
        
        all_flashcards: List[GeneratedFlashcard] = []
        
        for i, chunk in enumerate(chunks):
            # Add remainder cards to first chunks
            chunk_cards = cards_per_chunk + (1 if i < remainder else 0)
            
            logger.debug("Processing chunk %d/%d, generating %d cards", i + 1, len(chunks), chunk_cards)
            
            try:
                chunk_flashcards = await self._generate_single(
                    text=chunk,
                    num_cards=chunk_cards,
                    generation_config=config,
                    user_id=user_id,
                    trace_id=f"{trace_id}-chunk{i}",
                )
                all_flashcards.extend(chunk_flashcards)
            except Exception:  # noqa: BLE001
                logger.warning("Chunk %d failed, continuing with others", i + 1, exc_info=True)
                continue
        
        if not all_flashcards:
            raise FlashcardGenerationError("Failed to generate flashcards from any chunk")
        
        # Deduplicate similar cards
        deduped_flashcards = self._deduplicate_cards(all_flashcards)
        
        return deduped_flashcards[:total_cards]  # Trim to requested count
    
    def _calculate_card_count(
        self,
        content: IngestedContent,
        config: FlashcardGenerationConfig
    ) -> int:
        """
        Calculate the number of flashcards to generate.
        
        If num_cards is specified in config, use that.
        Otherwise, calculate based on content length (~1 card per 100 words).
        
        Args:
            content: The ingested content
            config: Generation configuration
            
        Returns:
            Number of cards to generate
        """
        if config.num_cards is not None:
            return min(config.num_cards, MAX_CARDS_PER_REQUEST * 2)
        
        # Auto-calculate based on word count
        calculated = max(
            MIN_CARDS,
            content.word_count // 100 * DEFAULT_CARDS_PER_100_WORDS
        )
        
        # Cap at reasonable maximum
        return min(calculated, 100)
    
    def _split_into_chunks(self, text: str, max_words: int = 2500) -> List[str]:
        """
        Split text into chunks for processing.
        
        Tries to split at paragraph boundaries to maintain context.
        
        Args:
            text: Full text to split
            max_words: Maximum words per chunk
            
        Returns:
            List of text chunks
        """
        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = []
        current_word_count = 0
        
        for para in paragraphs:
            para_words = len(para.split())
            
            if current_word_count + para_words > max_words and current_chunk:
                # Save current chunk and start new one
                chunks.append("\n\n".join(current_chunk))
                current_chunk = [para]
                current_word_count = para_words
            else:
                current_chunk.append(para)
                current_word_count += para_words
        
        # Don't forget the last chunk
        if current_chunk:
            chunks.append("\n\n".join(current_chunk))
        
        return chunks
    
    def _parse_response(self, raw_content: str) -> List[GeneratedFlashcard]:
        """
        Parse the LLM response into flashcard objects.
        
        Args:
            raw_content: Raw JSON string from LLM
            
        Returns:
            List of GeneratedFlashcard objects
            
        Raises:
            FlashcardParseError: If parsing fails
        """
        try:
            data = json.loads(raw_content)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse JSON response: %s", str(e))
            raise FlashcardParseError(
                message="Failed to parse AI response as JSON",
                raw_response=raw_content[:500]
            ) from e
        
        # Handle different response formats
        cards_data = data.get("cards", [])
        if not cards_data:
            # Try alternative keys
            cards_data = data.get("flashcards", data.get("items", []))
        
        if not cards_data:
            logger.error("No cards found in response: %s", raw_content[:200])
            raise FlashcardParseError(
                message="AI response did not contain any flashcards",
                raw_response=raw_content[:500]
            )
        
        flashcards = []
        for i, card_data in enumerate(cards_data):
            try:
                # Handle variations in field names
                front = card_data.get("front", card_data.get("question", card_data.get("term", "")))
                back = card_data.get("back", card_data.get("answer", card_data.get("definition", "")))
                hint = card_data.get("hint")
                
                if not front or not back:
                    logger.warning("Skipping card %d with missing front/back", i)
                    continue
                
                flashcard = GeneratedFlashcard(
                    front=front.strip(),
                    back=back.strip(),
                    hint=hint.strip() if hint else None
                )
                flashcards.append(flashcard)
            except ValidationError as e:
                logger.warning("Failed to validate card %d: %s", i, str(e))
                continue
        
        if not flashcards:
            raise FlashcardParseError(
                message="Failed to parse any valid flashcards from AI response",
                raw_response=raw_content[:500]
            )
        
        return flashcards
    
    def _deduplicate_cards(
        self,
        flashcards: List[GeneratedFlashcard],
        similarity_threshold: float = 0.8
    ) -> List[GeneratedFlashcard]:
        """
        Remove duplicate or very similar flashcards.
        
        Uses simple string similarity to detect duplicates.
        
        Args:
            flashcards: List of flashcards to deduplicate
            similarity_threshold: Threshold for considering cards as duplicates
            
        Returns:
            Deduplicated list of flashcards
        """
        if len(flashcards) <= 1:
            return flashcards
        
        unique_cards = []
        seen_fronts = set()
        
        for card in flashcards:
            # Normalize front text for comparison
            normalized = card.front.lower().strip()
            
            # Check if we've seen a very similar front
            is_duplicate = False
            for seen in seen_fronts:
                if self._is_similar(normalized, seen, similarity_threshold):
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique_cards.append(card)
                seen_fronts.add(normalized)
        
        removed_count = len(flashcards) - len(unique_cards)
        if removed_count > 0:
            logger.info("Removed %d duplicate flashcards", removed_count)
        
        return unique_cards
    
    def _is_similar(self, text1: str, text2: str, threshold: float) -> bool:
        """
        Check if two texts are similar using simple word overlap.
        
        Args:
            text1: First text
            text2: Second text
            threshold: Similarity threshold (0-1)
            
        Returns:
            True if texts are similar above threshold
        """
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        if not words1 or not words2:
            return False
        
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        similarity = intersection / union if union > 0 else 0
        return similarity >= threshold


class EnhancedFlashcardGenerationService:
    """
    Enhanced flashcard generation using RAG pipeline.
    
    This service uses concept extraction, context retrieval, and
    Bloom's taxonomy to generate higher-quality flashcards.
    
    Requires:
    - RAGIngestionService for document/chunk management
    - ConceptExtractionService for identifying key concepts
    - ContextService for retrieving relevant context
    
    Example usage:
        service = EnhancedFlashcardGenerationService()
        
        result = await service.generate_enhanced(
            content="Educational content...",
            title="My Document",
            config=FlashcardGenerationConfig(
                num_cards=20,
                mode="enhanced"
            ),
            user_id="user-123",
            user_token="jwt-token",
            trace_id="trace-456"
        )
        
        # Result includes enhanced metadata
        flashcards = result["flashcards"]
        stats = result["generation_stats"]  # concepts, chunks, etc.
    """
    
    def __init__(self, provider_name: Optional[str] = None):
        """Initialize the enhanced flashcard service with dependencies."""
        self.provider: ILLMProvider = get_llm_provider(provider_name)
        
        # Lazy import to avoid circular dependencies
        from services.content.rag_ingestion_service import RAGIngestionService
        from services.ai_services.concept_extraction_service import ConceptExtractionService
        from services.ai_services.context_service import ContextService
        
        self.rag_service = RAGIngestionService()
        self.concept_service = ConceptExtractionService()
        self.context_service = ContextService()
    
    async def generate_enhanced(
        self,
        content: str,
        title: str,
        config: FlashcardGenerationConfig,
        user_id: str,
        user_token: str,
        trace_id: Optional[str] = None,
        content_source_type: str = "text",
    ) -> Dict[str, Any]:
        """
        Generate flashcards using the enhanced RAG pipeline.
        
        This method:
        1. Ingests content into the RAG pipeline (creates document + chunks)
        2. Extracts key concepts from the content
        3. Retrieves context for each concept
        4. Generates flashcards for each concept with Bloom's levels
        5. Returns flashcards with enhanced metadata
        
        Args:
            content: Text content to generate flashcards from
            title: Document title
            config: Generation configuration
            user_id: UUID of the requesting user
            user_token: JWT token for RLS enforcement
            trace_id: Trace ID for analytics
            content_source_type: Source type ("text", "file", "url")
            
        Returns:
            Dict with:
            - flashcards: List[GeneratedFlashcard] with enhanced fields
            - generation_stats: Dict with concepts, chunks, timing info
        """
        from services.ai_services.prompts import build_enhanced_flashcard_prompt
        
        start_time = time.time()
        trace_id = trace_id or str(uuid4())
        
        logger.info(
            "Starting enhanced flashcard generation for user %s..., trace: %s",
            user_id[:8], trace_id[:8]
        )
        
        # Step 1: Ingest content into RAG pipeline
        t0 = time.time()
        ingestion_result = await self.rag_service.ingest_content(
            user_id=user_id,
            user_token=user_token,
            content=content,
            title=title,
            source_type=content_source_type,
            trace_id=trace_id
        )
        document_id = ingestion_result["document_id"]
        chunks = ingestion_result.get("chunks", [])
        ingest_time = time.time() - t0
        logger.info("[TIMING] RAG ingestion took %.2fs, %d chunks", ingest_time, len(chunks))
        
        # Step 2: Extract concepts from chunks
        t1 = time.time()
        concepts = await self.concept_service.extract_concepts(
            chunks=chunks,
            user_id=user_id,
            user_token=user_token,
            document_id=document_id,
            trace_id=trace_id
        )
        concept_time = time.time() - t1
        logger.info("[TIMING] Concept extraction took %.2fs, %d concepts", concept_time, len(concepts))
        
        if not concepts:
            logger.warning("No concepts extracted, falling back to standard generation")
            # Fall back to standard generation
            standard_service = FlashcardGenerationService(provider_name=self.provider.provider_name)
            word_count = len(content.split())
            ingested_content = IngestedContent(
                text=content,
                word_count=word_count,
                char_count=len(content),
                title=title,
                source_type=content_source_type,
                metadata={}
            )
            flashcards = await standard_service.generate(
                ingested_content, config, user_id, trace_id
            )
            return {
                "flashcards": flashcards,
                "generation_stats": {
                    "mode": "enhanced_fallback",
                    "concepts_extracted": 0,
                    "chunks_processed": len(chunks),
                    "fallback_reason": "no_concepts_extracted"
                }
            }
        
        # Step 3: Calculate cards per concept
        num_cards = config.num_cards or self._estimate_cards(len(content.split()))
        cards_per_concept = max(1, num_cards // len(concepts))
        remaining_cards = num_cards - (cards_per_concept * len(concepts))
        
        # Step 4: Generate flashcards for each concept
        t2 = time.time()
        all_flashcards: List[GeneratedFlashcard] = []
        
        for i, concept in enumerate(concepts):
            # Give extra cards to top-relevance concepts
            concept_cards = cards_per_concept
            if remaining_cards > 0 and concept.get("relevance", 0) > 0.7:
                concept_cards += 1
                remaining_cards -= 1
            
            # Get context for this concept
            context = self.context_service.get_context_for_concept(
                concept=concept,
                user_token=user_token
            )
            
            # Build enhanced prompt
            prompt = build_enhanced_flashcard_prompt(
                concept_name=concept.get("name", "Unknown Concept"),
                context=context,
                num_cards=concept_cards,
                card_style=config.card_style,
                difficulty=config.difficulty,
            )
            
            # Generate flashcards for this concept
            try:
                cards = await self._generate_for_concept(
                    prompt=prompt,
                    concept=concept,
                    user_id=user_id,
                    trace_id=trace_id,
                )
                all_flashcards.extend(cards)
            except Exception as e:
                logger.warning(
                    "Failed to generate cards for concept '%s': %s",
                    concept.get("name"), str(e)
                )
                continue
        
        gen_time = time.time() - t2
        logger.info("[TIMING] Flashcard generation took %.2fs, %d cards", gen_time, len(all_flashcards))
        
        # Step 5: Deduplicate cards
        unique_flashcards = self._deduplicate_cards(all_flashcards)
        
        total_time = time.time() - start_time
        
        return {
            "flashcards": unique_flashcards,
            "generation_stats": {
                "mode": "enhanced",
                "concepts_extracted": len(concepts),
                "chunks_processed": len(chunks),
                "cards_generated": len(unique_flashcards),
                "duplicates_removed": len(all_flashcards) - len(unique_flashcards),
                "timing_ms": {
                    "ingestion": int(ingest_time * 1000),
                    "concept_extraction": int(concept_time * 1000),
                    "flashcard_generation": int(gen_time * 1000),
                    "total": int(total_time * 1000)
                }
            }
        }
    
    async def _generate_for_concept(
        self,
        prompt: str,
        concept: Dict[str, Any],
        user_id: str,
        trace_id: str,
    ) -> List[GeneratedFlashcard]:
        """
        Generate flashcards for a single concept.
        
        Args:
            prompt: The enhanced prompt for this concept
            concept: Concept dictionary with name, chunk_id, etc.
            user_id: User ID for analytics
            trace_id: Trace ID for correlation
            
        Returns:
            List of GeneratedFlashcard with enhanced metadata
        """
        system_message = "You are an expert educational flashcard creator. Always respond with valid JSON only."
        
        properties = {
            "feature": "flashcard_generation_enhanced",
            "concept": concept.get("name"),
            "model": self.provider.default_model,
            "provider": self.provider.provider_name,
        }
        
        try:
            response = await self.provider.generate(LLMGenerationRequest(
                prompt=prompt,
                system_message=system_message,
                response_format="json_object",
                temperature=0.7,
                max_tokens=2000,
                user_id=user_id,
                trace_id=trace_id,
                properties=properties,
            ))
        except Exception as e:
            logger.error("LLM call failed for concept '%s': %s", concept.get("name"), str(e))
            raise FlashcardGenerationError(
                message=f"Failed to generate flashcards for concept: {str(e)}",
                original_error=e
            ) from e
        
        # Parse response with enhanced fields
        return self._parse_enhanced_response(
            raw_content=response.content,
            concept=concept
        )
    
    def _parse_enhanced_response(
        self,
        raw_content: str,
        concept: Dict[str, Any]
    ) -> List[GeneratedFlashcard]:
        """
        Parse LLM response into GeneratedFlashcard objects with enhanced metadata.
        
        Args:
            raw_content: Raw JSON response from LLM
            concept: Concept dictionary for metadata enrichment
            
        Returns:
            List of GeneratedFlashcard with concept metadata
        """
        try:
            data = json.loads(raw_content)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse JSON response: %s", str(e))
            raise FlashcardParseError(
                message="Invalid JSON in AI response",
                raw_response=raw_content[:500]
            ) from e
        
        # Extract cards array (handle both "cards" and "flashcards" keys)
        cards_data = data.get("cards", data.get("flashcards", []))
        if not isinstance(cards_data, list):
            raise FlashcardParseError(
                message="Response does not contain a cards array",
                raw_response=raw_content[:500]
            )
        
        flashcards = []
        for i, card in enumerate(cards_data):
            try:
                flashcard = GeneratedFlashcard(
                    front=card.get("front", "").strip(),
                    back=card.get("back", "").strip(),
                    hint=card.get("hint", "").strip() if card.get("hint") else None,
                    # Enhanced metadata
                    concept_name=concept.get("name"),
                    bloom_level=card.get("bloom_level"),
                    difficulty_score=card.get("difficulty_score"),
                    source_chunk_id=concept.get("chunk_id"),
                )
                flashcards.append(flashcard)
            except ValidationError as e:
                logger.warning("Failed to validate enhanced card %d: %s", i, str(e))
                continue
        
        return flashcards
    
    def _estimate_cards(self, word_count: int) -> int:
        """Estimate appropriate number of cards based on content length."""
        cards = max(MIN_CARDS, word_count // 100)
        return min(cards, MAX_CARDS_PER_REQUEST)
    
    def _deduplicate_cards(
        self,
        flashcards: List[GeneratedFlashcard],
        similarity_threshold: float = 0.8
    ) -> List[GeneratedFlashcard]:
        """Remove duplicate or very similar flashcards."""
        if len(flashcards) <= 1:
            return flashcards
        
        unique_cards = []
        seen_fronts = set()
        
        for card in flashcards:
            normalized = card.front.lower().strip()
            
            is_duplicate = False
            for seen in seen_fronts:
                words1 = set(normalized.split())
                words2 = set(seen.split())
                if words1 and words2:
                    intersection = len(words1 & words2)
                    union = len(words1 | words2)
                    if union > 0 and (intersection / union) >= similarity_threshold:
                        is_duplicate = True
                        break
            
            if not is_duplicate:
                unique_cards.append(card)
                seen_fronts.add(normalized)
        
        return unique_cards


# Singleton instances
_flashcard_service: Optional[FlashcardGenerationService] = None
_enhanced_flashcard_service: Optional[EnhancedFlashcardGenerationService] = None


def get_flashcard_generation_service() -> FlashcardGenerationService:
    """Get or create the singleton FlashcardGenerationService instance."""
    global _flashcard_service  # noqa: PLW0603  # type: ignore[global-statement]
    if _flashcard_service is None:
        _flashcard_service = FlashcardGenerationService()
    return _flashcard_service


def get_enhanced_flashcard_service() -> EnhancedFlashcardGenerationService:
    """Get or create the singleton EnhancedFlashcardGenerationService instance."""
    global _enhanced_flashcard_service  # noqa: PLW0603  # type: ignore[global-statement]
    if _enhanced_flashcard_service is None:
        _enhanced_flashcard_service = EnhancedFlashcardGenerationService()
    return _enhanced_flashcard_service
