# Phase 0: Research - Redis Integration

**Created**: 2025-10-22  
**Status**: ✅ Complete  
**Next Phase**: Phase 1 (Design & Contracts)

---

## Overview

This document captures the research and technology decisions for integrating Redis into Quizify. Each section addresses a key technical question that must be resolved before implementation.

---

## 1. Redis Client Selection

### Question
Which Python Redis client library should we use for async FastAPI integration?

### Options Evaluated

#### Option A: redis-py with async support (`redis[hiredis]`)
- **Pros**:
  - Official Redis Python client (redis-py)
  - Async support via `redis.asyncio`
  - Hiredis C parser for 5-10x performance boost
  - Active maintenance (1M+ downloads/week)
  - Connection pooling built-in
  - Comprehensive documentation
  - Type hints support
  
- **Cons**:
  - Requires explicit async client usage
  - Slightly verbose for simple operations

- **Example**:
  ```python
  import redis.asyncio as redis
  
  client = await redis.from_url(
      "redis://localhost:6379",
      encoding="utf-8",
      decode_responses=True,
      max_connections=10
  )
  await client.set("key", "value", ex=300)
  value = await client.get("key")
  ```

#### Option B: aioredis (deprecated)
- **Status**: ⚠️ Merged into redis-py v4.2+
- **Recommendation**: Use redis-py instead

#### Option C: redis-om-python (Object Mapper)
- **Pros**:
  - Pydantic-based models
  - Nice abstractions for complex data
  
- **Cons**:
  - Overkill for simple key-value operations
  - Additional abstraction layer
  - Less control over Redis operations
  - Not widely adopted (22k downloads/week vs 1M+)

### Decision

✅ **Use `redis[hiredis]>=5.0.0`**

**Rationale**:
1. Official, well-maintained library
2. Full async support for FastAPI
3. Hiredis parser provides optimal performance
4. Direct control over Redis operations
5. Excellent documentation and community support
6. Simple integration with FastAPI lifespan

**Installation**:
```bash
pip install "redis[hiredis]>=5.0.0"
```

---

## 2. Connection Management

### Question
How should we manage Redis connections in FastAPI to optimize performance and prevent resource leaks?

### Options Evaluated

#### Option A: FastAPI Lifespan with Connection Pool
- **Pattern**:
  ```python
  from contextlib import asynccontextmanager
  from fastapi import FastAPI
  import redis.asyncio as redis
  
  @asynccontextmanager
  async def lifespan(app: FastAPI):
      # Startup: Create connection pool
      app.state.redis = await redis.from_url(
          settings.REDIS_URL,
          encoding="utf-8",
          decode_responses=True,
          max_connections=20,
          socket_keepalive=True,
          socket_connect_timeout=5,
          retry_on_timeout=True
      )
      
      yield  # Application runs here
      
      # Shutdown: Close connections
      await app.state.redis.close()
  
  app = FastAPI(lifespan=lifespan)
  ```

- **Pros**:
  - Single connection pool shared across all requests
  - Automatic cleanup on shutdown
  - FastAPI-native pattern
  - Connection reuse (no overhead per request)

#### Option B: Dependency Injection per Request
- **Pattern**:
  ```python
  async def get_redis():
      client = await redis.from_url(...)
      try:
          yield client
      finally:
          await client.close()
  ```

- **Cons**:
  - Creates new connection per request (expensive)
  - No connection pooling benefits
  - Higher latency

#### Option C: Global Singleton
- **Cons**:
  - Harder to test
  - Not FastAPI-idiomatic
  - No automatic cleanup

### Decision

✅ **Use FastAPI Lifespan with Connection Pool**

**Rationale**:
1. Single connection pool for entire app lifetime
2. Connection reuse across all requests
3. Automatic cleanup on shutdown
4. FastAPI best practice
5. Easy to access via `request.app.state.redis`

**Implementation Location**: `services/redis/client.py`

**Configuration**:
```python
# Recommended pool settings
max_connections=20          # Max concurrent connections
socket_keepalive=True       # Keep connections alive
socket_connect_timeout=5    # 5 second connection timeout
retry_on_timeout=True       # Retry on timeout
health_check_interval=30    # Check connection every 30s
```

---

## 3. Data Structure Selection

### Question
Which Redis data structures should we use for each use case?

### Use Case Analysis

#### A. Browser Slot Counting
**Requirement**: Track concurrent browser sessions per user (max 3)

**Options**:
1. **Simple String Counter** (INCR/DECR)
2. Set of session IDs
3. Sorted set with timestamps

**Decision**: ✅ **String Counter with INCR/DECR**

**Rationale**:
- Atomic operations (thread-safe)
- Simplest solution
- Fastest performance (<1ms)
- Easy to implement fallback

**Pattern**:
```python
# Key: browser_slots:{user_id}
# Value: integer count (0-3)

# Acquire slot
count = await redis.incr(f"browser_slots:{user_id}")
await redis.expire(f"browser_slots:{user_id}", 300)  # 5 min TTL

if count > 3:
    await redis.decr(f"browser_slots:{user_id}")
    raise TooManyBrowsersError()

# Release slot
await redis.decr(f"browser_slots:{user_id}")
```

#### B. Browser Session Metadata
**Requirement**: Store session details (URL, start time, process ID)

**Decision**: ✅ **Hash Structure**

**Rationale**:
- Store multiple fields per session
- Atomic field updates
- Memory efficient for structured data

**Pattern**:
```python
# Key: browser_session:{user_id}:{session_id}
# Fields: user_id, url, started_at, process_id

await redis.hset(
    f"browser_session:{user_id}:{session_id}",
    mapping={
        "user_id": user_id,
        "url": url,
        "started_at": datetime.utcnow().isoformat(),
        "process_id": os.getpid()
    }
)
await redis.expire(f"browser_session:{user_id}:{session_id}", 300)
```

#### C. Database Query Caching
**Requirement**: Cache user tier info, quiz metadata

**Decision**: ✅ **JSON String**

**Rationale**:
- Simple serialization with Pydantic
- Works with existing schemas
- Easy invalidation

**Pattern**:
```python
# Key: cache:user_tier:{user_id}
# Value: JSON string

# Set cache
user_tier = await db_service.get_user_tier(user_id)
await redis.set(
    f"cache:user_tier:{user_id}",
    user_tier.model_dump_json(),  # Pydantic v2
    ex=300  # 5 min TTL
)

# Get cache
cached = await redis.get(f"cache:user_tier:{user_id}")
if cached:
    user_tier = UserTierInfo.model_validate_json(cached)
```

#### D. User Sessions (Authentication)
**Requirement**: Track active login sessions per user

**Decision**: ✅ **Hash Structure + Set**

**Rationale**:
- Hash stores session details
- Set tracks all sessions per user (for logout_all)

**Pattern**:
```python
# Session details
# Key: session:{session_id}
await redis.hset(f"session:{session_id}", mapping={...})

# User's active sessions
# Key: user_sessions:{user_id}
# Value: Set of session_ids
await redis.sadd(f"user_sessions:{user_id}", session_id)

# Logout all devices
session_ids = await redis.smembers(f"user_sessions:{user_id}")
for sid in session_ids:
    await redis.delete(f"session:{sid}")
await redis.delete(f"user_sessions:{user_id}")
```

#### E. Rate Limiting
**Requirement**: Track API calls per user per time window

**Decision**: ✅ **String Counter with EXPIRE**

**Pattern**:
```python
# Key: rate_limit:{user_id}:{endpoint}:{window}
# Value: count
# Window: minute, hour, day

key = f"rate_limit:{user_id}:quiz_generation:minute"
count = await redis.incr(key)

if count == 1:
    await redis.expire(key, 60)  # First request sets TTL

if count > limit:
    raise RateLimitExceeded()
```

### Summary Table

| Use Case | Redis Type | Key Pattern | TTL |
|----------|-----------|-------------|-----|
| Browser slot count | String (integer) | `browser_slots:{user_id}` | 5 min |
| Browser session | Hash | `browser_session:{user_id}:{session_id}` | 5 min |
| DB cache | String (JSON) | `cache:{table}:{key}` | 5-30 min |
| User session | Hash + Set | `session:{sid}`, `user_sessions:{uid}` | 24 hours |
| Rate limiting | String (counter) | `rate_limit:{uid}:{endpoint}:{window}` | 1-60 min |

---

## 4. Fallback Strategy

### Question
What happens when Redis is unavailable? How do we maintain service continuity?

### Requirements
1. No downtime during Redis outages
2. Graceful degradation (reduced performance, not failure)
3. Automatic recovery when Redis comes back
4. Clear visibility into fallback mode

### Design

#### A. Fallback Architecture

```python
class RedisService:
    def __init__(self, redis_client: Optional[redis.Redis]):
        self.redis = redis_client
        self.fallback_mode = False
        self._memory_cache = {}  # In-memory fallback
    
    async def get(self, key: str) -> Optional[str]:
        """Get value with automatic fallback"""
        try:
            if self.redis and not self.fallback_mode:
                return await self.redis.get(key)
        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.warning(f"Redis error, falling back to memory: {e}")
            self.fallback_mode = True
        
        # Fallback to memory
        return self._memory_cache.get(key)
    
    async def set(self, key: str, value: str, ex: int = None):
        """Set value with automatic fallback"""
        try:
            if self.redis and not self.fallback_mode:
                await self.redis.set(key, value, ex=ex)
                return
        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.warning(f"Redis error, falling back to memory: {e}")
            self.fallback_mode = True
        
        # Fallback to memory
        self._memory_cache[key] = value
        # Note: TTL not enforced in memory fallback (acceptable trade-off)
```

#### B. Health Check Recovery

```python
async def check_redis_health(app: FastAPI):
    """Periodic health check to recover from fallback mode"""
    while True:
        await asyncio.sleep(30)  # Check every 30 seconds
        
        if app.state.redis_service.fallback_mode:
            try:
                await app.state.redis.ping()
                logger.info("Redis recovered, exiting fallback mode")
                app.state.redis_service.fallback_mode = False
            except Exception:
                logger.debug("Redis still unavailable")
```

#### C. Metrics & Monitoring

```python
@app.middleware("http")
async def track_redis_metrics(request: Request, call_next):
    """Track Redis usage and fallback events"""
    redis_service = request.app.state.redis_service
    
    # Track request
    start = time.time()
    response = await call_next(request)
    
    # Log if in fallback mode
    if redis_service.fallback_mode:
        logger.warning(
            f"Request served in Redis fallback mode",
            extra={
                "path": request.url.path,
                "duration_ms": (time.time() - start) * 1000
            }
        )
    
    return response
```

### Decision

✅ **Automatic Memory Fallback with Health Check Recovery**

**Rationale**:
1. **Zero Downtime**: Service continues without Redis
2. **Automatic Recovery**: Health checks restore Redis when available
3. **Visibility**: Logging and metrics show fallback state
4. **Acceptable Trade-offs**: Memory fallback doesn't scale, but prevents outages

**Trade-offs in Fallback Mode**:
- ❌ No distributed coordination (single instance only)
- ❌ No TTL enforcement (memory leaks possible)
- ❌ Limited capacity (memory constrained)
- ✅ Core functionality works (quiz generation, submission)
- ✅ Automatic recovery (no manual intervention)

**Monitoring**:
- Log entry on fallback activation
- Metric: `redis_fallback_mode` (boolean)
- Metric: `redis_fallback_duration_seconds`
- Alert: Fallback mode active > 5 minutes

---

## 5. Testing Strategy

### Question
How do we test Redis integration effectively in unit, integration, and contract tests?

### A. Unit Tests (Fast, Isolated)

**Tool**: ✅ **fakeredis**

**Installation**:
```bash
pip install fakeredis[lua]>=2.19.0
```

**Usage**:
```python
import pytest
from fakeredis import aioredis as fakeredis

@pytest.fixture
async def redis_client():
    """Fake Redis client for unit tests"""
    client = fakeredis.FakeRedis(decode_responses=True)
    yield client
    await client.flushall()  # Clean up
    await client.close()

@pytest.mark.asyncio
async def test_browser_slot_acquire(redis_client):
    """Test browser slot acquisition logic"""
    service = BrowserSlotService(redis_client)
    
    # Acquire 3 slots (should succeed)
    for i in range(3):
        session_id = await service.acquire_slot("user123")
        assert session_id is not None
    
    # Acquire 4th slot (should fail)
    with pytest.raises(TooManyBrowsersError):
        await service.acquire_slot("user123")
```

**Pros**:
- No Redis server required
- Fast (<1ms per test)
- Runs in CI/CD without setup
- Supports most Redis commands

**Cons**:
- Not 100% identical to real Redis
- Some advanced features unsupported

#### B. Integration Tests (Real Redis)

**Tool**: ✅ **pytest-redis**

**Installation**:
```bash
pip install pytest-redis>=3.0.0
```

**Usage**:
```python
import pytest
import redis.asyncio as redis

@pytest.fixture(scope="session")
def redis_server(redis_proc):
    """Real Redis server for integration tests"""
    return redis_proc

@pytest.fixture
async def redis_client(redis_server):
    """Real Redis client"""
    client = await redis.from_url(
        f"redis://{redis_server.host}:{redis_server.port}",
        decode_responses=True
    )
    yield client
    await client.flushall()
    await client.close()

@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_redis_connection(redis_client):
    """Test with actual Redis server"""
    await redis_client.set("test", "value")
    assert await redis_client.get("test") == "value"
```

**Configuration** (`pytest.ini`):
```ini
[pytest]
markers =
    integration: Integration tests requiring Redis
    
# Redis server configuration
redis_host = localhost
redis_port = 6379
redis_db = 15  # Use separate DB for tests
```

**Run Integration Tests**:
```bash
# Skip integration tests by default
pytest -m "not integration"

# Run only integration tests
pytest -m integration

# Run all tests
pytest
```

#### C. Contract Tests

**Purpose**: Verify service interfaces match specifications

```python
@pytest.mark.contract
@pytest.mark.asyncio
async def test_browser_slot_service_contract(redis_client):
    """Verify BrowserSlotService matches contract"""
    service = BrowserSlotService(redis_client)
    
    # Contract: acquire_slot(user_id) -> session_id
    session_id = await service.acquire_slot("user123")
    assert isinstance(session_id, str)
    assert len(session_id) == 36  # UUID format
    
    # Contract: get_slot_count(user_id) -> int
    count = await service.get_slot_count("user123")
    assert isinstance(count, int)
    assert 0 <= count <= 3
    
    # Contract: release_slot(user_id, session_id) -> None
    result = await service.release_slot("user123", session_id)
    assert result is None
    
    # Contract: verify slot released
    count_after = await service.get_slot_count("user123")
    assert count_after == 0
```

### Decision

✅ **Three-Tier Testing Strategy**

**Test Pyramid**:
```
     /\
    /  \  Integration (pytest-redis) - 10 tests
   /____\ 
  /      \ Contract (interface verification) - 15 tests
 /________\
/          \ Unit (fakeredis) - 50 tests
```

**Implementation**:
1. **Unit Tests** (70%): Use `fakeredis` for all business logic
2. **Contract Tests** (20%): Verify service interfaces
3. **Integration Tests** (10%): Validate real Redis behavior

**CI/CD Strategy**:
- PR checks: Unit + Contract tests only (no Redis required)
- Main branch: All tests including integration
- Nightly: Full test suite with performance benchmarks

**Test Organization**:
```
tests/
├── unit/
│   ├── test_redis_browser_slots.py
│   ├── test_redis_cache.py
│   └── test_redis_sessions.py
├── integration/
│   └── test_redis_integration.py
└── contract/
    └── test_redis_contracts.py
```

---

## 6. Railway Deployment

### Question
How do we deploy Redis on Railway and configure the application?

### A. Railway Redis Add-on

**Setup**:
```bash
# 1. Install Railway CLI
brew install railway

# 2. Login
railway login

# 3. Link project
railway link

# 4. Add Redis plugin
railway add redis

# 5. Verify
railway variables
```

**Pricing**:
- **Free Tier**: Not available (Redis is paid add-on)
- **Starter Plan**: $5/month for 256MB RAM
- **Pro Plan**: Scales with usage

**Specs (Starter)**:
- Memory: 256MB
- Persistence: RDB snapshots
- Eviction: allkeys-lru (when memory full)
- Max Connections: 100

### B. Environment Variables

**Automatic** (Railway sets these):
```bash
REDIS_URL=redis://default:password@redis.railway.internal:6379
REDIS_HOST=redis.railway.internal
REDIS_PORT=6379
REDIS_PASSWORD=<auto-generated>
```

**Manual Configuration** (`config.py`):
```python
class Settings(BaseSettings):
    # Redis configuration
    REDIS_URL: str = Field(
        default="redis://localhost:6379",
        description="Redis connection URL"
    )
    REDIS_ENABLED: bool = Field(
        default=True,
        description="Enable Redis (false for fallback mode)"
    )
    REDIS_MAX_CONNECTIONS: int = Field(
        default=20,
        description="Max Redis connection pool size"
    )
    REDIS_CONNECT_TIMEOUT: int = Field(
        default=5,
        description="Redis connection timeout (seconds)"
    )
    
    class Config:
        env_file = ".env"
```

**Local Development** (`.env`):
```bash
# Local Redis (Docker)
REDIS_URL=redis://localhost:6379
REDIS_ENABLED=true
```

**Production** (Railway):
```bash
# Railway auto-populates REDIS_URL
REDIS_ENABLED=true
REDIS_MAX_CONNECTIONS=20
```

### C. Local Development Setup

**Option 1: Docker Compose**

```yaml
# docker-compose.yml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

volumes:
  redis_data:
```

**Start Redis**:
```bash
docker-compose up -d redis
```

**Option 2: Direct Install (macOS)**

```bash
# Install Redis
brew install redis

# Start Redis
brew services start redis

# Test connection
redis-cli ping  # Should return "PONG"
```

### D. Monitoring & Management

**Railway Dashboard**:
- Memory usage
- Connection count
- Command stats
- Slow queries

**Redis CLI** (via Railway):
```bash
# Connect to Railway Redis
railway run redis-cli -u $REDIS_URL

# Check stats
INFO stats
INFO memory

# Monitor commands
MONITOR

# List all keys (use carefully in production)
KEYS *

# Get key info
TTL key_name
TYPE key_name
```

**Health Check Endpoint**:
```python
@app.get("/health/redis")
async def redis_health(request: Request):
    """Check Redis connectivity"""
    try:
        await request.app.state.redis.ping()
        return {
            "status": "healthy",
            "fallback_mode": False
        }
    except Exception as e:
        return {
            "status": "degraded",
            "fallback_mode": True,
            "error": str(e)
        }
```

### Decision

✅ **Railway Redis Add-on + Docker Compose for Local Dev**

**Rationale**:
1. **Railway Redis**: Managed, no ops burden
2. **Docker Compose**: Consistent local environment
3. **Environment Variables**: Railway auto-configures
4. **Cost Effective**: $5/month is affordable
5. **Health Checks**: Built-in monitoring

**Deployment Checklist**:
- [ ] Add Railway Redis plugin
- [ ] Verify `REDIS_URL` environment variable
- [ ] Set `REDIS_ENABLED=true`
- [ ] Configure connection pool size
- [ ] Add health check endpoint
- [ ] Set up alerting for fallback mode
- [ ] Document Redis access for team

**Local Development Checklist**:
- [ ] Create `docker-compose.yml`
- [ ] Add Redis service
- [ ] Update `.env` with `REDIS_URL`
- [ ] Test connection with `redis-cli`
- [ ] Run tests with local Redis

---

## 7. Performance Benchmarks

### Expected Performance

Based on Redis documentation and industry benchmarks:

| Operation | Redis Time | Database Time | Improvement |
|-----------|-----------|---------------|-------------|
| Simple GET | 0.5-1ms | 50-200ms | 50-200x |
| Simple SET | 0.5-1ms | 50-200ms | 50-200x |
| INCR/DECR | 0.1-0.5ms | N/A | Atomic |
| Hash GET | 0.5-1ms | 50-200ms | 50-200x |
| Hash SET | 0.5-1ms | 50-200ms | 50-200x |

### Bottleneck Analysis

**Current Architecture**:
```
User Request → FastAPI → Supabase Query (50-200ms) → Response
Total: ~100-300ms per request with DB query
```

**With Redis Caching**:
```
User Request → FastAPI → Redis GET (1ms) → Response
Total: ~10-20ms per cached request

Cache Miss → Supabase (50-200ms) → Redis SET (1ms) → Response
Total: ~100-300ms (first request only)
```

**Expected Improvements**:
- **API Response Time**: p95 200ms → 50ms (75% reduction)
- **Database Load**: 1000 queries/min → 200 queries/min (80% reduction)
- **Cache Hit Rate**: Target 80%+ (5 min TTL on user tier data)

### Load Testing Plan

**Phase 1: Baseline (Before Redis)**
```bash
# Install k6
brew install k6

# Run load test
k6 run scripts/load-test-baseline.js
```

**Phase 2: After Redis Integration**
```bash
k6 run scripts/load-test-redis.js
```

**Metrics to Compare**:
- Requests per second
- p50, p95, p99 latency
- Error rate
- Database query count
- Memory usage

---

## Summary of Decisions

| Area | Decision | Rationale |
|------|----------|-----------|
| **Client Library** | `redis[hiredis]>=5.0.0` | Official, async support, best performance |
| **Connection** | FastAPI lifespan + pool | Connection reuse, automatic cleanup |
| **Browser Slots** | String counter (INCR/DECR) | Atomic, simple, fast |
| **Session Data** | Hash structure | Multiple fields, memory efficient |
| **Caching** | JSON strings | Works with Pydantic, easy invalidation |
| **User Sessions** | Hash + Set | Details + tracking all sessions |
| **Rate Limiting** | String counter + EXPIRE | Simple, effective |
| **Fallback** | Memory fallback + health check | Zero downtime, auto recovery |
| **Unit Tests** | fakeredis | Fast, no Redis required |
| **Integration Tests** | pytest-redis | Real Redis validation |
| **Deployment** | Railway Redis add-on | Managed, cost-effective ($5/month) |
| **Local Dev** | Docker Compose | Consistent environment |

---

## Risk Assessment

### Identified Risks

1. **Redis Downtime** → Mitigated by automatic fallback to memory
2. **Memory Usage** → Mitigated by aggressive TTLs (5 min default)
3. **Cache Invalidation** → Mitigated by conservative TTLs, manual invalidation
4. **Network Latency** → Mitigated by connection pooling, co-location
5. **Learning Curve** → Mitigated by comprehensive docs, simple patterns

### Risk Level

🟢 **LOW RISK** - All major risks have mitigation strategies

---

## Next Steps

✅ **Phase 0 Research Complete**

**Ready for Phase 1**:
1. Create `data-model.md` - Detailed Redis key schemas
2. Create `contracts/` - Service interface specifications
3. Create `quickstart.md` - Developer setup guide
4. Update agent context with Redis patterns

**Estimated Time for Phase 1**: 2-3 days

---

**Document Version**: 1.0  
**Completed**: 2025-10-22  
**Reviewed By**: Pending  
**Approved**: Pending
