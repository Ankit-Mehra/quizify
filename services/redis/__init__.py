"""
Redis services for distributed state management.

This module provides:
- Redis client initialization and lifecycle management
- Connection pooling for optimal performance
- Health checks and automatic reconnection
- Graceful fallback to in-memory storage
- Browser slot management for distributed coordination
- Generic caching service with Pydantic support
"""

from .client import get_redis_client, lifespan, check_redis_health
from .browser_slots import browser_slot_manager
from .cache import CacheService, get_cache_service

__all__ = [
    "get_redis_client",
    "lifespan",
    "check_redis_health",
    "browser_slot_manager",
    "CacheService",
    "get_cache_service",
]
