# Phase 1: Redis Data Model

**Created**: 2025-10-22  
**Status**: ✅ Complete  
**Version**: 1.0

---

## Overview

This document defines the complete Redis data model for Quizify, including key naming conventions, data structures, TTL policies, and memory usage estimates.

---

## Key Naming Conventions

### Standard Format
```
{prefix}:{entity_type}:{identifier}[:{sub_identifier}]
```

### Principles
1. **Hierarchical**: Use colons (`:`) to separate levels
2. **Consistent**: Same pattern across all use cases
3. **Descriptive**: Clear entity type identification
4. **Scoped**: User ID or session ID as primary scope
5. **Lowercase**: All keys in lowercase for consistency

### Reserved Prefixes

| Prefix | Purpose | Example |
|--------|---------|---------|
| `browser_slots` | Browser slot counting | `browser_slots:user_123` |
| `browser_session` | Browser session metadata | `browser_session:user_123:sess_abc` |
| `cache` | Database query caching | `cache:user_tier:user_123` |
| `session` | User authentication sessions | `session:sess_xyz` |
| `user_sessions` | User's active session tracking | `user_sessions:user_123` |
| `rate_limit` | API rate limiting | `rate_limit:user_123:quiz_generation:minute` |

---

## 1. Browser Slot Management

### Purpose
Track concurrent browser instances per user (max 3) across multiple FastAPI processes.

### A. Browser Slot Counter

**Key Pattern**: `browser_slots:{user_id}`  
**Data Type**: String (integer)  
**Range**: 0-3  
**TTL**: 300 seconds (5 minutes)

**Operations**:
```python
# Acquire slot (atomic)
count = await redis.incr(f"browser_slots:{user_id}")
await redis.expire(f"browser_slots:{user_id}", 300)

# Release slot (atomic)
await redis.decr(f"browser_slots:{user_id}")

# Check current count
count = await redis.get(f"browser_slots:{user_id}")
if count is None:
    count = 0
```

**Example**:
```
Key: browser_slots:user_a1b2c3
Value: 2
TTL: 287 seconds remaining
```

**Memory Usage**: ~50 bytes per user

### B. Browser Session Metadata

**Key Pattern**: `browser_session:{user_id}:{session_id}`  
**Data Type**: Hash  
**TTL**: 300 seconds (5 minutes)

**Fields**:
| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `user_id` | string | User identifier | `user_a1b2c3` |
| `session_id` | string | UUID session ID | `550e8400-e29b-41d4-a716-446655440000` |
| `url` | string | Target URL being scraped | `https://example.com` |
| `started_at` | string | ISO 8601 timestamp | `2025-10-22T10:30:00Z` |
| `process_id` | string | FastAPI process ID | `railway_instance_1_pid_42` |
| `status` | string | Session status | `active`, `completed`, `failed` |

**Operations**:
```python
# Create session
await redis.hset(
    f"browser_session:{user_id}:{session_id}",
    mapping={
        "user_id": user_id,
        "session_id": session_id,
        "url": url,
        "started_at": datetime.utcnow().isoformat(),
        "process_id": f"{os.getpid()}",
        "status": "active"
    }
)
await redis.expire(f"browser_session:{user_id}:{session_id}", 300)

# Get session details
session = await redis.hgetall(f"browser_session:{user_id}:{session_id}")

# Update status
await redis.hset(
    f"browser_session:{user_id}:{session_id}",
    "status",
    "completed"
)

# List all sessions for user (scan pattern)
cursor = 0
sessions = []
while True:
    cursor, keys = await redis.scan(
        cursor,
        match=f"browser_session:{user_id}:*",
        count=100
    )
    for key in keys:
        sessions.append(await redis.hgetall(key))
    if cursor == 0:
        break
```

**Example**:
```
Key: browser_session:user_a1b2c3:550e8400-e29b-41d4-a716-446655440000
Fields:
  user_id: "user_a1b2c3"
  session_id: "550e8400-e29b-41d4-a716-446655440000"
  url: "https://example.com/article"
  started_at: "2025-10-22T10:30:00Z"
  process_id: "railway_instance_1_pid_42"
  status: "active"
TTL: 287 seconds remaining
```

**Memory Usage**: ~250 bytes per session

---

## 2. Database Query Caching

### Purpose
Cache Supabase queries to reduce database load and improve response times.

### Cache Entry

**Key Pattern**: `cache:{table}:{identifier}` or `cache:{query_type}:{identifier}`  
**Data Type**: String (JSON)  
**TTL**: Variable (60-1800 seconds, 1-30 minutes)

**Common Cache Keys**:
| Query Type | Key Pattern | TTL | Example |
|------------|-------------|-----|---------|
| User tier info | `cache:user_tier:{user_id}` | 300s (5min) | `cache:user_tier:user_123` |
| Quiz metadata | `cache:quiz:{quiz_id}` | 1800s (30min) | `cache:quiz:quiz_abc` |
| User profile | `cache:profile:{user_id}` | 600s (10min) | `cache:profile:user_123` |
| Quiz list | `cache:quiz_list:{user_id}:{page}` | 300s (5min) | `cache:quiz_list:user_123:1` |

**Operations**:
```python
# Set cache (with Pydantic model)
user_tier = UserTierInfo(...)
await redis.set(
    f"cache:user_tier:{user_id}",
    user_tier.model_dump_json(),  # Pydantic v2
    ex=300  # 5 minutes
)

# Get cache
cached = await redis.get(f"cache:user_tier:{user_id}")
if cached:
    user_tier = UserTierInfo.model_validate_json(cached)
else:
    # Cache miss - fetch from database
    user_tier = await db_service.get_user_tier(user_id)
    # Store in cache
    await redis.set(
        f"cache:user_tier:{user_id}",
        user_tier.model_dump_json(),
        ex=300
    )

# Invalidate cache (on update)
await redis.delete(f"cache:user_tier:{user_id}")

# Pattern-based invalidation (e.g., all quiz caches for user)
cursor = 0
while True:
    cursor, keys = await redis.scan(
        cursor,
        match=f"cache:quiz_list:{user_id}:*",
        count=100
    )
    if keys:
        await redis.delete(*keys)
    if cursor == 0:
        break
```

**Example**:
```
Key: cache:user_tier:user_a1b2c3
Value: {"id":"user_a1b2c3","account_tier":"basic","current_quiz_count":5,"quota_limit":20,"quota_exceeded":false}
TTL: 287 seconds remaining
```

**Memory Usage**: ~200-500 bytes per cached query (depends on data size)

### Cache Invalidation Strategy

**Automatic (TTL-based)**:
- User tier: 5 minutes (frequently checked, changes rarely)
- Quiz metadata: 30 minutes (stable data, rarely changes)
- User profile: 10 minutes (moderate change frequency)
- Quiz lists: 5 minutes (changes on quiz creation)

**Manual (Event-based)**:
```python
# After quiz creation
await redis.delete(f"cache:quiz_list:{user_id}:*")  # Pattern delete

# After tier upgrade
await redis.delete(f"cache:user_tier:{user_id}")

# After profile update
await redis.delete(f"cache:profile:{user_id}")

# After quiz deletion
await redis.delete(f"cache:quiz:{quiz_id}")
await redis.delete(f"cache:quiz_list:{user_id}:*")
```

---

## 3. User Session Management

### Purpose
Track authenticated user sessions across devices for enhanced security.

### A. Session Details

**Key Pattern**: `session:{session_id}`  
**Data Type**: Hash  
**TTL**: 86400 seconds (24 hours)

**Fields**:
| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `session_id` | string | UUID session ID | `sess_550e8400-e29b-41d4` |
| `user_id` | string | User identifier | `user_a1b2c3` |
| `created_at` | string | ISO 8601 timestamp | `2025-10-22T10:00:00Z` |
| `last_active` | string | ISO 8601 timestamp | `2025-10-22T10:30:00Z` |
| `device_type` | string | Device type | `browser`, `mobile`, `api` |
| `ip_address` | string | IP address (hashed) | `hash_of_ip` |
| `user_agent` | string | User agent (truncated) | `Mozilla/5.0...` |

**Operations**:
```python
# Create session
session_id = str(uuid.uuid4())
await redis.hset(
    f"session:{session_id}",
    mapping={
        "session_id": session_id,
        "user_id": user_id,
        "created_at": datetime.utcnow().isoformat(),
        "last_active": datetime.utcnow().isoformat(),
        "device_type": device_type,
        "ip_address": hash_ip(ip_address),
        "user_agent": user_agent[:100]  # Truncate
    }
)
await redis.expire(f"session:{session_id}", 86400)

# Add to user's session set
await redis.sadd(f"user_sessions:{user_id}", session_id)
await redis.expire(f"user_sessions:{user_id}", 86400)

# Validate session
session = await redis.hgetall(f"session:{session_id}")
if not session:
    raise InvalidSessionError()

# Refresh session (extend TTL)
await redis.hset(
    f"session:{session_id}",
    "last_active",
    datetime.utcnow().isoformat()
)
await redis.expire(f"session:{session_id}", 86400)

# Logout (delete session)
await redis.delete(f"session:{session_id}")
await redis.srem(f"user_sessions:{user_id}", session_id)
```

**Example**:
```
Key: session:sess_550e8400-e29b-41d4
Fields:
  session_id: "sess_550e8400-e29b-41d4"
  user_id: "user_a1b2c3"
  created_at: "2025-10-22T10:00:00Z"
  last_active: "2025-10-22T10:30:00Z"
  device_type: "browser"
  ip_address: "hash_abc123"
  user_agent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)..."
TTL: 85000 seconds remaining
```

**Memory Usage**: ~300 bytes per session

### B. User Session Tracking

**Key Pattern**: `user_sessions:{user_id}`  
**Data Type**: Set  
**TTL**: 86400 seconds (24 hours)

**Operations**:
```python
# Add session to user's set
await redis.sadd(f"user_sessions:{user_id}", session_id)

# Get all sessions for user
session_ids = await redis.smembers(f"user_sessions:{user_id}")

# Count active sessions
count = await redis.scard(f"user_sessions:{user_id}")

# Logout all devices
session_ids = await redis.smembers(f"user_sessions:{user_id}")
if session_ids:
    # Delete all session details
    session_keys = [f"session:{sid}" for sid in session_ids]
    await redis.delete(*session_keys)
    # Delete the set
    await redis.delete(f"user_sessions:{user_id}")
```

**Example**:
```
Key: user_sessions:user_a1b2c3
Members: [
  "sess_550e8400-e29b-41d4",
  "sess_661f9511-f3ac-52e5",
  "sess_772g0622-g4bd-63f6"
]
TTL: 85000 seconds remaining
```

**Memory Usage**: ~100 bytes + (40 bytes × number of sessions)

---

## 4. Rate Limiting

### Purpose
Prevent abuse by limiting API calls per user per time window.

### Rate Limit Counter

**Key Pattern**: `rate_limit:{user_id}:{endpoint}:{window}`  
**Data Type**: String (integer)  
**TTL**: Window duration (60, 3600, or 86400 seconds)

**Windows**:
- `minute`: 60 seconds
- `hour`: 3600 seconds
- `day`: 86400 seconds

**Operations**:
```python
# Check and increment rate limit
key = f"rate_limit:{user_id}:{endpoint}:minute"
count = await redis.incr(key)

# Set TTL on first request
if count == 1:
    await redis.expire(key, 60)  # 60 seconds for minute window

# Check if limit exceeded
limit = get_rate_limit(user_tier, endpoint)  # e.g., 10 per minute
if count > limit:
    ttl = await redis.ttl(key)
    raise RateLimitExceeded(
        limit=limit,
        window="minute",
        retry_after=ttl
    )

# Get current usage
current = await redis.get(key)
if current is None:
    current = 0
```

**Example**:
```
Key: rate_limit:user_a1b2c3:quiz_generation:minute
Value: 3
TTL: 45 seconds remaining

# User has made 3 quiz generation requests in the last 15 seconds
# If limit is 5/minute, they can make 2 more
```

**Rate Limit Matrix**:
| Tier | Endpoint | Minute | Hour | Day |
|------|----------|--------|------|-----|
| Free | quiz_generation | 2 | 5 | 5 |
| Basic | quiz_generation | 5 | 20 | 20 |
| Premium | quiz_generation | 10 | 100 | unlimited |
| Free | submission | 10 | 50 | 100 |
| Basic | submission | 20 | 100 | 500 |
| Premium | submission | 50 | 500 | unlimited |

**Memory Usage**: ~60 bytes per active rate limit counter

---

## Memory Usage Estimates

### Per User (Average Activity)

| Data Structure | Count | Bytes/Item | Total | TTL |
|----------------|-------|------------|-------|-----|
| Browser slot counter | 1 | 50 | 50 | 5 min |
| Browser sessions | 2 | 250 | 500 | 5 min |
| User tier cache | 1 | 300 | 300 | 5 min |
| Quiz cache (recent) | 3 | 400 | 1,200 | 30 min |
| User session | 2 | 300 | 600 | 24 hours |
| Session tracking set | 1 | 140 | 140 | 24 hours |
| Rate limit counters | 3 | 60 | 180 | 1-60 min |
| **Total per active user** | | | **~3 KB** | |

### Capacity Planning

| Concurrent Users | Memory Usage | Redis Plan | Cost |
|------------------|--------------|------------|------|
| 10 | 30 KB | Dev (256MB) | $0 (included) |
| 100 | 300 KB | Starter (256MB) | $5/month |
| 1,000 | 3 MB | Starter (256MB) | $5/month |
| 10,000 | 30 MB | Starter (256MB) | $5/month |
| 50,000 | 150 MB | Starter (256MB) | $5/month |
| 100,000 | 300 MB | Pro (512MB+) | $15/month |

**Headroom**: Railway Starter (256MB) can handle 50,000+ concurrent users with aggressive TTLs.

### Memory Optimization Strategies

1. **Aggressive TTLs**: 5-30 minute expiration on most keys
2. **LRU Eviction**: `maxmemory-policy allkeys-lru` (least recently used)
3. **Compression**: JSON serialization keeps data compact
4. **Pattern Cleanup**: Periodic deletion of expired session patterns
5. **Monitoring**: Alert at 80% memory usage (200MB of 256MB)

---

## Data Consistency Patterns

### 1. Atomic Operations
Use Redis atomic commands to prevent race conditions:
```python
# Browser slot acquisition (atomic)
count = await redis.incr(f"browser_slots:{user_id}")
if count > 3:
    await redis.decr(f"browser_slots:{user_id}")  # Rollback
    raise TooManyBrowsersError()
```

### 2. Pipeline for Multiple Operations
Batch related operations for better performance:
```python
# Create session atomically
async with redis.pipeline() as pipe:
    pipe.hset(f"session:{session_id}", mapping={...})
    pipe.expire(f"session:{session_id}", 86400)
    pipe.sadd(f"user_sessions:{user_id}", session_id)
    pipe.expire(f"user_sessions:{user_id}", 86400)
    await pipe.execute()
```

### 3. Cache-Aside Pattern
Application checks cache first, then database:
```python
async def get_user_tier(user_id: str) -> UserTierInfo:
    # Try cache first
    cached = await redis.get(f"cache:user_tier:{user_id}")
    if cached:
        return UserTierInfo.model_validate_json(cached)
    
    # Cache miss - fetch from database
    user_tier = await supabase.table("user_tier_info")\
        .select("*")\
        .eq("id", user_id)\
        .single()
    
    # Store in cache
    await redis.set(
        f"cache:user_tier:{user_id}",
        UserTierInfo(**user_tier).model_dump_json(),
        ex=300
    )
    
    return UserTierInfo(**user_tier)
```

### 4. Write-Through for Critical Data
Update both cache and database simultaneously:
```python
async def update_user_tier(user_id: str, new_tier: str):
    # Update database first
    await supabase.table("profiles")\
        .update({"account_tier": new_tier})\
        .eq("id", user_id)\
        .execute()
    
    # Invalidate cache (will refresh on next read)
    await redis.delete(f"cache:user_tier:{user_id}")
```

---

## Monitoring & Observability

### Key Metrics to Track

1. **Memory Usage**:
   ```python
   info = await redis.info("memory")
   used_memory_mb = info["used_memory"] / 1024 / 1024
   memory_percent = (used_memory_mb / 256) * 100
   ```

2. **Cache Hit Rate**:
   ```python
   stats = await redis.info("stats")
   hits = stats["keyspace_hits"]
   misses = stats["keyspace_misses"]
   hit_rate = hits / (hits + misses) if (hits + misses) > 0 else 0
   ```

3. **Key Count by Prefix**:
   ```python
   # Count browser slots
   cursor = 0
   count = 0
   while True:
       cursor, keys = await redis.scan(cursor, match="browser_slots:*", count=1000)
       count += len(keys)
       if cursor == 0:
           break
   ```

4. **Average TTL**:
   ```python
   # Sample keys and check TTL
   keys = await redis.randomkey()  # Sample random keys
   ttl = await redis.ttl(key)
   ```

### Health Check Query
```python
@app.get("/health/redis")
async def redis_health():
    try:
        # Ping Redis
        await redis.ping()
        
        # Get memory info
        info = await redis.info("memory")
        used_mb = info["used_memory"] / 1024 / 1024
        
        # Get cache stats
        stats = await redis.info("stats")
        hits = stats.get("keyspace_hits", 0)
        misses = stats.get("keyspace_misses", 0)
        total = hits + misses
        hit_rate = (hits / total * 100) if total > 0 else 0
        
        return {
            "status": "healthy",
            "memory_used_mb": round(used_mb, 2),
            "memory_percent": round((used_mb / 256) * 100, 2),
            "cache_hit_rate": round(hit_rate, 2),
            "total_requests": total
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }
```

---

## Migration from In-Memory

### Phase 1: Browser Slots (Week 1)
1. Deploy Redis-backed browser slot service
2. Run in parallel with memory-based (both incremented)
3. Compare counts for accuracy
4. Switch to Redis-only after 48 hours validation

### Phase 2: Database Caching (Week 2)
1. Add cache layer to `get_user_tier()` calls
2. Monitor cache hit rate (target 80%+)
3. Expand to quiz metadata caching
4. Remove direct database calls where cached

### Phase 3: Session Management (Week 3)
1. Implement Redis session storage
2. Migrate existing JWT-only auth to Redis sessions
3. Add logout-all-devices functionality
4. Monitor for session-related issues

---

## Summary

### Key Patterns
- **Browser Slots**: String counters with atomic INCR/DECR
- **Browser Sessions**: Hash structures with session metadata
- **Database Cache**: JSON strings with Pydantic models
- **User Sessions**: Hash + Set for multi-device tracking
- **Rate Limiting**: String counters with TTL windows

### Memory Efficiency
- **3 KB per active user** (with typical usage)
- **256 MB handles 50,000+ concurrent users**
- **Aggressive TTLs** prevent memory bloat
- **LRU eviction** as safety net

### Performance
- **<1ms** for simple operations (GET, SET, INCR)
- **1-2ms** for complex operations (Hash, Set operations)
- **50-200x faster** than database queries
- **80%+ cache hit rate** expected

---

**Document Version**: 1.0  
**Last Updated**: 2025-10-22  
**Next**: Service contracts in `contracts/` directory
