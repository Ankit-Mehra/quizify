"""
OpenAI Service with PostHog LLM Analytics Integration.

This service provides quiz generation using OpenAI's GPT models with
automatic tracking of:
- Token usage (input/output)
- Latency and response times
- Cost estimation
- User-level analytics
- Trace correlation for multi-step workflows
"""

from typing import List, Optional, Dict, Any
from openai import AsyncOpenAI as BaseAsyncOpenAI
import os
import re
from uuid import uuid4
from dotenv import load_dotenv

from schemas.quiz import Quizzes, Question
from schemas.quizzes_parsed import QuizzesParsed
from schemas.conversion import convert_parsed_to_quizzes
from services.ai_services.prompt_smart import (
    build_quiz_prompt_mcq,
    build_quiz_prompt_true_false,
    build_quiz_prompt_fill_blank,
    build_quiz_prompt_matching,
)
from services.ai_services.prompts import build_quiz_prompt_mixed
from services.posthog_service import get_posthog_client, is_posthog_enabled
from services.logger import ai_logger as logger

logger.debug("OpenAI service initialized")
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


def _create_openai_client() -> BaseAsyncOpenAI:
    """
    Create the appropriate OpenAI client based on PostHog configuration.
    
    Returns PostHog-wrapped client if analytics is enabled, otherwise
    returns the standard AsyncOpenAI client.
    """
    if is_posthog_enabled():
        posthog_client = get_posthog_client()
        if posthog_client:
            # Import PostHog wrapper only when needed
            from posthog.ai.openai import AsyncOpenAI as PostHogAsyncOpenAI
            logger.info("Using PostHog-wrapped AsyncOpenAI client for LLM analytics")
            return PostHogAsyncOpenAI(
                api_key=OPENAI_API_KEY,
                posthog_client=posthog_client
            )
    
    logger.info("Using standard AsyncOpenAI client (PostHog analytics disabled)")
    return BaseAsyncOpenAI(api_key=OPENAI_API_KEY)


# Global client instance (lazy initialization)
_client: Optional[BaseAsyncOpenAI] = None


def get_openai_client() -> BaseAsyncOpenAI:
    """Get or create the OpenAI client instance."""
    global _client
    if _client is None:
        _client = _create_openai_client()
    return _client


# Mapping from type -> prompt builder
QUESTION_TYPE_PROMPTS = {
    "mcq": build_quiz_prompt_mcq,
    "true_false": build_quiz_prompt_true_false,
    "fill_blank": build_quiz_prompt_fill_blank,
    "matching": build_quiz_prompt_matching,
}


def _build_posthog_kwargs(
    user_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    properties: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build PostHog-specific kwargs for OpenAI calls.
    
    These kwargs are only used when PostHog analytics is enabled.
    The PostHog wrapper will ignore these if it's not the wrapped client.
    
    Args:
        user_id: User's distinct ID for analytics attribution
        trace_id: Trace ID for correlating multi-step workflows
        properties: Additional custom properties to track
        
    Returns:
        Dict of PostHog kwargs to pass to OpenAI calls
    """
    kwargs = {}
    
    if not is_posthog_enabled():
        return kwargs
    
    if user_id:
        kwargs["posthog_distinct_id"] = user_id
    
    if trace_id:
        kwargs["posthog_trace_id"] = trace_id
    
    if properties:
        kwargs["posthog_properties"] = properties
    
    return kwargs


async def generate_quiz_for_type(
    qtype: str,
    text: str,
    num_questions: int,
    user_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> List[Question]:
    """
    Generate quiz questions of a specific type using GPT-4o.
    
    Args:
        qtype: Question type (mcq, true_false, fill_blank, matching)
        text: Source text to generate questions from
        num_questions: Number of questions to generate
        user_id: Optional user ID for PostHog analytics
        trace_id: Optional trace ID for correlating related LLM calls
        
    Returns:
        List of generated Question objects
    """
    logger.debug("Generating %s questions of type %s", num_questions, qtype)
    prompt_builder = QUESTION_TYPE_PROMPTS[qtype]
    prompt = prompt_builder(text, num_questions)
    
    client = get_openai_client()
    
    # Build PostHog tracking kwargs
    posthog_kwargs = _build_posthog_kwargs(
        user_id=user_id,
        trace_id=trace_id,
        properties={
            "question_type": qtype,
            "num_questions": num_questions,
            "content_length": len(text),
            "feature": "quiz_generation",
        }
    )

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        **posthog_kwargs
    )

    raw_json = response.choices[0].message.content.strip()

    # Strip triple backticks and "json" if present
    if raw_json.startswith("```json") and raw_json.endswith("```"):
        raw_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_json.strip())

    logger.debug(f"Raw JSON response for {qtype}: {raw_json[:200]}...")

    parsed = Quizzes.model_validate_json(raw_json)
    return parsed.quizzes


async def generate_quiz_async(
    text: str,
    num_questions: int,
    question_types: List[str],
    user_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> List[Question]:
    """
    Generate a mixed-type quiz using GPT-4o-mini with structured output.
    
    This is the primary quiz generation function that supports multiple
    question types in a single call using OpenAI's structured output feature.
    
    Args:
        text: Source text to generate questions from
        num_questions: Total number of questions to generate
        question_types: List of question types to include
        user_id: Optional user ID for PostHog analytics
        trace_id: Optional trace ID for correlating related LLM calls
        
    Returns:
        List of generated Question objects
    """
    prompt = build_quiz_prompt_mixed(text, num_questions, question_types)
    
    logger.debug("Generating quiz with %s questions for types %s", num_questions, question_types)
    
    client = get_openai_client()
    
    # Build PostHog tracking kwargs
    posthog_kwargs = _build_posthog_kwargs(
        user_id=user_id,
        trace_id=trace_id,
        properties={
            "question_types": question_types,
            "num_questions": num_questions,
            "content_length": len(text),
            "feature": "quiz_generation",
            "model": "gpt-4o-mini",
        }
    )
    
    response = await client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format=QuizzesParsed,
        **posthog_kwargs
    )
    parsed_response = response.choices[0].message.parsed

    if not parsed_response or not parsed_response.quizzes:
        return []
    
    quiz_id = uuid4()
    parsed_quizzes = convert_parsed_to_quizzes(parsed_response, quiz_id)
    return parsed_quizzes.quizzes


# Legacy client export for backward compatibility
# Provides direct access to the OpenAI client for edge cases
client = None  # Will be initialized on first use via get_openai_client()

