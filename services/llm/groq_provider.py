"""
Groq LLM Provider Implementation.

This module implements the ILLMProvider interface for Groq,
enabling use of fast inference with models like Llama and Mixtral.

Features:
- OpenAI-compatible API (uses openai SDK)
- Ultra-fast inference (Groq's hardware advantage)
- PostHog analytics tracking
- Retry logic for transient errors
"""

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

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"


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
    
    DEFAULT_MODEL = "llama-3.3-70b-versatile"
    
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
        """Return the default Groq model."""
        return self.DEFAULT_MODEL
    
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
            except ImportError:
                raise LLMProviderError(
                    "openai package not installed. Run: pip install openai",
                    provider=self.provider_name
                )
        return self._client
    
    @property
    def posthog(self):
        """Lazy-load PostHog client for analytics."""
        if self._posthog is None and is_posthog_enabled():
            self._posthog = get_posthog_client()
        return self._posthog
    
    async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResponse:
        """
        Generate a response using Groq's API.
        
        Args:
            request: The generation request parameters
            
        Returns:
            LLMGenerationResponse with the raw content
            
        Raises:
            LLMProviderError: If generation fails
            LLMRateLimitError: If rate limited
        """
        start_time = time.time()
        model = request.model or self.default_model
        
        logger.debug(
            "Groq generation request: model=%s, prompt_len=%d",
            model, len(request.prompt)
        )
        
        # Build request kwargs
        request_kwargs = {
            "model": model,
            "messages": [{"role": "user", "content": request.prompt}],
        }
        
        # Add response format if JSON requested
        if request.response_format == "json_object":
            request_kwargs["response_format"] = {"type": "json_object"}
        
        # Add optional parameters
        if request.max_tokens:
            request_kwargs["max_tokens"] = request.max_tokens
        
        if request.temperature != 1.0:
            request_kwargs["temperature"] = request.temperature
        
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
            
            # Track analytics
            self._track_analytics(request, model, latency_ms, usage)
            
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
            
            # Check for rate limit errors
            if "rate" in error_msg or "RateLimitError" in error_type:
                retry_after = getattr(e, 'retry_after', None)
                raise LLMRateLimitError(self.provider_name, retry_after)
            
            logger.error(f"Groq generation failed: {error_type}: {e}")
            raise LLMProviderError(
                message=str(e),
                provider=self.provider_name,
                original_error=e
            )
    
    def _track_analytics(
        self,
        request: LLMGenerationRequest,
        model: str,
        latency_ms: int,
        usage: Optional[dict]
    ) -> None:
        """Track generation analytics via PostHog."""
        if not self.posthog or not request.user_id:
            return
        
        properties = {
            "$ai_provider": "groq",
            "$ai_model": model,
            "$ai_latency_ms": latency_ms,
        }
        
        if request.trace_id:
            properties["$ai_trace_id"] = request.trace_id
        
        if usage:
            properties["$ai_input_tokens"] = usage.get("prompt_tokens", 0)
            properties["$ai_output_tokens"] = usage.get("completion_tokens", 0)
        
        if request.properties:
            properties.update(request.properties)
        
        try:
            self.posthog.capture(
                distinct_id=request.user_id,
                event="$ai_generation",
                properties=properties
            )
        except Exception as e:
            logger.warning(f"Failed to track Groq analytics: {e}")
