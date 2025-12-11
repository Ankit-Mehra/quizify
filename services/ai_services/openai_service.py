"""
OpenAI Service with PostHog LLM Analytics Integration.

This service provides quiz generation using OpenAI's GPT models with
automatic tracking of:
- Token usage (input/output)
- Latency and response times
- Cost estimation
- User-level analytics
- Trace correlation for multi-step workflows
- Thread-safe singleton initialization

Note: Once initialized, the client type (PostHog-wrapped vs standard) cannot
change without restarting the application. This is intentional for performance
and to maintain consistent behavior throughout the application lifecycle.
"""

import os
import random
import re
import threading
import time
import asyncio
from collections import OrderedDict
from typing import List, Optional, Dict, Any
from uuid import uuid4

from dotenv import load_dotenv
from httpx import Timeout
from openai import AsyncOpenAI as BaseAsyncOpenAI, RateLimitError, APIConnectionError, APITimeoutError
from pydantic import ValidationError

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
from services.posthog_service import get_posthog_client, is_posthog_enabled, is_posthog_wrapper_active
from services.logger import ai_logger as logger

logger.debug("OpenAI service initialized")
load_dotenv()


class QuizParseError(Exception):
    """Raised when AI-generated quiz response cannot be parsed.
    
    This is a domain-specific exception that allows the API layer to
    handle the error and return an appropriate HTTP response.
    """
    def __init__(self, message: str, raw_response: Optional[str] = None):
        self.message = message
        self.raw_response = raw_response
        super().__init__(self.message)


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# LLM request timeout configuration
# - connect: Time to establish connection (5s is generous for cloud APIs)
# - read: Time to wait for response chunks (90s allows for complex quiz generation)
# - write: Time to send request body (30s for large prompts)
# - pool: Time to acquire connection from pool (10s)
# Total timeout ensures requests don't hang indefinitely, preventing worker exhaustion
LLM_TIMEOUT = Timeout(
    connect=5.0,
    read=90.0,
    write=30.0,
    pool=10.0
)

# Retry configuration for transient LLM errors
# Handles rate limits, connection issues, and timeouts with exponential backoff
LLM_MAX_RETRIES = 3
LLM_INITIAL_DELAY = 1.0  # seconds
LLM_MAX_DELAY = 30.0  # seconds
LLM_BACKOFF_FACTOR = 2.0


async def _retry_with_backoff(coro_factory, max_retries: int = LLM_MAX_RETRIES):
    """
    Execute an async operation with exponential backoff retry on transient errors.
    
    Retries on:
    - RateLimitError: OpenAI rate limits (429) - respects Retry-After header if present
    - APIConnectionError: Network issues
    - APITimeoutError: Request timeout
    
    Args:
        coro_factory: Callable that returns the coroutine to execute
        max_retries: Maximum number of retry attempts
        
    Returns:
        The result of the successful coroutine execution
        
    Raises:
        The last exception if all retries fail
    """
    delay = LLM_INITIAL_DELAY
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            return await coro_factory()
        except (RateLimitError, APIConnectionError, APITimeoutError) as e:
            last_exception = e
            if attempt == max_retries:
                logger.error(f"LLM request failed after {max_retries + 1} attempts: {e}")
                raise
            
            # For RateLimitError, respect Retry-After header if present
            if isinstance(e, RateLimitError):
                retry_after = getattr(e, 'retry_after', None)
                if retry_after:
                    actual_delay = min(float(retry_after), LLM_MAX_DELAY)
                    logger.warning(
                        f"Rate limited (attempt {attempt + 1}/{max_retries + 1}). "
                        f"Respecting Retry-After: {actual_delay:.1f}s"
                    )
                else:
                    # Fallback to exponential backoff with jitter
                    jitter = random.uniform(-delay * 0.1, delay * 0.1)
                    actual_delay = min(delay + jitter, LLM_MAX_DELAY)
                    logger.warning(
                        f"Rate limited (attempt {attempt + 1}/{max_retries + 1}). "
                        f"Retrying in {actual_delay:.1f}s..."
                    )
            else:
                # For connection/timeout errors, use exponential backoff with jitter
                jitter = random.uniform(-delay * 0.1, delay * 0.1)
                actual_delay = min(delay + jitter, LLM_MAX_DELAY)
                logger.warning(
                    f"LLM request failed (attempt {attempt + 1}/{max_retries + 1}): {type(e).__name__}. "
                    f"Retrying in {actual_delay:.1f}s..."
                )
            
            await asyncio.sleep(actual_delay)
            delay = min(delay * LLM_BACKOFF_FACTOR, LLM_MAX_DELAY)
    
    raise last_exception  # Should never reach here, but for type safety


# Global client instance with thread-safe initialization
# Note: Client type is determined at first initialization and persists until restart
_client: Optional[BaseAsyncOpenAI] = None
_client_lock = threading.Lock()


def _create_openai_client() -> BaseAsyncOpenAI:
    """
    Create the appropriate OpenAI client based on PostHog configuration.
    
    Returns PostHog-wrapped client if analytics is enabled, otherwise
    returns the standard AsyncOpenAI client.
    
    Both clients are configured with LLM_TIMEOUT to prevent hung requests.
    """
    if is_posthog_enabled():
        posthog_client = get_posthog_client()
        if posthog_client:
            # Import PostHog wrapper only when needed
            from posthog.ai.openai import AsyncOpenAI as PostHogAsyncOpenAI
            logger.info("Using PostHog-wrapped AsyncOpenAI client for LLM analytics (timeout: 90s read)")
            return PostHogAsyncOpenAI(
                api_key=OPENAI_API_KEY,
                posthog_client=posthog_client,
                timeout=LLM_TIMEOUT
            )
    
    logger.info("Using standard AsyncOpenAI client (PostHog analytics disabled, timeout: 90s read)")
    return BaseAsyncOpenAI(api_key=OPENAI_API_KEY, timeout=LLM_TIMEOUT)


def get_openai_client() -> BaseAsyncOpenAI:
    """
    Get or create the OpenAI client instance (thread-safe).
    
    Uses double-checked locking pattern for thread-safe lazy initialization.
    """
    global _client
    
    # Fast path: return cached client if already initialized
    if _client is not None:
        return _client
    
    # Thread-safe initialization with lock
    with _client_lock:
        # Double-check after acquiring lock
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

# TTL-based cache for user_id → email mapping (avoids DB call on every LLM request)
# Uses time-based expiration to handle email changes
# Cache configuration
_EMAIL_CACHE_TTL_SECONDS = 300  # 5 minutes (same as user_tier cache)
_EMAIL_CACHE_MAX_SIZE = 1000

# Thread-safe cache storage: {user_id: (email, expiry_timestamp)}
_email_cache: OrderedDict[str, tuple[Optional[str], float]] = OrderedDict()
_email_cache_lock = threading.Lock()


def _get_user_email_cached(user_id: str) -> Optional[str]:
    """
    Get user email from user_id with TTL-based caching.
    
    Uses service role client to query user_tier_info view.
    Cached with 5-minute TTL to:
    - Avoid DB call on every LLM request
    - Handle email changes gracefully (stale data expires)
    
    Thread-safe with LRU eviction when cache exceeds max size.
    
    Args:
        user_id: UUID of the user
        
    Returns:
        User's email or None if not found
    """
    current_time = time.time()
    
    # Check cache first (thread-safe)
    with _email_cache_lock:
        if user_id in _email_cache:
            email, expiry = _email_cache[user_id]
            if current_time < expiry:
                # Move to end for LRU ordering
                _email_cache.move_to_end(user_id)
                logger.debug(f"Email cache HIT for user {user_id[:8]}...")
                return email
            else:
                # Expired - remove from cache
                del _email_cache[user_id]
                logger.debug(f"Email cache EXPIRED for user {user_id[:8]}...")
    
    # Cache miss or expired - fetch from database
    email = None
    try:
        from config import config
        supabase = config.get_supabase_client()
        response = supabase.table("user_tier_info").select("email").eq("id", user_id).execute()
        if response.data and len(response.data) > 0:
            email = response.data[0].get("email")
    except Exception as e:
        logger.warning(f"Failed to get email for user {user_id[:8]}...: {e}")
        # Don't cache failures - return None and try again next time
        return None
    
    # Store in cache (thread-safe)
    with _email_cache_lock:
        # Evict oldest entries if cache is full
        while len(_email_cache) >= _EMAIL_CACHE_MAX_SIZE:
            _email_cache.popitem(last=False)  # Remove oldest (first) item
        
        _email_cache[user_id] = (email, current_time + _EMAIL_CACHE_TTL_SECONDS)
        logger.debug(f"Email cache SET for user {user_id[:8]}... (TTL: {_EMAIL_CACHE_TTL_SECONDS}s)")
    
    return email


def invalidate_user_email_cache(user_id: str) -> bool:
    """
    Invalidate cached email for a specific user.
    
    Call this when a user's email is updated to ensure
    fresh data is fetched on next access.
    
    Args:
        user_id: UUID of the user
        
    Returns:
        True if entry was removed, False if not found
    """
    with _email_cache_lock:
        if user_id in _email_cache:
            del _email_cache[user_id]
            logger.info(f"Invalidated email cache for user {user_id[:8]}...")
            return True
        return False


def _build_posthog_kwargs(
    user_id: Optional[str] = None,
    user_email: Optional[str] = None,
    trace_id: Optional[str] = None,
    properties: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build PostHog-specific kwargs for OpenAI calls.
    
    These kwargs are only added when PostHog wrapper is actively initialized.
    They must not be passed to the standard AsyncOpenAI client as it will
    raise TypeError for unexpected keyword arguments.
    
    Args:
        user_id: User's UUID (used to lookup email if user_email not provided)
        user_email: User's email for PostHog distinct_id (preferred over user_id)
        trace_id: Trace ID for correlating multi-step workflows
        properties: Additional custom properties to track
        
    Returns:
        Dict of PostHog kwargs to pass to OpenAI calls (empty if PostHog not active)
    """
    kwargs = {}
    
    # Only add kwargs if PostHog wrapper is actually active
    # This prevents TypeError when using standard OpenAI client
    if not is_posthog_wrapper_active():
        return kwargs
    
    # Prefer email as distinct_id (shows nicely in PostHog UI)
    # Fall back to user_id if email not available
    if user_email:
        kwargs["posthog_distinct_id"] = user_email
    elif user_id:
        # Try to get email from cache
        email = _get_user_email_cached(user_id)
        kwargs["posthog_distinct_id"] = email if email else user_id
    
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
    generation_mode: str = "standard",
    content_source_type: Optional[str] = None,
) -> List[Question]:
    """
    Generate quiz questions of a specific type using GPT-4o.
    
    Args:
        qtype: Question type (mcq, true_false, fill_blank, matching)
        text: Source text to generate questions from
        num_questions: Number of questions to generate
        user_id: Optional user ID for PostHog analytics
        trace_id: Optional trace ID for correlating related LLM calls
        generation_mode: "standard" or "enhanced" for analytics tracking
        content_source_type: "text", "file", or "url" for analytics tracking
        
    Returns:
        List of generated Question objects
    """
    logger.debug("Generating %s questions of type %s", num_questions, qtype)
    prompt_builder = QUESTION_TYPE_PROMPTS[qtype]
    prompt = prompt_builder(text, num_questions)
    
    client = get_openai_client()
    
    # Build PostHog tracking kwargs with generation mode and source type
    properties = {
        "question_type": qtype,
        "num_questions": num_questions,
        "content_length": len(text),
        "feature": "quiz_generation",
        "generation_mode": generation_mode,
        "quiz_type": generation_mode,  # Epic 5.1: Add quiz_type (standard/enhanced)
    }
    if content_source_type:
        properties["content_source_type"] = content_source_type
    
    # Note: Plan info for PostHog tracking is already included via quiz_type.
    # Adding plan here would require a DB call per LLM request which is inefficient.
    # The handler already tracks plan in the capture_event call when needed.
    
    posthog_kwargs = _build_posthog_kwargs(
        user_id=user_id,
        trace_id=trace_id,
        properties=properties
    )

    # Use retry wrapper for transient errors (rate limits, connection issues)
    response = await _retry_with_backoff(
        lambda: client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            **posthog_kwargs
        )
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
    generation_mode: str = "standard",
    content_source_type: Optional[str] = None,
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
        generation_mode: "standard" or "enhanced" for analytics tracking
        content_source_type: "text", "file", or "url" for analytics tracking
        
    Returns:
        List of generated Question objects
    """
    prompt = build_quiz_prompt_mixed(text, num_questions, question_types)
    
    logger.debug("Generating quiz with %s questions for types %s", num_questions, question_types)
    
    client = get_openai_client()
    
    # Determine question_type for PostHog (use "mixed" if multiple types, otherwise the single type)
    # This ensures consistent filtering in PostHog - always use singular "question_type" 
    if len(question_types) == 1:
        question_type_value = question_types[0]
    else:
        question_type_value = "mixed"
    
    # Build PostHog tracking kwargs with generation mode and source type
    properties = {
        "question_type": question_type_value,  # Singular, consistent with generate_quiz_for_type
        "num_questions": num_questions,
        "content_length": len(text),
        "feature": "quiz_generation",
        "model": "gpt-4o-mini",
        "generation_mode": generation_mode,
        "quiz_type": generation_mode,  # Epic 5.1: Add quiz_type (standard/enhanced)
    }
    if content_source_type:
        properties["content_source_type"] = content_source_type
    
    posthog_kwargs = _build_posthog_kwargs(
        user_id=user_id,
        trace_id=trace_id,
        properties=properties
    )
    
    # OpenAI's structured outputs API doesn't support Union types (it generates oneOf in the JSON schema).
    # This is problematic because our QuizzesParsed model uses a discriminated Union for question types.
    # OpenAI's output may not match the expected schema, causing parsing failures with Pydantic.
    # Therefore, we parse the JSON manually and validate with Pydantic after.
    # Use retry wrapper for transient errors (rate limits, connection issues)
    response = await _retry_with_backoff(
        lambda: client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            **posthog_kwargs
        )
    )
    
    raw_json = (response.choices[0].message.content or "").strip()
    
    if not raw_json:
        logger.warning("OpenAI returned empty content for quiz generation")
        return []
    
    # Strip triple backticks and "json" if present (defensive parsing, case-insensitive)
    if re.match(r"^```(?:json)?", raw_json, re.IGNORECASE) and raw_json.endswith("```"):
        raw_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_json, flags=re.IGNORECASE)
    
    logger.debug(f"Raw JSON response for mixed quiz: {raw_json[:200]}...")
    
    # Validate with Pydantic
    try:
        parsed_response = QuizzesParsed.model_validate_json(raw_json)
    except ValidationError as e:
        logger.error(f"Failed to parse quiz response: {e}")
        raise QuizParseError(
            message="Failed to parse AI-generated quiz. Please try again.",
            raw_response=raw_json[:500] if raw_json else None
        )

    if not parsed_response or not parsed_response.quizzes:
        return []
    
    quiz_id = uuid4()
    parsed_quizzes = convert_parsed_to_quizzes(parsed_response, quiz_id)
    return parsed_quizzes.quizzes
