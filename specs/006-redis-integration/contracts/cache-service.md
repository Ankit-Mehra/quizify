# Cache Service Contract

**Version**: 1.0  
**Created**: 2025-10-22  
**Status**: ✅ Approved for Implementation

---

## Service Overview

The **CacheService** provides a caching layer for Supabase database queries, reducing response times from 50-200ms to 1-2ms (50-200x improvement). It uses Redis as the backing store with TTL-based expiration and Pydantic model integration.

**Primary Responsibilities**:
1. Store database query results in Redis with TTL
2. Retrieve cached results with automatic deserialization
3. Invalidate cache entries on data updates
4. Provide "get-or-fetch" pattern for simplified caching
5. Track cache hit/miss rates for monitoring

**Key Design Principles**:
- **Type-safe**: Works with Pydantic models
- **TTL-based**: Automatic expiration prevents stale data
- **Transparent**: Drop-in caching for existing queries
- **Observable**: Metrics for cache performance

---

## Service Interface

### Class Definition

```python
from typing import Optional, TypeVar, Generic, Callable, Awaitable
from pydantic import BaseModel
import redis.asyncio as redis
from datetime import timedelta

T = TypeVar('T', bound=BaseModel)

class CacheService:
    """
    Generic caching service for database queries using Redis.
    
    Stores Pydantic models as JSON strings with TTL-based expiration.
    Provides automatic serialization/deserialization and cache-aside pattern.
    """
    
    def __init__(self, redis_client: redis.Redis, prefix: str = "cache"):
        """
        Initialize cache service.
        
        Args:
            redis_client: Async Redis client instance
            prefix: Key prefix for all cache entries (default: "cache")
        """
        self.redis = redis_client
        self.prefix = prefix
        self._stats = {"hits": 0, "misses": 0}
    
    async def get(
        self,
        key: str,
        model: type[T]
    ) -> Optional[T]:
        """
        Get cached value and deserialize to Pydantic model.
        
        Args:
            key: Cache key (without prefix)
            model: Pydantic model class for deserialization
        
        Returns:
            Deserialized model instance or None if not found
        
        Example:
            >>> cache = CacheService(redis_client)
            >>> user_tier = await cache.get("user_tier:user_123", UserTierInfo)
            >>> if user_tier:
            ...     print(user_tier.account_tier)
            'basic'
        """
        ...
    
    async def set(
        self,
        key: str,
        value: BaseModel,
        ttl: int = 300
    ) -> None:
        """
        Cache a Pydantic model with TTL.
        
        Args:
            key: Cache key (without prefix)
            value: Pydantic model instance to cache
            ttl: Time to live in seconds (default: 300 = 5 minutes)
        
        Returns:
            None
        
        Example:
            >>> user_tier = UserTierInfo(...)
            >>> await cache.set("user_tier:user_123", user_tier, ttl=300)
        """
        ...
    
    async def delete(self, key: str) -> bool:
        """
        Delete cached value.
        
        Args:
            key: Cache key (without prefix)
        
        Returns:
            True if key was deleted, False if key didn't exist
        
        Example:
            >>> deleted = await cache.delete("user_tier:user_123")
            >>> print(deleted)
            True
        """
        ...
    
    async def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching a pattern.
        
        Useful for invalidating related cache entries (e.g., all quiz
        lists for a user when new quiz is created).
        
        Args:
            pattern: Glob pattern (e.g., "quiz_list:user_123:*")
        
        Returns:
            Number of keys deleted
        
        Example:
            >>> count = await cache.delete_pattern("quiz_list:user_123:*")
            >>> print(f"Deleted {count} cache entries")
            Deleted 5 cache entries
        """
        ...
    
    async def get_or_fetch(
        self,
        key: str,
        fetch_fn: Callable[[], Awaitable[T]],
        model: type[T],
        ttl: int = 300
    ) -> T:
        """
        Get from cache or fetch from source if not found.
        
        Implements cache-aside pattern. If cache miss, calls fetch_fn
        to get fresh data, stores in cache, and returns result.
        
        Args:
            key: Cache key (without prefix)
            fetch_fn: Async function to call on cache miss
            model: Pydantic model class for deserialization
            ttl: Time to live in seconds (default: 300 = 5 minutes)
        
        Returns:
            Cached or fetched model instance
        
        Example:
            >>> async def fetch_user_tier():
            ...     result = await supabase.table("user_tier_info")\\
            ...         .select("*")\\
            ...         .eq("id", "user_123")\\
            ...         .single()
            ...     return UserTierInfo(**result)
            >>>
            >>> user_tier = await cache.get_or_fetch(
            ...     "user_tier:user_123",
            ...     fetch_user_tier,
            ...     UserTierInfo,
            ...     ttl=300
            ... )
        """
        ...
    
    async def exists(self, key: str) -> bool:
        """
        Check if key exists in cache.
        
        Args:
            key: Cache key (without prefix)
        
        Returns:
            True if key exists, False otherwise
        
        Example:
            >>> if await cache.exists("user_tier:user_123"):
            ...     print("Cache hit!")
        """
        ...
    
    async def get_ttl(self, key: str) -> int:
        """
        Get remaining TTL for a cached key.
        
        Args:
            key: Cache key (without prefix)
        
        Returns:
            Remaining TTL in seconds, or -1 if key doesn't exist
        
        Example:
            >>> ttl = await cache.get_ttl("user_tier:user_123")
            >>> print(f"Cache expires in {ttl} seconds")
            Cache expires in 287 seconds
        """
        ...
    
    def get_stats(self) -> dict:
        """
        Get cache hit/miss statistics.
        
        Returns:
            Dictionary with hits, misses, and hit rate
        
        Example:
            >>> stats = cache.get_stats()
            >>> print(f"Hit rate: {stats['hit_rate']:.1f}%")
            Hit rate: 82.3%
        """
        ...
    
    def reset_stats(self) -> None:
        """Reset cache statistics."""
        ...
```

---

## Usage Patterns

### 1. Simple Caching (Manual)

```python
from services.redis.cache import CacheService
from schemas.user import UserTierInfo

async def get_user_tier_with_cache(
    user_id: str,
    cache: CacheService,
    db: SupabaseClient
) -> UserTierInfo:
    """Get user tier with manual cache management"""
    
    # Try cache first
    cached = await cache.get(f"user_tier:{user_id}", UserTierInfo)
    if cached:
        return cached
    
    # Cache miss - fetch from database
    result = await db.table("user_tier_info")\
        .select("*")\
        .eq("id", user_id)\
        .single()
    
    user_tier = UserTierInfo(**result)
    
    # Store in cache
    await cache.set(f"user_tier:{user_id}", user_tier, ttl=300)
    
    return user_tier
```

### 2. Cache-Aside Pattern (Automatic)

```python
async def get_user_tier_auto(
    user_id: str,
    cache: CacheService,
    db: SupabaseClient
) -> UserTierInfo:
    """Get user tier with automatic cache-aside pattern"""
    
    async def fetch_from_db():
        result = await db.table("user_tier_info")\
            .select("*")\
            .eq("id", user_id)\
            .single()
        return UserTierInfo(**result)
    
    return await cache.get_or_fetch(
        key=f"user_tier:{user_id}",
        fetch_fn=fetch_from_db,
        model=UserTierInfo,
        ttl=300  # 5 minutes
    )
```

### 3. Cache Invalidation (Single Key)

```python
async def update_user_tier(
    user_id: str,
    new_tier: str,
    cache: CacheService,
    db: SupabaseClient
) -> None:
    """Update user tier and invalidate cache"""
    
    # Update database
    await db.table("profiles")\
        .update({"account_tier": new_tier})\
        .eq("id", user_id)\
        .execute()
    
    # Invalidate cache
    await cache.delete(f"user_tier:{user_id}")
```

### 4. Pattern-Based Invalidation

```python
async def create_quiz(
    user_id: str,
    quiz_data: dict,
    cache: CacheService,
    db: SupabaseClient
) -> Quiz:
    """Create quiz and invalidate related caches"""
    
    # Create quiz in database
    result = await db.table("quizzes")\
        .insert(quiz_data)\
        .execute()
    
    quiz = Quiz(**result[0])
    
    # Invalidate all quiz list caches for this user
    await cache.delete_pattern(f"quiz_list:{user_id}:*")
    
    return quiz
```

### 5. Batch Caching

```python
async def get_multiple_quizzes_cached(
    quiz_ids: List[str],
    cache: CacheService,
    db: SupabaseClient
) -> List[Quiz]:
    """Get multiple quizzes with caching"""
    
    results = []
    uncached_ids = []
    
    # Check cache for each quiz
    for quiz_id in quiz_ids:
        cached = await cache.get(f"quiz:{quiz_id}", Quiz)
        if cached:
            results.append(cached)
        else:
            uncached_ids.append(quiz_id)
    
    # Fetch uncached quizzes from database
    if uncached_ids:
        db_results = await db.table("quizzes")\
            .select("*")\
            .in_("id", uncached_ids)\
            .execute()
        
        for quiz_data in db_results:
            quiz = Quiz(**quiz_data)
            results.append(quiz)
            
            # Cache for next time
            await cache.set(f"quiz:{quiz.id}", quiz, ttl=1800)  # 30 min
    
    return results
```

---

## Caching Strategies by Use Case

### User Tier Information
**TTL**: 300 seconds (5 minutes)  
**Key**: `cache:user_tier:{user_id}`  
**Rationale**: Frequently checked, rarely changes

```python
user_tier = await cache.get_or_fetch(
    f"user_tier:{user_id}",
    lambda: fetch_user_tier(user_id),
    UserTierInfo,
    ttl=300
)
```

### Quiz Metadata
**TTL**: 1800 seconds (30 minutes)  
**Key**: `cache:quiz:{quiz_id}`  
**Rationale**: Stable data, rarely changes after creation

```python
quiz = await cache.get_or_fetch(
    f"quiz:{quiz_id}",
    lambda: fetch_quiz(quiz_id),
    Quiz,
    ttl=1800
)
```

### User Profile
**TTL**: 600 seconds (10 minutes)  
**Key**: `cache:profile:{user_id}`  
**Rationale**: Moderate change frequency

```python
profile = await cache.get_or_fetch(
    f"profile:{user_id}",
    lambda: fetch_profile(user_id),
    UserProfile,
    ttl=600
)
```

### Quiz Lists (Paginated)
**TTL**: 300 seconds (5 minutes)  
**Key**: `cache:quiz_list:{user_id}:{page}`  
**Rationale**: Changes when new quiz created, page-specific

```python
quiz_list = await cache.get_or_fetch(
    f"quiz_list:{user_id}:{page}",
    lambda: fetch_quiz_list(user_id, page),
    QuizListResponse,
    ttl=300
)
```

---

## Error Handling

### Fallback Behavior

```python
class CacheService:
    def __init__(self, redis_client: Optional[redis.Redis], prefix: str = "cache"):
        self.redis = redis_client
        self.prefix = prefix
        self.fallback_mode = False
        self._memory_cache = {}
    
    async def get(self, key: str, model: type[T]) -> Optional[T]:
        """Get with automatic fallback"""
        try:
            if self.redis and not self.fallback_mode:
                # Try Redis
                full_key = f"{self.prefix}:{key}"
                cached = await self.redis.get(full_key)
                if cached:
                    self._stats["hits"] += 1
                    return model.model_validate_json(cached)
                self._stats["misses"] += 1
                return None
        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.warning(f"Redis error, falling back to memory: {e}")
            self.fallback_mode = True
        
        # Fallback to memory
        if key in self._memory_cache:
            self._stats["hits"] += 1
            return self._memory_cache[key]
        
        self._stats["misses"] += 1
        return None
```

### Error Scenarios

| Error | Cause | Behavior |
|-------|-------|----------|
| `RedisConnectionError` | Redis unavailable | Fall back to memory cache, log warning |
| `JSONDecodeError` | Corrupted cache data | Return None (cache miss), log error |
| `ValidationError` | Schema mismatch | Return None (cache miss), log error |
| `MemoryError` | Memory cache full | Evict oldest entries (LRU) |

---

## Performance Characteristics

### Expected Latency

| Operation | Redis Time | Database Time | Improvement |
|-----------|-----------|---------------|-------------|
| `get` (hit) | 0.5-1ms | 50-200ms | **50-200x** |
| `get` (miss) | 0.5-1ms | - | N/A |
| `set` | 0.5-1ms | - | - |
| `delete` | 0.3-0.5ms | - | - |
| `delete_pattern` | 2-10ms | - | Depends on match count |
| `get_or_fetch` (hit) | 0.5-1ms | - | **50-200x** |
| `get_or_fetch` (miss) | 50-201ms | 50-200ms | Adds 1ms overhead |

### Cache Hit Rate Targets

| Use Case | Target Hit Rate | Actual (Expected) |
|----------|----------------|-------------------|
| User tier info | 95%+ | 90-95% |
| Quiz metadata | 90%+ | 85-90% |
| User profile | 85%+ | 80-85% |
| Quiz lists | 75%+ | 70-75% |
| **Overall** | **80%+** | **75-85%** |

### Memory Usage

| Cache Entry Type | Average Size | 1000 Entries | 10000 Entries |
|------------------|-------------|--------------|---------------|
| User tier | 300 bytes | 300 KB | 3 MB |
| Quiz metadata | 400 bytes | 400 KB | 4 MB |
| User profile | 350 bytes | 350 KB | 3.5 MB |
| Quiz list | 2 KB | 2 MB | 20 MB |

**Total Estimate**: ~10-30 MB for typical workload (10,000 cached entries)

---

## Testing Requirements

### Unit Tests (fakeredis)

```python
import pytest
from fakeredis import aioredis as fakeredis
from services.redis.cache import CacheService
from schemas.user import UserTierInfo

@pytest.fixture
async def cache_service():
    client = fakeredis.FakeRedis(decode_responses=True)
    service = CacheService(client)
    yield service
    await client.flushall()
    await client.close()

@pytest.mark.asyncio
async def test_set_and_get(cache_service):
    """Should cache and retrieve Pydantic model"""
    user_tier = UserTierInfo(
        id="user_123",
        account_tier="basic",
        current_quiz_count=5,
        quota_limit=20,
        quota_exceeded=False
    )
    
    # Set cache
    await cache_service.set("user_tier:user_123", user_tier, ttl=300)
    
    # Get cache
    cached = await cache_service.get("user_tier:user_123", UserTierInfo)
    
    assert cached is not None
    assert cached.id == "user_123"
    assert cached.account_tier == "basic"

@pytest.mark.asyncio
async def test_get_or_fetch_hit(cache_service):
    """Should return cached value without calling fetch_fn"""
    user_tier = UserTierInfo(...)
    await cache_service.set("user_tier:user_123", user_tier)
    
    fetch_called = False
    async def fetch_fn():
        nonlocal fetch_called
        fetch_called = True
        return user_tier
    
    result = await cache_service.get_or_fetch(
        "user_tier:user_123",
        fetch_fn,
        UserTierInfo
    )
    
    assert result.id == "user_123"
    assert not fetch_called  # Should not call fetch on cache hit

@pytest.mark.asyncio
async def test_get_or_fetch_miss(cache_service):
    """Should call fetch_fn on cache miss and store result"""
    user_tier = UserTierInfo(...)
    
    async def fetch_fn():
        return user_tier
    
    result = await cache_service.get_or_fetch(
        "user_tier:user_123",
        fetch_fn,
        UserTierInfo,
        ttl=300
    )
    
    assert result.id == "user_123"
    
    # Verify it was cached
    cached = await cache_service.get("user_tier:user_123", UserTierInfo)
    assert cached is not None

@pytest.mark.asyncio
async def test_delete_pattern(cache_service):
    """Should delete all keys matching pattern"""
    # Cache multiple quiz lists
    for page in range(1, 4):
        await cache_service.set(
            f"quiz_list:user_123:{page}",
            QuizListResponse(...),
            ttl=300
        )
    
    # Delete all quiz lists for user
    count = await cache_service.delete_pattern("quiz_list:user_123:*")
    
    assert count == 3

@pytest.mark.asyncio
async def test_cache_stats(cache_service):
    """Should track hit/miss statistics"""
    user_tier = UserTierInfo(...)
    await cache_service.set("user_tier:user_123", user_tier)
    
    # Hit
    await cache_service.get("user_tier:user_123", UserTierInfo)
    
    # Miss
    await cache_service.get("user_tier:user_456", UserTierInfo)
    
    stats = cache_service.get_stats()
    
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["hit_rate"] == 50.0
```

### Integration Tests (Real Database)

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_cache_with_real_database(redis_server, supabase_client):
    """Test caching with real Supabase queries"""
    redis_client = await redis.from_url(f"redis://{redis_server.host}:{redis_server.port}")
    cache = CacheService(redis_client)
    
    # First call - should hit database
    start = time.time()
    user_tier1 = await cache.get_or_fetch(
        "user_tier:test_user",
        lambda: fetch_from_supabase(supabase_client, "test_user"),
        UserTierInfo,
        ttl=300
    )
    db_time = time.time() - start
    
    # Second call - should hit cache
    start = time.time()
    user_tier2 = await cache.get_or_fetch(
        "user_tier:test_user",
        lambda: fetch_from_supabase(supabase_client, "test_user"),
        UserTierInfo,
        ttl=300
    )
    cache_time = time.time() - start
    
    assert user_tier1 == user_tier2
    assert cache_time < db_time / 10  # Cache should be 10x+ faster
    
    await redis_client.close()
```

---

## Implementation Checklist

- [ ] Create `services/redis/cache.py`
- [ ] Implement `CacheService` class
- [ ] Implement `get()` with Pydantic deserialization
- [ ] Implement `set()` with Pydantic serialization
- [ ] Implement `delete()` and `delete_pattern()`
- [ ] Implement `get_or_fetch()` cache-aside pattern
- [ ] Implement `exists()` and `get_ttl()`
- [ ] Add statistics tracking (`get_stats()`)
- [ ] Add memory fallback logic
- [ ] Add comprehensive logging
- [ ] Write unit tests (fakeredis)
- [ ] Write integration tests (real DB + Redis)
- [ ] Update database services to use caching
- [ ] Add cache invalidation on data updates
- [ ] Add monitoring metrics

---

## Dependencies

```python
# requirements.txt
redis[hiredis]>=5.0.0  # Redis client
pydantic>=2.0.0        # Data validation and serialization
```

---

**Contract Status**: ✅ **APPROVED**  
**Implementation Priority**: **HIGH** (Week 2)  
**Estimated Effort**: 2-3 days (including tests)  
**Next**: Implement `services/redis/cache.py`
