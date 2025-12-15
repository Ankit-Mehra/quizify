"""
Shared LLM pricing constants and cost calculation utilities.

Centralizes pricing information to avoid duplication across services.
"""

from typing import Dict

# Pricing per 1K tokens (as of Dec 2024)
# Source: https://openai.com/pricing
LLM_PRICING: Dict[str, Dict[str, float]] = {
    "gpt-4.1": {"input": 0.002, "output": 0.008},
    "gpt-4.1-mini": {"input": 0.0004, "output": 0.0016},
    # Legacy models (keep for backward compatibility)
    "gpt-4o": {"input": 0.0025, "output": 0.01},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "text-embedding-3-small": {"input": 0.00002, "output": 0},
}


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """
    Calculate USD cost for an LLM call.
    
    Args:
        model: The model name (e.g., "gpt-4o", "gpt-4o-mini")
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        
    Returns:
        Cost in USD
    """
    pricing = LLM_PRICING.get(model, {"input": 0, "output": 0})
    return (input_tokens * pricing["input"] / 1000) + (output_tokens * pricing["output"] / 1000)
