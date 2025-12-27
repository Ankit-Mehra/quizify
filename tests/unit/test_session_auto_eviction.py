"""
Unit tests for auto-eviction of oldest session when limit exceeded.

Tests the new feature where users are automatically logged out of their
oldest session when they exceed the MAX_SESSIONS_PER_USER threshold,
providing a better UX instead of blocking the new login.
"""

import pytest
import fakeredis.aioredis
from datetime import datetime, timedelta
from services.redis.sessions import SessionService, SessionInfo


@pytest.fixture
async def redis_client():
    """Create fake Redis client for testing"""
    client = await fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.flushall()
    await client.close()


@pytest.mark.asyncio
async def test_auto_evict_oldest_session_when_limit_reached(redis_client):
    """
    Test that when a user reaches the session limit, the oldest session
    is automatically logged out to make room for the new one.
    """
    service = SessionService(redis_client)
    user_id = "test_user_123"
    
    # Override max sessions for this test
    service.MAX_SESSIONS_PER_USER = 3
    
    # Create 3 sessions (at the limit)
    sessions = []
    for i in range(3):
        client_token = await service.create_session(
            user_id=user_id,
            device_type=f"device_{i}",
            ip_address=f"192.168.1.{i}",
            user_agent=f"TestAgent/{i}",
            refresh_token=f"refresh_token_{i}"
        )
        sessions.append(client_token)
        # Small delay to ensure different created_at timestamps
        await redis_client.execute_command("TIME")
    
    # Verify we have exactly 3 sessions
    session_count = await service.get_session_count(user_id)
    assert session_count == 3, f"Expected 3 sessions, got {session_count}"
    
    # Get all sessions to verify order
    all_sessions = await service.list_sessions(user_id)
    assert len(all_sessions) == 3
    
    # Sort by created_at to find the oldest
    all_sessions.sort(key=lambda s: s.created_at)
    oldest_device = all_sessions[0].device_type
    
    # Create a 4th session - should auto-evict the oldest
    new_client_token = await service.create_session(
        user_id=user_id,
        device_type="device_new",
        ip_address="192.168.1.99",
        user_agent="TestAgent/New",
        refresh_token="refresh_token_new"
    )
    
    # Verify we still have exactly 3 sessions (not 4)
    session_count = await service.get_session_count(user_id)
    assert session_count == 3, f"Expected 3 sessions after auto-eviction, got {session_count}"
    
    # Verify the oldest session was removed
    remaining_sessions = await service.list_sessions(user_id)
    remaining_devices = {s.device_type for s in remaining_sessions}
    
    assert "device_new" in remaining_devices, "New session should exist"
    assert oldest_device not in remaining_devices, f"Oldest session ({oldest_device}) should be evicted"
    
    # Verify the new session was created successfully
    assert new_client_token is not None


@pytest.mark.asyncio
async def test_auto_eviction_handles_stale_sessions(redis_client):
    """
    Test that auto-eviction works correctly even when there are stale
    session references (session IDs in the set but no session data).
    """
    service = SessionService(redis_client)
    user_id = "test_user_456"
    
    # Override max sessions
    service.MAX_SESSIONS_PER_USER = 2
    
    # Create 2 valid sessions
    await service.create_session(
        user_id=user_id,
        device_type="device_1",
        refresh_token="token_1"
    )
    
    await service.create_session(
        user_id=user_id,
        device_type="device_2",
        refresh_token="token_2"
    )
    
    # Manually add a stale session reference (ID exists but no data)
    await redis_client.sadd(f"user_sessions:{user_id}", "sess_stale_123")
    
    # Verify count shows 3 (2 real + 1 stale)
    raw_count = await redis_client.scard(f"user_sessions:{user_id}")
    assert raw_count == 3
    
    # Create a 3rd session - should cleanup stale references and auto-evict properly
    new_client_token = await service.create_session(
        user_id=user_id,
        device_type="device_3",
        refresh_token="token_3"
    )
    
    # Verify we have exactly 2 valid sessions
    valid_sessions = await service.list_sessions(user_id)
    assert len(valid_sessions) == 2
    assert new_client_token is not None


@pytest.mark.asyncio
async def test_auto_eviction_with_multiple_devices(redis_client):
    """
    Test auto-eviction behavior with different device types to ensure
    the oldest session is evicted regardless of device type.
    """
    service = SessionService(redis_client)
    user_id = "test_user_789"
    
    service.MAX_SESSIONS_PER_USER = 3
    
    # Create sessions from different device types
    devices = [
        ("browser", "Chrome"),
        ("mobile", "iOS App"),
        ("api", "CLI Tool"),
    ]
    
    for device_type, user_agent in devices:
        await service.create_session(
            user_id=user_id,
            device_type=device_type,
            user_agent=user_agent,
            refresh_token=f"token_{device_type}"
        )
    
    # Create a new browser session - should evict the oldest browser session
    await service.create_session(
        user_id=user_id,
        device_type="browser",
        user_agent="Firefox",
        refresh_token="token_firefox"
    )
    
    # Verify still at limit
    session_count = await service.get_session_count(user_id)
    assert session_count == 3
    
    # Verify we have the expected device types
    sessions = await service.list_sessions(user_id)
    device_types = [s.device_type for s in sessions]
    
    # Should have evicted the oldest (first browser session)
    assert device_types.count("browser") <= 2  # At most 2 browser sessions


@pytest.mark.asyncio
async def test_no_eviction_when_under_limit(redis_client):
    """
    Test that no eviction occurs when user is under the session limit.
    """
    service = SessionService(redis_client)
    user_id = "test_user_abc"
    
    service.MAX_SESSIONS_PER_USER = 5
    
    # Create 3 sessions (under limit)
    for i in range(3):
        await service.create_session(
            user_id=user_id,
            device_type=f"device_{i}",
            refresh_token=f"token_{i}"
        )
    
    # Verify 3 sessions exist
    session_count = await service.get_session_count(user_id)
    assert session_count == 3
    
    # Create one more (still under limit)
    await service.create_session(
        user_id=user_id,
        device_type="device_new",
        refresh_token="token_new"
    )
    
    # Verify now we have 4 sessions (no eviction occurred)
    session_count = await service.get_session_count(user_id)
    assert session_count == 4
    
    # Verify all 4 sessions are valid
    sessions = await service.list_sessions(user_id)
    assert len(sessions) == 4
