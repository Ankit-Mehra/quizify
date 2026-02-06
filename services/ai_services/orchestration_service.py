import json
import time
import random
from typing import Dict, Any, Optional, List

from services.ai_services.llm_client_service import get_groq_client, GROQ_ENHANCED_MODEL
from services.ai_services.context_service import ContextService
from services.ai_services.pricing import calculate_cost
from services.ai_services.explanation_service import ExplanationService
from services.ai_services.prompts import BLOOM_DESCRIPTIONS, RAG_QUESTION_TYPE_PROMPTS, RAG_PROMPT_MCQ
from services.db_services.supabase_llm_analytics import track_llm_call
from services.posthog_service import capture_exception
from services.logger import ai_logger as logger
from schemas.quiz import BloomLevel, Difficulty


# Minimum length for a valid explanation (shorter = likely just "X matches Y" or empty)
# 30 chars allows for at least one meaningful sentence fragment
MIN_EXPLANATION_LENGTH = 30

# Template for fallback matching explanation when LLM doesn't provide one
MATCHING_FALLBACK_TEMPLATE = "In this matching exercise: {pairs}. Understanding these relationships helps reinforce key concepts from the material."


def build_matching_fallback_explanation(left: List[str], right: List[str], correct_answer: List[int]) -> str:
    """
    Build a fallback explanation for matching questions when the LLM doesn't provide one.
    
    Args:
        left: List of items on the left side
        right: List of items on the right side  
        correct_answer: List of indices mapping left[i] to right[correct_answer[i]]
        
    Returns:
        A simple but useful explanation string
    """
    if not left or not right or not correct_answer:
        return ""
        
    pairs_desc = []
    for i, left_item in enumerate(left):
        if i < len(correct_answer) and correct_answer[i] < len(right):
            right_item = right[correct_answer[i]]
            pairs_desc.append(f"{left_item} corresponds to {right_item}")
    
    return MATCHING_FALLBACK_TEMPLATE.format(pairs="; ".join(pairs_desc))


class QuizOrchestrationService:
    """
    Orchestrates question generation using RAG-retrieved context.
    
    Supports Bloom's taxonomy levels and difficulty distribution.
    """
    
    def __init__(self):
        self.client = get_groq_client()
        self.context_service = ContextService()
        self.explanation_service = ExplanationService()

    @staticmethod
    def _format_source_snippet(
        context: str,
        *,
        max_words: int = 100,
        head_words: int | None = None,
        tail_words: int | None = None,
        separator: str = " [......] "
    ) -> str:
        """Return a compact snippet that includes both start and end of context.

        Uses word boundaries (not raw characters) so the snippet reads naturally.
        For long contexts, returns: <start words><separator><end words>.
        For short contexts, returns the context as-is.
        
        The default separator "[...]" is a standard editorial convention indicating
        omitted text, making it clearly visible that content has been truncated.
        """
        if not context:
            return ""

        words = context.split()
        if not words:
            return ""

        if len(words) <= max_words:
            return " ".join(words)

        if head_words is None and tail_words is None:
            head_words = max(0, max_words // 2)
            tail_words = max(0, max_words - head_words)
        else:
            head_words = max(0, head_words or 0)
            tail_words = max(0, tail_words or 0)

        # Ensure we never exceed the requested max word budget.
        if head_words + tail_words > max_words:
            head_words = max(0, max_words // 2)
            tail_words = max(0, max_words - head_words)

        parts = []
        if head_words > 0:
            parts.append(" ".join(words[:head_words]))
        
        parts.append(separator)
        
        if tail_words > 0:
            parts.append(" ".join(words[-tail_words:]))
            
        return " ".join(parts)
    
    def _validate_question_structure(self, result: Dict[str, Any], question_type: str) -> None:
        """
        Validate that LLM response has required fields for the question type.
        
        This catches malformed responses BEFORE expensive verification calls.
        Raises ValueError if validation fails.
        """
        if not result.get("question"):
            raise ValueError("Question text is missing or empty")
        
        if question_type == "multiple_choice":
            options = result.get("options")
            if not options or len(options) < 2:
                raise ValueError(f"MCQ requires at least 2 options, got: {options}")
            if not result.get("correct_answer"):
                raise ValueError("MCQ correct_answer is missing")
                
        elif question_type == "fill_blank":
            options = result.get("options")
            if not options or len(options) < 2:
                raise ValueError(f"Fill-blank requires at least 2 options, got: {options}")
            if not result.get("correct_answer"):
                raise ValueError("Fill-blank correct_answer is missing")
            # Check for blank marker in question
            question = result.get("question", "")
            if "_____" not in question and "____" not in question and "{{blank}}" not in question.lower():
                logger.warning("Fill-blank question may be missing blank marker: %s...", question[:50])
                
        elif question_type == "matching":
            left = result.get("left")
            right = result.get("right")
            correct_answer = result.get("correct_answer")
            
            if not left or not isinstance(left, list) or len(left) < 2:
                raise ValueError(f"Matching question requires 'left' list with at least 2 items, got: {left}")
            if not right or not isinstance(right, list) or len(right) < 2:
                raise ValueError(f"Matching question requires 'right' list with at least 2 items, got: {right}")
            if len(left) != len(right):
                raise ValueError(f"Matching 'left' ({len(left)}) and 'right' ({len(right)}) must have same length")
            if not correct_answer or not isinstance(correct_answer, list):
                raise ValueError(f"Matching correct_answer must be a list of indices, got: {correct_answer}")
            if len(correct_answer) != len(left):
                raise ValueError(f"Matching correct_answer length ({len(correct_answer)}) must match items ({len(left)})")
                
        elif question_type == "true_false":
            if result.get("correct_answer") is None:
                raise ValueError("True/false correct_answer is missing")
        
    async def generate_question_for_concept(
        self,
        concept: Dict[str, Any],
        question_type: str,
        user_id: str,
        user_token: str,
        trace_id: str,
        bloom_level: BloomLevel = BloomLevel.UNDERSTAND,
        difficulty: Difficulty = Difficulty.MEDIUM,
        content_source_type: str = "text"
    ) -> Dict[str, Any]:
        """
        Generate a single question for a concept.
        
        Args:
            concept: Concept dict with name, chunk_id, embedding, etc.
            question_type: multiple_choice, true_false, fill_blank (NOT matching)
            user_id: UUID of the user
            user_token: JWT token for RLS enforcement
            trace_id: Trace ID for analytics
            bloom_level: Target Bloom's taxonomy level
            difficulty: easy, medium, or hard
            content_source_type: Source type for analytics (text, file, url)
            
        Returns:
            Generated question dict with all fields
            
        Note:
            For matching questions, use generate_matching_question() instead
            which aggregates context from multiple concepts.
        """
        start_time = time.time()
        
        # Get Context (chunk + related chunks)
        context = self.context_service.get_context_for_concept(concept, user_token)
        
        # 3. Build Prompt - use question-type-specific prompt for clarity
        bloom_description = BLOOM_DESCRIPTIONS.get(bloom_level.value, "testing knowledge")
        
        # Select the appropriate prompt template for this question type
        prompt_template = RAG_QUESTION_TYPE_PROMPTS.get(question_type, RAG_PROMPT_MCQ)
        
        prompt = prompt_template.format(
            difficulty=difficulty.value,
            bloom_level=bloom_level.value,
            bloom_description=bloom_description,
            concept_name=concept["name"],
            concept_type=concept.get("concept_type", "general"),
            context=context
        )
        
        # 4. Call LLM
        # Use Groq (OpenAI-compatible) with llama-3.1-8b-instant for enhanced pipeline
        model = GROQ_ENHANCED_MODEL
        
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a professional quiz generator. Generate clear, educationally valuable questions."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
            )
            
            latency_ms = int((time.time() - start_time) * 1000)
            usage = response.usage
            content = response.choices[0].message.content
            
            # 5. Parse Response
            try:
                result = json.loads(content)
            except json.JSONDecodeError as exc:
                logger.error("Failed to parse JSON from question generation: %s...", content[:100])
                raise ValueError("Invalid JSON response from LLM") from exc
            
            # 5b. Pre-validate required fields BEFORE expensive verification call
            # This catches malformed LLM responses early and saves verification tokens
            self._validate_question_structure(result, question_type)
                
            # 6. Track Analytics (sync, fire-and-forget)
            cost = calculate_cost(model, usage.prompt_tokens, usage.completion_tokens)
            track_llm_call(
                user_id=user_id,
                trace_id=trace_id,
                call_type="generation",
                model=model,
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
                latency_ms=latency_ms,
                cost_usd=cost,
                metadata={
                    "concept_id": str(concept.get("id")),
                    "question_type": question_type,
                    "bloom_level": bloom_level.value,
                    "difficulty": difficulty.value,
                    "quiz_type": "enhanced",  # Epic 5.2: Tag RAG calls as enhanced
                    "pipeline": "rag_llama_index"  # Epic 5.2: Tag pipeline type
                }
            )
            
            # 7. Verify + Explain in ONE LLM call (50% faster than separate calls)
            is_valid, _confidence, issues, explanation, distractor_explanations = await self.explanation_service.verify_and_explain(
                question_data=result,
                context=context,
                user_id=user_id,
                trace_id=trace_id,
                content_source_type=content_source_type
            )
            
            if not is_valid:
                logger.warning("Question verification failed: %s", issues)
                # Strictly filter out low-quality questions
                raise ValueError(f"Question rejected by verification: {issues}")
            
            # 8. Format Result with metadata
            # Use .value for JSON serialization compatibility
            result["explanation"] = explanation
            # NEW: Add structured distractor explanations for MCQ and fill_blank
            # Frontend can choose to parse this or just use the main explanation field
            if distractor_explanations:
                result["distractor_explanations"] = distractor_explanations
            result["type"] = question_type
            result["bloom_level"] = bloom_level.value
            result["difficulty"] = difficulty.value
            # Convert UUIDs to strings for JSON serialization
            # Use .get() for optional fields from concept dict
            concept_id = concept.get("id")
            result["concept_id"] = str(concept_id) if concept_id else None
            result["concept_name"] = concept.get("name")
            chunk_id = concept.get("chunk_id")
            result["chunk_id"] = str(chunk_id) if chunk_id else None
            # Store source snippet (start + end) to keep context useful while bounded
            result["source"] = self._format_source_snippet(context)
            
            return result
            
        except Exception as e:
            logger.error("Error generating question: %s", e)
            # Track failure to Supabase (sync)
            track_llm_call(
                user_id=user_id,
                trace_id=trace_id,
                call_type="generation",
                model=GROQ_ENHANCED_MODEL,
                input_tokens=0,
                output_tokens=0,
                latency_ms=int((time.time() - start_time) * 1000),
                success=False,
                error_message=str(e)
            )
            # Capture to PostHog Error Tracking for proper stack traces
            # Uses capture_exception as per PostHog docs for error grouping
            capture_exception(
                exception=e,
                distinct_id=user_id,
                properties={
                    "generation_mode": "enhanced",
                    "stage": "rag_question_generation",
                    "model": GROQ_ENHANCED_MODEL,
                    "question_type": question_type,
                    "content_source_type": content_source_type,
                    "trace_id": trace_id,
                }
            )
            raise

    def assign_bloom_and_difficulty(
        self,
        num_questions: int,
        bloom_distribution: Optional[Dict[str, float]] = None,
        difficulty_distribution: Optional[Dict[str, float]] = None
    ) -> List[tuple]:
        """
        Generate a list of (bloom_level, difficulty) pairs for balanced question generation.
        
        Args:
            num_questions: Number of questions to generate
            bloom_distribution: Optional custom distribution (default: balanced)
            difficulty_distribution: Optional custom distribution (default: 30/50/20)
            
        Returns:
            List of (BloomLevel, Difficulty) tuples
        """
        # Default distributions
        if bloom_distribution is None:
            bloom_distribution = {
                "remember": 0.2,
                "understand": 0.35,
                "apply": 0.25,
                "analyze": 0.15,
                "evaluate": 0.05,
                "create": 0.0
            }
        
        if difficulty_distribution is None:
            difficulty_distribution = {
                "easy": 0.3,
                "medium": 0.5,
                "hard": 0.2
            }
        
        # Generate bloom levels based on distribution
        bloom_levels = []
        for level, weight in bloom_distribution.items():
            count = int(num_questions * weight)
            bloom_levels.extend([BloomLevel(level)] * count)
        
        # Fill remaining with UNDERSTAND
        while len(bloom_levels) < num_questions:
            bloom_levels.append(BloomLevel.UNDERSTAND)
        
        # Shuffle to distribute evenly
        random.shuffle(bloom_levels)
        
        # Generate difficulties based on distribution
        difficulties = []
        for diff, weight in difficulty_distribution.items():
            count = int(num_questions * weight)
            difficulties.extend([Difficulty(diff)] * count)
        
        # Fill remaining with MEDIUM
        while len(difficulties) < num_questions:
            difficulties.append(Difficulty.MEDIUM)
        
        random.shuffle(difficulties)
        
        return list(zip(bloom_levels[:num_questions], difficulties[:num_questions]))

    async def generate_matching_question(
        self,
        concepts: List[Dict[str, Any]],
        user_id: str,
        user_token: str,
        trace_id: str,
        bloom_level: BloomLevel = BloomLevel.UNDERSTAND,
        difficulty: Difficulty = Difficulty.MEDIUM,
        content_source_type: str = "text"
    ) -> Dict[str, Any]:
        """
        Generate a matching question using aggregated context from multiple concepts.
        
        Matching questions need 4 pairs, so we aggregate context from 4 concepts
        to give the LLM enough material to create meaningful matches.
        
        Args:
            concepts: List of 4 concept dicts to use for matching
            user_id: UUID of the user
            user_token: JWT token for RLS enforcement
            trace_id: Trace ID for analytics
            bloom_level: Target Bloom's taxonomy level
            difficulty: easy, medium, or hard
            content_source_type: Source type for analytics (text, file, url)
            
        Returns:
            Generated matching question dict with all fields
        """
        start_time = time.time()
        
        # Get aggregated context from multiple concepts
        context = self.context_service.get_aggregated_context_for_matching(concepts, user_token)
        
        if not context:
            raise ValueError("Could not aggregate context for matching question")
        
        # Build Prompt using matching template
        prompt_template = RAG_QUESTION_TYPE_PROMPTS.get("matching", RAG_PROMPT_MCQ)
        
        # Use first concept's name as topic, but note we're matching across concepts
        primary_concept = concepts[0] if concepts else {}
        concept_names = [c.get("name", "Unknown") for c in concepts[:4]]
        
        prompt = prompt_template.format(
            difficulty=difficulty.value,
            bloom_level=bloom_level.value,
            concept_name=", ".join(concept_names),
            context=context
        )
        
        # Call LLM
        model = GROQ_ENHANCED_MODEL
        
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a professional quiz generator. Generate clear, educationally valuable matching questions."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
            )
            
            latency_ms = int((time.time() - start_time) * 1000)
            usage = response.usage
            content = response.choices[0].message.content
            
            # Parse Response
            try:
                result = json.loads(content)
            except json.JSONDecodeError as exc:
                logger.error("Failed to parse JSON from matching generation: %s...", content[:100])
                raise ValueError("Invalid JSON response from LLM") from exc
            
            # Validate matching structure
            self._validate_question_structure(result, "matching")
            
            # Track Analytics
            cost = calculate_cost(model, usage.prompt_tokens, usage.completion_tokens)
            track_llm_call(
                user_id=user_id,
                trace_id=trace_id,
                call_type="matching_generation",
                model=model,
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
                latency_ms=latency_ms,
                cost_usd=cost,
                metadata={
                    "concept_count": len(concepts),
                    "question_type": "matching",
                    "bloom_level": bloom_level.value,
                    "difficulty": difficulty.value
                }
            )
            
            # For matching questions, explanation is generated inline during generation (faster)
            # No separate verification call needed - we trust the primary model
            explanation = result.get("explanation", "")
            
            # Fallback if generation didn't include explanation
            if not explanation or len(explanation) < MIN_EXPLANATION_LENGTH:
                explanation = build_matching_fallback_explanation(
                    left=result.get("left", []),
                    right=result.get("right", []),
                    correct_answer=result.get("correct_answer", [])
                )
                if explanation:
                    logger.info("Used fallback explanation for matching question")
            
            logger.info("Matching question generated successfully with %d pairs", len(result.get('left', [])))
            
            # Format Result
            result["explanation"] = explanation
            result["type"] = "matching"
            result["bloom_level"] = bloom_level.value
            result["difficulty"] = difficulty.value
            result["concept_id"] = str(primary_concept.get("id")) if primary_concept.get("id") else None
            result["concept_name"] = ", ".join(concept_names)
            result["chunk_id"] = None  # Multiple chunks used
            result["source"] = self._format_source_snippet(context)
            
            return result
            
        except Exception as e:
            logger.error("Error generating matching question: %s", e)
            # Track failure to Supabase
            track_llm_call(
                user_id=user_id,
                trace_id=trace_id,
                call_type="matching_generation",
                model=GROQ_ENHANCED_MODEL,
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
                    "generation_mode": "enhanced",
                    "stage": "rag_matching_generation",
                    "model": GROQ_ENHANCED_MODEL,
                    "question_type": "matching",
                    "content_source_type": content_source_type,
                    "trace_id": trace_id,
                }
            )
            raise
