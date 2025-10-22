# Quizify Scaling Strategy

## Current Architecture (v1.0 - Single Instance)

### Deployment Overview
- **Platform**: Railway (single instance)
- **Architecture**: Monolithic FastAPI application
- **State Management**: In-memory (Python dictionaries)
- **Database**: Supabase PostgreSQL (shared across all deployments)

### Current Capacity

| Metric | Current Limit | Bottleneck |
|--------|--------------|------------|
| **Concurrent Users** | 3-5 users | Browser slot management |
| **Daily Active Users** | 50-100 users | Database queries + browser slots |
| **Browser Instances** | 3 per user | In-memory tracking |
| **Database Queries** | 50-200ms each | No caching layer |
| **Horizontal Scaling** | ❌ Not supported | In-memory state |

### Stateful Operations (Requiring Coordination)

1. **Browser Slot Management**
   - Tracks active browser instances per user
   - Enforces 3 concurrent browser limit per user
   - Current: In-memory dictionary `_active_browsers = defaultdict(int)`
   - Location: `services/web_scraping_service.py`

2. **User Quota Tracking**
   - Validates quiz generation limits (5/20/unlimited per tier)
   - Current: Direct database queries on every request
   - Location: `services/db_services/supabase_quiz.py::get_user_tier_info()`

3. **Session Management**
   - JWT token validation via Supabase
   - Stateless tokens (no server-side session tracking)
   - Current: No session invalidation capability

### Architecture Constraints

#### ✅ What Works Well
- Simple deployment and maintenance
- Sufficient for MVP and early users (5-50 users)
- No distributed system complexity
- Low operational overhead

#### ❌ Current Limitations
- **Cannot scale horizontally**: In-memory state lost across instances
- **Single point of failure**: If instance crashes, service is down
- **No caching**: Every request hits database (50-200ms latency)
- **Resource conflicts**: Multiple instances would exceed browser limits
- **No coordination**: Instances can't share state or enforce global limits

## Scaling Decision Points

### When to Scale Vertically (Add More Resources to Single Instance)

**Triggers:**
- 10-30 concurrent users
- CPU usage consistently > 60%
- Memory usage > 70%
- Response times > 2 seconds

**How:**
- Increase Railway instance size (more CPU/RAM)
- Optimize database queries (add indexes)
- Implement basic in-memory caching (LRU cache)

**Cost:** ~$10-20/month for larger instance

**Limitations:**
- Still single point of failure
- Physical limits on single machine capacity
- No redundancy or high availability

---

### When to Scale Horizontally (Add Multiple Instances + Redis)

**Triggers:**
- > 50 concurrent users
- > 100 daily active users
- Need for high availability (99.9% uptime)
- Geographic distribution requirements
- Instance failures causing service disruptions

**Requirements:**
- Redis for shared state management (~$5/month)
- Load balancer (Railway provides automatically)
- Distributed coordination strategy

**Benefits:**
- 50-100+ concurrent users capacity
- High availability (instance failures don't affect service)
- Geographic redundancy
- Dynamic scaling (add/remove instances as needed)

**Implementation Complexity:** High (requires architecture changes)

---

## Vertical Scaling Strategy (Short-Term)

### Phase 1: Optimize Current Architecture (No Redis)

#### 1.1 Database Query Optimization
```python
# Add simple in-memory caching for user tier info
from functools import lru_cache
from datetime import datetime, timedelta

_tier_cache = {}
_cache_ttl = timedelta(minutes=5)

def get_user_tier_info_cached(user_id: str):
    """Cached user tier lookup (5 minute TTL)"""
    cache_key = f"tier:{user_id}"
    
    # Check cache
    if cache_key in _tier_cache:
        cached_data, cached_time = _tier_cache[cache_key]
        if datetime.now() - cached_time < _cache_ttl:
            return cached_data
    
    # Cache miss - fetch from DB
    tier_info = get_user_tier_info(user_id)
    _tier_cache[cache_key] = (tier_info, datetime.now())
    
    return tier_info
```

**Impact:** Reduces database calls by ~90%, improves response time to 1-5ms

#### 1.2 Browser Resource Management
```python
# Increase browser limit and add timeout-based cleanup
MAX_CONCURRENT_BROWSERS = 5  # Increased from 3
BROWSER_TIMEOUT = 300  # 5 minutes

# Add periodic cleanup for hung browsers
import asyncio
from datetime import datetime

_browser_timestamps = {}

async def _cleanup_hung_browsers():
    """Remove browser slots that have been held too long"""
    while True:
        await asyncio.sleep(60)  # Check every minute
        now = datetime.now()
        
        async with _browser_lock:
            for user_id, timestamp in list(_browser_timestamps.items()):
                if (now - timestamp).seconds > BROWSER_TIMEOUT:
                    if user_id in _active_browsers:
                        _active_browsers[user_id] = max(0, _active_browsers[user_id] - 1)
                    del _browser_timestamps[user_id]
```

**Impact:** Prevents browser slot leaks, supports 5 concurrent browsers per user

#### 1.3 Connection Pooling
```python
# Optimize Supabase connection usage
# Ensure proper connection cleanup in all operations
```

**Expected Results:**
- Support 10-15 concurrent users (3x improvement)
- Support 150-200 daily active users (2x improvement)
- Response times: 100-500ms (2x improvement)

**Cost:** $0 (optimization only)
**Timeline:** 1-2 days implementation

---

## Horizontal Scaling Strategy (Long-Term)

### Phase 2: Redis Integration for Distributed State

**When:** > 50 concurrent users or high availability required

#### 2.1 Redis Setup
```bash
# Add Redis to Railway project
railway add redis  # ~$5/month

# Environment variables automatically added:
# REDIS_URL=redis://default:password@host:port
```

#### 2.2 Shared State Implementation

**Browser Slot Management:**
```python
import redis.asyncio as redis

class RedisBrowserManager:
    async def acquire_slot(self, user_id: str) -> bool:
        """Acquire browser slot globally across all instances"""
        key = f"browser_slots:{user_id}"
        current = await redis_client.get(key) or 0
        
        if int(current) >= MAX_CONCURRENT_BROWSERS:
            return False  # Limit reached
        
        # Atomic increment with expiration
        await redis_client.incr(key)
        await redis_client.expire(key, 300)  # 5 min TTL
        return True
    
    async def release_slot(self, user_id: str):
        """Release browser slot"""
        key = f"browser_slots:{user_id}"
        await redis_client.decr(key)
```

**User Quota Caching:**
```python
async def get_user_tier_info_redis(user_id: str):
    """Cache user tier in Redis (5 minute TTL)"""
    cache_key = f"user_tier:{user_id}"
    
    # Try cache
    cached = await redis_client.get(cache_key)
    if cached:
        return json.loads(cached)
    
    # Cache miss
    tier_info = get_user_tier_info(user_id)
    await redis_client.setex(cache_key, 300, json.dumps(tier_info))
    
    return tier_info
```

**Expected Results:**
- Support 50-100+ concurrent users
- Support 1,000-5,000+ daily active users
- Response times: 1-5ms (cached), 50-200ms (cache miss)
- High availability (instance failures transparent)
- Perfect coordination across instances

**Cost:** ~$5/month for Redis
**Timeline:** 2-3 days implementation

---

## Scaling Comparison

| Aspect | Current (Single Instance) | Vertical Scaling | Horizontal Scaling + Redis |
|--------|--------------------------|------------------|---------------------------|
| **Concurrent Users** | 3-5 | 10-15 | 50-100+ |
| **Daily Users** | 50-100 | 150-200 | 1,000-5,000+ |
| **Database Response** | 50-200ms | 50-200ms | 1-5ms (cached) |
| **Availability** | Single point of failure | Single point of failure | High availability |
| **Scaling** | Manual instance resize | Manual instance resize | Auto-scaling |
| **Cost/Month** | $5-10 | $10-20 | $15-25 |
| **Complexity** | Low | Low | Medium-High |
| **Implementation** | Current | 1-2 days | 2-3 days |

---

## Decision Matrix

### Stay on Single Instance If:
- ✅ < 50 daily active users
- ✅ < 10 concurrent users
- ✅ Acceptable to have brief downtime for deployments
- ✅ Cost optimization is priority
- ✅ Simple architecture preferred

### Implement Vertical Scaling If:
- ✅ 50-100 daily active users
- ✅ 10-20 concurrent users
- ✅ Need better performance without complexity
- ✅ Can tolerate single point of failure
- ✅ Budget < $20/month

### Implement Horizontal Scaling + Redis If:
- ✅ > 100 daily active users
- ✅ > 20 concurrent users
- ✅ High availability required (99.9% uptime)
- ✅ Geographic distribution needed
- ✅ Budget allows $20-30/month
- ✅ Can handle distributed system complexity

---

## Monitoring & Triggers

### Key Metrics to Track

```python
# Add to application monitoring
metrics = {
    "concurrent_users": gauge,
    "active_browser_slots": gauge,
    "database_query_time": histogram,
    "cache_hit_rate": gauge,
    "request_response_time": histogram,
}
```

### Alert Thresholds

| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| Concurrent users | 8 | 10 | Consider vertical scaling |
| Browser slots used | 70% | 90% | Increase browser limit |
| Avg response time | 1s | 2s | Optimize or scale |
| Database query time | 200ms | 500ms | Add caching |
| Error rate | 1% | 5% | Investigate bottleneck |

---

## Next Steps

### Immediate (Current Sprint)
1. ✅ Document current architecture
2. ⏳ Add basic monitoring (response times, error rates)
3. ⏳ Implement simple in-memory caching for user tier info

### Short-Term (1-2 months)
1. Monitor growth metrics
2. Implement vertical scaling optimizations if needed
3. Prepare Redis integration plan

### Long-Term (3-6 months)
1. Implement Redis when triggers are met
2. Add horizontal scaling capability
3. Implement auto-scaling policies

---

## References
- [Current Capacity Analysis](./CURRENT_CAPACITY_ANALYSIS.md)
- [Redis Architecture Guide](./REDIS_ARCHITECTURE_GUIDE.md)
- [Redis Complete Architecture](./REDIS_COMPLETE_ARCHITECTURE.md)
