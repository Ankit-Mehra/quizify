"""
LLM Provider Module.

This module provides an abstraction layer for LLM providers,
enabling easy switching between different AI services while
maintaining consistent API contracts.

Supported Providers:
- OpenAI (default): GPT-4, GPT-4o-mini with PostHog analytics
- Gemini: Google's Gemini models
- Groq: Fast inference with Llama/Mixtral models

Exports:
- ILLMProvider: Abstract interface for LLM providers
- LLMGenerationRequest: Request parameters dataclass
- LLMGenerationResponse: Response dataclass
- get_llm_provider: Factory function to get provider instances
- get_available_providers: List available provider names
- LLMProviderError: Base exception class
- LLMParseError: Exception for parse failures
- LLMRateLimitError: Exception for rate limiting

Example:
    from services.llm import get_llm_provider, LLMGenerationRequest
    
    # Default (OpenAI)
    provider = get_llm_provider()
    
    # Or specify provider
    provider = get_llm_provider("gemini")
    provider = get_llm_provider("groq")
    
    response = await provider.generate(
        LLMGenerationRequest(
            prompt="Generate quiz questions...",
            model="gpt-4o-mini"  # or provider's default
        )
    )
    
    print(response.content)
"""

from services.llm.base import (
    ILLMProvider,
    LLMGenerationRequest,
    LLMGenerationResponse,
    LLMProviderError,
    LLMParseError,
    LLMRateLimitError,
    get_llm_provider,
    get_available_providers,
    reset_provider_instances,
)

__all__ = [
    # Interface and data classes
    "ILLMProvider",
    "LLMGenerationRequest",
    "LLMGenerationResponse",
    # Exceptions
    "LLMProviderError",
    "LLMParseError",
    "LLMRateLimitError",
    # Factory functions
    "get_llm_provider",
    "get_available_providers",
    "reset_provider_instances",
]
