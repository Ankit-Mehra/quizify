# ✅ Redis Setup Complete - Next Steps

## 🎉 What's Working

You have Redis running in Docker:
- Container: `quizify-redis`
- Port: `6379:6379`
- Status: ✅ Running (verified with `docker exec -it quizify-redis redis-cli ping`)
- Memory: 1.09M used
- Uptime: 2+ minutes

## 🚀 How to Test Cache Performance

### **Quickest Test (30 seconds)**

```bash
# Terminal 1: Watch Redis activity
docker exec -it quizify-redis redis-cli MONITOR

# Terminal 2: Start your API
REDIS_ENABLED=true REDIS_URL=redis://localhost:6379 uvicorn main:app --reload

# Terminal 3: Make API request (use Postman or curl)
curl -X GET "http://localhost:8000/api/user/tier-info" \
  -H "Authorization: Bearer YOUR_JWT"

# Go back to Terminal 1 - you should see:
# "SET" "user_tier:..." "..." "EX" "300"
```

**If you see SET commands appear → Caching is working! ✅**

---

## 📋 Testing Checklist

### ✅ Basic Verification
```bash
# 1. Redis is running
docker exec -it quizify-redis redis-cli ping
# Expected: PONG

# 2. Redis is empty (fresh state)
docker exec -it quizify-redis redis-cli DBSIZE
# Expected: (integer) 0

# 3. Use monitoring script
./scripts/monitor_redis.sh
# Expected: Shows "✅ Redis is running" and stats
```

### ✅ Performance Testing
```bash
# 1. Clear cache
docker exec -it quizify-redis redis-cli FLUSHDB

# 2. Run Python test (after setting real user_id)
REDIS_ENABLED=true python3 scripts/test_redis_caching.py
# Expected: First call ~150ms, second call ~5ms, 30-50x speedup

# 3. Check cache was created
docker exec -it quizify-redis redis-cli KEYS '*'
# Expected: Shows user_tier:* and quiz_metadata:* keys
```

---

## 🛠️ Tools You Have

### 1. **Monitor Script** (`./scripts/monitor_redis.sh`)
**What it does:**
- Shows total keys in Redis
- Counts keys by type (user_tier, quiz_metadata, browser)
- Displays memory usage
- Shows cache statistics
- Auto-detects Docker setup

**When to use:** Quick health check of Redis cache

---

### 2. **Python Test Script** (`scripts/test_redis_caching.py`)
**What it does:**
- Tests user tier caching (database vs cache speed)
- Tests quiz metadata caching
- Measures actual performance improvement
- Shows cache hit/miss statistics
- Inspects Redis keys directly

**When to use:** Prove caching works with real timing data

**Note:** Update line ~30 with a real `user_id` from your database before running

---

### 3. **Redis Aliases** (`scripts/redis_aliases.sh`)
**What it does:**
- Creates short commands like `redis-ping`, `redis-keys`, `redis-monitor`
- Saves typing `docker exec -it quizify-redis redis-cli` every time

**How to use:**
```bash
source scripts/redis_aliases.sh
# Now use: redis-ping, redis-keys, redis-monitor, etc.
```

---

### 4. **Documentation**
| File | Purpose |
|------|---------|
| `docs/redis/REDIS_QUICK_REFERENCE.md` | Quick command reference |
| `docs/redis/DOCKER_REDIS_COMMANDS.md` | All Docker Redis commands |
| `docs/redis/CACHE_TESTING_GUIDE.md` | Complete testing guide |
| `docs/redis/REDIS_INTEGRATION_STATUS.md` | Implementation details |

---

## 🎯 What to Expect

### Performance Improvement
| Metric | Without Cache | With Cache | Improvement |
|--------|--------------|------------|-------------|
| User tier query | 150-200ms | 2-5ms | **50x faster** |
| Quiz metadata | 150-200ms | 2-5ms | **50x faster** |
| Database load | 100% | ~2% | **98% reduction** |

### Redis Cache Keys
After making API requests, you should see:
```bash
$ docker exec -it quizify-redis redis-cli KEYS '*'
1) "user_tier:550e8400-e29b-41d4-a716-446655440000"
2) "quiz_metadata:123abc...:user456..."
3) "browser:slot:global"
4) "browser:user:550e8400..."
```

### Cache TTLs (Time to Live)
- **User tier cache**: 300 seconds (5 minutes)
- **Quiz metadata cache**: 1800 seconds (30 minutes)
- **Browser slots**: 300 seconds (5 minutes)

---

## 🔍 How to Verify Caching Works

### Method 1: Visual Confirmation (MONITOR)
```bash
# Start monitoring
docker exec -it quizify-redis redis-cli MONITOR

# Make API request
# You should see output like:
1699123456.789 [0 172.18.0.1:12345] "SET" "user_tier:..." "..." "EX" "300"

# Make same request again
# You should see:
1699123457.123 [0 172.18.0.1:12345] "GET" "user_tier:..."
```

**SET = Cache miss (slow, database query)**  
**GET = Cache hit (fast, from Redis)**

---

### Method 2: Performance Timing
```bash
# First request (cache miss)
time curl -X GET "http://localhost:8000/api/user/tier-info" \
  -H "Authorization: Bearer TOKEN"
# Should take: ~150-200ms

# Second request (cache hit)
time curl -X GET "http://localhost:8000/api/user/tier-info" \
  -H "Authorization: Bearer TOKEN"
# Should take: ~2-5ms (50x faster!)
```

---

### Method 3: Key Inspection
```bash
# Before request - empty
docker exec -it quizify-redis redis-cli DBSIZE
# Returns: 0

# After request - populated
docker exec -it quizify-redis redis-cli DBSIZE
# Returns: 1 (or more)

# See what got cached
docker exec -it quizify-redis redis-cli KEYS '*'
# Returns: user_tier:550e8400...

# Check TTL (countdown timer)
docker exec -it quizify-redis redis-cli TTL "user_tier:550e8400..."
# Returns: 295 (seconds until expiration)
```

---

## 🚨 Common Issues & Solutions

### Issue: No keys appearing in Redis
**Check:**
1. Is `REDIS_ENABLED=true` set?
   ```bash
   echo $REDIS_ENABLED
   ```
2. Is API using Redis URL correctly?
   ```bash
   echo $REDIS_URL  # Should be: redis://localhost:6379
   ```
3. Are you calling the **cached** functions?
   - ✅ `get_user_tier_info_cached()`
   - ❌ `get_user_tier_info()` (old sync version)

---

### Issue: Performance not improving
**Verify cache is being used:**
```bash
# 1. Monitor shows GET commands
docker exec -it quizify-redis redis-cli MONITOR

# 2. Cache stats show hits
python3 -c "
from services.redis import get_cache_service
cache = get_cache_service(prefix='user_tier')
print(cache.get_stats())
"
```

---

### Issue: Redis connection refused
**Check Docker:**
```bash
# Is container running?
docker ps | grep redis

# Check logs
docker logs quizify-redis

# Restart if needed
docker-compose restart redis
```

---

## 💡 Pro Tips

### 1. Watch cache grow in real-time
```bash
watch -n 1 'docker exec -i quizify-redis redis-cli DBSIZE'
```

### 2. Clear cache for fresh testing
```bash
docker exec -it quizify-redis redis-cli FLUSHDB
```

### 3. Check memory usage
```bash
docker exec -it quizify-redis redis-cli INFO memory | grep used_memory_human
```

### 4. Export cache statistics
```python
from services.redis import get_cache_service

user_cache = get_cache_service(prefix="user_tier")
quiz_cache = get_cache_service(prefix="quiz_metadata")

print(f"User Cache Hit Rate: {user_cache.get_stats()['redis_hit_rate']:.1%}")
print(f"Quiz Cache Hit Rate: {quiz_cache.get_stats()['redis_hit_rate']:.1%}")
```

---

## 📊 Expected Timeline

### Phase 1: Basic Verification (5 minutes)
1. ✅ Redis running: `docker exec -it quizify-redis redis-cli ping`
2. ✅ Monitoring works: `./scripts/monitor_redis.sh`
3. ✅ Can view keys: `docker exec -it quizify-redis redis-cli KEYS '*'`

### Phase 2: Functional Testing (10 minutes)
1. Start API with Redis enabled
2. Make API requests
3. Verify keys appear in Redis
4. Check TTL countdown

### Phase 3: Performance Testing (10 minutes)
1. Clear cache: `redis-cli FLUSHDB`
2. Measure first request (slow)
3. Measure second request (fast)
4. Calculate speedup (~50x expected)

### Phase 4: Production Validation (ongoing)
1. Monitor cache hit rate over time
2. Verify browser slot coordination
3. Check database load reduction
4. Monitor memory usage

---

## ✅ Success Criteria

You'll know caching is working when:

1. ✅ **MONITOR shows activity**
   - You see `SET` commands on first request
   - You see `GET` commands on subsequent requests

2. ✅ **Performance improves dramatically**
   - First call: 150-200ms
   - Second call: 2-5ms
   - Improvement: 30-50x faster

3. ✅ **Keys persist with correct TTL**
   - Keys visible in Redis: `KEYS '*'`
   - TTL counts down: `TTL "key"` shows decreasing numbers
   - User tier: 300s max
   - Quiz metadata: 1800s max

4. ✅ **Cache statistics show hits**
   - Hit rate > 50% after warm-up
   - Cache hits increasing over time
   - Cache misses only on first access

---

## 🎓 Next Steps

1. **Run basic verification** (5 min)
   ```bash
   docker exec -it quizify-redis redis-cli ping
   ./scripts/monitor_redis.sh
   ```

2. **Start your API** (1 min)
   ```bash
   REDIS_ENABLED=true uvicorn main:app --reload
   ```

3. **Make test requests** (5 min)
   - Use Postman collections in `postman/`
   - Or use curl with your JWT token

4. **Watch cache populate** (5 min)
   ```bash
   docker exec -it quizify-redis redis-cli MONITOR
   # Make requests, watch keys appear
   ```

5. **Measure performance** (10 min)
   - Update `scripts/test_redis_caching.py` with real user_id
   - Run: `REDIS_ENABLED=true python3 scripts/test_redis_caching.py`
   - Verify 30-50x speedup

---

## 📞 Need Help?

If you're stuck:
1. Check Redis logs: `docker logs quizify-redis -f`
2. Verify environment: `env | grep REDIS`
3. Test basic operations: `docker exec -it quizify-redis redis-cli SET test "hello"`
4. Review documentation in `docs/redis/`

**Key files:**
- `docs/redis/REDIS_QUICK_REFERENCE.md` - Command cheat sheet
- `docs/redis/DOCKER_REDIS_COMMANDS.md` - All Docker commands
- `docs/redis/CACHE_TESTING_GUIDE.md` - Complete testing walkthrough
