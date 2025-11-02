"""
Redis services for distributed state management.

This module provides:
- Redis client initialization and lifecycle management
- Connection pooling for optimal performance
- Health checks and automatic reconnection
- Graceful fallback to in-memory storage
"""

from .client import get_redis_client, lifespan, check_redis_health

__all__ = ["get_redis_client", "lifespan", "check_redis_health"]
