"""
Base class for Redis-backed services with automatic memory fallback.

This module provides a foundation for building services that:
1. Try to use Redis for distributed state (production)
2. Automatically fall back to in-memory storage if Redis unavailable (dev/outage)
3. Log all fallback events for monitoring
4. Maintain consistent interface regardless of backend
"""

from typing import Optional, Any
from abc import ABC
from collections import defaultdict
import asyncio

from services.logger import app_logger as logger
from services.redis.client import get_redis_client
import redis.asyncio as redis


class RedisServiceBase(ABC):
    """
    Base class for services using Redis with memory fallback.
    
    Subclasses should implement:
    - _redis_<operation>(): Redis implementation
    - _memory_<operation>(): In-memory fallback implementation
    
    The base class automatically chooses the correct backend.
    """
    
    def __init__(self):
        # In-memory storage for fallback (per-instance storage)
        self._memory_store: dict = {}
        self._memory_lock = asyncio.Lock()
        
    def _get_redis_client(self) -> Optional[redis.Redis]:
        """Get Redis client or None if unavailable"""
        return get_redis_client()
    
    async def _with_fallback(
        self, 
        redis_fn, 
        memory_fn, 
        operation_name: str,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute operation with automatic fallback.
        
        Args:
            redis_fn: Async function to call with Redis
            memory_fn: Async function to call with memory fallback
            operation_name: Name for logging
            *args, **kwargs: Arguments to pass to both functions
            
        Returns:
            Result from redis_fn or memory_fn
        """
        redis_client = self._get_redis_client()
        
        if redis_client:
            try:
                return await redis_fn(*args, **kwargs)
            except redis.RedisError as e:
                logger.warning(
                    f"🚨 Redis {operation_name} failed (RedisError), using memory fallback: {type(e).__name__}"
                )
            except Exception as e:
                logger.error(
                    f"🚨 Unexpected error in Redis {operation_name}, using memory fallback: {type(e).__name__}",
                    exc_info=True
                )
        
        # Fallback to memory
        return await memory_fn(*args, **kwargs)


class RedisMetricsMixin:
    """
    Mixin for tracking Redis operations metrics.
    
    Add this to services that want operation counting.
    """
    
    def __init__(self):
        super().__init__()
        self._metrics = defaultdict(int)
    
    def _increment_metric(self, metric_name: str):
        """Increment a metric counter"""
        self._metrics[metric_name] += 1
    
    def get_metrics(self) -> dict:
        """Get all metrics"""
        return dict(self._metrics)
    
    def reset_metrics(self):
        """Reset all metrics to zero"""
        self._metrics.clear()
