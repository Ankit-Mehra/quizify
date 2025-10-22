# Session Service Contract

**Version**: 1.0  
**Created**: 2025-10-22  
**Status**: ✅ Approved for Implementation

---

## Service Overview

The **SessionService** manages user authentication sessions across multiple devices using Redis. It provides enhanced security features like logout-all-devices, session tracking, and activity monitoring.

**Primary Responsibilities**:
1. Create authenticated sessions with device metadata
2. Validate session tokens on each request
3. Refresh session activity timestamps
4. Logout individual or all devices
5. Track active sessions per user

**Key Design Principles**:
- **Multi-device**: Track sessions across browsers, mobile, API clients
- **Secure**: Store session details, not JWT secrets
- **Auditable**: Track creation time, last activity, device info
- **Distributed**: Works across multiple FastAPI instances

---

## Service Interface

### Class Definition

```python
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field
import redis.asyncio as redis
import uuid

class SessionInfo(BaseModel):
    """Session metadata"""
    session_id: str = Field(..., description="Unique session identifier")
    user_id: str = Field(..., description="User who owns this session")
    created_at: datetime = Field(..., description="Session creation timestamp")
    last_active: datetime = Field(..., description="Last activity timestamp")
    device_type: str = Field(..., description="Device type: browser, mobile, api")
    ip_address: str = Field(..., description="Hashed IP address")
    user_agent: str = Field(..., description="User agent string (truncated)")
    
    @property
    def is_expired(self) -> bool:
        """Check if session is older than 24 hours"""
        age = datetime.utcnow() - self.last_active
        return age.total_seconds() > 86400  # 24 hours

class SessionService:
    """
    Manages user authentication sessions using Redis.
    
    Provides multi-device session tracking, logout-all-devices,
    and session activity monitoring. Sessions expire after 24 hours
    of inactivity.
    """
    
    def __init__(self, redis_client: redis.Redis):
        """
        Initialize session service.
        
        Args:
            redis_client: Async Redis client instance
        """
        self.redis = redis_client
        self.session_ttl = 86400  # 24 hours
    
    async def create_session(
        self,
        user_id: str,
        device_type: str = "browser",
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> str:
        """
        Create a new authentication session.
        
        Generates a unique session ID, stores session metadata in Redis,
        and adds session to user's active session set.
        
        Args:
            user_id: User identifier
            device_type: Type of device ('browser', 'mobile', 'api')
            ip_address: Client IP address (will be hashed)
            user_agent: Client user agent string (will be truncated)
        
        Returns:
            session_id: Unique session identifier (UUID)
        
        Raises:
            RedisConnectionError: If Redis is unavailable
        
        Example:
            >>> service = SessionService(redis_client)
            >>> session_id = await service.create_session(
            ...     user_id="user_123",
            ...     device_type="browser",
            ...     ip_address="192.168.1.1",
            ...     user_agent="Mozilla/5.0..."
            ... )
            >>> print(session_id)
            'sess_550e8400-e29b-41d4-a716-446655440000'
        """
        ...
    
    async def validate_session(self, session_id: str) -> Optional[SessionInfo]:
        """
        Validate a session and return its metadata.
        
        Args:
            session_id: Session identifier to validate
        
        Returns:
            SessionInfo if valid, None if session doesn't exist or expired
        
        Example:
            >>> session_info = await service.validate_session(session_id)
            >>> if session_info:
            ...     print(f"User: {session_info.user_id}")
            ...     print(f"Device: {session_info.device_type}")
            User: user_123
            Device: browser
        """
        ...
    
    async def refresh_session(self, session_id: str) -> bool:
        """
        Refresh session activity timestamp and extend TTL.
        
        Should be called on each authenticated request to prevent
        session expiration during active use.
        
        Args:
            session_id: Session identifier to refresh
        
        Returns:
            True if session was refreshed, False if session doesn't exist
        
        Example:
            >>> refreshed = await service.refresh_session(session_id)
            >>> if not refreshed:
            ...     raise SessionExpiredError()
        """
        ...
    
    async def logout(self, session_id: str) -> bool:
        """
        Logout a single session (single device).
        
        Deletes session metadata and removes from user's session set.
        
        Args:
            session_id: Session identifier to logout
        
        Returns:
            True if session was deleted, False if session didn't exist
        
        Example:
            >>> success = await service.logout(session_id)
            >>> print(f"Logged out: {success}")
            Logged out: True
        """
        ...
    
    async def logout_all_devices(self, user_id: str) -> int:
        """
        Logout all sessions for a user (all devices).
        
        Useful for security actions like password change or account
        compromise. Deletes all session metadata and clears session set.
        
        Args:
            user_id: User identifier
        
        Returns:
            Number of sessions deleted
        
        Example:
            >>> count = await service.logout_all_devices("user_123")
            >>> print(f"Logged out {count} devices")
            Logged out 3 devices
        """
        ...
    
    async def list_sessions(self, user_id: str) -> List[SessionInfo]:
        """
        List all active sessions for a user.
        
        Returns session metadata for all devices. Useful for displaying
        "Active Sessions" in user settings.
        
        Args:
            user_id: User identifier
        
        Returns:
            List of SessionInfo objects
        
        Example:
            >>> sessions = await service.list_sessions("user_123")
            >>> for session in sessions:
            ...     print(f"{session.device_type}: {session.created_at}")
            browser: 2025-10-22 10:00:00
            mobile: 2025-10-22 09:30:00
        """
        ...
    
    async def get_session_count(self, user_id: str) -> int:
        """
        Get number of active sessions for user.
        
        Args:
            user_id: User identifier
        
        Returns:
            Number of active sessions
        
        Example:
            >>> count = await service.get_session_count("user_123")
            >>> print(f"Active sessions: {count}")
            Active sessions: 2
        """
        ...
    
    async def cleanup_expired_sessions(self, user_id: str) -> int:
        """
        Remove expired sessions from user's session set.
        
        Redis TTL handles session detail expiration automatically, but
        the session set may contain references to expired sessions.
        This method cleans up those references.
        
        Args:
            user_id: User identifier
        
        Returns:
            Number of expired sessions removed
        
        Example:
            >>> removed = await service.cleanup_expired_sessions("user_123")
            >>> print(f"Cleaned up {removed} expired sessions")
            Cleaned up 1 expired sessions
        """
        ...
```

---

## Usage Patterns

### 1. Login Flow

```python
from services.redis.sessions import SessionService
from fastapi import Request, HTTPException

@app.post("/auth/login")
async def login(
    credentials: LoginRequest,
    request: Request
) -> LoginResponse:
    """Login endpoint with session creation"""
    
    # Verify credentials
    user = await authenticate_user(credentials.email, credentials.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Generate JWT
    access_token = create_access_token(user_id=user.id)
    
    # Create session in Redis
    session_service = SessionService(request.app.state.redis)
    session_id = await session_service.create_session(
        user_id=user.id,
        device_type="browser",
        ip_address=request.client.host,
        user_agent=request.headers.get("user-agent")
    )
    
    return LoginResponse(
        access_token=access_token,
        session_id=session_id,
        user=user
    )
```

### 2. Request Authentication Middleware

```python
from fastapi import Depends, HTTPException, Request
from typing import Optional

async def get_current_session(
    request: Request,
    session_id: Optional[str] = Header(None, alias="X-Session-ID")
) -> SessionInfo:
    """Dependency for authenticated routes"""
    
    if not session_id:
        raise HTTPException(status_code=401, detail="No session ID provided")
    
    session_service = SessionService(request.app.state.redis)
    
    # Validate session
    session_info = await session_service.validate_session(session_id)
    if not session_info:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    
    # Refresh session activity
    await session_service.refresh_session(session_id)
    
    return session_info

@app.get("/api/protected-resource")
async def protected_route(
    session: SessionInfo = Depends(get_current_session)
) -> dict:
    """Protected route that requires active session"""
    return {
        "message": "Success",
        "user_id": session.user_id,
        "device": session.device_type
    }
```

### 3. Logout Single Device

```python
@app.post("/auth/logout")
async def logout(
    session_id: str = Header(..., alias="X-Session-ID"),
    request: Request
) -> dict:
    """Logout current device"""
    
    session_service = SessionService(request.app.state.redis)
    success = await session_service.logout(session_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {"message": "Logged out successfully"}
```

### 4. Logout All Devices

```python
@app.post("/auth/logout-all-devices")
async def logout_all(
    current_user: User = Depends(get_current_user),
    request: Request
) -> dict:
    """Logout all devices (e.g., after password change)"""
    
    session_service = SessionService(request.app.state.redis)
    count = await session_service.logout_all_devices(current_user.id)
    
    return {
        "message": f"Logged out {count} devices",
        "devices_logged_out": count
    }
```

### 5. Active Sessions Management

```python
@app.get("/user/sessions")
async def get_active_sessions(
    current_user: User = Depends(get_current_user),
    request: Request
) -> List[SessionInfo]:
    """Get user's active sessions across all devices"""
    
    session_service = SessionService(request.app.state.redis)
    sessions = await session_service.list_sessions(current_user.id)
    
    return sessions

@app.delete("/user/sessions/{session_id}")
async def revoke_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    request: Request
) -> dict:
    """Revoke a specific session (e.g., from sessions management page)"""
    
    session_service = SessionService(request.app.state.redis)
    
    # Verify session belongs to user
    session_info = await session_service.validate_session(session_id)
    if not session_info or session_info.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Logout session
    await session_service.logout(session_id)
    
    return {"message": "Session revoked"}
```

### 6. Periodic Cleanup (Background Task)

```python
from fastapi_utils.tasks import repeat_every

@app.on_event("startup")
@repeat_every(seconds=3600)  # Run every hour
async def cleanup_expired_sessions():
    """Background task to cleanup expired session references"""
    
    redis_client = app.state.redis
    session_service = SessionService(redis_client)
    
    # This would need to iterate over all users
    # In practice, cleanup happens naturally via TTL
    # This is just for orphaned session set members
    logger.info("Session cleanup task completed")
```

---

## Security Considerations

### 1. IP Address Hashing

```python
import hashlib

def hash_ip(ip_address: str) -> str:
    """Hash IP address for privacy"""
    return hashlib.sha256(ip_address.encode()).hexdigest()[:16]

# In create_session:
hashed_ip = hash_ip(ip_address) if ip_address else "unknown"
```

### 2. User Agent Truncation

```python
def truncate_user_agent(user_agent: str, max_length: int = 100) -> str:
    """Truncate user agent to prevent excessive memory usage"""
    if len(user_agent) > max_length:
        return user_agent[:max_length] + "..."
    return user_agent
```

### 3. Session ID Format

```python
def generate_session_id() -> str:
    """Generate cryptographically secure session ID"""
    return f"sess_{uuid.uuid4()}"
```

### 4. Suspicious Activity Detection

```python
async def detect_suspicious_activity(
    user_id: str,
    session_service: SessionService
) -> bool:
    """Detect potentially compromised accounts"""
    
    sessions = await session_service.list_sessions(user_id)
    
    # Check for unusual patterns
    if len(sessions) > 10:  # Too many devices
        return True
    
    # Check for conflicting locations (would need geo-IP)
    # Check for unusual device types
    # Check for rapid session creation
    
    return False
```

---

## Error Handling

### Custom Exceptions

```python
class SessionError(Exception):
    """Base exception for session operations"""
    pass

class SessionNotFoundError(SessionError):
    """Raised when session doesn't exist"""
    pass

class SessionExpiredError(SessionError):
    """Raised when session has expired"""
    pass

class TooManySessionsError(SessionError):
    """Raised when user has too many active sessions"""
    
    def __init__(self, user_id: str, count: int, max_sessions: int = 10):
        self.user_id = user_id
        self.count = count
        self.max_sessions = max_sessions
        super().__init__(
            f"User {user_id} has {count} active sessions (max: {max_sessions})"
        )
```

### Error Scenarios

| Error | Cause | HTTP Status | User Message |
|-------|-------|-------------|--------------|
| `SessionNotFoundError` | Invalid session_id | 401 | "Session not found. Please login again." |
| `SessionExpiredError` | Session older than 24h | 401 | "Session expired. Please login again." |
| `TooManySessionsError` | >10 active sessions | 429 | "Too many active sessions. Please logout unused devices." |
| `RedisConnectionError` | Redis unavailable | 503 | "Authentication service temporarily unavailable." |

---

## Performance Characteristics

### Expected Latency

| Operation | Redis Time | Description |
|-----------|-----------|-------------|
| `create_session` | 2-3ms | HSET + SADD + 2× EXPIRE |
| `validate_session` | 1-2ms | HGETALL |
| `refresh_session` | 1-2ms | HSET + EXPIRE |
| `logout` | 1-2ms | DEL + SREM |
| `logout_all_devices` | 3-10ms | SMEMBERS + DEL × N |
| `list_sessions` | 2-5ms | SMEMBERS + HGETALL × N |
| `get_session_count` | 0.5-1ms | SCARD |

### Memory Usage

| Component | Size per Session | Example |
|-----------|-----------------|---------|
| Session details | ~300 bytes | Hash with 7 fields |
| Session set entry | ~40 bytes | Set member (session_id) |
| **Total** | **~340 bytes** | Per active session |

**Capacity**: 256MB Redis can handle ~750,000 active sessions

---

## Testing Requirements

### Unit Tests (fakeredis)

```python
import pytest
from fakeredis import aioredis as fakeredis
from services.redis.sessions import SessionService, SessionNotFoundError

@pytest.fixture
async def session_service():
    client = fakeredis.FakeRedis(decode_responses=True)
    service = SessionService(client)
    yield service
    await client.flushall()
    await client.close()

@pytest.mark.asyncio
async def test_create_session(session_service):
    """Should create session with metadata"""
    session_id = await session_service.create_session(
        user_id="user_123",
        device_type="browser",
        ip_address="192.168.1.1",
        user_agent="Mozilla/5.0..."
    )
    
    assert session_id.startswith("sess_")
    assert len(session_id) == 41  # "sess_" + UUID (36 chars)

@pytest.mark.asyncio
async def test_validate_session(session_service):
    """Should validate and return session info"""
    session_id = await session_service.create_session(
        user_id="user_123",
        device_type="browser"
    )
    
    session_info = await session_service.validate_session(session_id)
    
    assert session_info is not None
    assert session_info.user_id == "user_123"
    assert session_info.device_type == "browser"
    assert not session_info.is_expired

@pytest.mark.asyncio
async def test_validate_nonexistent_session(session_service):
    """Should return None for invalid session"""
    session_info = await session_service.validate_session("sess_invalid")
    assert session_info is None

@pytest.mark.asyncio
async def test_logout_single_device(session_service):
    """Should logout single session"""
    session_id = await session_service.create_session(
        user_id="user_123",
        device_type="browser"
    )
    
    success = await session_service.logout(session_id)
    assert success is True
    
    # Session should no longer exist
    session_info = await session_service.validate_session(session_id)
    assert session_info is None

@pytest.mark.asyncio
async def test_logout_all_devices(session_service):
    """Should logout all user sessions"""
    # Create 3 sessions
    session_ids = []
    for device in ["browser", "mobile", "api"]:
        session_id = await session_service.create_session(
            user_id="user_123",
            device_type=device
        )
        session_ids.append(session_id)
    
    # Logout all devices
    count = await session_service.logout_all_devices("user_123")
    assert count == 3
    
    # All sessions should be gone
    for session_id in session_ids:
        session_info = await session_service.validate_session(session_id)
        assert session_info is None

@pytest.mark.asyncio
async def test_list_sessions(session_service):
    """Should list all active sessions"""
    # Create 2 sessions
    await session_service.create_session("user_123", "browser")
    await session_service.create_session("user_123", "mobile")
    
    sessions = await session_service.list_sessions("user_123")
    
    assert len(sessions) == 2
    device_types = {s.device_type for s in sessions}
    assert device_types == {"browser", "mobile"}

@pytest.mark.asyncio
async def test_refresh_session(session_service):
    """Should refresh session activity timestamp"""
    session_id = await session_service.create_session("user_123", "browser")
    
    # Get initial last_active
    session1 = await session_service.validate_session(session_id)
    initial_last_active = session1.last_active
    
    # Wait a bit and refresh
    await asyncio.sleep(0.1)
    await session_service.refresh_session(session_id)
    
    # last_active should be updated
    session2 = await session_service.validate_session(session_id)
    assert session2.last_active > initial_last_active
```

### Integration Tests

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_session_expiration(redis_server):
    """Test session TTL expiration with real Redis"""
    client = await redis.from_url(f"redis://{redis_server.host}:{redis_server.port}")
    service = SessionService(client)
    
    # Create session with 1 second TTL (for testing)
    service.session_ttl = 1
    session_id = await service.create_session("user_123", "browser")
    
    # Session should exist immediately
    assert await service.validate_session(session_id) is not None
    
    # Wait for expiration
    await asyncio.sleep(1.5)
    
    # Session should be expired
    assert await service.validate_session(session_id) is None
    
    await client.close()
```

---

## Implementation Checklist

- [ ] Create `services/redis/sessions.py`
- [ ] Implement `SessionService` class
- [ ] Implement `create_session()` with metadata
- [ ] Implement `validate_session()` with deserialization
- [ ] Implement `refresh_session()` to extend TTL
- [ ] Implement `logout()` for single device
- [ ] Implement `logout_all_devices()` for security actions
- [ ] Implement `list_sessions()` for user management
- [ ] Implement `get_session_count()`
- [ ] Implement `cleanup_expired_sessions()`
- [ ] Add custom exceptions
- [ ] Add IP hashing and user agent truncation
- [ ] Add memory fallback logic
- [ ] Add comprehensive logging
- [ ] Write unit tests (fakeredis)
- [ ] Write integration tests (pytest-redis)
- [ ] Integrate with authentication middleware
- [ ] Add session management UI endpoints

---

## Dependencies

```python
# requirements.txt
redis[hiredis]>=5.0.0  # Redis client
pydantic>=2.0.0        # Data validation
```

---

**Contract Status**: ✅ **APPROVED**  
**Implementation Priority**: **MEDIUM** (Week 3)  
**Estimated Effort**: 2-3 days (including tests)  
**Next**: Implement `services/redis/sessions.py`
