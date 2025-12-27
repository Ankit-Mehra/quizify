"""
OpenAI LLM Provider Implementation.

This module implements the ILLMProvider interface for OpenAI,
leveraging the existing openai_service infrastructure including:
- PostHog analytics integration
- Connection pooling
- Retry logic with exponential backoff
- Thread-safe client initialization
"""

import time

from services.llm.base import (
    ILLMProvider,
    LLMGenerationRequest,
    LLMGenerationResponse,
    LLMProviderError,
    LLMRateLimitError,
)
from services.ai_services.llm_client_service import (
    get_openai_client,
    _build_posthog_kwargs,
    _retry_with_backoff,
)
from services.logger import ai_logger as logger
from config import config


class OpenAIProvider(ILLMProvider):
    """
    OpenAI implementation of the LLM provider interface.
    
    This provider wraps the existing OpenAI client infrastructure
    and provides a consistent interface for LLM operations.
    
    Features:
    - PostHog analytics integration (when enabled)
    - Automatic retry with exponential backoff
    - Connection pooling for high throughput
    - Thread-safe client initialization
    """
    
    def __init__(self):
        """Initialize the OpenAI provider."""
        self._client = None
    
    @property
    def provider_name(self) -> str:
        """Return 'openai' as the provider name."""
        return "openai"
    
    @property
    def default_model(self) -> str:
        """Return the default model from config."""
        return config.LLM_MODEL_MINI
    
    @property
    def client(self):
        """Lazy-load the OpenAI client."""
        if self._client is None:
            self._client = get_openai_client()
        return self._client
    
    async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResponse:
        """
        Generate a response using OpenAI's API.
        
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
            "OpenAI generation request: model=%s, prompt_len=%d",
            model, len(request.prompt)
        )
        
        # Build PostHog kwargs if analytics enabled
        posthog_kwargs = _build_posthog_kwargs(
            user_id=request.user_id,
            trace_id=request.trace_id,
            properties=request.properties
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
            **posthog_kwargs
        }
        
        # Add response format if specified
        if request.response_format:
            request_kwargs["response_format"] = {"type": request.response_format}
        
        # Add optional parameters
        if request.max_tokens:
            request_kwargs["max_tokens"] = request.max_tokens
        
        if request.temperature != 1.0:
            request_kwargs["temperature"] = request.temperature
        
        try:
            # Use retry wrapper for transient errors
            response = await _retry_with_backoff(
                lambda: self.client.chat.completions.create(**request_kwargs)
            )
            
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
            
            logger.debug(
                "OpenAI generation completed: model=%s, latency=%dms, tokens=%s",
                model, latency_ms, usage.get("total_tokens") if usage else "N/A"
            )
            
            return LLMGenerationResponse(
                content=content,
                model=model,
                usage=usage,
                latency_ms=latency_ms
            )
            
        except Exception as e:
            # Map OpenAI exceptions to provider exceptions
            error_type = type(e).__name__
            
            if "RateLimitError" in error_type:
                retry_after = getattr(e, 'retry_after', None)
                raise LLMRateLimitError(self.provider_name, retry_after) from e
            
            logger.error("OpenAI generation failed: %s: %s", error_type, e)
            raise LLMProviderError(
                message=str(e),
                provider=self.provider_name,
                original_error=e
            ) from e
