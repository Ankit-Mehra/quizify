import json
import time
from typing import Dict, Any, List, Optional, Tuple

from services.ai_services.llm_client_service import get_groq_client, GROQ_ENHANCED_MODEL, track_groq_posthog
from services.db_services.supabase_llm_analytics import track_llm_call
from services.posthog_service import capture_exception
from services.ai_services.pricing import calculate_cost
from services.logger import ai_logger as logger

# Combined prompt for verification + explanation in ONE call (50% latency reduction)
VERIFY_AND_EXPLAIN_PROMPT = """
Verify and explain this quiz question based on the provided context.

Question: {question}
Correct Answer: {correct_answer}
Options: {options}

Context:
{context}

Tasks:
1. VERIFY: Is the answer factually accurate and supported by the context?
2. EXPLAIN: Write an educational explanation that:
   - Explains WHY the correct answer is right (with reasoning, not just restating)
   - Provides context about the underlying concept
   - Briefly explains why incorrect options are wrong (if applicable)
   - Helps the learner understand, not just memorize

Return JSON:
{{
    "is_accurate": true/false,
    "confidence_score": 0.0-1.0,
    "issues": [],
    "explanation": "Educational explanation of WHY the correct answer is right.",
    "distractor_explanations": {{
        "option_name_1": "Why this option is incorrect...",
        "option_name_2": "Why this option is incorrect..."
    }}
}}

Be strict on accuracy. If the answer isn't clearly supported by context, set is_accurate=false.

GOOD EXPLANATION: "The mitochondria is called the powerhouse of the cell because it produces ATP through cellular respiration."
GOOD DISTRACTOR: "The nucleus stores DNA and controls cell activities, but does not generate energy."

BAD EXPLANATION: "The correct answer is mitochondria because mitochondria is the powerhouse of the cell."
"""

# Separate prompt for FILL-IN-THE-BLANK questions
VERIFY_AND_EXPLAIN_FILL_BLANK_PROMPT = """
Verify and explain this fill-in-the-blank quiz question based on the provided context.

Question: {question}
Correct Answer to fill the blank: {correct_answer}
Options: {options}

Context:
{context}

Tasks:
1. VERIFY: Is the answer factually accurate and supported by the context?
   - Does this word/phrase correctly complete the sentence?
   - Is it the most appropriate term for the blank?

2. EXPLAIN: Write an educational explanation that:
   - Explains WHY this word/phrase correctly fills the blank
   - Provides context about the concept being tested
   - Explains the meaning and significance of the term
   - Briefly explains why the other options don't fit as well
   - Helps the learner understand the concept, not just memorize the answer

Return JSON:
{{
    "is_accurate": true/false,
    "confidence_score": 0.0-1.0,
    "issues": [],
    "explanation": "Educational explanation about why this term correctly fills the blank.",
    "distractor_explanations": {{
        "option_name_1": "Why this option doesn't fit the blank as well...",
        "option_name_2": "Why this option doesn't fit the blank as well..."
    }}
}}

Be strict on accuracy. If the answer isn't clearly supported by context, set is_accurate=false.

GOOD EXPLANATION: "The term 'retrospective' correctly fills the blank because it refers to the specific Scrum ceremony held at the end of each sprint where the team reflects on their process and identifies improvements. This differs from the sprint review, which focuses on demonstrating completed work to stakeholders."

BAD EXPLANATION: "The correct answer is retrospective because retrospective fits in the blank."
"""

# Separate prompt for TRUE/FALSE questions
VERIFY_AND_EXPLAIN_TRUE_FALSE_PROMPT = """
Verify and explain this true/false quiz question based on the provided context.

Question: {question}
Correct Answer: {correct_answer}

Context:
{context}

Tasks:
1. VERIFY: Is the statement's truth value factually accurate and supported by the context?
   - Is the statement actually true/false as claimed?
   - Is this clearly supported or contradicted by the context?

2. EXPLAIN: Write an educational explanation that:
   - Explains WHY the statement is true or false
   - Provides evidence from the context or general knowledge
   - Clarifies any misconceptions the statement might reveal
   - Helps the learner understand the underlying concept

Return JSON:
{{
    "is_accurate": true/false,
    "confidence_score": 0.0-1.0,
    "issues": [],
    "explanation": "Educational explanation about why the statement is true or false."
}}

Be strict on accuracy. If the truth value isn't clearly supported by context, set is_accurate=false.

GOOD EXPLANATION: "This statement is FALSE because the mitochondria produces ATP through cellular respiration, not the nucleus. The nucleus stores genetic material (DNA) and controls cell activities, but energy production occurs in the mitochondria."

BAD EXPLANATION: "The statement is false because that's not how it works."
"""

# Separate prompt for MATCHING questions (different structure: left/right/indices)
VERIFY_AND_EXPLAIN_MATCHING_PROMPT = """
Verify and explain this MATCHING quiz question based on the provided context.

Question: {question}

The correct matching pairs are:
{matched_pairs}

Context:
{context}

Tasks:
1. VERIFY: Check if these matching pairs are educationally valid.
   - Each pair should represent a reasonable relationship (term→definition, concept→example, cause→effect, etc.)
   - Pairs can be derived from, summarized from, or logically related to the context
   - DO NOT require pairs to appear verbatim in the context
   - Only mark is_accurate=false if a pair is FACTUALLY INCORRECT (contradicts known facts)
   - If you cannot verify from context alone, but pairs seem reasonable, mark is_accurate=true

2. EXPLAIN: ALWAYS write an educational explanation that:
   - Explains each matching pair's relationship and significance
   - Provides context about WHY each pair belongs together
   - Uses your general knowledge if context is limited
   - NEVER say "I cannot verify" or "context doesn't contain" - just explain the pairs
   - DO NOT just restate "X matches with Y" - explain the relationship

Return JSON:
{{
    "is_accurate": true,
    "confidence_score": 0.85,
    "issues": [],
    "explanation": "Educational explanation of each pair's relationship."
}}

CRITICAL RULES:
- ALWAYS set is_accurate=true unless pairs are PROVABLY WRONG
- ALWAYS provide a useful explanation, even if context is limited
- Use your knowledge to explain educational concepts
- NEVER return an explanation that says you can't verify - that's not helpful to learners

GOOD EXPLANATION EXAMPLE:
"Project initiation involves defining the project scope and objectives before work begins. Task breakdown (WBS) divides complex projects into manageable components. Constraints like time, budget, and resources limit project options and require trade-offs. A tracking system monitors progress against plans, enabling timely corrective actions."

BAD EXPLANATION (NEVER DO THIS):
"I cannot verify these matches because the context doesn't contain the specific definitions."
"""

# Legacy prompts kept for backward compatibility (individual calls)
EXPLANATION_PROMPT = """
You are an expert educator. Provide a detailed explanation for the following quiz question.

Question: {question}
Correct Answer: {correct_answer}
Distractors: {distractors}

Context:
{context}

Requirements:
1. Explain clearly why the correct answer is right, referencing the context.
2. Explain briefly why EACH distractor is incorrect (if applicable).
3. Ensure the tone is encouraging and educational.

Return JSON:
{{
    "explanation": "...",
    "distractor_explanations": {{
        "distractor_1": "...",
        "distractor_2": "..."
    }}
}}
"""

VERIFICATION_PROMPT = """
Verify the factual accuracy and quality of this quiz question based on the provided context.

Question: {question}
Correct Answer: {correct_answer}

Context:
{context}

Check for:
1. Factual Accuracy: Is the answer supported by the context?
2. Clarity: Is the question unambiguous?
3. Quality: Is it free of bias and inappropriate content?

Return JSON:
{{
    "is_accurate": true/false,
    "confidence_score": 0.0-1.0,
    "issues": ["..."]
}}
"""


class ExplanationService:
    """
    Service for generating detailed explanations and verifying question quality.
    
    Provides two modes:
    - Combined: verify_and_explain() - Single LLM call for both (recommended, 50% faster)
    - Separate: verify_question() + generate_explanation() - Two LLM calls (legacy)
    """
    
    def __init__(self):
        self.client = get_groq_client()

    async def verify_and_explain(
        self,
        question_data: Dict[str, Any],
        context: str,
        user_id: str,
        trace_id: str,
        content_source_type: str = "text"
    ) -> Tuple[bool, float, List[str], str, Optional[Dict[str, str]]]:
        """
        Combined verification + explanation in a single LLM call.
        
        This is 50% faster than calling verify_question + generate_explanation separately.
        Handles different question types (MCQ, fill_blank, true_false, matching).
        
        Args:
            question_data: The question dictionary to verify
            context: Context text for verification
            user_id: UUID of the user
            trace_id: Trace ID for analytics
            content_source_type: Source type for analytics (text, file, url)
        
        Returns:
            Tuple of (is_valid, confidence_score, issues_list, explanation_text, distractor_explanations_dict)
            distractor_explanations_dict is None for true_false and matching, populated for MCQ and fill_blank
        """
        start_time = time.time()
        model = GROQ_ENHANCED_MODEL
        
        try:
            # Detect question type and build appropriate prompt
            question_type = question_data.get("type", "")
            
            if question_type == "matching":
                # Matching questions have left/right lists instead of options
                left = question_data.get("left", [])
                right = question_data.get("right", [])
                correct_answer = question_data.get("correct_answer", [])
                
                # Build explicit matched pairs for clarity
                # correct_answer[i] tells us which right item matches left[i]
                matched_pairs_list = []
                if left and right and correct_answer:
                    for i, left_item in enumerate(left):
                        if i < len(correct_answer):
                            right_idx = correct_answer[i]
                            if isinstance(right_idx, int) and right_idx < len(right):
                                right_item = right[right_idx]
                                matched_pairs_list.append(f"  • \"{left_item}\" → \"{right_item}\"")
                            else:
                                # Log skipped pair for debugging - invalid right index
                                logger.debug(
                                    "Skipping pair: left[%d] ('%s') - "
                                    "invalid right_idx (%s) or out of bounds (right len: %d)",
                                    i, left_item, right_idx, len(right)
                                )
                        else:
                            # Log skipped pair for debugging - no mapping in correct_answer
                            logger.debug(
                                "Skipping pair: left[%d] ('%s') - "
                                "correct_answer does not have index %d (len: %d)",
                                i, left_item, i, len(correct_answer)
                            )
                
                # Log summary if not all left items were matched
                if left and len(matched_pairs_list) != len(left):
                    logger.debug(
                        "Not all left items were matched: %d pairs created "
                        "from %d left items (correct_answer length: %d)",
                        len(matched_pairs_list), len(left), len(correct_answer)
                    )
                
                matched_pairs_str = "\n".join(matched_pairs_list) if matched_pairs_list else "N/A (invalid matching data)"
                
                # Log what we're sending to verification
                logger.info("Matching verification - pairs built: %d, left: %d, right: %d",
                           len(matched_pairs_list), len(left) if left else 0, len(right) if right else 0)
                if matched_pairs_str == "N/A (invalid matching data)":
                    logger.warning("Matching verification getting invalid data - left: %s, right: %s, correct_answer: %s",
                                  left, right, correct_answer)
                
                prompt = VERIFY_AND_EXPLAIN_MATCHING_PROMPT.format(
                    question=question_data.get("question"),
                    matched_pairs=matched_pairs_str,
                    context=context[:2000]  # Limit context size
                )
            
            elif question_type == "fill_blank":
                # Fill-in-the-blank: focus on why this word/phrase fits the blank
                options = question_data.get("options", [])
                options_str = ", ".join(str(opt) for opt in options) if options else "N/A"
                
                prompt = VERIFY_AND_EXPLAIN_FILL_BLANK_PROMPT.format(
                    question=question_data.get("question"),
                    correct_answer=question_data.get("correct_answer"),
                    options=options_str,
                    context=context[:2000]
                )
            
            elif question_type == "true_false":
                # True/False: explain why the statement is true or false
                prompt = VERIFY_AND_EXPLAIN_TRUE_FALSE_PROMPT.format(
                    question=question_data.get("question"),
                    correct_answer=question_data.get("correct_answer"),
                    context=context[:2000]
                )
            
            else:
                # Multiple choice (default): explain correct answer and why distractors are wrong
                options = question_data.get("options", [])
                options_str = ", ".join(str(opt) for opt in options) if options else "N/A"
                
                prompt = VERIFY_AND_EXPLAIN_PROMPT.format(
                    question=question_data.get("question"),
                    correct_answer=question_data.get("correct_answer"),
                    options=options_str,
                    context=context[:2000]  # Limit context size
                )
            
            response = await self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a strict fact-checker and helpful educator."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=800,  # Increased to handle MCQ with multiple detailed distractor explanations
            )
            
            latency_ms = int((time.time() - start_time) * 1000)
            content = response.choices[0].message.content
            usage = getattr(response, "usage", None)
            input_tok = usage.prompt_tokens if usage else 0
            output_tok = usage.completion_tokens if usage else 0
            
            # Defensive JSON parsing
            try:
                result = json.loads(content)
            except json.JSONDecodeError as json_err:
                logger.error("verify_and_explain: invalid JSON from LLM: %s", content[:200])
                track_llm_call(
                    user_id=user_id,
                    trace_id=trace_id,
                    call_type="verify_explain",
                    model=model,
                    input_tokens=input_tok,
                    output_tokens=output_tok,
                    latency_ms=latency_ms,
                    success=False,
                    error_message=f"JSON decode error: {str(json_err)}",
                    cost_usd=calculate_cost(model, input_tok, output_tok)
                )
                return False, 0.0, ["Model returned invalid JSON"], "", None
            
            # Track analytics (combined call)
            track_llm_call(
                user_id=user_id,
                trace_id=trace_id,
                call_type="verify_explain",
                model=model,
                input_tokens=input_tok,
                output_tokens=output_tok,
                latency_ms=latency_ms,
                cost_usd=calculate_cost(model, input_tok, output_tok),
                metadata={
                    "is_accurate": result.get("is_accurate"),
                    "quiz_type": "enhanced",
                    "pipeline": "rag_llama_index"
                }
            )
            track_groq_posthog(
                model=model,
                user_id=user_id,
                trace_id=trace_id,
                input_tokens=input_tok,
                output_tokens=output_tok,
                latency_ms=latency_ms,
                call_type="verify_explain",
                extra_properties={
                    "question_type": question_type,
                    "content_source_type": content_source_type,
                },
            )
            
            return (
                result.get("is_accurate", False),
                result.get("confidence_score", 0.0),
                result.get("issues", []),
                result.get("explanation", ""),
                result.get("distractor_explanations", None)  # None for true_false/matching, dict for MCQ/fill_blank
            )
            
        except Exception as e:  # noqa: BLE001
            logger.error("Verify+explain failed: %s", e)
            # Capture to PostHog Error Tracking for proper stack traces
            capture_exception(
                exception=e,
                distinct_id=user_id,
                properties={
                    "generation_mode": "enhanced",
                    "stage": "verify_and_explain",
                    "model": GROQ_ENHANCED_MODEL,
                    "content_source_type": content_source_type,
                    "trace_id": trace_id,
                }
            )
            return False, 0.0, [f"Verification error: {str(e)}"], "", None

    async def verify_question(
        self,
        question_data: Dict[str, Any],
        context: str,
        user_id: str,
        trace_id: str,
        content_source_type: str = "text"
    ) -> Tuple[bool, float, List[str]]:
        """
        Verify question accuracy and quality.
        Returns (is_valid, confidence_score, issues_list)
        
        Note: Consider using verify_and_explain() instead for better performance.
        """
        start_time = time.time()
        model = GROQ_ENHANCED_MODEL
        
        try:
            prompt = VERIFICATION_PROMPT.format(
                question=question_data.get("question"),
                correct_answer=question_data.get("correct_answer"),
                context=context[:2000] # Limit context size
            )
            
            response = await self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a strict fact-checker."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=500,  # Increased to allow more detailed verification output
            )
            
            latency_ms = int((time.time() - start_time) * 1000)
            content = response.choices[0].message.content
            usage = getattr(response, "usage", None)
            input_tok = usage.prompt_tokens if usage else 0
            output_tok = usage.completion_tokens if usage else 0
            
            # Defensive JSON parsing
            try:
                result = json.loads(content)
            except json.JSONDecodeError as json_err:
                logger.error("verify_question: invalid JSON from LLM: %s", content[:200])
                track_llm_call(
                    user_id=user_id,
                    trace_id=trace_id,
                    call_type="verification",
                    model=model,
                    input_tokens=input_tok,
                    output_tokens=output_tok,
                    latency_ms=latency_ms,
                    success=False,
                    error_message=f"JSON decode error: {str(json_err)}",
                    cost_usd=calculate_cost(model, input_tok, output_tok)
                )
                return False, 0.0, ["Model returned invalid JSON"]
            
            # Track analytics
            track_llm_call(
                user_id=user_id,
                trace_id=trace_id,
                call_type="verification",
                model=model,
                input_tokens=input_tok,
                output_tokens=output_tok,
                latency_ms=latency_ms,
                cost_usd=calculate_cost(model, input_tok, output_tok),
                metadata={
                    "is_accurate": result.get("is_accurate"),
                    "quiz_type": "enhanced",
                    "pipeline": "rag_llama_index"
                }
            )
            track_groq_posthog(
                model=model,
                user_id=user_id,
                trace_id=trace_id,
                input_tokens=input_tok,
                output_tokens=output_tok,
                latency_ms=latency_ms,
                call_type="verification",
                extra_properties={
                    "content_source_type": content_source_type,
                },
            )
            
            return (
                result.get("is_accurate", False),
                result.get("confidence_score", 0.0),
                result.get("issues", [])
            )
            
        except Exception as e:  # noqa: BLE001
            logger.error("Verification failed: %s", e)
            # Capture exception to PostHog for proper error tracking with stack trace
            capture_exception(
                exception=e,
                distinct_id=user_id,
                properties={
                    "generation_mode": "enhanced",
                    "stage": "verification",
                    "model": GROQ_ENHANCED_MODEL,
                    "content_source_type": content_source_type,
                    "trace_id": trace_id,
                }
            )
            # Fail safe: if verification crashes, we assume it's risky to proceed
            return False, 0.0, [f"Verification error: {str(e)}"]

    async def generate_explanation(
        self,
        question_data: Dict[str, Any],
        context: str,
        user_id: str,
        trace_id: str,
        content_source_type: str = "text"
    ) -> str:
        """
        Generate detailed explanation string.
        """
        start_time = time.time()
        model = GROQ_ENHANCED_MODEL
        
        try:
            # Prepare distractors string
            options = question_data.get("options", [])
            correct = question_data.get("correct_answer")
            distractors = [o for o in options if o != correct] if options else []
            
            prompt = EXPLANATION_PROMPT.format(
                question=question_data.get("question"),
                correct_answer=correct,
                distractors=distractors,
                context=context[:2000]
            )

            response = await self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a helpful teacher."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
                max_tokens=500,  # Cap explanation length for predictable cost
            )
            
            latency_ms = int((time.time() - start_time) * 1000)
            content = response.choices[0].message.content
            usage = getattr(response, "usage", None)
            input_tok = usage.prompt_tokens if usage else 0
            output_tok = usage.completion_tokens if usage else 0
            
            # Defensive JSON parsing
            try:
                result = json.loads(content)
            except json.JSONDecodeError as json_err:
                logger.error("generate_explanation: invalid JSON from LLM: %s", content[:200])
                track_llm_call(
                    user_id=user_id,
                    trace_id=trace_id,
                    call_type="explanation",
                    model=model,
                    input_tokens=input_tok,
                    output_tokens=output_tok,
                    latency_ms=latency_ms,
                    success=False,
                    error_message=f"JSON decode error: {str(json_err)}",
                    cost_usd=calculate_cost(model, input_tok, output_tok)
                )
                # Return user-friendly fallback
                correct_answer = question_data.get("correct_answer", "")
                if correct_answer:
                    return f"The correct answer is: {correct_answer}. A detailed explanation could not be generated at this time."
                return "An explanation could not be generated at this time."
            
            # Track analytics
            track_llm_call(
                user_id=user_id,
                trace_id=trace_id,
                call_type="explanation",
                model=model,
                input_tokens=input_tok,
                output_tokens=output_tok,
                latency_ms=latency_ms,
                cost_usd=calculate_cost(model, input_tok, output_tok),
                metadata={
                    "quiz_type": "enhanced",
                    "pipeline": "rag_llama_index"
                }
            )
            track_groq_posthog(
                model=model,
                user_id=user_id,
                trace_id=trace_id,
                input_tokens=input_tok,
                output_tokens=output_tok,
                latency_ms=latency_ms,
                call_type="explanation",
                extra_properties={
                    "content_source_type": content_source_type,
                },
            )
            
            # Format final string
            main_expl = result.get("explanation", "")
            dist_expls = result.get("distractor_explanations", {})
            
            final_text = f"{main_expl}\n\n"
            if dist_expls:
                final_text += "Analysis of options:\n"
                for _k, v in dist_expls.items():
                    # If key is like "distractor_1", try to map to option text if possible
                    # But simple listing is fine
                    final_text += f"- {v}\n"
            
            return final_text.strip()
            
        except Exception as e:  # noqa: BLE001
            logger.error("Explanation generation failed: %s", e)
            # Capture exception to PostHog for proper error tracking with stack trace
            capture_exception(
                exception=e,
                distinct_id=user_id,
                properties={
                    "generation_mode": "enhanced",
                    "stage": "explanation_generation",
                    "model": GROQ_ENHANCED_MODEL,
                    "content_source_type": content_source_type,
                    "trace_id": trace_id,
                }
            )
            # Provide user-friendly fallback that includes the correct answer
            correct_answer = question_data.get("correct_answer", "")
            if correct_answer:
                return f"The correct answer is: {correct_answer}. A detailed explanation could not be generated at this time."
            return "An explanation could not be generated at this time."
