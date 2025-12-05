# Phase 2: Implementation Tasks

**Created**: 2025-10-22  
**Status**: ✅ Complete - Ready for Implementation  
**Version**: 1.0

---

## Overview

This document breaks down the Redis integration implementation into actionable tasks organized by epics. Each task includes effort estimates, dependencies, acceptance criteria, and test requirements.

**Total Estimated Effort**: 3-4 weeks (1 developer)  
**Phases**: 4 epics across 3 implementation weeks + 1 deployment week

---

## Epic Breakdown

```
Epic 1: Core Infrastructure          [Week 1, Days 1-2]    8-12 hours
Epic 2: Browser Slot Management      [Week 1, Days 3-5]   12-16 hours
Epic 3: Database Caching             [Week 2, Days 1-3]   12-16 hours
Epic 4: Session Management           [Week 2-3]           16-20 hours
Epic 5: Monitoring & Deployment      [Week 3-4]           12-16 hours

Total: 60-80 hours (3-4 weeks)
```

---

## Priority Legend

- **P0** - Critical path, blocks other work
- **P1** - Important, needed for core functionality
- **P2** - Nice to have, can be deferred

---

## Epic 1: Core Infrastructure
**Timeline**: Week 1, Days 1-2 (8-12 hours)  
**Goal**: Set up Redis client and foundational infrastructure

### Task 1.1: Redis Client Setup
**Priority**: P0  
**Effort**: 2-3 hours  
**Dependencies**: None

**Description**: Create Redis client module with connection pooling and FastAPI lifespan integration.

**Implementation Steps**:
1. Create `services/redis/client.py`
2. Implement `get_redis_client()` with connection pool
3. Add FastAPI lifespan context manager
4. Configure connection pool settings (20 max connections)
5. Add health check method (`ping()`)
6. Add connection error handling

**Code Structure**:
```python
# services/redis/client.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
import redis.asyncio as redis
from config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan for Redis connection management"""
    # Startup: Create Redis connection pool
    app.state.redis = await redis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        max_connections=settings.REDIS_MAX_CONNECTIONS,
        socket_keepalive=True,
        socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT,
        retry_on_timeout=True,
        health_check_interval=30
    )
    
    yield  # Application runs
    
    # Shutdown: Close Redis connections
    await app.state.redis.close()

async def get_redis_client(app: FastAPI) -> redis.Redis:
    """Get Redis client from app state"""
    return app.state.redis
```

**Acceptance Criteria**:
- [ ] Redis client connects successfully to `localhost:6379`
- [ ] Connection pool is configured with 20 max connections
- [ ] Health check (`ping()`) returns True
- [ ] Connections are properly closed on shutdown
- [ ] Environment variables are read from config

**Tests Required**:
- [ ] Unit test: Connection creation
- [ ] Unit test: Health check
- [ ] Integration test: Real Redis connection
- [ ] Integration test: Connection pool behavior

**Files Modified**:
- `services/redis/client.py` (new)
- `main.py` (update lifespan)
- `config.py` (add Redis settings)

---

### Task 1.2: Configuration & Environment Variables
**Priority**: P0  
**Effort**: 1 hour  
**Dependencies**: None

**Description**: Add Redis configuration to settings and environment variables.

**Implementation Steps**:
1. Update `config.py` with Redis settings
2. Add environment variables to `.env.example`
3. Document configuration in README
4. Add validation for required settings

**Code Structure**:
```python
# config.py
class Settings(BaseSettings):
    # Existing settings...
    
    # Redis Configuration
    REDIS_URL: str = Field(
        default="redis://localhost:6379",
        description="Redis connection URL"
    )
    REDIS_ENABLED: bool = Field(
        default=True,
        description="Enable Redis features (false for fallback mode)"
    )
    REDIS_MAX_CONNECTIONS: int = Field(
        default=20,
        description="Maximum Redis connection pool size"
    )
    REDIS_CONNECT_TIMEOUT: int = Field(
        default=5,
        description="Redis connection timeout in seconds"
    )
```

**Acceptance Criteria**:
- [ ] All Redis settings defined in `config.py`
- [ ] `.env.example` updated with Redis variables
- [ ] Default values work for local development
- [ ] Settings are validated on app startup

**Tests Required**:
- [ ] Unit test: Default settings validation
- [ ] Unit test: Custom settings override

**Files Modified**:
- `config.py` (update)
- `.env.example` (update)
- `README.md` (update)

---

### Task 1.3: Memory Fallback Base Class
**Priority**: P0  
**Effort**: 2-3 hours  
**Dependencies**: Task 1.1

**Description**: Create base class for Redis services with automatic memory fallback.

**Implementation Steps**:
1. Create `services/redis/base.py`
2. Implement `RedisServiceBase` with fallback logic
3. Add health check recovery mechanism
4. Add logging for fallback events
5. Add metrics tracking (fallback mode duration)

**Code Structure**:
```python
# services/redis/base.py
import logging
from typing import Optional
import redis.asyncio as redis

logger = logging.getLogger(__name__)

class RedisServiceBase:
    """Base class for Redis services with automatic fallback"""
    
    def __init__(self, redis_client: Optional[redis.Redis]):
        self.redis = redis_client
        self.fallback_mode = False
        self._fallback_start = None
    
    async def _with_fallback(self, redis_fn, memory_fn):
        """Execute Redis operation with automatic memory fallback"""
        try:
            if self.redis and not self.fallback_mode:
                return await redis_fn()
        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.warning(f"Redis error, falling back to memory: {e}")
            self._activate_fallback()
        
        return await memory_fn()
    
    def _activate_fallback(self):
        """Activate fallback mode"""
        if not self.fallback_mode:
            self.fallback_mode = True
            self._fallback_start = time.time()
            logger.error("Redis fallback mode ACTIVATED")
    
    async def check_health(self) -> bool:
        """Check Redis health and recover from fallback if possible"""
        if not self.redis:
            return False
        
        try:
            await self.redis.ping()
            if self.fallback_mode:
                duration = time.time() - self._fallback_start
                logger.info(f"Redis recovered after {duration:.1f}s, exiting fallback mode")
                self.fallback_mode = False
                self._fallback_start = None
            return True
        except Exception:
            return False
```

**Acceptance Criteria**:
- [ ] Base class provides fallback decorator
- [ ] Fallback activates on Redis connection errors
- [ ] Health check recovers from fallback automatically
- [ ] Fallback events are logged with context
- [ ] Fallback duration is tracked

**Tests Required**:
- [ ] Unit test: Fallback activation on error
- [ ] Unit test: Health check recovery
- [ ] Unit test: Logging verification

**Files Modified**:
- `services/redis/base.py` (new)
- `services/redis/__init__.py` (new)

---

### Task 1.4: Docker Compose Setup
**Priority**: P1  
**Effort**: 1 hour  
**Dependencies**: None

**Description**: Create Docker Compose configuration for local Redis development.

**Implementation Steps**:
1. Create/update `docker-compose.yml`
2. Configure Redis with appropriate settings
3. Add volume for data persistence
4. Add health check
5. Document usage in README

**Code Structure**:
```yaml
# docker-compose.yml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    container_name: quizify-redis
    ports:
      - "6379:6379"
    command: >
      redis-server
      --appendonly yes
      --maxmemory 256mb
      --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
    restart: unless-stopped

volumes:
  redis_data:
    driver: local
```

**Acceptance Criteria**:
- [ ] Redis starts with `docker-compose up -d redis`
- [ ] Redis is accessible on `localhost:6379`
- [ ] Health check passes
- [ ] Data persists across container restarts
- [ ] Memory limit is enforced (256MB)

**Tests Required**:
- [ ] Manual test: Docker Compose startup
- [ ] Manual test: Connection from application
- [ ] Manual test: Data persistence

**Files Modified**:
- `docker-compose.yml` (create/update)
- `README.md` (update)

---

## Epic 2: Browser Slot Management
**Timeline**: Week 1, Days 3-5 (12-16 hours)  
**Goal**: Implement distributed browser slot coordination

### Task 2.1: BrowserSlotService Implementation
**Priority**: P0  
**Effort**: 4-5 hours  
**Dependencies**: Task 1.1, Task 1.3

**Description**: Implement complete BrowserSlotService with atomic operations.

**Implementation Steps**:
1. Create `services/redis/browser_slots.py`
2. Implement `BrowserSlotService` class
3. Implement `acquire_slot()` with atomic INCR
4. Implement `release_slot()` with atomic DECR
5. Implement `get_slot_count()`
6. Implement `list_sessions()` with SCAN
7. Implement `update_session_status()`
8. Add custom exception `TooManyBrowsersError`
9. Add comprehensive logging

**Key Methods**:
```python
# services/redis/browser_slots.py
class BrowserSlotService(RedisServiceBase):
    async def acquire_slot(self, user_id: str, url: str, process_id: Optional[str] = None) -> str:
        """Acquire browser slot (atomic)"""
        session_id = f"sess_{uuid.uuid4()}"
        
        async def redis_acquire():
            # Atomic increment
            count = await self.redis.incr(f"browser_slots:{user_id}")
            await self.redis.expire(f"browser_slots:{user_id}", 300)
            
            if count > 3:
                # Rollback on limit exceeded
                await self.redis.decr(f"browser_slots:{user_id}")
                raise TooManyBrowsersError(user_id, count, 3)
            
            # Store session metadata
            await self.redis.hset(
                f"browser_session:{user_id}:{session_id}",
                mapping={
                    "user_id": user_id,
                    "session_id": session_id,
                    "url": url,
                    "started_at": datetime.utcnow().isoformat(),
                    "process_id": process_id or f"pid_{os.getpid()}",
                    "status": "active"
                }
            )
            await self.redis.expire(f"browser_session:{user_id}:{session_id}", 300)
            
            return session_id
        
        async def memory_acquire():
            # Memory fallback implementation
            ...
        
        return await self._with_fallback(redis_acquire, memory_acquire)
```

**Acceptance Criteria**:
- [ ] Can acquire up to 3 slots per user
- [ ] 4th slot acquisition raises `TooManyBrowsersError`
- [ ] Slot release decrements counter correctly
- [ ] Session metadata is stored and retrievable
- [ ] TTL is set correctly (5 minutes)
- [ ] Fallback to memory works when Redis is down

**Tests Required**:
- [ ] Unit test: Acquire single slot
- [ ] Unit test: Acquire multiple slots (up to 3)
- [ ] Unit test: Exceed limit (4th slot fails)
- [ ] Unit test: Release slot decrements counter
- [ ] Unit test: Session metadata storage
- [ ] Unit test: TTL expiration behavior
- [ ] Integration test: Concurrent slot acquisition
- [ ] Contract test: Interface compliance

**Files Modified**:
- `services/redis/browser_slots.py` (new)

---

### Task 2.2: BrowserSlotService Unit Tests
**Priority**: P0  
**Effort**: 3-4 hours  
**Dependencies**: Task 2.1

**Description**: Write comprehensive unit tests using fakeredis.

**Implementation Steps**:
1. Create `tests/unit/test_redis_browser_slots.py`
2. Set up fakeredis fixture
3. Test acquire_slot success scenarios
4. Test acquire_slot failure scenarios
5. Test release_slot
6. Test list_sessions
7. Test memory fallback
8. Achieve >90% code coverage

**Test Structure**:
```python
# tests/unit/test_redis_browser_slots.py
import pytest
from fakeredis import aioredis as fakeredis
from services.redis.browser_slots import BrowserSlotService, TooManyBrowsersError

@pytest.fixture
async def redis_client():
    client = fakeredis.FakeRedis(decode_responses=True)
    yield client
    await client.flushall()
    await client.close()

@pytest.fixture
def browser_service(redis_client):
    return BrowserSlotService(redis_client)

@pytest.mark.asyncio
async def test_acquire_slot_success(browser_service):
    """Should successfully acquire slot"""
    session_id = await browser_service.acquire_slot("user123", "https://example.com")
    assert session_id.startswith("sess_")
    assert await browser_service.get_slot_count("user123") == 1

@pytest.mark.asyncio
async def test_acquire_slot_at_limit(browser_service):
    """Should raise error at 4th slot"""
    # Acquire 3 slots
    for i in range(3):
        await browser_service.acquire_slot("user123", f"https://example{i}.com")
    
    # 4th should fail
    with pytest.raises(TooManyBrowsersError):
        await browser_service.acquire_slot("user123", "https://example3.com")

# ... 13 more tests
```

**Acceptance Criteria**:
- [ ] All interface methods have tests
- [ ] Edge cases are covered
- [ ] Error scenarios are tested
- [ ] Code coverage >90%
- [ ] All tests pass consistently

**Tests Required**: 15 unit tests total

**Files Modified**:
- `tests/unit/test_redis_browser_slots.py` (new)
- `tests/conftest.py` (update with fixtures)

---

### Task 2.3: Web Scraping Integration
**Priority**: P0  
**Effort**: 2-3 hours  
**Dependencies**: Task 2.1, Task 2.2

**Description**: Update web scraping service to use Redis browser slots.

**Implementation Steps**:
1. Update `handlers/quiz_handlers.py`
2. Replace in-memory slot tracking with BrowserSlotService
3. Add try/finally for guaranteed slot release
4. Update error handling for TooManyBrowsersError
5. Add logging for slot acquisition/release
6. Update tests

**Code Changes**:
```python
# handlers/quiz_handlers.py
async def generate_quiz_from_url(
    url: str,
    user_id: str,
    redis_client: redis.Redis
) -> Quiz:
    browser_service = BrowserSlotService(redis_client)
    session_id = None
    
    try:
        # Acquire browser slot
        session_id = await browser_service.acquire_slot(user_id, url)
        logger.info(f"Acquired browser slot {session_id} for user {user_id}")
        
        # Scrape content
        content = await scrape_url(url)
        
        # Update status to completed
        await browser_service.update_session_status(user_id, session_id, "completed")
        
        # Generate quiz from content
        quiz = await generate_quiz_content(content)
        
        return quiz
        
    except TooManyBrowsersError as e:
        logger.warning(f"Browser limit exceeded for user {user_id}: {e}")
        raise HTTPException(
            status_code=429,
            detail="Maximum concurrent browsers reached (3). Please wait for active requests to complete."
        )
    
    finally:
        # Always release slot
        if session_id:
            await browser_service.release_slot(user_id, session_id)
            logger.info(f"Released browser slot {session_id} for user {user_id}")
```

**Acceptance Criteria**:
- [ ] Web scraping uses Redis browser slots
- [ ] In-memory slot tracking code removed
- [ ] Slots are always released (even on error)
- [ ] HTTP 429 returned when limit exceeded
- [ ] Logging shows slot lifecycle
- [ ] Existing tests still pass

**Tests Required**:
- [ ] Update existing web scraping tests
- [ ] Test slot release on success
- [ ] Test slot release on error
- [ ] Test concurrent requests with slot limits

**Files Modified**:
- `handlers/quiz_handlers.py` (update)
- `api/quiz_routes.py` (update dependencies)
- `tests/integration/test_url_quiz_generation.py` (update)

---

### Task 2.4: Browser Slot Integration Tests
**Priority**: P1  
**Effort**: 2 hours  
**Dependencies**: Task 2.3

**Description**: Write integration tests with real Redis.

**Implementation Steps**:
1. Update `tests/integration/test_redis_integration.py`
2. Test concurrent slot acquisition atomicity
3. Test cross-process coordination
4. Test TTL expiration behavior
5. Test session metadata persistence

**Acceptance Criteria**:
- [ ] Integration tests pass with real Redis
- [ ] Atomic operations verified
- [ ] TTL behavior confirmed
- [ ] Cross-process coordination works

**Tests Required**: 3 integration tests

**Files Modified**:
- `tests/integration/test_redis_integration.py` (update)

---

### Task 2.5: Browser Slot Monitoring
**Priority**: P2  
**Effort**: 1-2 hours  
**Dependencies**: Task 2.1

**Description**: Add monitoring endpoint for browser slot debugging.

**Implementation Steps**:
1. Create `/debug/browser-sessions/{user_id}` endpoint
2. Create `/health/browser-slots` endpoint
3. Add metrics for slot usage

**Acceptance Criteria**:
- [ ] Debug endpoint returns active sessions
- [ ] Health endpoint shows slot capacity
- [ ] Endpoints are admin-only

**Files Modified**:
- `api/admin_routes.py` (update)

---

## Epic 3: Database Caching
**Timeline**: Week 2, Days 1-3 (12-16 hours)  
**Goal**: Implement query caching for 50x performance improvement

### Task 3.1: CacheService Implementation
**Priority**: P0  
**Effort**: 4-5 hours  
**Dependencies**: Task 1.1, Task 1.3

**Description**: Implement generic CacheService with Pydantic support.

**Implementation Steps**:
1. Create `services/redis/cache.py`
2. Implement `CacheService` class with generic typing
3. Implement `get()` with Pydantic deserialization
4. Implement `set()` with Pydantic serialization
5. Implement `delete()` and `delete_pattern()`
6. Implement `get_or_fetch()` cache-aside pattern
7. Implement `exists()` and `get_ttl()`
8. Add statistics tracking
9. Add comprehensive logging

**Key Methods**:
```python
# services/redis/cache.py
from typing import TypeVar, Generic, Optional, Callable, Awaitable
from pydantic import BaseModel

T = TypeVar('T', bound=BaseModel)

class CacheService(RedisServiceBase):
    def __init__(self, redis_client: Optional[redis.Redis], prefix: str = "cache"):
        super().__init__(redis_client)
        self.prefix = prefix
        self._stats = {"hits": 0, "misses": 0}
    
    async def get(self, key: str, model: type[T]) -> Optional[T]:
        """Get cached value and deserialize"""
        async def redis_get():
            full_key = f"{self.prefix}:{key}"
            cached = await self.redis.get(full_key)
            if cached:
                self._stats["hits"] += 1
                return model.model_validate_json(cached)
            self._stats["misses"] += 1
            return None
        
        async def memory_get():
            # Memory fallback
            ...
        
        return await self._with_fallback(redis_get, memory_get)
    
    async def get_or_fetch(
        self,
        key: str,
        fetch_fn: Callable[[], Awaitable[T]],
        model: type[T],
        ttl: int = 300
    ) -> T:
        """Cache-aside pattern"""
        # Try cache first
        cached = await self.get(key, model)
        if cached:
            return cached
        
        # Cache miss - fetch from source
        value = await fetch_fn()
        
        # Store in cache
        await self.set(key, value, ttl)
        
        return value
```

**Acceptance Criteria**:
- [ ] Generic type support works with any Pydantic model
- [ ] JSON serialization/deserialization works
- [ ] Cache-aside pattern (`get_or_fetch`) works
- [ ] Pattern deletion works correctly
- [ ] Statistics tracking is accurate
- [ ] Memory fallback works

**Tests Required**:
- [ ] Unit test: Set and get with Pydantic model
- [ ] Unit test: Cache miss returns None
- [ ] Unit test: get_or_fetch on hit (doesn't call fetch_fn)
- [ ] Unit test: get_or_fetch on miss (calls fetch_fn and caches)
- [ ] Unit test: delete_pattern with multiple keys
- [ ] Unit test: Statistics tracking
- [ ] Unit test: TTL expiration
- [ ] Unit test: Memory fallback

**Files Modified**:
- `services/redis/cache.py` (new)

---

### Task 3.2: CacheService Unit Tests
**Priority**: P0  
**Effort**: 3-4 hours  
**Dependencies**: Task 3.1

**Description**: Write comprehensive unit tests for CacheService.

**Acceptance Criteria**:
- [ ] All methods tested
- [ ] Edge cases covered
- [ ] Code coverage >90%
- [ ] All tests pass

**Tests Required**: 18 unit tests total

**Files Modified**:
- `tests/unit/test_redis_cache.py` (new)

---

### Task 3.3: User Tier Caching
**Priority**: P0  
**Effort**: 2-3 hours  
**Dependencies**: Task 3.1, Task 3.2

**Description**: Add caching to user tier queries.

**Implementation Steps**:
1. Update `services/db_services/tier_service.py`
2. Inject CacheService dependency
3. Wrap `get_user_tier()` with caching
4. Add cache invalidation on tier updates
5. Update tests

**Code Changes**:
```python
# services/db_services/tier_service.py
async def get_user_tier(
    user_id: str,
    cache: CacheService,
    db: SupabaseClient
) -> UserTierInfo:
    """Get user tier with caching"""
    
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

async def update_user_tier(
    user_id: str,
    new_tier: str,
    cache: CacheService,
    db: SupabaseClient
):
    """Update tier and invalidate cache"""
    await db.table("profiles")\
        .update({"account_tier": new_tier})\
        .eq("id", user_id)\
        .execute()
    
    # Invalidate cache
    await cache.delete(f"user_tier:{user_id}")
```

**Acceptance Criteria**:
- [ ] User tier queries use cache
- [ ] Cache TTL is 5 minutes
- [ ] Cache invalidation works on updates
- [ ] First request hits database
- [ ] Second request hits cache
- [ ] Tests verify caching behavior

**Tests Required**:
- [ ] Integration test: Cache hit/miss behavior
- [ ] Integration test: Cache invalidation

**Files Modified**:
- `services/db_services/tier_service.py` (update)
- `tests/integration/test_tier_caching.py` (new)

---

### Task 3.4: Quiz Metadata Caching
**Priority**: P1  
**Effort**: 2 hours  
**Dependencies**: Task 3.1

**Description**: Add caching to quiz retrieval queries.

**Acceptance Criteria**:
- [ ] Quiz metadata cached for 30 minutes
- [ ] Cache invalidated on quiz updates
- [ ] Performance improvement measured

**Files Modified**:
- `handlers/quiz_handlers.py` (update)

---

### Task 3.5: Cache Performance Monitoring
**Priority**: P1  
**Effort**: 2 hours  
**Dependencies**: Task 3.1

**Description**: Add cache performance metrics and monitoring.

**Implementation Steps**:
1. Create `/health/cache` endpoint
2. Add cache hit rate metrics
3. Add cache size monitoring
4. Add performance comparison (cached vs uncached)

**Acceptance Criteria**:
- [ ] Health endpoint shows cache statistics
- [ ] Hit rate >80% after warm-up
- [ ] Response times show 50x improvement

**Files Modified**:
- `api/admin_routes.py` (update)
- `middleware/metrics.py` (update)

---

## Epic 4: Session Management
**Timeline**: Week 2-3 (16-20 hours)  
**Goal**: Implement multi-device session tracking

### Task 4.1: SessionService Implementation
**Priority**: P1  
**Effort**: 5-6 hours  
**Dependencies**: Task 1.1, Task 1.3

**Description**: Implement complete SessionService.

**Implementation Steps**:
1. Create `services/redis/sessions.py`
2. Implement `SessionService` class
3. Implement all interface methods
4. Add IP address hashing
5. Add user agent truncation
6. Add custom exceptions
7. Add comprehensive logging

**Acceptance Criteria**:
- [ ] All methods implemented per contract
- [ ] Security features (IP hashing) work
- [ ] TTL is 24 hours
- [ ] Multi-device tracking works
- [ ] Logout-all-devices works

**Tests Required**: 17 unit tests

**Files Modified**:
- `services/redis/sessions.py` (new)

---

### Task 4.2: SessionService Unit Tests
**Priority**: P1  
**Effort**: 3-4 hours  
**Dependencies**: Task 4.1

**Description**: Write comprehensive unit tests.

**Acceptance Criteria**:
- [ ] All methods tested
- [ ] Code coverage >90%
- [ ] Tests pass consistently

**Files Modified**:
- `tests/unit/test_redis_sessions.py` (new)

---

### Task 4.3: Authentication Integration
**Priority**: P1  
**Effort**: 4-5 hours  
**Dependencies**: Task 4.1, Task 4.2

**Description**: Integrate sessions into authentication flow.

**Implementation Steps**:
1. Update `/auth/login` to create session
2. Create session validation middleware
3. Add `X-Session-ID` header support
4. Update `/auth/logout` endpoint
5. Create `/auth/logout-all-devices` endpoint
6. Update tests

**Acceptance Criteria**:
- [ ] Login creates Redis session
- [ ] Session validated on each request
- [ ] Logout deletes session
- [ ] Logout-all-devices works
- [ ] Tests verify session lifecycle

**Files Modified**:
- `handlers/auth_handlers.py` (update)
- `dependencies/auth_dependencies.py` (update)
- `api/auth_routes.py` (update)
- `tests/integration/test_auth_sessions.py` (new)

---

### Task 4.4: Session Management UI Endpoints
**Priority**: P2  
**Effort**: 2-3 hours  
**Dependencies**: Task 4.1

**Description**: Create endpoints for managing active sessions.

**Implementation Steps**:
1. Create `GET /user/sessions` endpoint
2. Create `DELETE /user/sessions/{session_id}` endpoint
3. Add session listing with metadata
4. Add session revocation

**Acceptance Criteria**:
- [ ] Users can view active sessions
- [ ] Users can revoke individual sessions
- [ ] Session metadata is displayed

**Files Modified**:
- `api/auth_routes.py` (update)

---

### Task 4.5: Session Security Enhancements
**Priority**: P2  
**Effort**: 2-3 hours  
**Dependencies**: Task 4.3

**Description**: Add suspicious activity detection.

**Implementation Steps**:
1. Add max sessions limit (10 per user)
2. Add concurrent login detection
3. Add session expiry notifications
4. Add security event logging

**Acceptance Criteria**:
- [ ] Max 10 sessions enforced
- [ ] Suspicious activity logged
- [ ] Security events tracked

**Files Modified**:
- `services/redis/sessions.py` (update)
- `services/logger.py` (update)

---

## Epic 5: Monitoring & Deployment
**Timeline**: Week 3-4 (12-16 hours)  
**Goal**: Deploy to production with monitoring

### Task 5.1: Health Check Endpoints
**Priority**: P0  
**Effort**: 2-3 hours  
**Dependencies**: Tasks 2.1, 3.1, 4.1

**Description**: Create comprehensive health check endpoints.

**Implementation Steps**:
1. Create `/health/redis` endpoint
2. Add memory usage metrics
3. Add cache hit rate metrics
4. Add connection pool status
5. Add fallback mode indicator

**Code Structure**:
```python
# api/admin_routes.py
@app.get("/health/redis")
async def redis_health(request: Request):
    """Redis health and metrics"""
    redis_client = request.app.state.redis
    
    try:
        # Ping Redis
        await redis_client.ping()
        
        # Get memory info
        info = await redis_client.info("memory")
        used_mb = info["used_memory"] / 1024 / 1024
        
        # Get cache stats
        stats_info = await redis_client.info("stats")
        hits = stats_info.get("keyspace_hits", 0)
        misses = stats_info.get("keyspace_misses", 0)
        total = hits + misses
        hit_rate = (hits / total * 100) if total > 0 else 0
        
        # Get application cache service stats
        cache_service = CacheService(redis_client)
        app_stats = cache_service.get_stats()
        
        return {
            "status": "healthy",
            "fallback_mode": False,
            "memory_used_mb": round(used_mb, 2),
            "memory_percent": round((used_mb / 256) * 100, 2),
            "redis_cache_hit_rate": round(hit_rate, 2),
            "app_cache_hit_rate": round(app_stats["hit_rate"], 2),
            "total_requests": total
        }
    except Exception as e:
        return {
            "status": "unhealthy" if not fallback_mode else "degraded",
            "fallback_mode": True,
            "error": str(e)
        }
```

**Acceptance Criteria**:
- [ ] Health endpoint returns detailed metrics
- [ ] Memory usage is accurate
- [ ] Cache hit rate is calculated
- [ ] Fallback mode is indicated
- [ ] Endpoint responds <100ms

**Files Modified**:
- `api/admin_routes.py` (update)

---

### Task 5.2: Performance Benchmarking
**Priority**: P1  
**Effort**: 3-4 hours  
**Dependencies**: Tasks 3.3, 3.4

**Description**: Measure and document performance improvements.

**Implementation Steps**:
1. Create baseline performance test (without Redis)
2. Create Redis-enabled performance test
3. Measure database query times
4. Measure API response times
5. Calculate improvement metrics
6. Document results

**Acceptance Criteria**:
- [ ] Baseline performance documented
- [ ] Redis performance documented
- [ ] 50x improvement demonstrated
- [ ] Results added to documentation

**Files Modified**:
- `tests/performance/test_benchmarks.py` (new)
- `specs/006-redis-integration/BENCHMARKS.md` (new)

---

### Task 5.3: Railway Redis Addon Setup
**Priority**: P0  
**Effort**: 1 hour  
**Dependencies**: None

**Description**: Add Redis to Railway deployment.

**Implementation Steps**:
1. Login to Railway CLI
2. Add Redis plugin
3. Verify environment variables
4. Test connection from Railway
5. Document setup process

**CLI Commands**:
```bash
# Login
railway login

# Link project
railway link

# Add Redis addon
railway add redis

# Verify variables
railway variables
# Should see: REDIS_URL=redis://default:password@...

# Set additional variables
railway variables set REDIS_ENABLED=true
railway variables set REDIS_MAX_CONNECTIONS=20
```

**Acceptance Criteria**:
- [ ] Railway Redis addon installed
- [ ] Environment variables configured
- [ ] Connection test passes
- [ ] Setup documented

**Files Modified**:
- `docs/RAILWAY_DEPLOYMENT_IMPLEMENTATION.md` (update)

---

### Task 5.4: Staging Deployment
**Priority**: P0  
**Effort**: 2-3 hours  
**Dependencies**: Task 5.3

**Description**: Deploy to staging with Redis enabled.

**Implementation Steps**:
1. Deploy to Railway staging
2. Run smoke tests
3. Monitor for errors
4. Check Redis metrics
5. Verify fallback works

**Acceptance Criteria**:
- [ ] Staging deployment successful
- [ ] All tests pass in staging
- [ ] Redis metrics look healthy
- [ ] No errors in logs

---

### Task 5.5: Production Canary Deployment
**Priority**: P0  
**Effort**: 4-5 hours over 3 days  
**Dependencies**: Task 5.4

**Description**: Gradual rollout to production with monitoring.

**Implementation Steps**:
1. **Day 1**: Deploy with 10% traffic to Redis
2. Monitor metrics for 8 hours
3. **Day 2**: Increase to 50% traffic
4. Monitor metrics for 8 hours
5. **Day 3**: Increase to 100% traffic
6. Monitor for 24 hours
7. Remove fallback after 2 weeks stable

**Monitoring Checklist**:
- [ ] Error rate remains <0.1%
- [ ] Response time improves 50x
- [ ] Cache hit rate >80%
- [ ] Memory usage <100MB
- [ ] No fallback activations

**Rollback Plan**:
- Set `REDIS_ENABLED=false` if issues occur
- Automatic fallback to memory
- Zero downtime rollback

**Acceptance Criteria**:
- [ ] Gradual rollout completed
- [ ] Metrics look healthy at each stage
- [ ] Production is stable
- [ ] Performance improvements confirmed

---

### Task 5.6: Documentation & Knowledge Transfer
**Priority**: P1  
**Effort**: 2-3 hours  
**Dependencies**: Task 5.5

**Description**: Update documentation and create runbooks.

**Implementation Steps**:
1. Update README with Redis setup
2. Create operational runbook
3. Document troubleshooting steps
4. Update agent context
5. Create deployment checklist

**Deliverables**:
- [ ] README updated
- [ ] Runbook created (`docs/redis/RUNBOOK.md`)
- [ ] Troubleshooting guide updated
- [ ] Agent context updated

**Files Modified**:
- `README.md` (update)
- `docs/redis/RUNBOOK.md` (new)
- `.github/copilot-instructions.md` (update)

---

## Summary Statistics

### Total Effort Breakdown

| Epic | Tasks | Effort (hours) | Priority |
|------|-------|---------------|----------|
| Epic 1: Core Infrastructure | 4 | 8-12 | P0 |
| Epic 2: Browser Slot Management | 5 | 12-16 | P0 |
| Epic 3: Database Caching | 5 | 12-16 | P0 |
| Epic 4: Session Management | 5 | 16-20 | P1 |
| Epic 5: Monitoring & Deployment | 6 | 12-16 | P0/P1 |
| **TOTAL** | **25** | **60-80** | Mixed |

### Task Priority Distribution

- **P0 (Critical)**: 15 tasks (60%)
- **P1 (Important)**: 8 tasks (32%)
- **P2 (Nice-to-have)**: 2 tasks (8%)

### Test Requirements Summary

| Test Type | Count | Coverage Target |
|-----------|-------|-----------------|
| Unit Tests | 50+ | >90% |
| Contract Tests | 16 | 100% of interfaces |
| Integration Tests | 8 | Key flows |
| Performance Tests | 2 | Benchmark suite |
| **TOTAL** | **76+** | **>85% overall** |

### Files to Create (New)

1. `services/redis/client.py`
2. `services/redis/base.py`
3. `services/redis/browser_slots.py`
4. `services/redis/cache.py`
5. `services/redis/sessions.py`
6. `services/redis/__init__.py`
7. `tests/unit/test_redis_browser_slots.py`
8. `tests/unit/test_redis_cache.py`
9. `tests/unit/test_redis_sessions.py`
10. `tests/integration/test_redis_integration.py`
11. `tests/integration/test_tier_caching.py`
12. `tests/integration/test_auth_sessions.py`
13. `tests/performance/test_benchmarks.py`
14. `specs/006-redis-integration/BENCHMARKS.md`
15. `docs/redis/RUNBOOK.md`

**Total**: 15 new files

### Files to Modify (Existing)

1. `main.py`
2. `config.py`
3. `docker-compose.yml`
4. `handlers/quiz_handlers.py`
5. `handlers/auth_handlers.py`
6. `services/db_services/tier_service.py`
7. `api/quiz_routes.py`
8. `api/auth_routes.py`
9. `api/admin_routes.py`
10. `dependencies/auth_dependencies.py`
11. `tests/conftest.py`
12. `README.md`
13. `.github/copilot-instructions.md`

**Total**: 13 files to modify

---

## Implementation Schedule

### Week 1: Core + Browser Slots

**Monday-Tuesday** (Days 1-2):
- Task 1.1: Redis Client Setup
- Task 1.2: Configuration
- Task 1.3: Memory Fallback Base
- Task 1.4: Docker Compose

**Wednesday-Friday** (Days 3-5):
- Task 2.1: BrowserSlotService Implementation
- Task 2.2: BrowserSlotService Tests
- Task 2.3: Web Scraping Integration
- Task 2.4: Integration Tests
- Task 2.5: Monitoring (if time)

### Week 2: Caching + Session Start

**Monday-Wednesday** (Days 1-3):
- Task 3.1: CacheService Implementation
- Task 3.2: CacheService Tests
- Task 3.3: User Tier Caching
- Task 3.4: Quiz Metadata Caching
- Task 3.5: Cache Monitoring

**Thursday-Friday** (Days 4-5):
- Task 4.1: SessionService Implementation
- Task 4.2: SessionService Tests

### Week 3: Sessions + Monitoring

**Monday-Wednesday** (Days 1-3):
- Task 4.3: Authentication Integration
- Task 4.4: Session Management UI
- Task 4.5: Session Security (if time)

**Thursday-Friday** (Days 4-5):
- Task 5.1: Health Check Endpoints
- Task 5.2: Performance Benchmarking
- Task 5.3: Railway Redis Setup
- Task 5.4: Staging Deployment

### Week 4: Production Deployment

**Monday-Wednesday** (Days 1-3):
- Task 5.5: Production Canary (Day 1: 10%, Day 2: 50%, Day 3: 100%)

**Thursday-Friday** (Days 4-5):
- Task 5.6: Documentation
- Monitoring and stabilization
- Bug fixes if needed

---

## Success Criteria

### Phase 2 Complete When:

- [ ] All P0 tasks completed (15 tasks)
- [ ] All P1 tasks completed or deferred (8 tasks)
- [ ] Unit test coverage >90%
- [ ] All integration tests passing
- [ ] Performance improvement demonstrated (50x)
- [ ] Staging deployment successful
- [ ] Production canary at 100%
- [ ] Documentation updated
- [ ] No P0 bugs in production

---

**Document Version**: 1.0  
**Created**: 2025-10-22  
**Status**: ✅ Complete - Ready for Implementation  
**Next**: Begin Epic 1, Task 1.1 (Redis Client Setup)
