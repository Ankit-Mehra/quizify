# Redis Testing in Production - Postman Guide

## 📦 What You Have

Two comprehensive Postman collections for testing Redis functionality in production:

### 1. **Redis Cache Testing** (`Quizify_Redis_Cache_Testing.postman_collection.json`)
Tests database caching performance (50x improvement)

### 2. **Browser Slot Management** (`Quizify_Browser_Slot_Management.postman_collection.json`)
Tests distributed browser slot coordination (3 slots per user)

---

## 🚀 Quick Start (5 Minutes)

### Step 1: Import Collections into Postman

1. Open Postman Desktop
2. Click **Import** (top left)
3. Drag and drop these files:
   - `Quizify_Redis_Cache_Testing.postman_collection.json`
   - `Quizify_Browser_Slot_Management.postman_collection.json`
   - `Quizify_Production.postman_environment.json`

### Step 2: Configure Production Environment

1. In Postman, select **Environments** (left sidebar)
2. Select **Quizify Production**
3. Set these variables:

| Variable | Value | How to Get |
|----------|-------|------------|
| `base_url` | `https://your-app.railway.app` | Your Railway deployment URL |
| `auth_token` | `eyJhbGc...` | Login via API, copy JWT token |
| `auth_token_user1` | `eyJhbGc...` | JWT for User A (for browser tests) |
| `auth_token_user2` | `eyJhbGc...` | JWT for User B (for browser tests) |
| `quiz_id` | `550e8400-...` | ID of an existing quiz in your DB |
| `user_id` | `550e8400-...` | Your user ID from database |
| `test_url` | `https://en.wikipedia.org/wiki/Python_(programming_language)` | Already set (Wikipedia article) |

**To get JWT tokens:**
```bash
# Use existing Auth collection or curl:
curl -X POST "https://your-app.railway.app/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "password"}'

# Copy the "access_token" from response
```

### Step 3: Run Tests

#### Option A: Run Redis Cache Tests
1. Select **Quizify - Redis Cache Testing** collection
2. Click **Run** (or Ctrl/Cmd + R)
3. In Collection Runner:
   - Select **Quizify Production** environment
   - Check **Save responses**
   - Click **Run Quizify - Redis Cache Testing**

**Expected Results:**
```
✅ Health Check - Redis Status          PASS (200 OK)
✅ User Tier Info (CACHE MISS)          PASS (50-200ms)
✅ User Tier Info (CACHE HIT)           PASS (2-5ms, 50x faster!)
✅ Get Quiz (CACHE MISS)                PASS (50-200ms)
✅ Get Quiz (CACHE HIT)                 PASS (2-5ms, 50x faster!)
✅ Final Performance Report             PASS

📊 Average Speedup: 40-50x faster
```

#### Option B: Run Browser Slot Tests
1. Select **Quizify - Browser Slot Management** collection
2. Click **Run**
3. In Collection Runner:
   - Select **Quizify Production** environment
   - Check **Save responses**
   - Click **Run Quizify - Browser Slot Management**

**Expected Results:**
```
✅ Redis Health Check                   PASS
✅ User A - Slot 1                      PASS (acquired)
✅ User A - Slot 2                      PASS (acquired)
✅ User A - Slot 3                      PASS (acquired, at limit)
❌ User A - Slot 4                      HTTP 429 (quota exceeded, expected!)
✅ User B - Slot 1                      PASS (independent quota)
```

---

## 📊 Test Scenarios Explained

### Collection 1: Redis Cache Testing

#### **Scenario: User Tier Caching (5 min TTL)**

**Request 1 - Cache Miss:**
- Endpoint: `GET /api/user/tier-info`
- Expected: 50-200ms (hits database)
- Redis: `SET user_tier:<user_id> "..." EX 300`

**Request 2 - Cache Hit:**
- Endpoint: `GET /api/user/tier-info` (same)
- Expected: 2-5ms (from Redis, 50x faster!)
- Redis: `GET user_tier:<user_id>`

**Console Output:**
```
🔴 CACHE MISS - First Call: 187ms
🟢 CACHE HIT - Second Call: 4ms
📈 Performance improvement: 46.8x faster
✅ EXCELLENT! Cache is working as expected
```

#### **Scenario: Quiz Metadata Caching (30 min TTL)**

Same pattern as user tier, but for quiz metadata.

**Cache Key:** `quiz_metadata:<quiz_id>:<user_id>`  
**TTL:** 1800 seconds (30 minutes)

---

### Collection 2: Browser Slot Management

#### **Scenario 1: Single User Quota**

Tests that one user cannot exceed 3 concurrent browser slots.

1. User A acquires slot 1 → ✅ Success
2. User A acquires slot 2 → ✅ Success
3. User A acquires slot 3 → ✅ Success (at limit)
4. User A attempts slot 4 → ❌ HTTP 429 (quota exceeded)

**Redis Keys Created:**
```
browser:user:<user_a_id> = "3"              # Slot count
browser:slot:<lock_id_1> = {...}            # Slot metadata
browser:slot:<lock_id_2> = {...}
browser:slot:<lock_id_3> = {...}
```

#### **Scenario 2: Multi-User Isolation**

Tests that different users have independent quotas.

**Setup:** User A has 3/3 slots (blocked)  
**Test:** User B acquires slot 1  
**Expected:** ✅ Success (users are isolated)

**Proves:** Browser slots are per-user, not global.

#### **Scenario 3: Automatic Slot Release**

Tests that slots are automatically freed after 5 minutes (TTL).

**Important:** This test requires waiting 5+ minutes between runs.

**Check TTL manually:**
```bash
docker exec -it quizify-redis redis-cli TTL "browser:user:<user_id>"
# Returns: seconds remaining (300 max = 5 minutes)
# If -2: Key expired (slots released)
```

#### **Scenario 4: Production Load Test**

Simulates multiple concurrent users making requests.

**How to run:**
1. In Postman Collection Runner
2. Select "Scenario 4: Production Load Test"
3. Set **Iterations: 10**
4. Set **Delay: 0ms** (concurrent)
5. Click **Run**

**Expected:** Each user independently limited to 3 slots, no race conditions.

---

## 🔍 Manual Verification (Redis CLI)

While tests are running, monitor Redis in real-time:

### **For Cache Testing:**

```bash
# Watch cache activity
docker exec -it quizify-redis redis-cli MONITOR

# You'll see:
"SET" "user_tier:550e8400..." "..." "EX" "300"      # Cache miss
"GET" "user_tier:550e8400..."                        # Cache hit
"SET" "quiz_metadata:123abc..." "..." "EX" "1800"   # Quiz cached
```

```bash
# Check cache keys
docker exec -it quizify-redis redis-cli KEYS 'user_tier:*'
docker exec -it quizify-redis redis-cli KEYS 'quiz_metadata:*'

# Check TTL
docker exec -it quizify-redis redis-cli TTL "user_tier:<user_id>"
# Returns: 245 (seconds remaining, max 300 = 5 min)
```

### **For Browser Slot Testing:**

```bash
# Watch slot operations
docker exec -it quizify-redis redis-cli MONITOR

# You'll see:
"INCR" "browser:user:550e8400..."                    # Slot acquired
"DECR" "browser:user:550e8400..."                    # Slot released
```

```bash
# Check browser slots
docker exec -it quizify-redis redis-cli KEYS 'browser:*'

# Check user slot count
docker exec -it quizify-redis redis-cli GET "browser:user:<user_id>"
# Returns: "2" (current slot count, max 3)

# Check slot TTL
docker exec -it quizify-redis redis-cli TTL "browser:user:<user_id>"
# Returns: 287 (seconds remaining, max 300)
```

---

## 📈 Expected Performance Results

### **Cache Performance (Collection 1)**

| Metric | Without Cache | With Cache | Improvement |
|--------|--------------|------------|-------------|
| User Tier Query | 150-200ms | 2-5ms | **50x faster** |
| Quiz Metadata | 150-200ms | 2-5ms | **50x faster** |
| Database Load | 100% | ~2% | **98% reduction** |

**Success Criteria:**
- ✅ Cache hit response time < 10ms
- ✅ Speedup > 20x
- ✅ Redis MONITOR shows SET then GET

### **Browser Slot Management (Collection 2)**

| Test | Expected Result | Verifies |
|------|----------------|----------|
| User A slots 1-3 | HTTP 200/201 | Slot acquisition works |
| User A slot 4 | HTTP 429 | Quota enforcement (3 max) |
| User B slot 1 | HTTP 200/201 | User isolation |
| After 5 min | HTTP 200/201 | TTL cleanup |

**Success Criteria:**
- ✅ Max 3 slots per user
- ✅ HTTP 429 on 4th slot
- ✅ Independent user quotas
- ✅ Automatic cleanup after 5 min

---

## 🚨 Troubleshooting

### **Problem: Cache tests failing**

**Check 1: Is Redis enabled in production?**
```bash
# Run Health Check request in Postman
# Should return: "redis_enabled": true, "redis_connected": true

# Or check Railway environment variables:
# REDIS_ENABLED=true
# REDIS_URL=redis://...
```

**Check 2: Are you using real user_id/quiz_id?**
```bash
# Update Postman environment with actual IDs from your database
# user_id: From profiles table
# quiz_id: From quizzes table (must be owned by auth_token user)
```

**Check 3: Check server logs**
```bash
# In Railway dashboard, check logs for:
# "Redis caching enabled"
# "Cache HIT (Redis): user_tier:..."
# "Cache SET (Redis): ..."
```

### **Problem: Browser slot tests failing**

**Check 1: Web scraping endpoint exists**
```bash
# Verify endpoint is available:
curl -X POST "https://your-app.railway.app/api/quizzes/web" \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "num_questions": 5}'
```

**Check 2: JWT tokens are valid**
```bash
# Tokens expire after 24 hours
# Get fresh tokens if needed:
curl -X POST "https://your-app.railway.app/api/auth/login" \
  -d '{"email": "user@example.com", "password": "password"}'
```

**Check 3: Redis MONITOR shows INCR/DECR**
```bash
# Should see atomic operations:
docker exec -it quizify-redis redis-cli MONITOR
# Look for: "INCR" "browser:user:..." and "DECR" "browser:user:..."
```

### **Problem: No speedup observed**

**Possible causes:**
1. Cache not enabled: Check `REDIS_ENABLED=true`
2. Using old non-cached functions: Check server code uses `_cached` versions
3. Network latency: Production response times include network overhead
4. First run: Ensure you run each request TWICE (miss then hit)

**Debug steps:**
1. Run Health Check - verify Redis connected
2. Check Redis MONITOR - should show SET then GET
3. Check response times in Postman (bottom right)
4. Try local testing first (lower network latency)

---

## 💡 Pro Tips

### **Tip 1: Use Collection Runner**
Instead of clicking each request individually, use Collection Runner to run all tests sequentially.

### **Tip 2: Save Test Results**
Collection Runner → Check "Save responses" → Export results as JSON

### **Tip 3: Monitor Redis in Real-Time**
Keep a terminal open with `redis-cli MONITOR` while running tests to see Redis activity live.

### **Tip 4: Test Locally First**
Before production testing:
1. Set `base_url` to `http://localhost:8000`
2. Start local server with Redis
3. Run tests locally to verify behavior
4. Then test in production

### **Tip 5: Clear Cache Between Tests**
```bash
# Clear all cache for fresh testing:
docker exec -it quizify-redis redis-cli FLUSHDB

# Clear specific patterns:
docker exec -it quizify-redis redis-cli --scan --pattern "user_tier:*" | \
  xargs docker exec -i quizify-redis redis-cli DEL
```

---

## 📞 Need Help?

### **Quick Diagnostics**

```bash
# 1. Check Redis connection in production
curl https://your-app.railway.app/health/redis

# 2. Check if cache keys exist (after running tests)
docker exec -it quizify-redis redis-cli KEYS '*'

# 3. Check server logs in Railway
# Look for: "Redis caching enabled" on startup

# 4. Test basic Redis operations
docker exec -it quizify-redis redis-cli SET test "hello"
docker exec -it quizify-redis redis-cli GET test
```

### **Common Issues**

| Issue | Solution |
|-------|----------|
| "redis_connected: false" | Check REDIS_URL in Railway env vars |
| "401 Unauthorized" | Get fresh JWT token (expires after 24h) |
| "404 Not Found" | Verify base_url is correct |
| "429 Too Many Requests" | Expected for browser slot test #4 |
| No speedup | Ensure running request TWICE (miss then hit) |

---

## 📚 Additional Resources

- **Redis Quick Reference**: `docs/redis/REDIS_QUICK_REFERENCE.md`
- **Docker Commands**: `docs/redis/DOCKER_REDIS_COMMANDS.md`
- **Complete Testing Guide**: `docs/redis/CACHE_TESTING_GUIDE.md`
- **Implementation Status**: `docs/redis/REDIS_INTEGRATION_STATUS.md`

---

## ✅ Success Checklist

Before considering tests complete:

### Cache Testing
- [ ] Health check passes (Redis connected)
- [ ] User tier cache miss: 50-200ms
- [ ] User tier cache hit: <10ms
- [ ] Speedup > 20x
- [ ] Quiz metadata cache working
- [ ] Redis MONITOR shows SET/GET

### Browser Slot Testing
- [ ] Health check passes
- [ ] User A acquires 3 slots successfully
- [ ] User A blocked on 4th slot (HTTP 429)
- [ ] User B can acquire slots independently
- [ ] Redis shows browser:user:* keys
- [ ] Slot counts correct (0-3)

### Production Verification
- [ ] Tests pass in production (Railway)
- [ ] Server logs show Redis enabled
- [ ] No errors in Railway logs
- [ ] Performance improvement visible
- [ ] Multi-instance coordination works

**All checked? Redis integration is working perfectly! 🎉**
