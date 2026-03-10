# Redis Commands for Docker Setup

## 🐳 Your Setup
You have Redis running in a Docker container named `quizify-redis`.  
All Redis commands need to be run through Docker.

---

## 🚀 Quick Start Commands

### **Test Redis Connection**
```bash
docker exec -it quizify-redis redis-cli ping
# Should return: PONG
```

### **See All Cache Keys**
```bash
docker exec -it quizify-redis redis-cli KEYS '*'
```

### **Monitor Redis in Real-Time** ⭐
```bash
docker exec -it quizify-redis redis-cli MONITOR
# Press Ctrl+C to stop
```

### **Count Keys by Type**
```bash
# User tier cache
docker exec -it quizify-redis redis-cli KEYS 'user_tier:*' | wc -l

# Quiz metadata cache
docker exec -it quizify-redis redis-cli KEYS 'quiz_metadata:*' | wc -l

# Browser slots
docker exec -it quizify-redis redis-cli KEYS 'browser:*' | wc -l
```

### **Check Total Keys**
```bash
docker exec -it quizify-redis redis-cli DBSIZE
```

---

## 🔍 Inspect Cache Contents

### **Get a Specific Key**
```bash
docker exec -it quizify-redis redis-cli GET "user_tier:YOUR_USER_ID"
```

### **Check TTL (Time to Live)**
```bash
docker exec -it quizify-redis redis-cli TTL "user_tier:YOUR_USER_ID"
# Returns seconds until expiration
# -1 = no expiration
# -2 = key doesn't exist
```

### **Get All Keys with Pattern**
```bash
docker exec -it quizify-redis redis-cli --scan --pattern "user_tier:*"
```

### **Get Memory Usage**
```bash
docker exec -it quizify-redis redis-cli INFO memory | grep used_memory_human
```

---

## 🧪 Testing Cache Performance

### **1. Clear Cache (Fresh Start)**
```bash
docker exec -it quizify-redis redis-cli FLUSHDB
echo "Cache cleared - ready for testing!"
```

### **2. Start Monitoring in One Terminal**
```bash
docker exec -it quizify-redis redis-cli MONITOR
```

### **3. Make API Requests in Another Terminal**
```bash
# Example: Get user tier info
curl -X GET "http://localhost:8000/api/user/tier-info" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# Watch the MONITOR terminal - you'll see:
# SET "user_tier:550e8400..." "..."
# GET "user_tier:550e8400..." (on subsequent requests)
```

### **4. Check Cache Hit Rate**
```bash
docker exec -it quizify-redis redis-cli INFO stats | grep keyspace
```

---

## 📊 Our Monitoring Script (Updated for Docker)

```bash
# One-time check
./scripts/monitor_redis.sh

# Continuous monitoring
./scripts/monitor_redis.sh watch
```

**Script now auto-detects Docker and uses:**
- `docker exec -i quizify-redis redis-cli` for all Redis commands

---

## 🎯 Verify Caching is Working

### **Step 1: Clear Cache**
```bash
docker exec -it quizify-redis redis-cli FLUSHDB
```

### **Step 2: Check Empty**
```bash
docker exec -it quizify-redis redis-cli DBSIZE
# Should return: (integer) 0
```

### **Step 3: Start Your API**
```bash
REDIS_ENABLED=true REDIS_URL=redis://quizify-redis:6379 \
  uvicorn main:app --reload --port 8000
```

### **Step 4: Make a Request**
```bash
# First request (database hit - slow)
time curl -X GET "http://localhost:8000/api/user/tier-info" \
  -H "Authorization: Bearer YOUR_JWT"

# Check Redis - should see a new key
docker exec -it quizify-redis redis-cli DBSIZE
# Should return: (integer) 1

# Second request (cache hit - fast!)
time curl -X GET "http://localhost:8000/api/user/tier-info" \
  -H "Authorization: Bearer YOUR_JWT"
```

### **Step 5: Inspect the Cached Data**
```bash
# Find the key
docker exec -it quizify-redis redis-cli KEYS '*'

# Get the cached value
docker exec -it quizify-redis redis-cli GET "user_tier:YOUR_USER_ID"

# Check TTL
docker exec -it quizify-redis redis-cli TTL "user_tier:YOUR_USER_ID"
# Should return: ~300 (5 minutes)
```

---

## 🔧 Docker Management

### **Start Redis Container**
```bash
docker-compose up -d redis
```

### **Stop Redis Container**
```bash
docker-compose stop redis
```

### **View Redis Logs**
```bash
docker logs quizify-redis -f
```

### **Restart Redis**
```bash
docker-compose restart redis
```

### **Redis Container Stats**
```bash
docker stats quizify-redis
```

---

## 💡 Pro Tips

### **Create Aliases (Add to ~/.zshrc)**
```bash
# Redis aliases for Docker
alias redis-cli='docker exec -it quizify-redis redis-cli'
alias redis-monitor='docker exec -it quizify-redis redis-cli MONITOR'
alias redis-keys='docker exec -it quizify-redis redis-cli KEYS "*"'
alias redis-clear='docker exec -it quizify-redis redis-cli FLUSHDB'

# Reload shell: source ~/.zshrc
# Then just use: redis-cli ping
```

### **Watch Cache Grow**
```bash
# In one terminal
watch -n 1 'docker exec -i quizify-redis redis-cli DBSIZE'

# In another terminal - make API requests
# Watch the counter increase!
```

### **Pretty Print JSON from Cache**
```bash
docker exec -it quizify-redis redis-cli GET "user_tier:YOUR_ID" | jq .
```

---

## 🎨 Expected Output Examples

### **Empty Cache**
```bash
$ docker exec -it quizify-redis redis-cli DBSIZE
(integer) 0
```

### **Cache with Data**
```bash
$ docker exec -it quizify-redis redis-cli KEYS '*'
1) "user_tier:550e8400-e29b-41d4-a716-446655440000"
2) "quiz_metadata:123abc:user456"
3) "browser:slot:global"
```

### **Cache Hit in MONITOR**
```bash
$ docker exec -it quizify-redis redis-cli MONITOR
OK
1699123456.789 [0 172.18.0.1:12345] "GET" "user_tier:550e8400..."
1699123457.123 [0 172.18.0.1:12345] "SET" "quiz_metadata:123abc..." "{...}"
```

---

## 🚨 Troubleshooting

### **Error: Cannot connect to Redis**
```bash
# Check container is running
docker ps | grep redis

# Check network connectivity
docker exec -it quizify-redis redis-cli ping

# Check logs
docker logs quizify-redis
```

### **Error: Permission denied**
```bash
# Use -i instead of -it for scripts
docker exec -i quizify-redis redis-cli KEYS '*'
```

### **No keys showing up**
```bash
# Verify REDIS_URL in your app points to container
echo $REDIS_URL
# Should be: redis://quizify-redis:6379 (for Docker network)
# Or: redis://localhost:6379 (if port is exposed)

# Check docker-compose port mapping
docker-compose ps redis
```

---

## 📞 Need Help?

If monitoring script fails, try:
```bash
# Manual check
docker exec -it quizify-redis redis-cli ping

# View script output
bash -x ./scripts/monitor_redis.sh

# Check Docker network
docker network inspect quizify_default
```
