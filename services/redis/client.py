"""
Redis client management for FastAPI application.

Features:
- Connection pooling (20 max connections)
- Health checks every 30 seconds
- FastAPI lifespan integration
- Automatic reconnection on failure
"""

import time
import redis.asyncio as redis
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI
from services.logger import app_logger as logger
from config import config as app_config

# Global Redis client instance
redis_client: Optional[redis.Redis] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager for Redis connection.
    
    Manages Redis connection pool lifecycle:
    - Startup: Initialize connection pool and test connectivity
    - Shutdown: Gracefully close all connections
    
    If Redis is unavailable, logs error but allows app to start
    (services will fall back to in-memory storage).
    """
    global redis_client
    
    if app_config.REDIS_ENABLED and app_config.REDIS_URL:
        try:
            logger.info(f"Connecting to Redis at {app_config.REDIS_URL[:20]}...")
            
            redis_client = redis.from_url(
                app_config.REDIS_URL,
                max_connections=app_config.REDIS_MAX_CONNECTIONS,
                socket_timeout=app_config.REDIS_SOCKET_TIMEOUT,
                socket_connect_timeout=app_config.REDIS_SOCKET_CONNECT_TIMEOUT,
                decode_responses=True,  # Automatically decode bytes to strings
                health_check_interval=app_config.REDIS_HEALTH_CHECK_INTERVAL
            )
            
            # Test connection
            await redis_client.ping()
            logger.info("✅ Redis connected successfully")
            
            # Store in app.state for access in request handlers
            app.state.redis = redis_client
            
        except redis.RedisError as e:
            logger.error(f"❌ Redis connection failed: {e}")
            logger.warning("Application will use memory fallback for state management")
            redis_client = None
            
        except Exception as e:
            logger.error(f"❌ Unexpected error connecting to Redis: {e}")
            redis_client = None
    else:
        logger.info("Redis disabled via configuration, using memory fallback")
    
    yield
    
    # Cleanup: Close Redis connection pool
    if redis_client:
        try:
            await redis_client.aclose()
            logger.info("Redis connection pool closed")
        except Exception as e:
            logger.error(f"Error closing Redis connection: {e}")


def get_redis_client() -> Optional[redis.Redis]:
    """
    Get the global Redis client instance.
    
    Returns:
        redis.Redis instance if connected, None if unavailable
        
    Usage:
        redis_client = get_redis_client()
        if redis_client:
            await redis_client.set("key", "value")
        else:
            # Use memory fallback
            pass
    """
    return redis_client


async def check_redis_health() -> dict:
    """
    Check Redis connectivity and return health status.
    
    Returns:
        dict with keys:
            - connected: bool
            - latency_ms: float (if connected)
            - error: str (if disconnected)
    """
    if not redis_client:
        return {"connected": False, "error": "Redis client not initialized"}
    
    try:
        start = time.time()
        await redis_client.ping()
        latency = (time.time() - start) * 1000  # Convert to milliseconds
        
        return {
            "connected": True,
            "latency_ms": round(latency, 2)
        }
    except Exception as e:
        return {
            "connected": False,
            "error": str(e)
        }
