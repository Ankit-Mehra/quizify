"""
LLM Provider Module.

This module provides an abstraction layer for LLM providers,
enabling easy switching between different AI services while
maintaining consistent API contracts.

Exports:
- ILLMProvider: Abstract interface for LLM providers
- LLMGenerationRequest: Request parameters dataclass
- LLMGenerationResponse: Response dataclass
- get_llm_provider: Factory function to get provider instances
- LLMProviderError: Base exception class
- LLMParseError: Exception for parse failures
- LLMRateLimitError: Exception for rate limiting

Example:
    from services.llm import get_llm_provider, LLMGenerationRequest
    
    provider = get_llm_provider()
    
    response = await provider.generate(
        LLMGenerationRequest(
            prompt="Generate quiz questions...",
            model="gpt-4o-mini"
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
    reset_provider_instance,
)

__all__ = [
    "ILLMProvider",
    "LLMGenerationRequest",
    "LLMGenerationResponse",
    "LLMProviderError",
    "LLMParseError",
    "LLMRateLimitError",
    "get_llm_provider",
    "reset_provider_instance",
]
