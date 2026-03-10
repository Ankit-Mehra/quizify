# Redis Caching & Browser Slot Management Testing Guide

## 🎯 What You Should See

### **Database Caching (Epic 3)**
- **First query**: 50-200ms (database hit)
- **Cached query**: 1-5ms (Redis hit)
- **Improvement**: **~50x faster** ⚡

### **Browser Slot Management (Epic 2)**
- **Distributed coordination**: Multiple instances can share browser slots
- **User isolation**: Each user gets max 3 concurrent browsers
- **Automatic cleanup**: Slots released after 5 minutes

---

## 📋 Quick Start - 5 Ways to Verify Caching

### **Method 1: Redis CLI via Docker (Simplest)**
```bash
# Check if Redis is running
docker exec -it quizify-redis redis-cli ping
# Should return: PONG

# See all cache keys
docker exec -it quizify-redis redis-cli KEYS '*'

# Count keys by type
docker exec -it quizify-redis redis-cli KEYS 'user_tier:*' | wc -l
docker exec -it quizify-redis redis-cli KEYS 'quiz_metadata:*' | wc -l
docker exec -it quizify-redis redis-cli KEYS 'browser:*' | wc -l

# Watch Redis in real-time
docker exec -it quizify-redis redis-cli MONITOR
# Then make API requests and watch keys appear!

# 💡 TIP: Use aliases for shorter commands:
source scripts/redis_aliases.sh
redis-ping  # Now you can use simple commands!
```

### **Method 2: Monitoring Script (Recommended)**
```bash
# One-time check
./scripts/monitor_redis.sh

# Continuous monitoring
./scripts/monitor_redis.sh watch
```

**Expected Output:**
```
🔍 REDIS CACHE MONITOR - Quizify
✅ Redis is running

📦 Total Keys in Redis: 5

🔑 Cache Keys by Type:
1️⃣ User Tier Cache (user_tier:*):
   Count: 2 keys
   • user_tier:550e8400-e29b-... (TTL: 245s)

2️⃣ Quiz Metadata Cache (quiz_metadata:*):
   Count: 3 keys
   • quiz_metadata:123abc...:user456... (TTL: 1654s)
```

### **Method 3: Python Test Script**
```bash
# Make sure Redis is running
redis-server --daemonize yes

# Run comprehensive cache test
REDIS_ENABLED=true python3 scripts/test_redis_caching.py
```

**Expected Output:**
```
🧪 TEST 1: User Tier Info Caching
1️⃣ FIRST CALL (Cache Miss - Database Query):
   ✅ Response time: 187.45ms

2️⃣ SECOND CALL (Cache Hit - From Redis):
   ✅ Response time: 3.21ms

📈 PERFORMANCE IMPROVEMENT:
   • First call (database):  187.45ms
   • Second call (cached):   3.21ms
   • Speedup:                58.4x faster ⚡
   ✅ EXCELLENT! Cache is working as expected
```

### **Method 4: API Testing with curl**
```bash
# Start your FastAPI server
REDIS_ENABLED=true uvicorn main:app --reload

# In another terminal, test with timing
time curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  http://localhost:8000/api/endpoint

# First call:  ~200ms (database)
# Second call: ~5ms (cached)
```

### **Method 5: Redis Desktop Manager (GUI)**
- Download: https://redis.com/redis-enterprise/redis-insight/
- Connect to: `localhost:6379`
- Visual key browser with TTL display
- Real-time monitoring graphs

---

## 🧪 Step-by-Step Testing Instructions

### **Step 1: Start Redis**
```bash
# Start Redis server
redis-server --daemonize yes

# Verify it's running
redis-cli ping
# Should return: PONG
```

### **Step 2: Clear Existing Cache (Optional)**
```bash
# Flush all keys to start fresh
redis-cli FLUSHDB

# Verify empty
redis-cli DBSIZE
# Should return: (integer) 0
```

### **Step 3: Start Your API Server**
```bash
# In terminal 1: Start server with Redis enabled
REDIS_ENABLED=true REDIS_URL=redis://localhost:6379 \
  uvicorn main:app --reload --port 8000
```

### **Step 4: Monitor Redis (Real-Time)**
```bash
# In terminal 2: Watch Redis activity
redis-cli MONITOR

# You'll see commands like:
# "SET" "user_tier:550e8400..." "..."
# "GET" "user_tier:550e8400..."
# "SCAN" "0" "MATCH" "quiz_metadata:*"
```

### **Step 5: Make API Requests**
```bash
# In terminal 3: Test user tier caching
# First request (database hit)
time curl -X GET "http://localhost:8000/api/user/tier-info" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# Second request (cache hit) - should be MUCH faster
time curl -X GET "http://localhost:8000/api/user/tier-info" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### **Step 6: Verify in Redis**
```bash
# Check what got cached
redis-cli KEYS '*'

# Get a specific cached value
redis-cli GET "user_tier:YOUR_USER_ID"

# Check TTL (time until expiration)
redis-cli TTL "user_tier:YOUR_USER_ID"
# Returns seconds remaining (300 = 5 minutes)
```

---

## 📊 What to Look For - Cache Working Indicators

### ✅ **Signs Caching is Working:**
1. **Speed Improvement**
   - First request: 50-200ms
   - Subsequent requests: 1-10ms
   - **Minimum 10x improvement**

2. **Redis Keys Present**
   ```bash
   redis-cli KEYS 'user_tier:*'
   # Should return: user_tier:<user_id>
   
   redis-cli KEYS 'quiz_metadata:*'
   # Should return: quiz_metadata:<quiz_id>:<user_id>
   ```

3. **Cache Statistics**
   ```python
   from services.redis import get_cache_service
   cache = get_cache_service(prefix="user_tier")
   stats = cache.get_stats()
   
   # Should show:
   # - redis_cache_hits > 0
   # - redis_hit_rate > 0.5 (50%)
   ```

4. **TTL Countdown**
   ```bash
   # Check same key twice, 10 seconds apart
   redis-cli TTL "user_tier:YOUR_ID"  # Returns: 295
   # Wait 10 seconds
   redis-cli TTL "user_tier:YOUR_ID"  # Returns: 285
   ```

### ⚠️ **Signs Caching is NOT Working:**
1. No speed improvement between requests
2. No keys in Redis (`redis-cli KEYS '*'` returns empty)
3. Server logs show "Using memory fallback" messages
4. Environment variable `REDIS_ENABLED=false` or not set

---

## 🔧 Troubleshooting

### **Problem: No cache keys in Redis**
```bash
# Check Redis connection
redis-cli ping
# Should return: PONG

# Check environment variables
echo $REDIS_ENABLED  # Should be: true
echo $REDIS_URL      # Should be: redis://localhost:6379

# Check server logs for errors
grep -i redis logs/app.log
```

### **Problem: Speed not improving**
```bash
# Verify cache is actually being used
redis-cli MONITOR
# Make a request and watch for GET/SET commands

# Check if fallback to memory
grep "memory fallback" logs/app.log

# Verify cache service is initialized
python3 -c "from services.redis import get_cache_service; print(get_cache_service())"
```

### **Problem: Browser slots not coordinating**
```bash
# Check browser slot keys
redis-cli KEYS 'browser:slot:*'

# Check user browser counts
redis-cli KEYS 'browser:user:*'

# Get current slot value
redis-cli GET 'browser:slot:global'
```

---

## 📈 Performance Benchmarking

### **Benchmark Script**
```bash
# Run 100 requests and measure average time
for i in {1..100}; do
  time curl -s "http://localhost:8000/api/user/tier-info" \
    -H "Authorization: Bearer TOKEN" > /dev/null
done 2>&1 | grep real | awk '{sum += $2; count++} END {print "Average:", sum/count}'
```

### **Expected Results:**
| Metric | Without Cache | With Cache | Improvement |
|--------|--------------|------------|-------------|
| First Request | 150-200ms | 150-200ms | - |
| Subsequent | 150-200ms | 3-5ms | **~50x** |
| Database Load | 100% | 2% | **98% reduction** |
| Throughput | ~20 req/s | ~200 req/s | **10x increase** |

---

## 🎓 Advanced Verification

### **Check Cache Hit Rate**
```python
from services.redis import get_cache_service

# User tier cache stats
user_cache = get_cache_service(prefix="user_tier")
user_stats = user_cache.get_stats()
print(f"Hit Rate: {user_stats['redis_hit_rate']:.1%}")
print(f"Total Hits: {user_stats['redis_cache_hits']}")
print(f"Total Misses: {user_stats['redis_cache_misses']}")

# Quiz metadata cache stats
quiz_cache = get_cache_service(prefix="quiz_metadata")
quiz_stats = quiz_cache.get_stats()
print(f"Hit Rate: {quiz_stats['redis_hit_rate']:.1%}")
```

### **Manual Cache Testing**
```python
import asyncio
from services.db_services.supabase_quiz import (
    get_user_tier_info_cached,
    invalidate_user_tier_cache
)

async def test():
    user_id = "YOUR_USER_ID"
    
    # Clear cache
    await invalidate_user_tier_cache(user_id)
    
    # First call (miss)
    import time
    start = time.time()
    data1 = await get_user_tier_info_cached(user_id)
    time1 = time.time() - start
    
    # Second call (hit)
    start = time.time()
    data2 = await get_user_tier_info_cached(user_id)
    time2 = time.time() - start
    
    print(f"Miss: {time1*1000:.2f}ms")
    print(f"Hit:  {time2*1000:.2f}ms")
    print(f"Speedup: {time1/time2:.1f}x")

asyncio.run(test())
```

---

## 🚀 Quick Validation Checklist

Run these commands to verify everything works:

```bash
# 1. Redis is running
redis-cli ping && echo "✅ Redis OK" || echo "❌ Redis NOT running"

# 2. Cache keys exist (after making requests)
[ $(redis-cli DBSIZE) -gt 0 ] && echo "✅ Cache populated" || echo "⚠️  Cache empty"

# 3. Environment configured
[ "$REDIS_ENABLED" = "true" ] && echo "✅ Redis enabled" || echo "❌ Redis disabled"

# 4. Monitor script works
./scripts/monitor_redis.sh | head -10

# 5. Keys have TTL
redis-cli --scan --pattern "user_tier:*" | head -1 | xargs redis-cli TTL | 
  awk '{if($1>0) print "✅ TTL active:" $1"s"; else print "❌ No TTL"}'
```

**All checks should show ✅**

---

## 📞 Support

If you're still not seeing cache improvements:
1. Check server logs: `tail -f logs/app.log | grep -i redis`
2. Verify Redis config: `redis-cli CONFIG GET maxmemory`
3. Test basic operations: `redis-cli SET test "hello" && redis-cli GET test`
4. Review error messages in FastAPI startup logs

**Expected logs on successful cache:**
```
INFO: Redis caching enabled
DEBUG: Cache HIT (Redis): user_tier:550e8400...
DEBUG: Cache SET (Redis): quiz_metadata:123abc... [TTL=1800s]
```
