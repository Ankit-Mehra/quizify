"""
LLM Client Service with PostHog Analytics Integration.

This service provides:
1. OpenAI client management (singleton, thread-safe)
2. PostHog LLM analytics tracking
3. Retry logic for transient errors
4. Quiz generation functions using OpenAI's GPT models

Tracked metrics:
- Token usage (input/output)
- Latency and response times
- Cost estimation
- User-level analytics
- Trace correlation for multi-step workflows

Note: Once initialized, the client type (PostHog-wrapped vs standard) cannot
change without restarting the application. This is intentional for performance
and to maintain consistent behavior throughout the application lifecycle.

Renamed from openai_service.py to llm_client_service.py to better reflect
that this provides the core LLM client infrastructure used by all AI services.
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
import httpx
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
from services.ai_services.pricing import calculate_cost, LLM_PRICING
from services.posthog_service import get_posthog_client, is_posthog_enabled, is_posthog_wrapper_active
from services.logger import ai_logger as logger
from config import config

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
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")

# Groq model for enhanced quiz generation and flashcard generation.
# Uses same env var as config.GROQ_MODEL_MINI to keep a single source of truth.
GROQ_ENHANCED_MODEL = os.getenv("GROQ_MODEL_MINI", "llama-3.1-8b-instant")

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
                logger.error("LLM request failed after %d attempts: %s", max_retries + 1, e)
                raise
            
            # For RateLimitError, respect Retry-After header if present
            if isinstance(e, RateLimitError):
                retry_after = getattr(e, 'retry_after', None)
                if retry_after:
                    actual_delay = min(float(retry_after), LLM_MAX_DELAY)
                    logger.warning(
                        "Rate limited (attempt %d/%d). "
                        "Respecting Retry-After: %.1fs",
                        attempt + 1, max_retries + 1, actual_delay
                    )
                else:
                    # Fallback to exponential backoff with jitter
                    jitter = random.uniform(-delay * 0.1, delay * 0.1)
                    actual_delay = min(delay + jitter, LLM_MAX_DELAY)
                    logger.warning(
                        "Rate limited (attempt %d/%d). "
                        "Retrying in %.1fs...",
                        attempt + 1, max_retries + 1, actual_delay
                    )
            else:
                # For connection/timeout errors, use exponential backoff with jitter
                jitter = random.uniform(-delay * 0.1, delay * 0.1)
                actual_delay = min(delay + jitter, LLM_MAX_DELAY)
                logger.warning(
                    "LLM request failed (attempt %d/%d): %s. "
                    "Retrying in %.1fs...",
                    attempt + 1, max_retries + 1, type(e).__name__, actual_delay
                )
            
            await asyncio.sleep(actual_delay)
            delay = min(delay * LLM_BACKOFF_FACTOR, LLM_MAX_DELAY)
    
    # For type safety - this line should never be reached since we raise inside the loop
    if last_exception is not None:
        raise last_exception
    else:
        raise RuntimeError("Retry logic failed: no exception captured to raise.")


# Global client instance with thread-safe initialization
# Note: Client type is determined at first initialization and persists until restart
_client: Optional[BaseAsyncOpenAI] = None
_http_client: Optional[httpx.AsyncClient] = None
_client_lock = threading.Lock()


def _create_openai_client() -> BaseAsyncOpenAI:
    """
    Create the appropriate OpenAI client based on PostHog configuration.
    
    Returns PostHog-wrapped client if analytics is enabled, otherwise
    returns the standard AsyncOpenAI client.
    
    Both clients are configured with LLM_TIMEOUT to prevent hung requests.
    The httpx client is stored globally for proper lifecycle management.
    """
    global _http_client  # noqa: PLW0603  # type: ignore[global-statement]
    
    # Create httpx client with higher connection limits for parallel batch requests
    # Default is 10 connections per host which serializes parallel calls
    _http_client = httpx.AsyncClient(
        timeout=LLM_TIMEOUT,
        limits=httpx.Limits(max_connections=50, max_keepalive_connections=20)
    )
    
    if is_posthog_enabled():
        posthog_client = get_posthog_client()
        if posthog_client:
            # Import PostHog wrapper only when needed
            from posthog.ai.openai import AsyncOpenAI as PostHogAsyncOpenAI
            logger.info("Using PostHog-wrapped AsyncOpenAI client for LLM analytics (timeout: 90s read, max_connections: 50, keepalive: 20)")
            return PostHogAsyncOpenAI(
                api_key=OPENAI_API_KEY,
                posthog_client=posthog_client,
                http_client=_http_client
            )
    
    logger.info("Using standard AsyncOpenAI client (PostHog analytics disabled, timeout: 90s read, max_connections: 50, keepalive: 20)")
    return BaseAsyncOpenAI(api_key=OPENAI_API_KEY, http_client=_http_client)


def get_openai_client() -> BaseAsyncOpenAI:
    """
    Get or create the OpenAI client instance (thread-safe).
    
    Uses double-checked locking pattern for thread-safe lazy initialization.
    """
    global _client  # noqa: PLW0603  # type: ignore[global-statement]
    
    # Fast path: return cached client if already initialized
    if _client is not None:
        return _client
    
    # Thread-safe initialization with lock
    with _client_lock:
        # Double-check after acquiring lock
        if _client is None:
            _client = _create_openai_client()
        return _client


async def cleanup_openai_client() -> None:
    """
    Cleanup OpenAI client and httpx resources.
    
    Should be called on application shutdown to properly close connections
    and prevent resource leaks. This is especially important for the httpx
    AsyncClient which manages connection pooling.
    """
    global _client, _http_client  # noqa: PLW0603  # type: ignore[global-statement]
    
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
        logger.info("httpx client closed")
    
    _client = None
    logger.info("OpenAI client cleaned up")


# =============================================================================
# Groq Client (OpenAI-compatible, used for enhanced pipeline)
# =============================================================================
_groq_client: Optional[BaseAsyncOpenAI] = None
_groq_http_client: Optional[httpx.AsyncClient] = None
_groq_client_lock = threading.Lock()


def _create_groq_client() -> BaseAsyncOpenAI:
    """
    Create a Groq client using OpenAI-compatible SDK.
    
    Groq's API is OpenAI-compatible, so we use the standard AsyncOpenAI
    client with a custom base_url pointing to Groq's API.
    """
    global _groq_http_client  # noqa: PLW0603  # type: ignore[global-statement]
    
    _groq_http_client = httpx.AsyncClient(
        timeout=LLM_TIMEOUT,
        limits=httpx.Limits(max_connections=50, max_keepalive_connections=20)
    )
    
    if not GROQ_API_KEY:
        logger.warning("GROQ_API_KEY not set - Groq client will fail on use")
    
    logger.info(
        "Using Groq client (OpenAI-compatible, base_url=%s, model=%s)",
        GROQ_BASE_URL, GROQ_ENHANCED_MODEL
    )
    return BaseAsyncOpenAI(
        api_key=GROQ_API_KEY,
        base_url=GROQ_BASE_URL,
        http_client=_groq_http_client
    )


def get_groq_client() -> BaseAsyncOpenAI:
    """
    Get or create the Groq client instance (thread-safe).
    
    Returns an OpenAI-compatible AsyncOpenAI client pointed at Groq's API.
    Used by enhanced quiz/flashcard pipeline services.
    """
    global _groq_client  # noqa: PLW0603  # type: ignore[global-statement]
    
    if _groq_client is not None:
        return _groq_client
    
    with _groq_client_lock:
        if _groq_client is None:
            _groq_client = _create_groq_client()
        return _groq_client


async def cleanup_groq_client() -> None:
    """Cleanup Groq client and httpx resources on shutdown."""
    global _groq_client, _groq_http_client  # noqa: PLW0603  # type: ignore[global-statement]
    
    if _groq_http_client is not None:
        await _groq_http_client.aclose()
        _groq_http_client = None
        logger.info("Groq httpx client closed")
    
    _groq_client = None
    logger.info("Groq client cleaned up")


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
                logger.debug("Email cache HIT for user %s...", user_id[:8])
                return email
            else:
                # Expired - remove from cache
                del _email_cache[user_id]
                logger.debug("Email cache EXPIRED for user %s...", user_id[:8])
    
    # Cache miss or expired - fetch from database
    email = None
    try:
        # Use module-level config (already imported at top)
        supabase = config.get_supabase_client()
        response = supabase.table("user_tier_info").select("email").eq("id", user_id).execute()
        if response.data and len(response.data) > 0:
            email = response.data[0].get("email")
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to get email for user %s...: %s", user_id[:8], e)
        # Don't cache failures - return None and try again next time
        return None
    
    # Store in cache (thread-safe)
    with _email_cache_lock:
        # Evict oldest entries if cache is full
        while len(_email_cache) >= _EMAIL_CACHE_MAX_SIZE:
            _email_cache.popitem(last=False)  # Remove oldest (first) item
        
        _email_cache[user_id] = (email, current_time + _EMAIL_CACHE_TTL_SECONDS)
        logger.debug("Email cache SET for user %s... (TTL: %ds)", user_id[:8], _EMAIL_CACHE_TTL_SECONDS)
    
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
            logger.info("Invalidated email cache for user %s...", user_id[:8])
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
    # CRITICAL: Always provide distinct_id - PostHog falls back to trace_id if not provided
    # which creates separate "Person" entries for each trace (showing UUIDs instead of user)
    if user_email:
        kwargs["posthog_distinct_id"] = user_email
    elif user_id:
        # Try to get email from cache
        email = _get_user_email_cached(user_id)
        kwargs["posthog_distinct_id"] = email if email else user_id
    else:
        # Always provide a distinct_id, even if no user context
        # This prevents PostHog from using trace_id as distinct_id
        kwargs["posthog_distinct_id"] = "system"
    
    if trace_id:
        kwargs["posthog_trace_id"] = trace_id
    
    if properties:
        kwargs["posthog_properties"] = properties
    
    return kwargs


def track_groq_posthog(
    *,
    model: str,
    user_id: Optional[str],
    trace_id: Optional[str],
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    call_type: str,
    extra_properties: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Track a Groq LLM call to PostHog with standard $ai_* property names.
    
    This is the canonical way to record PostHog analytics for enhanced-pipeline
    Groq calls that bypass the PostHog-wrapped OpenAI client. Uses the same
    $ai_* property schema as GroqProvider/GeminiProvider for consistent
    analytics dashboards.
    
    Args:
        model: Groq model name (e.g. "llama-3.1-8b-instant")
        user_id: User UUID (resolved to email for distinct_id)
        trace_id: Workflow correlation ID
        input_tokens: Prompt token count
        output_tokens: Completion token count
        latency_ms: Call latency in milliseconds
        call_type: Descriptive call type (e.g. "concept_extraction", "verify_explain")
        extra_properties: Additional custom properties to merge
    """
    from services.posthog_service import capture_event

    cost = calculate_cost(model, input_tokens, output_tokens)

    properties: Dict[str, Any] = {
        "$ai_provider": "groq",
        "$ai_model": model,
        "$ai_latency_ms": latency_ms,
        "$ai_input_tokens": input_tokens,
        "$ai_output_tokens": output_tokens,
        "$ai_input_cost_usd": round((input_tokens / 1_000_000) * (LLM_PRICING.get(model, {}).get("input", 0) * 1000), 6),
        "$ai_output_cost_usd": round((output_tokens / 1_000_000) * (LLM_PRICING.get(model, {}).get("output", 0) * 1000), 6),
        "$ai_total_cost_usd": round(cost, 6),
        "call_type": call_type,
        "generation_mode": "enhanced",
    }

    if trace_id:
        properties["$ai_trace_id"] = trace_id

    if extra_properties:
        properties.update(extra_properties)

    # Resolve user email for consistent PostHog identity
    distinct_id = user_id
    if user_id:
        email = _get_user_email_cached(user_id)
        if email:
            distinct_id = email

    capture_event(
        distinct_id=distinct_id,
        event="$ai_generation",
        properties=properties,
    )


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
    Generate quiz questions of a specific type.
    
    Routes to the appropriate LLM provider based on generation_mode:
    - "standard": Uses OpenAI client (with PostHog tracking)
    - "enhanced": Uses Groq client (faster, cheaper) with PostHog capture_event
    
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
    logger.debug("Generating %s questions of type %s (mode=%s)", num_questions, qtype, generation_mode)
    prompt_builder = QUESTION_TYPE_PROMPTS[qtype]
    prompt = prompt_builder(text, num_questions)
    
    # Route to appropriate provider based on generation mode
    if generation_mode == "enhanced":
        # Enhanced pipeline uses Groq for faster inference
        client = get_groq_client()
        model = GROQ_ENHANCED_MODEL
        provider = "groq"
    else:
        # Standard pipeline uses OpenAI (with PostHog wrapper)
        client = get_openai_client()
        model = config.OPENAI_MODEL_PRIMARY
        provider = "openai"
    
    # Build analytics properties
    properties = {
        "question_type": qtype,
        "num_questions": num_questions,
        "content_length": len(text),
        "feature": "quiz_generation",
        "generation_mode": generation_mode,
        "quiz_type": generation_mode,
        "provider": provider,
        "model": model,
    }
    if content_source_type:
        properties["content_source_type"] = content_source_type
    
    if generation_mode == "enhanced":
        # Groq client doesn't use PostHog wrapper - call LLM directly and track via track_groq_posthog
        start_time = time.time()
        response = await _retry_with_backoff(
            lambda: client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
        )
        latency_ms = int((time.time() - start_time) * 1000)
        usage = getattr(response, "usage", None)
        track_groq_posthog(
            model=model,
            user_id=user_id,
            trace_id=trace_id,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            latency_ms=latency_ms,
            call_type="quiz_generation",
            extra_properties=properties,
        )
    else:
        # Standard pipeline: OpenAI client with PostHog wrapper tracks automatically
        posthog_kwargs = _build_posthog_kwargs(
            user_id=user_id,
            trace_id=trace_id,
            properties=properties,
        )
        response = await _retry_with_backoff(
            lambda: client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                **posthog_kwargs,
            )
        )

    raw_json = response.choices[0].message.content.strip()

    # Strip triple backticks and "json" if present
    if raw_json.startswith("```json") and raw_json.endswith("```"):
        raw_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_json.strip())

    logger.debug("Raw JSON response for %s: %s...", qtype, raw_json[:200])

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
    provider_name: Optional[str] = None,
) -> List[Question]:
    """
    Generate a mixed-type quiz using the configured LLM provider.
    
    This is the primary quiz generation function that supports multiple
    question types in a single call. Supports multiple LLM providers
    (OpenAI, Gemini, Groq) via the provider abstraction layer.
    
    Args:
        text: Source text to generate questions from
        num_questions: Total number of questions to generate
        question_types: List of question types to include
        user_id: Optional user ID for PostHog analytics
        trace_id: Optional trace ID for correlating related LLM calls
        generation_mode: "standard" or "enhanced" for analytics tracking
        content_source_type: "text", "file", or "url" for analytics tracking
        provider_name: LLM provider to use (default: config.DEFAULT_LLM_PROVIDER)
        
    Returns:
        List of generated Question objects
    """
    from services.llm import get_llm_provider, LLMGenerationRequest
    
    prompt = build_quiz_prompt_mixed(text, num_questions, question_types)
    
    # Get the configured LLM provider
    provider = get_llm_provider(provider_name)
    
    logger.debug(
        "Generating quiz with %s questions for types %s using provider: %s",
        num_questions, question_types, provider.provider_name
    )
    
    # Determine question_type for analytics (use "mixed" if multiple types)
    if len(question_types) == 1:
        question_type_value = question_types[0]
    else:
        question_type_value = "mixed"
    
    # Build analytics properties
    properties = {
        "question_type": question_type_value,
        "num_questions": num_questions,
        "content_length": len(text),
        "feature": "quiz_generation",
        "model": provider.default_model,
        "provider": provider.provider_name,
        "generation_mode": generation_mode,
        "quiz_type": generation_mode,
    }
    if content_source_type:
        properties["content_source_type"] = content_source_type
    
    # Generate using the provider abstraction
    try:
        response = await provider.generate(LLMGenerationRequest(
            prompt=prompt,
            response_format="json_object",
            user_id=user_id,
            trace_id=trace_id,
            properties=properties,
            temperature=0.7,
        ))
    except Exception as e:
        logger.error("LLM generation failed with provider %s: %s", provider.provider_name, e)
        raise QuizParseError(
            message=f"Failed to generate quiz: {str(e)}",
            raw_response=None
        ) from e
    
    raw_json = (response.content or "").strip()
    
    if not raw_json:
        logger.warning("LLM returned empty content for quiz generation")
        return []
    
    # Strip triple backticks and "json" if present (defensive parsing, case-insensitive)
    if re.match(r"^```(?:json)?", raw_json, re.IGNORECASE) and raw_json.endswith("```"):
        raw_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_json, flags=re.IGNORECASE)
    
    logger.debug("Raw JSON response for mixed quiz: %s...", raw_json[:200])
    
    # Validate with Pydantic
    try:
        parsed_response = QuizzesParsed.model_validate_json(raw_json)
    except ValidationError as e:
        logger.error("Failed to parse quiz response: %s", e)
        raise QuizParseError(
            message="Failed to parse AI-generated quiz. Please try again.",
            raw_response=raw_json[:500] if raw_json else None
        ) from e

    if not parsed_response or not parsed_response.quizzes:
        return []
    
    quiz_id = uuid4()
    parsed_quizzes = convert_parsed_to_quizzes(parsed_response, quiz_id)
    return parsed_quizzes.quizzes
