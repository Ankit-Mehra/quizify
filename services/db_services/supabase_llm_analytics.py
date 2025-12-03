from typing import Dict, Any, Optional
from services.logger import db_logger as logger
from config import config


def get_supabase_service():
    """Get service role client (bypasses RLS - required for llm_calls insert)."""
    return config.get_supabase_client()


def track_llm_call(
    user_id: str,
    trace_id: str,
    call_type: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    success: bool = True,
    error_message: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    cost_usd: Optional[float] = None
) -> None:
    """
    Track LLM call in the database for internal analytics.
    
    Uses service role client since llm_calls has a permissive INSERT policy
    for backend tracking. This is intentional for analytics.
    
    This is a synchronous fire-and-forget operation - errors are logged
    but don't fail the main request.
    
    Args:
        user_id: UUID of user making the request
        trace_id: UUID to correlate multi-step workflows
        call_type: 'embedding', 'generation', 'classification', 'extraction'
        model: LLM model used (e.g., 'gpt-4o', 'gpt-4o-mini')
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        latency_ms: Request latency in milliseconds
        success: Whether the call succeeded
        error_message: Error message if failed
        metadata: Additional metadata (feature, question_type, etc.)
        cost_usd: Calculated cost in USD
    """
    supabase = get_supabase_service()
    
    # Handle test mode where supabase is None
    if supabase is None:
        logger.debug("Skipping LLM call tracking in test mode")
        return
    
    data = {
        "user_id": user_id,
        "trace_id": trace_id,
        "call_type": call_type,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "latency_ms": latency_ms,
        "cost_usd": cost_usd,
        "success": success,
        "error_message": error_message,
        "metadata": metadata or {}
    }
    
    try:
        # Synchronous call - fire and forget
        supabase.table("llm_calls").insert(data).execute()
    except Exception as e:
        # Don't fail the request if analytics fails
        logger.error(f"Error tracking LLM call: {str(e)}")
