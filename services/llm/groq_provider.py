"""
Groq LLM Provider Implementation.

This module implements the ILLMProvider interface for Groq,
enabling use of fast inference with models like Llama and Mixtral.

Features:
- OpenAI-compatible API (uses openai SDK)
- Ultra-fast inference (Groq's hardware advantage)
- PostHog analytics tracking
- Automatic retry with exponential backoff for rate limits
"""

import asyncio
import os
import time
from typing import Optional

from dotenv import load_dotenv

from services.llm.base import (
    ILLMProvider,
    LLMGenerationRequest,
    LLMGenerationResponse,
    LLMProviderError,
    LLMRateLimitError,
)
from services.posthog_service import get_posthog_client, is_posthog_enabled
from services.logger import ai_logger as logger
from config import config

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Retry configuration for rate limits
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 2.0  # seconds
MAX_RETRY_DELAY = 30.0  # seconds


class GroqProvider(ILLMProvider):
    """
    Groq implementation of the LLM provider interface.
    
    Groq provides ultra-fast inference using their custom LPU hardware.
    The API is OpenAI-compatible, so we use the openai SDK with a custom base URL.
    
    Supported models:
    - llama-3.3-70b-versatile (default)
    - llama-3.1-8b-instant (faster, smaller)
    - mixtral-8x7b-32768 (good for longer context)
    
    Note: Requires GROQ_API_KEY environment variable to be set.
    """
    
    def __init__(self):
        """Initialize the Groq provider."""
        self._client = None
        self._posthog = None
        
        if not GROQ_API_KEY:
            logger.warning("GROQ_API_KEY not set - Groq provider will fail on use")
    
    @property
    def provider_name(self) -> str:
        """Return 'groq' as the provider name."""
        return "groq"
    
    @property
    def default_model(self) -> str:
        """Return the default Groq model from config."""
        return config.GROQ_MODEL_DEFAULT
    
    @property
    def client(self):
        """Lazy-load the Groq client (OpenAI-compatible)."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(
                    api_key=GROQ_API_KEY,
                    base_url=GROQ_BASE_URL
                )
                logger.info("Groq client initialized (OpenAI-compatible)")
            except ImportError as exc:
                raise LLMProviderError(
                    "openai package not installed. Run: pip install openai",
                    provider=self.provider_name
                ) from exc
        return self._client
    
    @property
    def posthog(self):
        """Lazy-load PostHog client for analytics."""
        if self._posthog is None and is_posthog_enabled():
            self._posthog = get_posthog_client()
        return self._posthog
    
    async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResponse:
        """
        Generate a response using Groq's API with automatic retry for rate limits.
        
        Args:
            request: The generation request parameters
            
        Returns:
            LLMGenerationResponse with the raw content
            
        Raises:
            LLMProviderError: If generation fails after all retries
            LLMRateLimitError: If rate limited and all retries exhausted
        """
        model = request.model or self.default_model
        
        logger.debug(
            "Groq generation request: model=%s, prompt_len=%d",
            model, len(request.prompt)
        )
        
        # Build messages list
        messages = []
        if request.system_message:
            messages.append({"role": "system", "content": request.system_message})
        messages.append({"role": "user", "content": request.prompt})
        
        # Build request kwargs
        request_kwargs = {
            "model": model,
            "messages": messages,
        }
        
        # Add response format if JSON requested
        if request.response_format == "json_object":
            request_kwargs["response_format"] = {"type": "json_object"}
        
        # Add optional parameters
        if request.max_tokens:
            request_kwargs["max_tokens"] = request.max_tokens
        
        if request.temperature != 1.0:
            request_kwargs["temperature"] = request.temperature
        
        # Build input content string for analytics
        input_content = request.prompt
        if request.system_message:
            input_content = f"[System]: {request.system_message}\n\n[User]: {request.prompt}"
        
        # Retry loop with exponential backoff
        last_exception = None
        for attempt in range(MAX_RETRIES + 1):
            start_time = time.time()
            
            try:
                response = await self.client.chat.completions.create(**request_kwargs)
                
                latency_ms = int((time.time() - start_time) * 1000)
                content = response.choices[0].message.content or ""
                
                # Extract usage if available
                usage = None
                if response.usage:
                    usage = {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens,
                    }
                
                # Track analytics with input/output content
                self._track_analytics(
                    request=request,
                    model=model,
                    latency_ms=latency_ms,
                    usage=usage,
                    input_content=input_content,
                    output_content=content
                )
                
                if attempt > 0:
                    logger.info("Groq request succeeded after %d retries", attempt)
                
                logger.debug(
                    "Groq generation completed: model=%s, latency=%dms, tokens=%s",
                    model, latency_ms, usage.get("total_tokens") if usage else "N/A"
                )
                
                return LLMGenerationResponse(
                    content=content,
                    model=model,
                    usage=usage,
                    latency_ms=latency_ms
                )
                
            except Exception as e:
                error_type = type(e).__name__
                error_msg = str(e).lower()
                last_exception = e
                
                # Check for rate limit errors
                is_rate_limit = "rate" in error_msg or "RateLimitError" in error_type or "429" in str(e)
                
                if is_rate_limit and attempt < MAX_RETRIES:
                    # Calculate backoff delay
                    retry_after = getattr(e, 'retry_after', None)
                    if retry_after:
                        delay = float(retry_after)
                    else:
                        delay = min(INITIAL_RETRY_DELAY * (2 ** attempt), MAX_RETRY_DELAY)
                    
                    logger.warning(
                        "Groq rate limited (attempt %d/%d), retrying in %.1fs...",
                        attempt + 1, MAX_RETRIES + 1, delay
                    )
                    await asyncio.sleep(delay)
                    continue
                
                # Non-retryable error or retries exhausted
                if is_rate_limit:
                    retry_after = getattr(e, 'retry_after', None)
                    raise LLMRateLimitError(self.provider_name, retry_after) from e
                
                logger.error("Groq generation failed: %s: %s", error_type, e)
                raise LLMProviderError(
                    message=str(e),
                    provider=self.provider_name,
                    original_error=e
                ) from e
        
        # Should never reach here, but just in case
        raise LLMRateLimitError(self.provider_name) from last_exception
    
    def _track_analytics(
        self,
        request: LLMGenerationRequest,
        model: str,
        latency_ms: int,
        usage: Optional[dict],
        input_content: str,
        output_content: str
    ) -> None:
        """
        Track generation analytics via PostHog with full LLM observability.
        
        Includes:
        - Input/output content for debugging
        - Token counts and cost calculation
        - Latency and model info
        """
        if not self.posthog or not request.user_id:
            return
        
        # Calculate cost based on Groq pricing (per million tokens)
        # Prices as of Dec 2025 from https://groq.com/pricing/
        input_cost = 0.0
        output_cost = 0.0
        
        if usage:
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            
            # Get pricing for model (prices per million tokens)
            input_price, output_price = self._get_model_pricing(model)
            
            # Calculate cost (convert from per-million to actual)
            input_cost = (input_tokens / 1_000_000) * input_price
            output_cost = (output_tokens / 1_000_000) * output_price
        
        properties = {
            # Standard PostHog LLM analytics fields
            "$ai_provider": "groq",
            "$ai_model": model,
            "$ai_latency_ms": latency_ms,
            
            # Input/Output content (truncate for large payloads)
            "$ai_input": input_content[:10000] if input_content else None,
            "$ai_output": output_content[:10000] if output_content else None,
            
            # Token counts
            "$ai_input_tokens": usage.get("prompt_tokens", 0) if usage else 0,
            "$ai_output_tokens": usage.get("completion_tokens", 0) if usage else 0,
            
            # Cost tracking (USD)
            "$ai_input_cost_usd": round(input_cost, 6),
            "$ai_output_cost_usd": round(output_cost, 6),
            "$ai_total_cost_usd": round(input_cost + output_cost, 6),
        }
        
        if request.trace_id:
            properties["$ai_trace_id"] = request.trace_id
        
        if request.properties:
            properties.update(request.properties)
        
        try:
            self.posthog.capture(
                distinct_id=request.user_id,
                event="$ai_generation",
                properties=properties
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to track Groq analytics: %s", e)
    
    def _get_model_pricing(self, model: str) -> tuple[float, float]:
        """
        Get input/output pricing per million tokens for a Groq model.
        
        Returns:
            Tuple of (input_price, output_price) in USD per million tokens
        """
        # Groq pricing as of Dec 2025 (USD per million tokens)
        # Source: https://groq.com/pricing/
        GROQ_PRICING = {
            # Production models
            "llama-3.3-70b-versatile": (0.59, 0.79),
            "llama-3.1-8b-instant": (0.05, 0.08),
            "meta-llama/llama-guard-4-12b": (0.20, 0.20),
            "openai/gpt-oss-120b": (0.15, 0.60),
            "openai/gpt-oss-20b": (0.075, 0.30),
            
            # Preview models
            "meta-llama/llama-4-maverick-17b-128e-instruct": (0.20, 0.60),
            "meta-llama/llama-4-scout-17b-16e-instruct": (0.11, 0.34),
            "qwen/qwen3-32b": (0.29, 0.59),
            "moonshotai/kimi-k2-instruct-0905": (1.00, 3.00),
            
            # Deprecated/older naming conventions (fallbacks)
            "llama3-70b-8192": (0.59, 0.79),
            "llama3-8b-8192": (0.05, 0.08),
            "mixtral-8x7b-32768": (0.24, 0.24),
        }
        
        # Return pricing or default to llama-3.3-70b pricing
        return GROQ_PRICING.get(model, (0.59, 0.79))
