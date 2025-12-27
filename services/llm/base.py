"""
LLM Provider Abstraction Layer.

This module defines the interface for LLM providers and provides
factory methods for creating provider instances. This enables
switching between different AI providers (OpenAI, Gemini, Groq, etc.)
while maintaining a consistent API.

Currently implemented:
- OpenAI (default)

Future providers (planned):
- Gemini (Google)
- Groq (fast inference)
- Anthropic (Claude)

Usage:
    from services.llm.base import get_llm_provider, LLMGenerationRequest
    
    provider = get_llm_provider()  # Gets default provider (OpenAI)
    
    response = await provider.generate_structured(
        LLMGenerationRequest(
            prompt="Generate 5 quiz questions...",
            response_schema=QuizSchema,
            model="gpt-4o-mini"
        )
    )
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, TypeVar, Type
from dataclasses import dataclass
from pydantic import BaseModel

from services.logger import ai_logger as logger

T = TypeVar('T', bound=BaseModel)


@dataclass
class LLMGenerationRequest:
    """
    Request parameters for LLM generation.
    
    Attributes:
        prompt: The prompt text to send to the LLM
        system_message: Optional system message for chat models
        model: The model to use (provider-specific)
        response_format: Response format type (e.g., "json_object")
        user_id: Optional user ID for analytics
        trace_id: Optional trace ID for request correlation
        properties: Additional properties for analytics tracking
        max_tokens: Maximum tokens to generate (optional)
        temperature: Sampling temperature (default: 1.0)
    """
    prompt: str
    system_message: Optional[str] = None
    model: Optional[str] = None
    response_format: str = "json_object"
    user_id: Optional[str] = None
    trace_id: Optional[str] = None
    properties: Optional[Dict[str, Any]] = None
    max_tokens: Optional[int] = None
    temperature: float = 1.0


@dataclass
class LLMGenerationResponse:
    """
    Response from LLM generation.
    
    Attributes:
        content: The raw response content (usually JSON string)
        model: The model that was actually used
        usage: Token usage statistics (provider-specific)
        latency_ms: Response latency in milliseconds
    """
    content: str
    model: str
    usage: Optional[Dict[str, int]] = None
    latency_ms: Optional[int] = None


class ILLMProvider(ABC):
    """
    Abstract interface for LLM providers.
    
    All LLM providers must implement this interface to ensure
    consistent behavior across different AI services.
    """
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the name of this provider (e.g., 'openai', 'gemini')."""
        raise NotImplementedError
    
    @property
    @abstractmethod
    def default_model(self) -> str:
        """Return the default model for this provider."""
        raise NotImplementedError
    
    @abstractmethod
    async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResponse:
        """
        Generate a response from the LLM.
        
        Args:
            request: The generation request parameters
            
        Returns:
            LLMGenerationResponse with the raw content
            
        Raises:
            LLMProviderError: If generation fails
        """
        raise NotImplementedError
    
    async def generate_structured(
        self,
        request: LLMGenerationRequest,
        response_type: Type[T]
    ) -> T:
        """
        Generate a response and parse it into a structured type.
        
        This is a convenience method that generates raw content and
        validates it against a Pydantic model.
        
        Args:
            request: The generation request parameters
            response_type: The Pydantic model to parse the response into
            
        Returns:
            Parsed response of type T
            
        Raises:
            LLMProviderError: If generation fails
            LLMParseError: If response cannot be parsed into the expected type
        """
        response = await self.generate(request)
        
        try:
            return response_type.model_validate_json(response.content)
        except Exception as e:
            raise LLMParseError(
                message=f"Failed to parse LLM response into {response_type.__name__}",
                raw_response=response.content[:500] if response.content else None,
                original_error=e
            ) from e


class LLMProviderError(Exception):
    """Base exception for LLM provider errors."""
    
    def __init__(
        self,
        message: str,
        provider: str = "unknown",
        original_error: Optional[Exception] = None
    ):
        self.message = message
        self.provider = provider
        self.original_error = original_error
        super().__init__(f"[{provider}] {message}")


class LLMParseError(LLMProviderError):
    """Exception raised when LLM response cannot be parsed."""
    
    def __init__(
        self,
        message: str,
        raw_response: Optional[str] = None,
        original_error: Optional[Exception] = None
    ):
        super().__init__(message, "parse", original_error)
        self.raw_response = raw_response


class LLMRateLimitError(LLMProviderError):
    """Exception raised when rate limited by the LLM provider."""
    
    def __init__(self, provider: str, retry_after: Optional[float] = None):
        super().__init__("Rate limited by provider", provider)
        self.retry_after = retry_after


# =============================================================================
# Provider Factory
# =============================================================================

# Cache for provider instances (one per provider type)
_provider_instances: Dict[str, ILLMProvider] = {}


def get_llm_provider(provider_name: Optional[str] = None) -> ILLMProvider:
    """
    Get an LLM provider instance.
    
    Supports multiple providers:
    - "openai" (default): OpenAI GPT models with PostHog analytics
    - "gemini": Google Gemini models
    - "groq": Fast inference with Llama/Mixtral models
    
    Provider instances are cached for reuse.
    
    Args:
        provider_name: Name of the provider. If None, uses config.DEFAULT_LLM_PROVIDER
        
    Returns:
        An instance of the requested LLM provider
        
    Raises:
        ValueError: If the provider is not supported
    """
    from config import config
    
    # Use config default if no provider specified
    if provider_name is None:
        provider_name = config.DEFAULT_LLM_PROVIDER
    
    # Return cached instance if available
    if provider_name in _provider_instances:
        return _provider_instances[provider_name]
    
    # Create new instance based on provider name
    if provider_name == "openai":
        from services.llm.openai_provider import OpenAIProvider
        _provider_instances[provider_name] = OpenAIProvider()
    elif provider_name == "gemini":
        from services.llm.gemini_provider import GeminiProvider
        _provider_instances[provider_name] = GeminiProvider()
    elif provider_name == "groq":
        from services.llm.groq_provider import GroqProvider
        _provider_instances[provider_name] = GroqProvider()
    else:
        raise ValueError(f"Unsupported LLM provider: {provider_name}. Supported: openai, gemini, groq")
    
    return _provider_instances[provider_name]


def get_available_providers() -> list[str]:
    """Return list of available provider names."""
    return ["openai", "gemini", "groq"]


def reset_provider_instances() -> None:
    """
    Reset all cached provider instances.
    
    Useful for testing or when provider configuration changes.
    """
    _provider_instances.clear()
    logger.info("LLM provider instances reset")
    logger.info("LLM provider instance reset")
