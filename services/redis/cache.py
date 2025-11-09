"""
Generic caching service with Redis backend and memory fallback.

Provides:
- Generic Pydantic model support for type-safe caching
- JSON serialization/deserialization
- Cache-aside pattern (get_or_fetch)
- Pattern-based deletion
- TTL management
- Statistics tracking (hits, misses)
- Automatic memory fallback when Redis unavailable
"""

from typing import TypeVar, Optional, Callable, Awaitable, Dict, Any
from pydantic import BaseModel, ValidationError
from collections import defaultdict
import asyncio
import re

from services.redis.base import RedisServiceBase, RedisMetricsMixin
from services.logger import app_logger as logger


# Generic type variable bound to Pydantic BaseModel
T = TypeVar('T', bound=BaseModel)


class CacheService(RedisServiceBase, RedisMetricsMixin):
    """
    Generic caching service with Pydantic model support.
    
    Features:
    - Type-safe caching with Pydantic models
    - Cache-aside pattern for easy integration
    - Pattern-based key deletion
    - Hit/miss statistics tracking
    - Automatic memory fallback
    
    Usage:
        cache = CacheService(prefix="quiz")
        user = await cache.get("user:123", UserProfile)
        await cache.set("user:123", user_obj, ttl=300)
    """
    
    def __init__(self, prefix: str = "cache"):
        """
        Initialize cache service.
        
        Args:
            prefix: Key prefix for namespacing (e.g., "cache", "quiz", "user")
        """
        RedisServiceBase.__init__(self)
        RedisMetricsMixin.__init__(self)
        self.prefix = prefix
        
        # Track expiry tasks to prevent race conditions when re-setting keys
        self._expiry_tasks: Dict[str, asyncio.Task] = {}
        
        # Initialize metrics if not already done by RedisMetricsMixin
        if not hasattr(self, '_metrics'):
            self._metrics = defaultdict(int)
    
    def _build_key(self, key: str) -> str:
        """Build full cache key with prefix"""
        return f"{self.prefix}:{key}"
    
    async def get(self, key: str, model: type[T]) -> Optional[T]:
        """
        Get cached value and deserialize to Pydantic model.
        
        Args:
            key: Cache key (without prefix)
            model: Pydantic model class for deserialization
            
        Returns:
            Deserialized model instance or None if not found
        """
        return await self._with_fallback(
            self._redis_get,
            self._memory_get,
            "cache_get",
            key, model
        )
    
    async def _redis_get(self, key: str, model: type[T]) -> Optional[T]:
        """Redis implementation of get"""
        redis_client = self._get_redis_client()
        if not redis_client:
            return None
        
        full_key = self._build_key(key)
        cached = await redis_client.get(full_key)
        
        if cached:
            self._increment_metric("redis_cache_hits")
            logger.debug(f"Cache HIT (Redis): {full_key}")
            try:
                return model.model_validate_json(cached)
            except ValidationError as e:
                logger.error(f"Failed to deserialize cached value for {full_key}: {e}")
                # Delete corrupted cache entry
                await redis_client.delete(full_key)
                return None
        else:
            self._increment_metric("redis_cache_misses")
            logger.debug(f"Cache MISS (Redis): {full_key}")
            return None
    
    async def _memory_get(self, key: str, model: type[T]) -> Optional[T]:
        """Memory fallback for get"""
        full_key = self._build_key(key)
        
        async with self._memory_lock:
            if full_key in self._memory_store:
                self._increment_metric("memory_cache_hits")
                logger.debug(f"Cache HIT (Memory): {full_key}")
                return self._memory_store[full_key]
            else:
                self._increment_metric("memory_cache_misses")
                logger.debug(f"Cache MISS (Memory): {full_key}")
                return None
    
    async def set(self, key: str, value: T, ttl: int = 300) -> None:
        """
        Set cached value with TTL.
        
        Args:
            key: Cache key (without prefix)
            value: Pydantic model instance to cache
            ttl: Time to live in seconds (default: 5 minutes)
        """
        return await self._with_fallback(
            self._redis_set,
            self._memory_set,
            "cache_set",
            key, value, ttl
        )
    
    async def _redis_set(self, key: str, value: T, ttl: int) -> None:
        """Redis implementation of set"""
        redis_client = self._get_redis_client()
        if not redis_client:
            return
        
        full_key = self._build_key(key)
        
        try:
            # Serialize Pydantic model to JSON
            json_value = value.model_dump_json()
            await redis_client.setex(full_key, ttl, json_value)
            self._increment_metric("redis_cache_sets")
            logger.debug(f"Cache SET (Redis): {full_key} [TTL={ttl}s]")
        except Exception as e:
            logger.error(f"Failed to cache value for {full_key}: {e}")
            # Don't raise - gracefully degrade, request should continue
            # Memory fallback will be used automatically via _with_fallback
    
    async def _memory_set(self, key: str, value: T, ttl: int) -> None:
        """Memory fallback for set"""
        full_key = self._build_key(key)
        
        async with self._memory_lock:
            # Cancel any existing expiry task for this key to prevent race conditions
            if full_key in self._expiry_tasks:
                task = self._expiry_tasks[full_key]
                task.cancel()
                # Remove from tracking immediately to avoid handling in _memory_expire
                del self._expiry_tasks[full_key]
            
            self._memory_store[full_key] = value
            self._increment_metric("memory_cache_sets")
            logger.debug(f"Cache SET (Memory): {full_key}")
            
            # Schedule cleanup after TTL (in-memory TTL simulation) and track task
            task = asyncio.create_task(self._memory_expire(full_key, ttl))
            self._expiry_tasks[full_key] = task
    
    async def _memory_expire(self, full_key: str, ttl: int):
        """Simulate TTL expiration in memory"""
        try:
            await asyncio.sleep(ttl)
            async with self._memory_lock:
                if full_key in self._memory_store:
                    del self._memory_store[full_key]
                    logger.debug(f"Cache EXPIRED (Memory): {full_key}")
                # Remove completed task from tracking
                self._expiry_tasks.pop(full_key, None)
        except asyncio.CancelledError:
            # Task was cancelled (key was re-set), clean up tracking
            self._expiry_tasks.pop(full_key, None)
            logger.debug(f"Cache EXPIRY CANCELLED (Memory): {full_key}")
    
    async def get_or_fetch(
        self,
        key: str,
        fetch_fn: Callable[[], Awaitable[T]],
        model: type[T],
        ttl: int = 300
    ) -> T:
        """
        Cache-aside pattern: Try cache first, fetch and cache on miss.
        
        This is the recommended way to use the cache service.
        
        Args:
            key: Cache key (without prefix)
            fetch_fn: Async function to fetch value on cache miss
            model: Pydantic model class
            ttl: Time to live in seconds (default: 5 minutes)
            
        Returns:
            Cached or freshly fetched model instance
            
        Example:
            async def fetch_user():
                return await db.get_user(user_id)
            
            user = await cache.get_or_fetch(
                f"user:{user_id}",
                fetch_user,
                UserProfile,
                ttl=300
            )
        """
        # Try cache first
        cached = await self.get(key, model)
        if cached is not None:
            return cached
        
        # Cache miss - fetch from source
        logger.debug(f"Cache miss - fetching fresh data for: {self._build_key(key)}")
        try:
            value = await fetch_fn()
        except Exception as e:
            logger.error(f"Failed to fetch data for {self._build_key(key)}: {e}")
            raise  # Re-raise fetch errors - these are business logic failures
        
        # Try to cache result for next time, but don't fail the request if caching fails
        try:
            await self.set(key, value, ttl)
        except Exception as e:
            # Cache set failure is non-critical, already logged in _redis_set
            pass
        
        return value
    
    async def delete(self, key: str) -> bool:
        """
        Delete a single cache entry.
        
        Args:
            key: Cache key (without prefix)
            
        Returns:
            True if key was deleted, False if not found
        """
        return await self._with_fallback(
            self._redis_delete,
            self._memory_delete,
            "cache_delete",
            key
        )
    
    async def _redis_delete(self, key: str) -> bool:
        """Redis implementation of delete"""
        redis_client = self._get_redis_client()
        if not redis_client:
            return False
        
        full_key = self._build_key(key)
        deleted = await redis_client.delete(full_key)
        
        if deleted > 0:
            self._increment_metric("redis_cache_deletes")
            logger.debug(f"Cache DELETE (Redis): {full_key}")
            return True
        return False
    
    async def _memory_delete(self, key: str) -> bool:
        """Memory fallback for delete"""
        full_key = self._build_key(key)
        
        async with self._memory_lock:
            if full_key in self._memory_store:
                del self._memory_store[full_key]
                self._increment_metric("memory_cache_deletes")
                logger.debug(f"Cache DELETE (Memory): {full_key}")
                return True
            return False
    
    async def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching a pattern.
        
        Args:
            pattern: Pattern to match (e.g., "user:*", "quiz:123:*")
                     Will be prefixed automatically
            
        Returns:
            Number of keys deleted
            
        Example:
            # Delete all user caches
            await cache.delete_pattern("user:*")
            
            # Delete all caches for a specific quiz
            await cache.delete_pattern("quiz:123:*")
        """
        return await self._with_fallback(
            self._redis_delete_pattern,
            self._memory_delete_pattern,
            "cache_delete_pattern",
            pattern
        )
    
    async def _redis_delete_pattern(self, pattern: str) -> int:
        """Redis implementation of delete_pattern"""
        redis_client = self._get_redis_client()
        if not redis_client:
            return 0
        
        full_pattern = self._build_key(pattern)
        deleted_count = 0
        
        # Use SCAN to find matching keys (more memory efficient than KEYS)
        # Use pipeline for efficient batch deletion
        cursor = 0
        pipeline = redis_client.pipeline()
        keys_to_delete = []
        
        while True:
            cursor, keys = await redis_client.scan(
                cursor=cursor,
                match=full_pattern,
                count=100
            )
            
            if keys:
                keys_to_delete.extend(keys)
            
            if cursor == 0:
                break
        
        # Execute batch deletion via pipeline for better performance
        if keys_to_delete:
            for key in keys_to_delete:
                pipeline.unlink(key)  # UNLINK is async, faster than DELETE
            await pipeline.execute()
            deleted_count = len(keys_to_delete)
        
        if deleted_count > 0:
            self._increment_metric("redis_cache_pattern_deletes")
            logger.debug(f"Cache DELETE PATTERN (Redis): {full_pattern} [{deleted_count} keys]")
        
        return deleted_count
    
    async def _memory_delete_pattern(self, pattern: str) -> int:
        """Memory fallback for delete_pattern"""
        full_pattern = self._build_key(pattern)
        
        # Convert Redis pattern to Python pattern (simple * wildcard support)
        regex_pattern = full_pattern.replace("*", ".*")
        regex = re.compile(f"^{regex_pattern}$")
        
        async with self._memory_lock:
            keys_to_delete = [
                key for key in self._memory_store.keys()
                if regex.match(key)
            ]
            
            for key in keys_to_delete:
                del self._memory_store[key]
            
            if keys_to_delete:
                self._increment_metric("memory_cache_pattern_deletes")
                logger.debug(
                    f"Cache DELETE PATTERN (Memory): {full_pattern} "
                    f"[{len(keys_to_delete)} keys]"
                )
            
            return len(keys_to_delete)
    
    async def exists(self, key: str) -> bool:
        """
        Check if a cache key exists.
        
        Args:
            key: Cache key (without prefix)
            
        Returns:
            True if key exists, False otherwise
        """
        return await self._with_fallback(
            self._redis_exists,
            self._memory_exists,
            "cache_exists",
            key
        )
    
    async def _redis_exists(self, key: str) -> bool:
        """Redis implementation of exists"""
        redis_client = self._get_redis_client()
        if not redis_client:
            return False
        
        full_key = self._build_key(key)
        exists = await redis_client.exists(full_key)
        return bool(exists)
    
    async def _memory_exists(self, key: str) -> bool:
        """Memory fallback for exists"""
        full_key = self._build_key(key)
        
        async with self._memory_lock:
            return full_key in self._memory_store
    
    async def get_ttl(self, key: str) -> int:
        """
        Get remaining TTL for a key.
        
        Args:
            key: Cache key (without prefix)
            
        Returns:
            Remaining TTL in seconds, -1 if no TTL, -2 if key doesn't exist
        """
        return await self._with_fallback(
            self._redis_get_ttl,
            self._memory_get_ttl,
            "cache_get_ttl",
            key
        )
    
    async def _redis_get_ttl(self, key: str) -> int:
        """Redis implementation of get_ttl"""
        redis_client = self._get_redis_client()
        if not redis_client:
            return -2
        
        full_key = self._build_key(key)
        ttl = await redis_client.ttl(full_key)
        return ttl
    
    async def _memory_get_ttl(self, key: str) -> int:
        """Memory fallback for get_ttl"""
        # In-memory doesn't track TTL precisely, just check existence
        exists = await self._memory_exists(key)
        return -1 if exists else -2
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dict with hit/miss counts and hit rate
            
        Example:
            {
                "redis_cache_hits": 150,
                "redis_cache_misses": 50,
                "redis_hit_rate": 0.75,
                "memory_cache_hits": 10,
                "memory_cache_misses": 5,
                "total_operations": 215
            }
        """
        metrics = self.get_metrics()
        
        # Calculate hit rates
        redis_hits = metrics.get("redis_cache_hits", 0)
        redis_misses = metrics.get("redis_cache_misses", 0)
        redis_total = redis_hits + redis_misses
        redis_hit_rate = redis_hits / redis_total if redis_total > 0 else 0.0
        
        memory_hits = metrics.get("memory_cache_hits", 0)
        memory_misses = metrics.get("memory_cache_misses", 0)
        memory_total = memory_hits + memory_misses
        memory_hit_rate = memory_hits / memory_total if memory_total > 0 else 0.0
        
        return {
            **metrics,
            "redis_hit_rate": round(redis_hit_rate, 3),
            "memory_hit_rate": round(memory_hit_rate, 3),
            "total_operations": sum(metrics.values())
        }


# Global cache service instances (lazy initialization) - dict for per-prefix singletons
_cache_services: Dict[str, CacheService] = {}


def get_cache_service(prefix: str = "cache") -> CacheService:
    """
    Get or create cache service instance.
    
    Args:
        prefix: Cache key prefix for namespacing
        
    Returns:
        CacheService instance (singleton per prefix)
        
    Note:
        This returns a singleton per prefix. Multiple prefixes are supported
        and each maintains its own instance.
    """
    global _cache_services
    if prefix not in _cache_services:
        _cache_services[prefix] = CacheService(prefix=prefix)
    return _cache_services[prefix]
