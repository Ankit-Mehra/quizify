# Browser Slot Service Contract

**Version**: 1.0  
**Created**: 2025-10-22  
**Status**: ✅ Approved for Implementation

---

## Service Overview

The **BrowserSlotService** manages concurrent browser session coordination across multiple FastAPI instances. It enforces a maximum of 3 concurrent browser sessions per user using Redis atomic operations.

**Primary Responsibilities**:
1. Acquire browser slots atomically (prevent race conditions)
2. Release browser slots when scraping completes
3. Track active browser sessions with metadata
4. List all active sessions for a user
5. Automatic cleanup via TTL (5 minutes)

**Key Design Principles**:
- **Thread-safe**: Uses Redis atomic INCR/DECR operations
- **Distributed**: Works across multiple FastAPI processes
- **Self-healing**: TTL prevents stuck slots from blocking users
- **Observable**: Provides session tracking and debugging info

---

## Service Interface

### Class Definition

```python
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field
import redis.asyncio as redis

class BrowserSession(BaseModel):
    """Browser session metadata"""
    session_id: str = Field(..., description="Unique session identifier (UUID)")
    user_id: str = Field(..., description="User who owns this session")
    url: str = Field(..., description="URL being scraped")
    started_at: datetime = Field(..., description="Session start timestamp")
    process_id: str = Field(..., description="FastAPI process identifier")
    status: str = Field(..., description="Session status: active, completed, failed")

class BrowserSlotService:
    """
    Manages browser slot allocation and session tracking using Redis.
    
    Thread-safe across multiple processes. Enforces max 3 concurrent
    browsers per user. Automatic cleanup via 5-minute TTL.
    """
    
    def __init__(self, redis_client: redis.Redis):
        """
        Initialize service with Redis client.
        
        Args:
            redis_client: Async Redis client instance
        """
        self.redis = redis_client
        self.max_slots = 3
        self.slot_ttl = 300  # 5 minutes
    
    async def acquire_slot(
        self, 
        user_id: str, 
        url: str,
        process_id: Optional[str] = None
    ) -> str:
        """
        Acquire a browser slot for the user.
        
        Atomically increments the slot counter. If limit exceeded, rolls back
        the increment and raises an exception. Creates session metadata.
        
        Args:
            user_id: User identifier
            url: URL to be scraped
            process_id: Optional process identifier (defaults to current PID)
        
        Returns:
            session_id: Unique session identifier (UUID)
        
        Raises:
            TooManyBrowsersError: If user already has 3 active slots
            RedisConnectionError: If Redis is unavailable
        
        Example:
            >>> service = BrowserSlotService(redis_client)
            >>> session_id = await service.acquire_slot(
            ...     "user_123", 
            ...     "https://example.com"
            ... )
            >>> print(session_id)
            '550e8400-e29b-41d4-a716-446655440000'
        """
        ...
    
    async def release_slot(
        self, 
        user_id: str, 
        session_id: str
    ) -> None:
        """
        Release a browser slot for the user.
        
        Atomically decrements the slot counter and deletes session metadata.
        Safe to call even if session doesn't exist (idempotent).
        
        Args:
            user_id: User identifier
            session_id: Session identifier to release
        
        Returns:
            None
        
        Raises:
            RedisConnectionError: If Redis is unavailable
        
        Example:
            >>> await service.release_slot("user_123", session_id)
        """
        ...
    
    async def get_slot_count(self, user_id: str) -> int:
        """
        Get current number of active slots for user.
        
        Args:
            user_id: User identifier
        
        Returns:
            count: Number of active browser slots (0-3)
        
        Example:
            >>> count = await service.get_slot_count("user_123")
            >>> print(count)
            2
        """
        ...
    
    async def list_sessions(self, user_id: str) -> List[BrowserSession]:
        """
        List all active browser sessions for user.
        
        Useful for debugging and monitoring. Returns session metadata
        including URLs, start times, and process IDs.
        
        Args:
            user_id: User identifier
        
        Returns:
            sessions: List of BrowserSession objects (0-3 items)
        
        Example:
            >>> sessions = await service.list_sessions("user_123")
            >>> for session in sessions:
            ...     print(f"{session.url} - {session.status}")
            https://example.com - active
            https://another.com - active
        """
        ...
    
    async def update_session_status(
        self,
        user_id: str,
        session_id: str,
        status: str
    ) -> None:
        """
        Update the status of an active session.
        
        Args:
            user_id: User identifier
            session_id: Session identifier
            status: New status ('active', 'completed', 'failed')
        
        Returns:
            None
        
        Example:
            >>> await service.update_session_status(
            ...     "user_123",
            ...     session_id,
            ...     "completed"
            ... )
        """
        ...
```

---

## Usage Patterns

### 1. Typical Flow (Web Scraping)

```python
from services.redis.browser_slots import BrowserSlotService
from services.web_scraping_service import scrape_url

async def generate_quiz_from_url(
    user_id: str,
    url: str,
    redis_client: redis.Redis
) -> Quiz:
    """Generate quiz with browser slot management"""
    
    browser_service = BrowserSlotService(redis_client)
    session_id = None
    
    try:
        # 1. Acquire slot (raises if limit exceeded)
        session_id = await browser_service.acquire_slot(user_id, url)
        
        # 2. Scrape content
        content = await scrape_url(url)
        
        # 3. Update status
        await browser_service.update_session_status(
            user_id, 
            session_id, 
            "completed"
        )
        
        # 4. Generate quiz
        quiz = await generate_quiz(content)
        
        return quiz
        
    except TooManyBrowsersError:
        # User has 3 active browsers
        raise HTTPException(
            status_code=429,
            detail="Maximum concurrent browsers reached (3). Please wait."
        )
    
    finally:
        # 5. Always release slot
        if session_id:
            await browser_service.release_slot(user_id, session_id)
```

### 2. Monitoring Active Sessions

```python
@app.get("/debug/browser-sessions/{user_id}")
async def get_user_browser_sessions(
    user_id: str,
    request: Request
) -> List[BrowserSession]:
    """Debug endpoint to view active browser sessions"""
    
    browser_service = BrowserSlotService(request.app.state.redis)
    sessions = await browser_service.list_sessions(user_id)
    
    return sessions
```

### 3. Admin: Force Release All Slots

```python
async def force_release_user_slots(
    user_id: str,
    redis_client: redis.Redis
) -> int:
    """Admin function to clear stuck browser slots"""
    
    browser_service = BrowserSlotService(redis_client)
    sessions = await browser_service.list_sessions(user_id)
    
    # Release all sessions
    for session in sessions:
        await browser_service.release_slot(user_id, session.session_id)
    
    return len(sessions)
```

---

## Error Handling

### Custom Exceptions

```python
class TooManyBrowsersError(Exception):
    """Raised when user exceeds maximum concurrent browser slots (3)"""
    
    def __init__(self, user_id: str, current_count: int, max_slots: int = 3):
        self.user_id = user_id
        self.current_count = current_count
        self.max_slots = max_slots
        super().__init__(
            f"User {user_id} has {current_count} active browsers "
            f"(max: {max_slots})"
        )

class BrowserSlotError(Exception):
    """Base exception for browser slot operations"""
    pass
```

### Error Scenarios

| Error | Cause | HTTP Status | User Message |
|-------|-------|-------------|--------------|
| `TooManyBrowsersError` | 3 active browsers | 429 | "Maximum concurrent browsers reached (3). Please wait for active requests to complete." |
| `RedisConnectionError` | Redis unavailable | 503 | "Service temporarily unavailable. Please try again." (falls back to memory) |
| `BrowserSlotError` | Other Redis errors | 500 | "Failed to acquire browser slot. Please try again." |

---

## Fallback Behavior

When Redis is unavailable, the service falls back to in-memory tracking:

```python
class BrowserSlotService:
    def __init__(self, redis_client: Optional[redis.Redis]):
        self.redis = redis_client
        self._memory_slots = {}  # {user_id: count}
        self._memory_sessions = {}  # {session_id: BrowserSession}
        self.fallback_mode = False
    
    async def acquire_slot(self, user_id: str, url: str, process_id: Optional[str] = None) -> str:
        try:
            if self.redis and not self.fallback_mode:
                # Try Redis first
                return await self._acquire_slot_redis(user_id, url, process_id)
        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.warning(f"Redis error, falling back to memory: {e}")
            self.fallback_mode = True
        
        # Fallback to memory
        return await self._acquire_slot_memory(user_id, url, process_id)
```

**Trade-offs in Fallback Mode**:
- ❌ No coordination across multiple processes (single instance only)
- ❌ No TTL enforcement (manual cleanup required)
- ✅ Core functionality works (prevents outages)
- ✅ Automatic recovery when Redis comes back

---

## Performance Characteristics

### Expected Latency

| Operation | Redis Time | Description |
|-----------|-----------|-------------|
| `acquire_slot` | 1-2ms | INCR + EXPIRE + HSET |
| `release_slot` | 0.5-1ms | DECR + DEL |
| `get_slot_count` | 0.1-0.5ms | GET |
| `list_sessions` | 2-5ms | SCAN + HGETALL × N |
| `update_session_status` | 0.5-1ms | HSET |

### Memory Usage

| Component | Size per User | Example |
|-----------|---------------|---------|
| Slot counter | ~50 bytes | `browser_slots:user_123` → `2` |
| Session metadata | ~250 bytes | Hash with 6 fields |
| **Total (3 sessions)** | **~800 bytes** | Maximum per user |

### Scalability

- **Atomic operations**: No race conditions up to 100,000 concurrent users
- **Memory efficient**: 256MB Redis handles 50,000+ concurrent users
- **TTL cleanup**: Automatic cleanup prevents memory leaks
- **Horizontal scaling**: Works seamlessly across N FastAPI instances

---

## Testing Requirements

### Unit Tests (fakeredis)

```python
import pytest
from fakeredis import aioredis as fakeredis
from services.redis.browser_slots import BrowserSlotService, TooManyBrowsersError

@pytest.fixture
async def redis_client():
    client = fakeredis.FakeRedis(decode_responses=True)
    yield client
    await client.flushall()
    await client.close()

@pytest.mark.asyncio
async def test_acquire_slot_success(redis_client):
    """Should successfully acquire slot when under limit"""
    service = BrowserSlotService(redis_client)
    
    session_id = await service.acquire_slot("user_123", "https://example.com")
    
    assert session_id is not None
    assert len(session_id) == 36  # UUID format
    assert await service.get_slot_count("user_123") == 1

@pytest.mark.asyncio
async def test_acquire_slot_at_limit(redis_client):
    """Should raise error when acquiring 4th slot"""
    service = BrowserSlotService(redis_client)
    
    # Acquire 3 slots (should succeed)
    for i in range(3):
        await service.acquire_slot("user_123", f"https://example{i}.com")
    
    # Try to acquire 4th slot (should fail)
    with pytest.raises(TooManyBrowsersError):
        await service.acquire_slot("user_123", "https://example3.com")

@pytest.mark.asyncio
async def test_release_slot(redis_client):
    """Should properly release slot and decrement counter"""
    service = BrowserSlotService(redis_client)
    
    session_id = await service.acquire_slot("user_123", "https://example.com")
    assert await service.get_slot_count("user_123") == 1
    
    await service.release_slot("user_123", session_id)
    assert await service.get_slot_count("user_123") == 0

@pytest.mark.asyncio
async def test_list_sessions(redis_client):
    """Should list all active sessions with metadata"""
    service = BrowserSlotService(redis_client)
    
    # Acquire 2 slots
    session1 = await service.acquire_slot("user_123", "https://example1.com")
    session2 = await service.acquire_slot("user_123", "https://example2.com")
    
    # List sessions
    sessions = await service.list_sessions("user_123")
    
    assert len(sessions) == 2
    assert sessions[0].user_id == "user_123"
    assert sessions[0].status == "active"
```

### Integration Tests (pytest-redis)

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_slot_acquisition(redis_server):
    """Test atomic operations with real Redis"""
    client = await redis.from_url(f"redis://{redis_server.host}:{redis_server.port}")
    service = BrowserSlotService(client)
    
    # Simulate concurrent requests (should be atomic)
    tasks = [
        service.acquire_slot("user_123", f"https://example{i}.com")
        for i in range(5)
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Should have 3 successes and 2 TooManyBrowsersError
    successes = [r for r in results if isinstance(r, str)]
    errors = [r for r in results if isinstance(r, TooManyBrowsersError)]
    
    assert len(successes) == 3
    assert len(errors) == 2
    
    await client.close()
```

### Contract Tests

```python
@pytest.mark.contract
@pytest.mark.asyncio
async def test_browser_slot_service_contract(redis_client):
    """Verify service matches contract specification"""
    service = BrowserSlotService(redis_client)
    
    # Contract: acquire_slot returns str (UUID)
    session_id = await service.acquire_slot("user_123", "https://example.com")
    assert isinstance(session_id, str)
    assert len(session_id) == 36
    
    # Contract: get_slot_count returns int (0-3)
    count = await service.get_slot_count("user_123")
    assert isinstance(count, int)
    assert 0 <= count <= 3
    
    # Contract: list_sessions returns List[BrowserSession]
    sessions = await service.list_sessions("user_123")
    assert isinstance(sessions, list)
    assert all(isinstance(s, BrowserSession) for s in sessions)
    
    # Contract: release_slot returns None
    result = await service.release_slot("user_123", session_id)
    assert result is None
```

---

## Implementation Checklist

- [ ] Create `services/redis/browser_slots.py`
- [ ] Implement `BrowserSlotService` class
- [ ] Implement `acquire_slot()` with atomic INCR
- [ ] Implement `release_slot()` with atomic DECR
- [ ] Implement `get_slot_count()`
- [ ] Implement `list_sessions()` with SCAN
- [ ] Implement `update_session_status()`
- [ ] Add custom exceptions (`TooManyBrowsersError`)
- [ ] Add memory fallback logic
- [ ] Add comprehensive logging
- [ ] Write unit tests (fakeredis)
- [ ] Write integration tests (pytest-redis)
- [ ] Write contract tests
- [ ] Update existing web scraping code to use service
- [ ] Add monitoring metrics

---

## Dependencies

```python
# requirements.txt
redis[hiredis]>=5.0.0  # Redis client with async support
pydantic>=2.0.0        # Data validation
```

---

**Contract Status**: ✅ **APPROVED**  
**Implementation Priority**: **HIGH** (Week 1)  
**Estimated Effort**: 2-3 days (including tests)  
**Next**: Implement `services/redis/browser_slots.py`
