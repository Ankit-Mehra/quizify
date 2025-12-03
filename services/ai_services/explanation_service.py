import json
import time
from typing import Dict, Any, List, Tuple
from services.ai_services.openai_service import get_openai_client
from services.db_services.supabase_llm_analytics import track_llm_call
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
2. EXPLAIN: Why is the correct answer right? Why are other options wrong?

Return JSON:
{{
    "is_accurate": true/false,
    "confidence_score": 0.0-1.0,
    "issues": [],
    "explanation": "Clear explanation of why the correct answer is right, referencing the context."
}}

Be strict on accuracy. If the answer isn't clearly supported by context, set is_accurate=false.
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
        self.client = get_openai_client()

    async def verify_and_explain(
        self,
        question_data: Dict[str, Any],
        context: str,
        user_id: str,
        trace_id: str
    ) -> Tuple[bool, float, List[str], str]:
        """
        Combined verification + explanation in a single LLM call.
        
        This is 50% faster than calling verify_question + generate_explanation separately.
        
        Returns:
            Tuple of (is_valid, confidence_score, issues_list, explanation_text)
        """
        start_time = time.time()
        model = "gpt-4o-mini"
        
        try:
            # Prepare options string
            options = question_data.get("options", [])
            options_str = ", ".join(options) if options else "N/A"
            
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
                temperature=0.2
            )
            
            latency_ms = int((time.time() - start_time) * 1000)
            content = response.choices[0].message.content
            result = json.loads(content)
            
            # Track analytics (combined call)
            track_llm_call(
                user_id=user_id,
                trace_id=trace_id,
                call_type="verify_explain",
                model=model,
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
                latency_ms=latency_ms,
                cost_usd=calculate_cost(model, response.usage.prompt_tokens, response.usage.completion_tokens),
                metadata={"is_accurate": result.get("is_accurate")}
            )
            
            return (
                result.get("is_accurate", False),
                result.get("confidence_score", 0.0),
                result.get("issues", []),
                result.get("explanation", "")
            )
            
        except Exception as e:
            logger.error(f"Verify+explain failed: {str(e)}")
            return False, 0.0, [f"Verification error: {str(e)}"], ""

    async def verify_question(
        self,
        question_data: Dict[str, Any],
        context: str,
        user_id: str,
        trace_id: str
    ) -> Tuple[bool, float, List[str]]:
        """
        Verify question accuracy and quality.
        Returns (is_valid, confidence_score, issues_list)
        
        Note: Consider using verify_and_explain() instead for better performance.
        """
        start_time = time.time()
        model = "gpt-4o-mini" # Use mini for verification to save cost/time
        
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
                temperature=0.1
            )
            
            latency_ms = int((time.time() - start_time) * 1000)
            content = response.choices[0].message.content
            result = json.loads(content)
            
            # Track analytics
            track_llm_call(
                user_id=user_id,
                trace_id=trace_id,
                call_type="verification",
                model=model,
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
                latency_ms=latency_ms,
                cost_usd=calculate_cost(model, response.usage.prompt_tokens, response.usage.completion_tokens),
                metadata={"is_accurate": result.get("is_accurate")}
            )
            
            return (
                result.get("is_accurate", False),
                result.get("confidence_score", 0.0),
                result.get("issues", [])
            )
            
        except Exception as e:
            logger.error(f"Verification failed: {str(e)}")
            # Fail safe: if verification crashes, we assume it's risky to proceed
            return False, 0.0, [f"Verification error: {str(e)}"]

    async def generate_explanation(
        self,
        question_data: Dict[str, Any],
        context: str,
        user_id: str,
        trace_id: str
    ) -> str:
        """
        Generate detailed explanation string.
        """
        start_time = time.time()
        model = "gpt-4o-mini" 
        
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
                temperature=0.7
            )
            
            latency_ms = int((time.time() - start_time) * 1000)
            content = response.choices[0].message.content
            result = json.loads(content)
            
            # Track analytics
            track_llm_call(
                user_id=user_id,
                trace_id=trace_id,
                call_type="explanation",
                model=model,
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
                latency_ms=latency_ms,
                cost_usd=calculate_cost(model, response.usage.prompt_tokens, response.usage.completion_tokens)
            )
            
            # Format final string
            main_expl = result.get("explanation", "")
            dist_expls = result.get("distractor_explanations", {})
            
            final_text = f"{main_expl}\n\n"
            if dist_expls:
                final_text += "Analysis of options:\n"
                for k, v in dist_expls.items():
                    # If key is like "distractor_1", try to map to option text if possible
                    # But simple listing is fine
                    final_text += f"- {v}\n"
            
            return final_text.strip()
            
        except Exception as e:
            logger.error(f"Explanation generation failed: {str(e)}")
            # Provide user-friendly fallback that includes the correct answer
            correct_answer = question_data.get("correct_answer", "")
            if correct_answer:
                return f"The correct answer is: {correct_answer}. A detailed explanation could not be generated at this time."
            return "An explanation could not be generated at this time."
