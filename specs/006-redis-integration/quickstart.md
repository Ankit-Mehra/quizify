# Redis Integration Quickstart Guide

**Version**: 1.0  
**Created**: 2025-10-22  
**Audience**: Developers

---

## Overview

This guide helps you set up Redis locally and use the Redis services in Quizify. Follow these steps to get started with Redis integration for development and testing.

**What You'll Learn**:
1. How to set up Redis locally (Docker or native)
2. How to configure the application
3. How to use Redis services in your code
4. How to test Redis functionality
5. How to troubleshoot common issues

**Time Required**: 15-30 minutes

---

## Prerequisites

- Docker Desktop installed (recommended) OR
- Homebrew (for macOS native Redis) OR
- Redis installed directly on your system
- Python 3.12+ environment
- Git repository cloned

---

## Part 1: Local Redis Setup

### Option A: Docker Compose (Recommended)

**Advantages**: Isolated, easy cleanup, consistent across machines

1. **Create docker-compose.yml** (if not exists):

```yaml
# docker-compose.yml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    container_name: quizify-redis
    ports:
      - "6379:6379"
    command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru
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

2. **Start Redis**:

```bash
# Start Redis in background
docker-compose up -d redis

# Check if Redis is running
docker-compose ps

# View Redis logs
docker-compose logs -f redis
```

3. **Test Connection**:

```bash
# Install redis-cli (if not installed)
brew install redis  # macOS (just for redis-cli)

# Test connection
redis-cli ping
# Should output: PONG

# Check Redis info
redis-cli INFO server
```

4. **Stop Redis** (when done):

```bash
docker-compose down  # Stop and remove containers
docker-compose down -v  # Also remove data volume
```

### Option B: Native macOS Installation

**Advantages**: No Docker overhead, direct access

1. **Install Redis**:

```bash
# Install via Homebrew
brew install redis

# Check installation
redis-server --version
```

2. **Start Redis**:

```bash
# Start as background service
brew services start redis

# Or start in foreground (for debugging)
redis-server /usr/local/etc/redis.conf
```

3. **Test Connection**:

```bash
redis-cli ping
# Should output: PONG
```

4. **Stop Redis**:

```bash
# Stop service
brew services stop redis
```

### Option C: Direct Installation (Linux)

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install redis-server

# Start Redis
sudo systemctl start redis-server

# Enable auto-start on boot
sudo systemctl enable redis-server

# Test connection
redis-cli ping
```

---

## Part 2: Application Configuration

### 1. Environment Variables

Create or update `.env` file in project root:

```bash
# .env
# Redis Configuration
REDIS_URL=redis://localhost:6379
REDIS_ENABLED=true
REDIS_MAX_CONNECTIONS=20
REDIS_CONNECT_TIMEOUT=5

# Existing variables...
SUPABASE_URL=your_supabase_url
SUPABASE_ANON_KEY=your_anon_key
# ...
```

### 2. Install Python Dependencies

```bash
# Activate virtual environment
source .venv/bin/activate  # macOS/Linux
# OR
.venv\Scripts\activate  # Windows

# Install Redis dependencies
pip install "redis[hiredis]>=5.0.0"

# Or install all requirements
pip install -r requirements.txt
```

### 3. Verify Configuration

```python
# test_redis_connection.py
import asyncio
import redis.asyncio as redis
from config import settings

async def test_connection():
    """Test Redis connection"""
    try:
        client = await redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True
        )
        
        # Test ping
        pong = await client.ping()
        print(f"✅ Redis connection successful: {pong}")
        
        # Test set/get
        await client.set("test_key", "test_value", ex=10)
        value = await client.get("test_key")
        print(f"✅ Redis set/get working: {value}")
        
        # Test info
        info = await client.info("server")
        print(f"✅ Redis version: {info['redis_version']}")
        
        await client.close()
        
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        print("Make sure Redis is running on localhost:6379")

if __name__ == "__main__":
    asyncio.run(test_connection())
```

Run the test:

```bash
python test_redis_connection.py
```

Expected output:
```
✅ Redis connection successful: True
✅ Redis set/get working: test_value
✅ Redis version: 7.2.3
```

---

## Part 3: Using Redis Services

### Browser Slot Service

```python
from services.redis.browser_slots import BrowserSlotService
import redis.asyncio as redis

# Initialize Redis client (typically in FastAPI lifespan)
redis_client = await redis.from_url("redis://localhost:6379")
browser_service = BrowserSlotService(redis_client)

# Acquire a browser slot
try:
    session_id = await browser_service.acquire_slot(
        user_id="user_123",
        url="https://example.com"
    )
    print(f"Acquired slot: {session_id}")
    
    # Do web scraping...
    
finally:
    # Always release slot
    await browser_service.release_slot("user_123", session_id)
    print("Released slot")
```

### Cache Service

```python
from services.redis.cache import CacheService
from schemas.user import UserTierInfo

cache = CacheService(redis_client)

# Get-or-fetch pattern (recommended)
async def get_user_tier(user_id: str) -> UserTierInfo:
    async def fetch_from_db():
        # Fetch from Supabase
        result = await supabase.table("user_tier_info")\
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

# Manual caching
user_tier = UserTierInfo(...)
await cache.set(f"user_tier:{user_id}", user_tier, ttl=300)

cached = await cache.get(f"user_tier:{user_id}", UserTierInfo)
if cached:
    print(f"Cache hit! Tier: {cached.account_tier}")
```

### Session Service

```python
from services.redis.sessions import SessionService

session_service = SessionService(redis_client)

# Create session (on login)
session_id = await session_service.create_session(
    user_id="user_123",
    device_type="browser",
    ip_address="192.168.1.1",
    user_agent="Mozilla/5.0..."
)

# Validate session (on each request)
session_info = await session_service.validate_session(session_id)
if session_info:
    print(f"Valid session for user: {session_info.user_id}")
    
    # Refresh activity
    await session_service.refresh_session(session_id)

# Logout single device
await session_service.logout(session_id)

# Logout all devices
count = await session_service.logout_all_devices("user_123")
print(f"Logged out {count} devices")
```

---

## Part 4: Testing

### Run Unit Tests (fakeredis)

```bash
# Unit tests run without real Redis
pytest tests/unit/test_redis_services.py -v

# All unit tests
pytest tests/unit/ -v
```

### Run Integration Tests (requires Redis)

```bash
# Make sure Redis is running
redis-cli ping  # Should return PONG

# Run integration tests
pytest tests/integration/test_redis_integration.py -v -m integration

# Skip integration tests (default)
pytest -m "not integration"
```

### Run All Tests

```bash
# Run everything
pytest -v

# Run with coverage
pytest --cov=services/redis --cov-report=html
open htmlcov/index.html  # View coverage report
```

---

## Part 5: Monitoring & Debugging

### Redis CLI Commands

```bash
# Connect to Redis
redis-cli

# Basic commands
> PING                          # Test connection
> INFO                          # Server info
> INFO memory                   # Memory usage
> INFO stats                    # Statistics
> DBSIZE                        # Number of keys

# View keys
> KEYS *                        # List all keys (don't use in production!)
> KEYS browser_slots:*          # List browser slot keys
> SCAN 0 MATCH cache:* COUNT 100  # Scan keys (production-safe)

# Inspect keys
> GET cache:user_tier:user_123  # Get string value
> HGETALL session:sess_abc      # Get hash fields
> SMEMBERS user_sessions:user_123  # Get set members
> TTL browser_slots:user_123    # Get remaining TTL

# Delete keys
> DEL cache:user_tier:user_123  # Delete single key
> FLUSHDB                       # Clear current database (use carefully!)

# Monitor activity
> MONITOR                       # Show all commands in real-time (Ctrl+C to stop)

# Exit
> EXIT
```

### Health Check Endpoint

Test the Redis health check:

```bash
# Start your FastAPI server
uvicorn main:app --reload

# Check Redis health
curl http://localhost:8000/health/redis

# Expected response
{
  "status": "healthy",
  "memory_used_mb": 2.34,
  "memory_percent": 0.91,
  "cache_hit_rate": 82.5,
  "total_requests": 1234
}
```

### View Cache Statistics

```python
# In your code or IPython
from services.redis.cache import CacheService
import redis.asyncio as redis

redis_client = await redis.from_url("redis://localhost:6379")
cache = CacheService(redis_client)

# Make some cached requests...

# View statistics
stats = cache.get_stats()
print(f"Hits: {stats['hits']}")
print(f"Misses: {stats['misses']}")
print(f"Hit Rate: {stats['hit_rate']:.1f}%")
```

### Common Debug Patterns

1. **Check if key exists**:
```python
exists = await redis_client.exists("cache:user_tier:user_123")
print(f"Key exists: {exists}")
```

2. **Check TTL**:
```python
ttl = await redis_client.ttl("browser_slots:user_123")
print(f"Expires in {ttl} seconds")
```

3. **View all browser sessions**:
```python
cursor = 0
sessions = []
while True:
    cursor, keys = await redis_client.scan(
        cursor, match="browser_session:*", count=100
    )
    sessions.extend(keys)
    if cursor == 0:
        break

for session_key in sessions:
    data = await redis_client.hgetall(session_key)
    print(f"{session_key}: {data}")
```

---

## Part 6: Troubleshooting

### Issue: "Connection refused" Error

**Cause**: Redis is not running

**Solution**:
```bash
# Docker Compose
docker-compose ps  # Check if redis container is running
docker-compose up -d redis  # Start if not running

# Native macOS
brew services list  # Check if redis is running
brew services start redis  # Start if not running

# Test connection
redis-cli ping  # Should return PONG
```

### Issue: "WRONGTYPE" Error

**Cause**: Trying to use wrong operation on a key (e.g., GET on a hash)

**Solution**:
```bash
# Check key type
redis-cli TYPE browser_slots:user_123
# Returns: string, hash, set, etc.

# Use correct command
redis-cli HGETALL session:sess_abc  # For hash
redis-cli GET cache:user_tier:user_123  # For string
redis-cli SMEMBERS user_sessions:user_123  # For set
```

### Issue: Out of Memory

**Cause**: Redis memory limit reached

**Solution**:
```bash
# Check memory usage
redis-cli INFO memory

# Check maxmemory setting
redis-cli CONFIG GET maxmemory

# Set maxmemory (256MB)
redis-cli CONFIG SET maxmemory 268435456

# Set eviction policy (LRU)
redis-cli CONFIG SET maxmemory-policy allkeys-lru

# Or edit redis.conf
maxmemory 256mb
maxmemory-policy allkeys-lru
```

### Issue: Tests Failing

**Cause**: Various reasons

**Solution**:
```bash
# Check if Redis is accessible for tests
redis-cli -p 6379 ping

# Clear test database
redis-cli -n 15 FLUSHDB  # pytest-redis uses DB 15

# Check test configuration
cat pytest.ini  # Verify redis_* settings

# Run with verbose output
pytest tests/unit/test_redis_services.py -vv -s

# Run single test
pytest tests/unit/test_redis_services.py::test_acquire_slot -vv
```

### Issue: Fallback Mode Activated

**Cause**: Redis connection lost during runtime

**Check Logs**:
```
WARNING: Redis error, falling back to memory: Connection refused
```

**Solution**:
```bash
# Verify Redis is running
redis-cli ping

# Check Redis logs
docker-compose logs redis  # Docker
tail -f /usr/local/var/log/redis.log  # macOS

# Restart Redis
docker-compose restart redis  # Docker
brew services restart redis  # macOS

# Application will auto-recover after 30 seconds
```

---

## Part 7: Development Workflow

### Typical Development Session

```bash
# 1. Start Redis
docker-compose up -d redis

# 2. Check Redis is running
redis-cli ping

# 3. Activate Python environment
source .venv/bin/activate

# 4. Run tests (optional)
pytest tests/unit/ -v

# 5. Start FastAPI server
uvicorn main:app --reload --port 8000

# 6. Test endpoints
curl http://localhost:8000/health/redis

# 7. Monitor Redis (optional, in new terminal)
redis-cli MONITOR

# 8. When done, stop Redis
docker-compose down
```

### Testing Changes

```bash
# 1. Make changes to Redis service
vim services/redis/browser_slots.py

# 2. Run unit tests (fast)
pytest tests/unit/test_redis_browser_slots.py -v

# 3. Run integration tests (requires Redis)
pytest tests/integration/test_redis_integration.py -v -m integration

# 4. Test manually
python -c "
import asyncio
from services.redis.browser_slots import BrowserSlotService
import redis.asyncio as redis

async def test():
    client = await redis.from_url('redis://localhost:6379')
    service = BrowserSlotService(client)
    session_id = await service.acquire_slot('user_test', 'https://example.com')
    print(f'Session ID: {session_id}')
    await service.release_slot('user_test', session_id)
    await client.close()

asyncio.run(test())
"
```

---

## Part 8: Useful Redis GUI Tools

### RedisInsight (Recommended)

**Free Redis GUI by Redis Labs**

```bash
# Download from: https://redis.com/redis-enterprise/redis-insight/

# Or install via Docker
docker run -d --name redisinsight -p 8001:8001 redislabs/redisinsight:latest

# Open browser
open http://localhost:8001

# Connect to localhost:6379
```

### Redis Commander

**Lightweight web-based UI**

```bash
# Install globally
npm install -g redis-commander

# Run
redis-commander

# Open browser
open http://localhost:8081
```

---

## Part 9: Production Deployment (Railway)

### Add Redis to Railway

```bash
# 1. Login to Railway
railway login

# 2. Link project
railway link

# 3. Add Redis plugin
railway add redis

# 4. Check environment variables
railway variables

# You should see:
# REDIS_URL=redis://default:password@redis.railway.internal:6379
```

### Verify Production Redis

```bash
# Deploy to Railway
git push

# Check health endpoint
curl https://your-app.railway.app/health/redis

# View Railway logs
railway logs --tail 100
```

---

## Quick Reference

### Essential Commands

| Task | Command |
|------|---------|
| Start Redis (Docker) | `docker-compose up -d redis` |
| Stop Redis (Docker) | `docker-compose down` |
| Start Redis (macOS) | `brew services start redis` |
| Test connection | `redis-cli ping` |
| Run unit tests | `pytest tests/unit/ -v` |
| Run integration tests | `pytest -m integration -v` |
| View cache stats | `redis-cli INFO stats` |
| Clear all data | `redis-cli FLUSHDB` |
| Monitor activity | `redis-cli MONITOR` |
| Health check | `curl localhost:8000/health/redis` |

### Environment Variables

```bash
REDIS_URL=redis://localhost:6379  # Local development
REDIS_ENABLED=true                 # Enable Redis features
REDIS_MAX_CONNECTIONS=20           # Connection pool size
REDIS_CONNECT_TIMEOUT=5            # Connection timeout (seconds)
```

### Common Key Patterns

```
browser_slots:{user_id}                      # Slot counter
browser_session:{user_id}:{session_id}       # Session metadata
cache:user_tier:{user_id}                    # User tier cache
cache:quiz:{quiz_id}                         # Quiz cache
session:{session_id}                         # Auth session
user_sessions:{user_id}                      # Active sessions set
rate_limit:{user_id}:{endpoint}:{window}     # Rate limiting
```

---

## Need Help?

1. **Check documentation**:
   - `specs/006-redis-integration/plan.md` - Implementation plan
   - `specs/006-redis-integration/research.md` - Technology decisions
   - `specs/006-redis-integration/data-model.md` - Redis data structures
   - `specs/006-redis-integration/contracts/` - Service interfaces

2. **View examples**:
   - `services/redis/` - Service implementations
   - `tests/unit/` - Unit test examples
   - `tests/integration/` - Integration test examples

3. **Redis resources**:
   - [Redis Documentation](https://redis.io/documentation)
   - [redis-py Documentation](https://redis-py.readthedocs.io/)
   - [Redis Commands Reference](https://redis.io/commands)

---

**Document Version**: 1.0  
**Last Updated**: 2025-10-22  
**Maintainer**: Development Team
