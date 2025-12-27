"""
Gemini LLM Provider Implementation.

This module implements the ILLMProvider interface for Google's Gemini,
enabling use of Gemini models as an alternative to OpenAI.

Features:
- Structured JSON output support
- PostHog analytics tracking (manual, not wrapped like OpenAI)
- Retry logic for transient errors
"""

import os
import time
import asyncio
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

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


class GeminiProvider(ILLMProvider):
    """
    Google Gemini implementation of the LLM provider interface.
    
    This provider uses Google's genai SDK to interact with Gemini models.
    Analytics are tracked manually via PostHog since there's no native wrapper.
    
    Note: Requires GEMINI_API_KEY environment variable to be set.
    """
    
    def __init__(self):
        """Initialize the Gemini provider."""
        self._client = None
        self._posthog = None
        
        if not GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY not set - Gemini provider will fail on use")
    
    @property
    def provider_name(self) -> str:
        """Return 'gemini' as the provider name."""
        return "gemini"
    
    @property
    def default_model(self) -> str:
        """Return the default Gemini model from config."""
        return config.GEMINI_MODEL_DEFAULT
    
    @property
    def client(self):
        """Lazy-load the Gemini client."""
        if self._client is None:
            try:
                from google import genai
                self._client = genai.Client(api_key=GEMINI_API_KEY)
                logger.info("Gemini client initialized")
            except ImportError as exc:
                raise LLMProviderError(
                    "google-genai package not installed. Run: pip install google-genai",
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
        Generate a response using Gemini's API.
        
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
            "Gemini generation request: model=%s, prompt_len=%d",
            model, len(request.prompt)
        )
        
        try:
            # Build generation config
            gen_config = {}
            if request.response_format == "json_object":
                gen_config["response_mime_type"] = "application/json"
            
            if request.max_tokens:
                gen_config["max_output_tokens"] = request.max_tokens
            
            if request.temperature != 1.0:
                gen_config["temperature"] = request.temperature
            
            # Build prompt with system message if provided
            prompt = request.prompt
            if request.system_message:
                prompt = f"{request.system_message}\n\n{request.prompt}"
            
            # Gemini's generate_content is synchronous, run in thread
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=model,
                contents=prompt,
                config=gen_config if gen_config else None
            )
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            # Extract content
            content = ""
            if response.text:
                content = response.text
            elif hasattr(response, 'candidates') and response.candidates:
                content = response.candidates[0].content.parts[0].text
            
            # Extract usage if available
            usage = None
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                usage = {
                    "prompt_tokens": getattr(response.usage_metadata, 'prompt_token_count', 0),
                    "completion_tokens": getattr(response.usage_metadata, 'candidates_token_count', 0),
                    "total_tokens": getattr(response.usage_metadata, 'total_token_count', 0),
                }
            
            # Track analytics manually
            self._track_analytics(request, model, latency_ms, usage)
            
            logger.debug(
                "Gemini generation completed: model=%s, latency=%dms",
                model, latency_ms
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
            if "rate" in error_msg and "limit" in error_msg:
                raise LLMRateLimitError(self.provider_name) from e
            
            if "quota" in error_msg:
                raise LLMRateLimitError(self.provider_name) from e
            
            logger.error("Gemini generation failed: %s: %s", error_type, e)
            raise LLMProviderError(
                message=str(e),
                provider=self.provider_name,
                original_error=e
            ) from e
    
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
            "$ai_provider": "gemini",
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
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to track Gemini analytics: %s", e)
