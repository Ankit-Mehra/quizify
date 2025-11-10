# 🚀 Redis Quick Reference - Quizify

## ⚡ Fastest Way to Test Cache

```bash
# 1. Watch Redis in one terminal
docker exec -it quizify-redis redis-cli MONITOR

# 2. In another terminal, start your API
REDIS_ENABLED=true uvicorn main:app --reload

# 3. Make a request (use Postman or curl)
# Watch terminal #1 - you'll see SET/GET commands appear!

# 4. Check what got cached
docker exec -it quizify-redis redis-cli KEYS '*'
```

---

## 📝 Most Common Commands

| What You Want | Command |
|---------------|---------|
| Test connection | `docker exec -it quizify-redis redis-cli ping` |
| See all keys | `docker exec -it quizify-redis redis-cli KEYS '*'` |
| Count keys | `docker exec -it quizify-redis redis-cli DBSIZE` |
| Watch real-time | `docker exec -it quizify-redis redis-cli MONITOR` |
| Clear cache | `docker exec -it quizify-redis redis-cli FLUSHDB` |
| Get a key | `docker exec -it quizify-redis redis-cli GET "key_name"` |
| Check TTL | `docker exec -it quizify-redis redis-cli TTL "key_name"` |
| Memory usage | `docker exec -it quizify-redis redis-cli INFO memory \| grep used_memory_human` |

---

## 🎯 Cache Verification Steps

### Step 1: Clear cache (fresh start)
```bash
docker exec -it quizify-redis redis-cli FLUSHDB
docker exec -it quizify-redis redis-cli DBSIZE  # Should return 0
```

### Step 2: Start monitoring
```bash
docker exec -it quizify-redis redis-cli MONITOR
```

### Step 3: Make API request
Use Postman or curl to call your API

### Step 4: Watch for cache activity
You should see in MONITOR terminal:
```
"SET" "user_tier:550e8400..." "..."
"EXPIRE" "user_tier:550e8400..." "300"
```

### Step 5: Make same request again
Should see in MONITOR:
```
"GET" "user_tier:550e8400..." (much faster!)
```

---

## 🛠️ Shortcut Aliases (Recommended)

Add this to your terminal session:
```bash
source scripts/redis_aliases.sh
```

Then use short commands:
```bash
redis-ping          # Test connection
redis-keys          # See all keys
redis-monitor       # Real-time monitoring
redis-dbsize        # Count keys
redis-clear         # Clear cache
redis-user-cache    # User tier keys
redis-quiz-cache    # Quiz metadata keys
```

Make it permanent (add to ~/.zshrc):
```bash
echo "source $PWD/scripts/redis_aliases.sh" >> ~/.zshrc
source ~/.zshrc
```

---

## 📊 Our Monitoring Tools

### Tool 1: Shell Script (Quick Overview)
```bash
./scripts/monitor_redis.sh
```
Shows: Total keys, keys by type, memory usage, stats

### Tool 2: Python Script (Performance Testing)
```bash
REDIS_ENABLED=true python3 scripts/test_redis_caching.py
```
Shows: Cache miss vs hit timing, speedup calculation, cache stats

---

## 🔍 Inspect Cached Data

### Find user tier cache
```bash
docker exec -it quizify-redis redis-cli KEYS 'user_tier:*'
# Returns: user_tier:550e8400-e29b-41d4-a716-446655440000
```

### Get the cached value
```bash
docker exec -it quizify-redis redis-cli GET 'user_tier:550e8400-e29b-41d4-a716-446655440000'
# Returns: JSON with user tier info
```

### Check how long until expiration
```bash
docker exec -it quizify-redis redis-cli TTL 'user_tier:550e8400-e29b-41d4-a716-446655440000'
# Returns: 287 (seconds remaining, max 300 = 5 min)
```

---

## ✅ Expected Results

### Before Cache (Empty)
```bash
$ docker exec -it quizify-redis redis-cli DBSIZE
(integer) 0
```

### After API Request (Populated)
```bash
$ docker exec -it quizify-redis redis-cli KEYS '*'
1) "user_tier:550e8400-e29b-41d4-a716-446655440000"
2) "quiz_metadata:123abc:user456"
```

### Performance Comparison
| Request | Time | Source |
|---------|------|--------|
| 1st call | 150-200ms | Database |
| 2nd call | 2-5ms | Redis Cache |
| **Speedup** | **~50x** | ⚡ |

---

## 🚨 Troubleshooting

### Problem: Command not found: redis-cli
**Solution:** Use Docker commands:
```bash
docker exec -it quizify-redis redis-cli ping
```

Or load aliases:
```bash
source scripts/redis_aliases.sh
```

### Problem: No keys in Redis
**Check:**
1. Is Redis enabled? `echo $REDIS_ENABLED` (should be `true`)
2. Is API using Redis? Check logs for "Redis caching enabled"
3. Is Redis URL correct? `echo $REDIS_URL`

**For Docker networking:**
- Inside containers: `redis://quizify-redis:6379`
- From host (Python scripts): `redis://localhost:6379`

### Problem: Not seeing performance improvement
**Verify:**
1. First request creates cache: `redis-keys` should show new entry
2. Second request uses cache: `redis-monitor` should show GET command
3. Check hit rate: Run Python test script

---

## 💡 Pro Tips

### Watch cache grow
```bash
watch -n 1 'docker exec -i quizify-redis redis-cli DBSIZE'
# Makes requests in another terminal
```

### Pretty print cached JSON
```bash
docker exec -it quizify-redis redis-cli GET "user_tier:YOUR_ID" | jq .
```

### Clear specific pattern
```bash
docker exec -it quizify-redis redis-cli --scan --pattern "user_tier:*" | \
  xargs docker exec -i quizify-redis redis-cli DEL
```

### Check cache hit rate
```python
from services.redis import get_cache_service
cache = get_cache_service(prefix="user_tier")
stats = cache.get_stats()
print(f"Hit rate: {stats['redis_hit_rate']:.1%}")
```

---

## 📚 Full Guides

- **Docker Commands**: `docs/redis/DOCKER_REDIS_COMMANDS.md`
- **Complete Testing**: `docs/redis/CACHE_TESTING_GUIDE.md`
- **Implementation**: `docs/redis/REDIS_INTEGRATION_STATUS.md`

---

## 🎓 Understanding the Output

### MONITOR command shows:
```
1699123456.789 [0 172.18.0.1:12345] "SET" "user_tier:550e..." "{...}" "EX" "300"
```
- Timestamp: `1699123456.789`
- Database: `[0]` (default)
- Client IP: `172.18.0.1:12345`
- Command: `SET` (or `GET`)
- Key: `user_tier:550e...`
- Value: `{...}` (JSON)
- Expiration: `EX 300` (5 minutes)

### TTL returns:
- Positive number: Seconds until expiration
- `-1`: Key exists but no expiration set
- `-2`: Key doesn't exist

### KEYS patterns:
- `*` = All keys
- `user_tier:*` = All user tier cache
- `quiz_metadata:*` = All quiz metadata cache
- `browser:*` = All browser slot keys
