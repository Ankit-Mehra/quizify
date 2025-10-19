# Redis Architecture Guide for Web Scraping Service

## What is Redis?

**Redis** (Remote Dictionary Server) is an **in-memory data structure store** that can be used as:
- 🗄️ **Database** (but data lives in RAM for speed)
- 🚀 **Cache** (temporary fast storage)
- 📨 **Message broker** (for pub/sub messaging)
- 🔒 **Session store** (for distributed applications)

### Key Characteristics:
- **Lightning Fast**: Data stored in RAM (1000x faster than disk)
- **Persistent**: Can save to disk for durability
- **Atomic Operations**: Thread-safe operations built-in
- **Data Structures**: Strings, Lists, Sets, Hashes, Sorted Sets, etc.
- **Distributed**: Works across multiple servers/processes

---

## Current Architecture Problems

### Before: Single-Process Memory (Current Implementation)

```mermaid
graph TB
    subgraph "Single Server Process"
        User1[User 1] --> App[FastAPI App]
        User2[User 2] --> App
        User3[User 3] --> App
        
        App --> Memory["In-Memory State<br/>_active_browsers = {<br/>  'user1': 2,<br/>  'user2': 1<br/>}"]
        App --> Lock["AsyncIO Lock<br/>_browser_lock"]
        
        Memory --> Browser1[Chrome Browser 1]
        Memory --> Browser2[Chrome Browser 2]
        Memory --> Browser3[Chrome Browser 3]
    end
    
    style Memory fill:#ffcccc
    style Lock fill:#ffcccc
```

**Problems with Current Architecture:**
- ❌ **Single Point of Failure**: If process crashes, all state lost
- ❌ **No Scalability**: Can't run multiple processes/servers
- ❌ **Memory Loss**: State resets on deployment/restart
- ❌ **Inefficient**: Under-utilizes server resources

---

## After: Multi-Process with Redis

### Distributed Architecture with Redis

```mermaid
graph TB
    subgraph "Load Balancer"
        LB[Railway Load Balancer]
    end
    
    subgraph "Application Tier"
        App1[FastAPI Process 1]
        App2[FastAPI Process 2] 
        App3[FastAPI Process 3]
    end
    
    subgraph "Redis Cluster"
        Redis[(Redis Server<br/>In-Memory Database)]
    end
    
    subgraph "Browser Pool"
        Browser1[Chrome Instance 1]
        Browser2[Chrome Instance 2]
        Browser3[Chrome Instance 3]
        Browser4[Chrome Instance 4]
        Browser5[Chrome Instance 5]
        Browser6[Chrome Instance 6]
    end
    
    User1[User 1] --> LB
    User2[User 2] --> LB
    User3[User 3] --> LB
    
    LB --> App1
    LB --> App2
    LB --> App3
    
    App1 --> Redis
    App2 --> Redis
    App3 --> Redis
    
    App1 --> Browser1
    App1 --> Browser2
    App2 --> Browser3
    App2 --> Browser4
    App3 --> Browser5
    App3 --> Browser6
    
    style Redis fill:#90EE90
    style LB fill:#87CEEB
```

---

## Detailed Flow Comparison

### Current Flow (Single Process)

```mermaid
sequenceDiagram
    participant U as User
    participant A as FastAPI App
    participant M as Memory Dict
    participant L as AsyncIO Lock
    participant B as Chrome Browser

    U->>A: Request scraping
    A->>L: Acquire lock
    L-->>A: Lock acquired
    A->>M: Check user browser count
    M-->>A: Current count: 1
    A->>M: Increment count to 2
    A->>B: Launch browser
    B-->>A: Scraping result
    A->>L: Acquire lock
    A->>M: Decrement count to 1
    A-->>U: Return result
    
    Note over A,M: Lost if process restarts<br/>Not shared across processes
```

### New Flow (Redis-Backed)

```mermaid
sequenceDiagram
    participant U as User
    participant LB as Load Balancer
    participant A1 as FastAPI Process 1
    participant A2 as FastAPI Process 2
    participant R as Redis
    participant B as Chrome Browser

    U->>LB: Request scraping
    LB->>A1: Route to Process 1
    
    A1->>R: INCR browser_slots:user123
    R-->>A1: New count: 2
    
    alt Count <= MAX_BROWSERS
        A1->>R: EXPIRE browser_slots:user123 300
        A1->>B: Launch browser
        B-->>A1: Scraping result
        A1->>R: DECR browser_slots:user123
        A1-->>U: Return result
    else Count > MAX_BROWSERS
        A1->>R: DECR browser_slots:user123
        A1-->>U: 429 Too Many Requests
    end
    
    Note over A1,R: Survives process restarts<br/>Shared across all processes<br/>Atomic operations prevent race conditions
```

---

## Redis Data Structures for Browser Management

### 1. Simple Counter Approach
```redis
# Key: browser_slots:{user_id}
# Value: Current browser count
# TTL: 300 seconds (auto-cleanup)

SET browser_slots:user123 0
INCR browser_slots:user123    # Returns: 1
INCR browser_slots:user123    # Returns: 2
EXPIRE browser_slots:user123 300
```

### 2. Advanced Session Tracking
```redis
# Hash for detailed session info
HMSET browser_session:user123:session456 user_id user123 started_at 1697712000 url "https://example.com" process_id "railway-process-1"

# Set for active sessions per user
SADD active_sessions:user123 session456

# Get count
SCARD active_sessions:user123  # Returns: 1
```

---

## Implementation Benefits

### Performance Comparison

| Operation | Current (Memory) | Redis (Network) | Improvement |
|-----------|------------------|-----------------|-------------|
| Single Process | 0.001ms | 0.1ms | Still very fast |
| Multi-Process | ❌ Broken | ✅ Works | Enables scaling |
| Process Restart | ❌ Lost state | ✅ Preserved | High availability |
| Concurrent Users | Limited | Unlimited | Better scaling |

### Scalability Scenarios

```mermaid
graph LR
    subgraph "Traffic Growth"
        T1[100 Users] --> T2[1,000 Users] --> T3[10,000 Users]
    end
    
    subgraph "Current Architecture"
        S1["1 Process<br/>Overloaded"] --> S2["Can't Scale<br/>Crashes"] --> S3["System Down"]
    end
    
    subgraph "Redis Architecture"
        R1["1 Process<br/>+ Redis"] --> R2["3 Processes<br/>+ Redis"] --> R3["10 Processes<br/>+ Redis"]
    end
    
    T1 --> S1
    T1 --> R1
    T2 --> S2
    T2 --> R2
    T3 --> S3
    T3 --> R3
    
    style S2 fill:#ffcccc
    style S3 fill:#ffcccc
    style R1 fill:#90EE90
    style R2 fill:#90EE90
    style R3 fill:#90EE90
```

---

## Code Implementation

### Current Implementation (Problematic)
```python
# ❌ Single-process only
import asyncio
from collections import defaultdict
from fastapi import HTTPException

_active_browsers = defaultdict(int)
_browser_lock = asyncio.Lock()

async def _acquire_browser_slot(user_id: str) -> None:
    async with _browser_lock:  # Only works within one process
        current_count = _active_browsers[user_id]
        if current_count >= MAX_CONCURRENT_BROWSERS:
            raise HTTPException(status_code=429)
        _active_browsers[user_id] += 1
```

### Redis Implementation (Scalable)
```python
# ✅ Multi-process compatible
import os
import uuid
from datetime import datetime
import redis.asyncio as redis
from fastapi import HTTPException
from services.logger import app_logger as logger

async def _acquire_browser_slot_redis(user_id: str) -> str:
    """
    Acquire browser slot using Redis for distributed coordination.
    Returns session_id for tracking.
    """
    MAX_CONCURRENT_BROWSERS = 3  # Define the constant
    redis_client = redis.from_url(os.environ.get('REDIS_URL'))
    session_id = str(uuid.uuid4())
    key = f"browser_slots:{user_id}"
    
    try:
        # Atomic increment and check
        current_count = await redis_client.incr(key)
        
        if current_count > MAX_CONCURRENT_BROWSERS:
            # Rollback the increment
            await redis_client.decr(key)
            raise HTTPException(
                status_code=429,
                detail="Too many concurrent browser sessions"
            )
        
        # Set expiration for cleanup (5 minutes)
        await redis_client.expire(key, 300)
        
        # Store session details
        session_key = f"browser_session:{user_id}:{session_id}"
        session_data = {
            "started_at": datetime.utcnow().isoformat(),
            "process_id": os.environ.get('RAILWAY_REPLICA_ID', 'unknown')
        }
        await redis_client.hset(session_key, session_data)
        await redis_client.expire(session_key, 300)
        
        logger.info(f"Browser slot acquired: {current_count}/{MAX_CONCURRENT_BROWSERS}")
        return session_id
        
    except redis.RedisError as e:
        logger.error(f"Redis error acquiring slot: {e}")
        # Fallback to memory-based tracking
        return await _acquire_browser_slot_memory(user_id)

async def _release_browser_slot_redis(user_id: str, session_id: str) -> None:
    """Release browser slot using Redis."""
    MAX_CONCURRENT_BROWSERS = 3  # Define the constant
    redis_client = redis.from_url(os.environ.get('REDIS_URL'))
    
    try:
        key = f"browser_slots:{user_id}"
        session_key = f"browser_session:{user_id}:{session_id}"
        
        # Decrement counter
        remaining = await redis_client.decr(key)
        
        # Clean up session info
        await redis_client.delete(session_key)
        
        # Remove key if no active sessions
        if remaining <= 0:
            await redis_client.delete(key)
            
        logger.info(f"Browser slot released: {remaining}/{MAX_CONCURRENT_BROWSERS}")
        
    except redis.RedisError as e:
        logger.error(f"Redis error releasing slot: {e}")
```

---

## Deployment Architecture

### Railway Deployment with Redis

```mermaid
graph TB
    subgraph "Railway Cloud"
        subgraph "Your Application"
            Web1[Web Process 1<br/>quizify-web]
            Web2[Web Process 2<br/>quizify-web]
            Web3[Web Process 3<br/>quizify-web]
        end
        
        subgraph "Redis Service"
            RedisDB[(Redis Database<br/>Managed Service)]
        end
        
        subgraph "Supabase"
            SPDB[(PostgreSQL<br/>Quiz Data)]
        end
        
        Router[Railway Router<br/>Load Balancer]
    end
    
    Internet[Internet Users] --> Router
    Router --> Web1
    Router --> Web2
    Router --> Web3
    
    Web1 --> RedisDB
    Web2 --> RedisDB
    Web3 --> RedisDB
    
    Web1 --> SPDB
    Web2 --> SPDB
    Web3 --> SPDB
    
    style RedisDB fill:#90EE90
    style SPDB fill:#87CEEB
```

### Environment Variables
```bash
# .env
REDIS_URL=redis://red-xxxxx:6379  # Railway provides this
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-key

# Railway automatically sets:
RAILWAY_REPLICA_ID=web-1  # Unique process identifier
PORT=3000
```

---

## Migration Strategy

### Phase 1: Add Redis Support (Backwards Compatible)
```python
import os
from services.logger import app_logger as logger

async def _acquire_browser_slot(user_id: str) -> str:
    """Smart fallback: Redis first, memory backup."""
    redis_url = os.environ.get('REDIS_URL')
    
    if redis_url:
        try:
            return await _acquire_browser_slot_redis(user_id)
        except Exception as e:
            logger.warning(f"Redis unavailable, using memory: {e}")
    
    # Fallback to current implementation
    return await _acquire_browser_slot_memory(user_id)
```

### Phase 2: Monitor and Optimize
```python
# Add metrics
await redis_client.incr("metrics:browser_slots_acquired")
await redis_client.incr(f"metrics:user_activity:{user_id}")

# Add alerting
ALERT_THRESHOLD = 100  # Define threshold
total_slots = await redis_client.get("browser_slots:total")
if total_slots and int(total_slots) > ALERT_THRESHOLD:
    logger.warning("High browser usage detected")
```

### Phase 3: Full Redis Migration
- Remove memory fallback
- Add Redis health checks
- Implement Redis clustering for high availability

---

## Cost and Infrastructure

### Redis Hosting Options

| Provider | Cost/Month | Memory | Use Case |
|----------|------------|---------|-----------|
| Railway Redis | $5 | 256MB | Development/Small |
| Railway Redis | $20 | 1GB | Production |
| Redis Cloud | $0 | 30MB | Free tier |
| Self-hosted | Server cost | Unlimited | Enterprise |

### Resource Requirements
```mermaid
pie title Redis Memory Usage Breakdown
    "Browser Slots" : 40
    "Session Data" : 30
    "Metrics" : 15
    "Overhead" : 15
```

**Estimated Memory Usage:**
- Browser slots: ~10KB per user (1000 users = 10MB)
- Session metadata: ~5KB per session
- Cleanup overhead: ~20% of total
- **Total for 1000 concurrent users: ~50MB**

---

## Monitoring and Debugging

### Redis Monitoring Commands
```bash
# Connect to Redis
redis-cli -u $REDIS_URL

# Check current browser slots
KEYS browser_slots:*
GET browser_slots:user123

# Monitor real-time commands
MONITOR

# Check memory usage
INFO memory

# List active sessions
KEYS browser_session:*
```

### Application Metrics
```python
# Add to your logging
stats = await redis_client.info('stats')
logger.info(f"Redis stats: {stats}")

active_keys = await redis_client.keys('browser_slots:*')
logger.info(f"Active browser slots: {len(active_keys)}")
```

---

## Summary: Why Redis Solves Your Problems

### Before Redis (Current Issues):
- ❌ **Broken in production**: Multi-process deployments don't work
- ❌ **Lost state**: Process restarts lose all tracking
- ❌ **Race conditions**: Potential memory corruption under load
- ❌ **No observability**: Can't see cross-process usage

### After Redis (Solutions):
- ✅ **Production ready**: Works across unlimited processes
- ✅ **Persistent state**: Survives deployments and crashes
- ✅ **Atomic operations**: Built-in thread safety
- ✅ **Real-time monitoring**: See usage across all instances
- ✅ **Horizontal scaling**: Add processes without coordination issues
- ✅ **Performance**: Sub-millisecond operations
- ✅ **Reliability**: Battle-tested by millions of applications

### Implementation Effort:
- **Time**: 2-4 hours for basic implementation
- **Risk**: Low (fallback to current system)
- **Complexity**: Medium (Redis is well-documented)
- **Benefit**: High (enables true production scaling)

**Recommendation**: Start with Railway Redis addon (~$5/month) for immediate production benefits.