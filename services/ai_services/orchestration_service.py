import json
import time
import random
from typing import Literal, Dict, Any, Optional, List

from services.ai_services.openai_service import get_openai_client
from services.ai_services.context_service import ContextService
from services.ai_services.concept_extraction_service import calculate_cost
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

QUESTION_GENERATION_PROMPT = """
You are an expert educational content creator.
Create a {difficulty} difficulty {question_type} question at the {bloom_level} Bloom's Taxonomy level.

Target Concept: {concept_name}
Concept Type: {concept_type}

Bloom Level Description: {bloom_description}

Context:
{context}

Requirements:
1. Question must be clear, unambiguous, and directly test the concept.
2. For multiple_choice: provide exactly 4 options with 1 correct answer and 3 plausible distractors.
3. For true_false: create a statement that is clearly true or false based on the context.
4. For fill_blank: create a sentence with a key term removed, marked with _____.
5. For matching: provide 4 pairs of related items. Return "left" and "right" lists, and "correct_answer" as list of indices [0, 1, 2, 3] mapping left to right.
6. Assign a confidence score (0.0-1.0) based on how well the question tests the concept.

Return JSON format:
{{
  "question": "...",
  "options": ["A) ...", "B) ...", "C) ...", "D) ..."],  // for multiple_choice only
  "left": ["Item 1", "Item 2", ...], // for matching only
  "right": ["Match A", "Match B", ...], // for matching only
  "correct_answer": "A" or true/false or "term" or [0,1,2,3],  // type-dependent
  "confidence_score": 0.95
}}
"""


class QuizOrchestrationService:
    """
    Orchestrates question generation using RAG-retrieved context.
    
    Supports Bloom's taxonomy levels and difficulty distribution.
    """
    
    def __init__(self):
        self.client = get_openai_client()
        self.context_service = ContextService()
        self.explanation_service = ExplanationService()
        
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
        
        # 3. Build Prompt with Bloom description
        bloom_description = BLOOM_DESCRIPTIONS.get(bloom_level.value, "testing knowledge")
        
        prompt = QUESTION_GENERATION_PROMPT.format(
            difficulty=difficulty.value,
            question_type=question_type,
            bloom_level=bloom_level.value,
            bloom_description=bloom_description,
            concept_name=concept["name"],
            concept_type=concept.get("concept_type", "general"),
            context=context
        )
        
        # 4. Call LLM
        model = "gpt-4o"  # Use stronger model for generation
        
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a professional quiz generator. Generate clear, educationally valuable questions."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.7
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
            
            # 7. Verify and Generate Explanation (New Step)
            # Verify question quality
            is_valid, confidence, issues = await self.explanation_service.verify_question(
                question_data=result,
                context=context,
                user_id=user_id,
                trace_id=trace_id
            )
            
            if not is_valid:
                logger.warning(f"Question verification failed: {issues}")
                # Strictly filter out low-quality questions
                raise ValueError(f"Question rejected by verification: {issues}")
            
            # Generate detailed explanation
            explanation = await self.explanation_service.generate_explanation(
                question_data=result,
                context=context,
                user_id=user_id,
                trace_id=trace_id
            )
            
            # 8. Format Result with metadata
            result["explanation"] = explanation
            result["type"] = question_type
            result["bloom_level"] = bloom_level
            result["difficulty"] = difficulty
            result["concept_id"] = concept.get("id")
            result["chunk_id"] = concept.get("chunk_id")
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
