"""
Redis-based browser slot management service.

Replaces in-memory browser slot tracking with distributed Redis coordination,
enabling horizontal scaling across multiple application instances.

Features:
- Per-user concurrent browser limits
- Automatic slot expiration (TTL)
- Distributed coordination across instances
- Memory fallback when Redis unavailable
"""

import asyncio
from typing import Optional
from fastapi import HTTPException
import redis.asyncio as redis
from services.redis.base import RedisServiceBase, RedisMetricsMixin
from services.logger import app_logger as logger
from config import config as app_config


class BrowserSlotManager(RedisServiceBase, RedisMetricsMixin):
    """
    Manages browser slot allocation across distributed instances.
    
    Uses Redis for coordination when available, falls back to in-memory
    tracking when Redis is unavailable (single-instance mode).
    
    Locking Algorithm (Redis Mode):
    1. Acquire distributed lock using Redis SET NX (atomic test-and-set)
    2. Fetch current slot count under lock protection (prevents race conditions)
    3. If under limit, increment count and set TTL
    4. Release lock using Lua script (atomic check-and-delete with owner verification)
    
    Retry Policy:
    - Single retry with 100ms backoff if lock is busy
    - Returns 503 if still busy after retry
    
    Race Condition Prevention:
    - Lock prevents concurrent modifications to slot count across instances
    - Slot count is always refetched after acquiring lock (even after retry)
    - Lua script ensures only lock owner can release the lock
    - TTL on lock prevents indefinite blocking (30s timeout for slow networks)
    - TTL on slots ensures automatic cleanup after 5 minutes
    
    Metrics Tracked:
    - slot_acquisition_attempts: Total attempts to acquire slots
    - slot_acquisition_success: Successful slot acquisitions
    - slot_limit_exceeded: Number of times 429 returned (user at limit)
    - slot_service_busy: Number of times 503 returned (lock contention)
    - slot_release_count: Total slot releases
    - redis_mode_used: Operations using Redis
    - memory_mode_used: Operations using memory fallback
    """
    
    def __init__(self):
        # Initialize both parent classes (RedisServiceBase and RedisMetricsMixin)
        super().__init__()
        # Explicitly initialize metrics if not already done by mixin
        if not hasattr(self, '_metrics'):
            from collections import defaultdict
            self._metrics = defaultdict(int)
        self._max_slots = app_config.MAX_CONCURRENT_BROWSERS
        self._slot_ttl = app_config.REDIS_BROWSER_SLOT_TTL
        
    def _get_slot_key(self, user_id: str) -> str:
        """Generate Redis key for user's browser slots"""
        return f"browser_slots:{user_id}"
    
    def _get_lock_key(self, user_id: str) -> str:
        """Generate Redis key for user's slot lock"""
        return f"browser_slots:lock:{user_id}"
    
    async def acquire_slot(self, user_id: str) -> None:
        """
        Acquire a browser slot for the user.
        
        Enforces MAX_CONCURRENT_BROWSERS limit per user across all instances.
        
        Args:
            user_id: User ID to acquire slot for
            
        Raises:
            HTTPException: 429 if user has exceeded concurrent browser limit
        """
        self._increment_metric("slot_acquisition_attempts")
        try:
            await self._with_fallback(
                self._acquire_slot_redis,
                self._acquire_slot_memory,
                "acquire_slot",
                user_id
            )
            self._increment_metric("slot_acquisition_success")
        except HTTPException as e:
            if e.status_code == 429:
                self._increment_metric("slot_limit_exceeded")
            elif e.status_code == 503:
                self._increment_metric("slot_service_busy")
            raise
    
    async def release_slot(self, user_id: str) -> None:
        """
        Release a browser slot for the user.
        
        Args:
            user_id: User ID to release slot for
        """
        self._increment_metric("slot_release_count")
        await self._with_fallback(
            self._release_slot_redis,
            self._release_slot_memory,
            "release_slot",
            user_id
        )
    
    async def get_slot_count(self, user_id: str) -> int:
        """
        Get current number of active browser slots for user.
        
        Args:
            user_id: User ID to check
            
        Returns:
            Number of active slots (0 if none)
        """
        return await self._with_fallback(
            self._get_slot_count_redis,
            self._get_slot_count_memory,
            "get_slot_count",
            user_id
        )
    
    # ========================================================================
    # REDIS IMPLEMENTATION (Distributed)
    # ========================================================================
    
    async def _acquire_slot_redis(self, user_id: str) -> None:
        """Redis implementation of slot acquisition with distributed locking"""
        self._increment_metric("redis_mode_used")
        redis_client = self._get_redis_client()
        if not redis_client:
            raise Exception("Redis client not available")
        
        slot_key = self._get_slot_key(user_id)
        lock_key = self._get_lock_key(user_id)
        
        # Use Redis SET NX (set if not exists) as a distributed lock
        # This prevents race conditions across multiple instances
        lock_acquired = False
        lock_value = f"{asyncio.current_task().get_name()}_{id(asyncio.current_task())}"
        
        try:
            # Try to acquire lock (expires in 30 seconds as safety)
            lock_acquired = await redis_client.set(
                lock_key,
                lock_value,
                nx=True,  # Only set if doesn't exist
                ex=30  # Expire in 30 seconds (prevents deadlock, allows for slow networks)
            )
            
            if not lock_acquired:
                # Another instance is modifying this user's slots
                logger.debug(f"Lock busy for user {user_id[:8]}..., retrying...")
                await asyncio.sleep(0.1)  # Brief wait
                # Retry once
                lock_acquired = await redis_client.set(lock_key, lock_value, nx=True, ex=30)
                if not lock_acquired:
                    logger.warning(f"Failed to acquire lock for user {user_id[:8]}... after retry")
                    raise HTTPException(
                        status_code=503,
                        detail="Browser slot service temporarily busy, please retry"
                    )
                logger.debug(f"Lock acquired on retry for user {user_id[:8]}...")
            else:
                logger.debug(f"Lock acquired for user {user_id[:8]}... by task {lock_value[:20]}... (Redis mode)")
            
            # ALWAYS fetch current count after acquiring lock (prevents stale data race condition)
            current_count = await redis_client.get(slot_key)
            current_count = int(current_count) if current_count else 0
            
            # Check limit INSIDE try block to ensure lock is released on exception
            if current_count >= self._max_slots:
                logger.warning(
                    f"User {user_id[:8]}... exceeded browser limit: {current_count}/{self._max_slots}"
                )
                raise HTTPException(
                    status_code=429,
                    detail=f"Too many concurrent browser sessions. Maximum allowed: {self._max_slots}"
                )
            
            # Increment slot count with TTL
            new_count = current_count + 1
            await redis_client.set(slot_key, new_count, ex=self._slot_ttl)
            
            logger.debug(f"Browser slot acquired for user {user_id[:8]}...: {new_count}/{self._max_slots} (Redis mode)")
            
        except HTTPException:
            # Re-raise HTTP exceptions (429, 503) after lock cleanup
            raise
        except redis.RedisError as e:
            logger.error(f"Redis error in slot acquisition for user {user_id[:8]}...: {e}")
            raise Exception("Redis error during slot acquisition")
        finally:
            # Always release the lock
            if lock_acquired:
                # Only delete if we still own the lock (value matches)
                script = """
                if redis.call("get", KEYS[1]) == ARGV[1] then
                    return redis.call("del", KEYS[1])
                else
                    return 0
                end
                """
                await redis_client.eval(script, 1, lock_key, lock_value)
    
    async def _release_slot_redis(self, user_id: str) -> None:
        """Redis implementation of slot release"""
        redis_client = self._get_redis_client()
        if not redis_client:
            raise Exception("Redis client not available")
        
        slot_key = self._get_slot_key(user_id)
        
        # Decrement slot count (minimum 0)
        current_count = await redis_client.get(slot_key)
        if current_count:
            current_count = int(current_count)
            if current_count > 0:
                new_count = current_count - 1
                if new_count > 0:
                    # Still has active slots, update with TTL
                    await redis_client.set(slot_key, new_count, ex=self._slot_ttl)
                else:
                    # No more slots, delete key
                    await redis_client.delete(slot_key)
                
                logger.debug(f"Browser slot released for user {user_id[:8]}...: {new_count}/{self._max_slots}")
    
    async def _get_slot_count_redis(self, user_id: str) -> int:
        """Redis implementation of getting slot count"""
        redis_client = self._get_redis_client()
        if not redis_client:
            raise Exception("Redis client not available")
        
        slot_key = self._get_slot_key(user_id)
        count = await redis_client.get(slot_key)
        
        return int(count) if count else 0
    
    # ========================================================================
    # MEMORY FALLBACK (Single Instance)
    # ========================================================================
    
    async def _acquire_slot_memory(self, user_id: str) -> None:
        """Memory fallback implementation of slot acquisition"""
        self._increment_metric("memory_mode_used")
        logger.info(f"Using MEMORY FALLBACK for slot acquisition - user {user_id[:8]}...")
        async with self._memory_lock:
            current_count = self._memory_store.get(user_id, 0)
            
            if current_count >= self._max_slots:
                logger.warning(
                    f"[MEMORY] User {user_id[:8]}... exceeded browser limit: {current_count}/{self._max_slots}"
                )
                raise HTTPException(
                    status_code=429,
                    detail=f"Too many concurrent browser sessions. Maximum allowed: {self._max_slots}"
                )
            
            self._memory_store[user_id] = current_count + 1
            logger.debug(
                f"[MEMORY] Browser slot acquired for user {user_id[:8]}...: "
                f"{self._memory_store[user_id]}/{self._max_slots}"
            )
    
    async def _release_slot_memory(self, user_id: str) -> None:
        """Memory fallback implementation of slot release"""
        async with self._memory_lock:
            current_count = self._memory_store.get(user_id, 0)
            if current_count > 0:
                new_count = current_count - 1
                if new_count > 0:
                    self._memory_store[user_id] = new_count
                else:
                    # Clean up if no slots
                    del self._memory_store[user_id]
                
                logger.debug(
                    f"[MEMORY] Browser slot released for user {user_id[:8]}...: "
                    f"{new_count}/{self._max_slots}"
                )
    
    async def _get_slot_count_memory(self, user_id: str) -> int:
        """Memory fallback implementation of getting slot count"""
        async with self._memory_lock:
            return self._memory_store.get(user_id, 0)


# Singleton instance
browser_slot_manager = BrowserSlotManager()
