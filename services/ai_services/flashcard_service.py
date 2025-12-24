"""
Flashcard Generation Service.

This service handles AI-powered flashcard generation from content.
It uses the ContentIngestionService for input processing and the
OpenAI service for generation.
"""

import time
import json
from typing import Optional, List
from uuid import uuid4

from pydantic import ValidationError

from services.content.models import IngestedContent
from services.ai_services.prompts import build_flashcard_prompt_with_difficulty
from services.ai_services.llm_client_service import get_openai_client, _retry_with_backoff
from services.logger import ai_logger as logger
from schemas.flashcard import (
    GeneratedFlashcard,
    FlashcardGenerationConfig,
)
from config import config


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
    OpenAI's GPT models with structured output.
    
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
    """
    
    def __init__(self):
        """Initialize the flashcard generation service."""
        self.client = get_openai_client()
        self.model = config.LLM_MODEL_MINI  # Use mini model for flashcard generation
    
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
        config: FlashcardGenerationConfig,
        user_id: Optional[str],
        trace_id: str,
    ) -> List[GeneratedFlashcard]:
        """
        Generate flashcards from a single text chunk.
        
        Args:
            text: Text content to generate from
            num_cards: Number of cards to generate
            config: Generation configuration
            user_id: User ID for tracking
            trace_id: Trace ID for correlation
            
        Returns:
            List of generated flashcards
        """
        # Build the prompt
        prompt = build_flashcard_prompt_with_difficulty(
            text=text,
            num_cards=num_cards,
            difficulty=config.difficulty,
            card_style=config.card_style,
            include_hints=config.include_hints,
        )
        
        # Call the LLM with retry logic
        try:
            response = await _retry_with_backoff(
                lambda: self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a flashcard generation expert. Always respond with valid JSON only, no additional text."
                        },
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.7,
                    max_tokens=4000,
                    response_format={"type": "json_object"},
                )
            )
        except Exception as e:
            logger.error("LLM call failed for flashcard generation: %s", str(e))
            raise FlashcardGenerationError(
                message=f"Failed to generate flashcards: {str(e)}",
                original_error=e
            )
        
        # Parse the response
        raw_content = response.choices[0].message.content
        flashcards = self._parse_response(raw_content)
        
        # Log token usage for analytics
        if response.usage:
            logger.debug(
                "Token usage - input: %d, output: %d, total: %d",
                response.usage.prompt_tokens,
                response.usage.completion_tokens,
                response.usage.total_tokens
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
                    config=config,
                    user_id=user_id,
                    trace_id=f"{trace_id}-chunk{i}",
                )
                all_flashcards.extend(chunk_flashcards)
            except Exception as e:
                logger.warning("Chunk %d failed, continuing with others: %s", i + 1, str(e))
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
            )
        
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


# Singleton instance
_flashcard_service: Optional[FlashcardGenerationService] = None


def get_flashcard_generation_service() -> FlashcardGenerationService:
    """Get or create the singleton FlashcardGenerationService instance."""
    global _flashcard_service
    if _flashcard_service is None:
        _flashcard_service = FlashcardGenerationService()
    return _flashcard_service
