import json
import time
import random
from typing import Literal, Dict, Any, Optional, List

from services.ai_services.openai_service import get_openai_client, _build_posthog_kwargs
from services.ai_services.context_service import ContextService
from services.ai_services.pricing import calculate_cost
from services.ai_services.explanation_service import ExplanationService
from services.db_services.supabase_llm_analytics import track_llm_call
from services.logger import ai_logger as logger
from schemas.quiz import BloomLevel, Difficulty

# Bloom level descriptions for prompting
BLOOM_DESCRIPTIONS = {
    "remember": "recall of facts and basic concepts (define, list, name)",
    "understand": "explaining ideas or concepts (describe, summarize, explain)",
    "apply": "using information in new situations (demonstrate, solve, use)",
    "analyze": "drawing connections among ideas (compare, contrast, differentiate)",
    "evaluate": "justifying a decision (argue, defend, critique)",
    "create": "producing original work (design, construct, propose)"
}

# Question-type specific prompts to avoid confusion
# Each prompt shows EXACTLY what JSON format is expected for that type

PROMPT_MCQ = """You are an expert educational content creator.
Create a {difficulty} difficulty multiple choice question at the {bloom_level} Bloom's Taxonomy level.

Target Concept: {concept_name}
Concept Type: {concept_type}
Bloom Level: {bloom_description}

Context:
{context}

Requirements:
1. Question must be clear, unambiguous, and directly test the concept.
2. Provide exactly 4 options with 1 correct answer and 3 plausible distractors.
3. Do NOT use labels like "A)", "B)", "1." in options - just the text.
4. correct_answer must exactly match one of the options.

Return this exact JSON format:
{{
  "question": "Your question text here?",
  "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
  "correct_answer": "Option 1",
  "confidence_score": 0.95
}}
"""

PROMPT_TRUE_FALSE = """You are an expert educational content creator.
Create a {difficulty} difficulty true/false question at the {bloom_level} Bloom's Taxonomy level.

Target Concept: {concept_name}
Concept Type: {concept_type}
Bloom Level: {bloom_description}

Context:
{context}

Requirements:
1. Create a statement that is clearly true or false based on the context.
2. The statement should test understanding, not trick the reader.
3. correct_answer must be a boolean: true or false.

Return this exact JSON format:
{{
  "question": "Statement that is either true or false.",
  "correct_answer": true,
  "confidence_score": 0.95
}}
"""

PROMPT_FILL_BLANK = """You are an expert educational content creator.
Create a {difficulty} difficulty fill-in-the-blank question at the {bloom_level} Bloom's Taxonomy level.

Target Concept: {concept_name}
Concept Type: {concept_type}
Bloom Level: {bloom_description}

Context:
{context}

Requirements:
1. Create a sentence with ONE key term removed, marked with _____ (five underscores).
2. You MUST provide exactly 4 options including the correct answer.
3. Options should be plausible alternatives to make the question challenging.
4. correct_answer must exactly match one of the options.

Return this exact JSON format:
{{
  "question": "The _____ is responsible for generating ATP in cells.",
  "options": ["mitochondria", "nucleus", "ribosome", "cytoplasm"],
  "correct_answer": "mitochondria",
  "confidence_score": 0.95
}}
"""

PROMPT_MATCHING = """You are an expert educational content creator.
Create a {difficulty} difficulty matching question at the {bloom_level} Bloom's Taxonomy level.

Target Concept: {concept_name}
Concept Type: {concept_type}
Bloom Level: {bloom_description}

Context:
{context}

Requirements:
1. Create exactly 4 pairs of related items to match.
2. "left" contains 4 items (e.g., terms, names, concepts).
3. "right" contains 4 corresponding matches (e.g., definitions, discoveries, descriptions).
4. "correct_answer" is a list of 4 indices showing which right item matches each left item.
   - Index 0 means the first item in "right" matches the corresponding "left" item.
   - Example: [0, 1, 2, 3] means left[0]→right[0], left[1]→right[1], etc.
   - Example: [2, 0, 3, 1] means left[0]→right[2], left[1]→right[0], etc.

Return this exact JSON format:
{{
  "question": "Match each scientist with their discovery.",
  "left": ["Einstein", "Newton", "Curie", "Darwin"],
  "right": ["Relativity", "Gravity", "Radioactivity", "Evolution"],
  "correct_answer": [0, 1, 2, 3],
  "confidence_score": 0.95
}}
"""

# Map question types to their specific prompts
QUESTION_TYPE_PROMPTS = {
    "multiple_choice": PROMPT_MCQ,
    "true_false": PROMPT_TRUE_FALSE,
    "fill_blank": PROMPT_FILL_BLANK,
    "matching": PROMPT_MATCHING,
}


class QuizOrchestrationService:
    """
    Orchestrates question generation using RAG-retrieved context.
    
    Supports Bloom's taxonomy levels and difficulty distribution.
    """
    
    def __init__(self):
        self.client = get_openai_client()
        self.context_service = ContextService()
        self.explanation_service = ExplanationService()
    
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
                raise ValueError(f"Fill-blank requires options, got: {options}")
            if not result.get("correct_answer"):
                raise ValueError("Fill-blank correct_answer is missing")
            # Check for blank marker in question
            question = result.get("question", "")
            if "_____" not in question and "____" not in question and "{{blank}}" not in question.lower():
                logger.warning(f"Fill-blank question may be missing blank marker: {question[:50]}...")
                
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
        mode: Literal["standard", "enhanced"] = "standard"
    ) -> Dict[str, Any]:
        """
        Generate a single question for a concept.
        
        Args:
            concept: Concept dict with name, chunk_id, embedding, etc.
            question_type: multiple_choice, true_false, fill_blank, matching
            user_id: UUID of the user
            user_token: JWT token for RLS enforcement
            trace_id: Trace ID for analytics
            bloom_level: Target Bloom's taxonomy level
            difficulty: easy, medium, or hard
            mode: "standard" or "enhanced" context retrieval
            
        Returns:
            Generated question dict with all fields
        """
        start_time = time.time()
        
        # 1. Determine context mode based on question type
        if mode == "standard":
            # Check if we should use enhanced mode
            mode = self.context_service.determine_context_mode(
                question_type=question_type,
                bloom_level=bloom_level.value
            )
        
        # 2. Get Context (sync call - fast enough for single chunk)
        context = self.context_service.get_context_for_concept(concept, user_token, mode)
        
        # 3. Build Prompt - use question-type-specific prompt for clarity
        bloom_description = BLOOM_DESCRIPTIONS.get(bloom_level.value, "testing knowledge")
        
        # Select the appropriate prompt template for this question type
        prompt_template = QUESTION_TYPE_PROMPTS.get(question_type, PROMPT_MCQ)
        
        prompt = prompt_template.format(
            difficulty=difficulty.value,
            bloom_level=bloom_level.value,
            bloom_description=bloom_description,
            concept_name=concept["name"],
            concept_type=concept.get("concept_type", "general"),
            context=context
        )
        
        # 4. Call LLM with PostHog tracking
        model = "gpt-4o"  # Use stronger model for generation
        posthog_kwargs = _build_posthog_kwargs(
            user_id=user_id,
            trace_id=trace_id,
            properties={"call_type": "question_generation", "bloom_level": bloom_level.value}
        )
        
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a professional quiz generator. Generate clear, educationally valuable questions."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
                **posthog_kwargs
            )
            
            latency_ms = int((time.time() - start_time) * 1000)
            usage = response.usage
            content = response.choices[0].message.content
            
            # 5. Parse Response
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                logger.error(f"Failed to parse JSON from question generation: {content[:100]}...")
                raise ValueError("Invalid JSON response from LLM")
            
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
                    "mode": mode
                }
            )
            
            # 7. Verify + Explain in ONE LLM call (50% faster than separate calls)
            is_valid, confidence, issues, explanation = await self.explanation_service.verify_and_explain(
                question_data=result,
                context=context,
                user_id=user_id,
                trace_id=trace_id
            )
            
            if not is_valid:
                logger.warning(f"Question verification failed: {issues}")
                # Strictly filter out low-quality questions
                raise ValueError(f"Question rejected by verification: {issues}")
            
            # 8. Format Result with metadata
            # Use .value for JSON serialization compatibility
            result["explanation"] = explanation
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
            result["source"] = "RAG"
            
            return result
            
        except Exception as e:
            logger.error(f"Error generating question: {str(e)}")
            # Track failure (sync)
            track_llm_call(
                user_id=user_id,
                trace_id=trace_id,
                call_type="generation",
                model="gpt-4o",
                input_tokens=0,
                output_tokens=0,
                latency_ms=int((time.time() - start_time) * 1000),
                success=False,
                error_message=str(e)
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
