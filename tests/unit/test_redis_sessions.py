"""
Unit tests for SessionService

Tests session management functionality using fakeredis:
- Session creation with metadata
- Session validation and expiration
- Session refresh to extend TTL
- Logout single/all devices
- Session listing and counting
- Expired session cleanup
- Error handling
"""

import asyncio
from datetime import datetime, timedelta

import pytest
from fakeredis import aioredis as fakeredis

from services.redis.sessions import (
    SessionError,
    SessionExpiredError,
    SessionInfo,
    SessionNotFoundError,
    SessionService,
    TooManySessionsError,
)


@pytest.fixture
async def redis_client():
    """Create fake Redis client for testing"""
    client = await fakeredis.FakeRedis(decode_responses=True)
    yield client
    await client.flushall()
    await client.close()


@pytest.fixture
async def session_service(redis_client):
    """Create SessionService with fake Redis"""
    return SessionService(redis_client)


class TestSessionCreation:
    """Tests for create_session()"""

    @pytest.mark.asyncio
    async def test_create_session_basic(self, session_service):
        """Should create session with minimal metadata"""
        session_id = await session_service.create_session(
            user_id="user_123", device_type="browser"
        )

        assert session_id.startswith("sess_")
        assert len(session_id) == 41  # "sess_" + UUID (36 chars)

    @pytest.mark.asyncio
    async def test_create_session_with_full_metadata(self, session_service):
        """Should create session with all metadata fields"""
        session_id = await session_service.create_session(
            user_id="user_123",
            device_type="mobile",
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)",
        )

        # Validate session was created
        session_info = await session_service.validate_session(session_id)

        assert session_info is not None
        assert session_info.user_id == "user_123"
        assert session_info.device_type == "mobile"
        assert session_info.ip_address != "192.168.1.1"  # Should be hashed
        assert len(session_info.ip_address) == 16  # SHA256 truncated to 16 chars
        assert "iPhone" in session_info.user_agent

    @pytest.mark.asyncio
    async def test_create_session_hashes_ip(self, session_service):
        """Should hash IP address for privacy"""
        session_id = await session_service.create_session(
            user_id="user_123", device_type="browser", ip_address="192.168.1.1"
        )

        session_info = await session_service.validate_session(session_id)

        # IP should be hashed, not plaintext
        assert session_info.ip_address != "192.168.1.1"
        assert len(session_info.ip_address) == 16

    @pytest.mark.asyncio
    async def test_create_session_truncates_long_user_agent(self, session_service):
        """Should truncate user agent to prevent memory bloat"""
        long_ua = "A" * 200  # 200 character user agent

        session_id = await session_service.create_session(
            user_id="user_123", device_type="browser", user_agent=long_ua
        )

        session_info = await session_service.validate_session(session_id)

        # Should be truncated to 100 chars + "..."
        assert len(session_info.user_agent) == 103
        assert session_info.user_agent.endswith("...")

    @pytest.mark.asyncio
    async def test_create_session_without_optional_fields(self, session_service):
        """Should handle missing IP and user agent"""
        session_id = await session_service.create_session(
            user_id="user_123", device_type="api"
        )

        session_info = await session_service.validate_session(session_id)

        assert session_info.ip_address == "unknown"
        assert session_info.user_agent == "unknown"

    @pytest.mark.asyncio
    async def test_create_session_adds_to_user_set(self, session_service, redis_client):
        """Should add session ID to user's session set"""
        session_id = await session_service.create_session(
            user_id="user_123", device_type="browser"
        )

        # Check Redis set
        user_sessions_key = "user_sessions:user_123"
        session_ids = await redis_client.smembers(user_sessions_key)

        assert session_id in session_ids

    @pytest.mark.asyncio
    async def test_create_session_sets_ttl(self, session_service, redis_client):
        """Should set TTL on session and user set"""
        session_id = await session_service.create_session(
            user_id="user_123", device_type="browser"
        )

        # Check TTL on session key
        session_key = f"session:{session_id}"
        ttl = await redis_client.ttl(session_key)
        assert ttl > 0
        assert ttl <= 86400  # 24 hours

        # Check TTL on user sessions set
        user_sessions_key = "user_sessions:user_123"
        ttl = await redis_client.ttl(user_sessions_key)
        assert ttl > 0
        assert ttl <= 86400

    @pytest.mark.asyncio
    async def test_create_session_enforces_max_limit(self, session_service):
        """Should reject session creation if user has 10+ sessions"""
        # Create 10 sessions
        for i in range(10):
            await session_service.create_session(
                user_id="user_123", device_type=f"device_{i}"
            )

        # 11th session should raise error
        with pytest.raises(TooManySessionsError) as exc_info:
            await session_service.create_session(
                user_id="user_123", device_type="device_11"
            )

        assert exc_info.value.user_id == "user_123"
        assert exc_info.value.count == 10
        assert exc_info.value.max_sessions == 10


class TestSessionValidation:
    """Tests for validate_session()"""

    @pytest.mark.asyncio
    async def test_validate_existing_session(self, session_service):
        """Should return session info for valid session"""
        session_id = await session_service.create_session(
            user_id="user_123", device_type="browser"
        )

        session_info = await session_service.validate_session(session_id)

        assert session_info is not None
        assert session_info.session_id == session_id
        assert session_info.user_id == "user_123"
        assert session_info.device_type == "browser"
        assert isinstance(session_info.created_at, datetime)
        assert isinstance(session_info.last_active, datetime)

    @pytest.mark.asyncio
    async def test_validate_nonexistent_session(self, session_service):
        """Should return None for invalid session ID"""
        session_info = await session_service.validate_session("sess_invalid_id")

        assert session_info is None

    @pytest.mark.asyncio
    async def test_validate_expired_session(self, session_service, redis_client):
        """Should return None and cleanup expired session"""
        session_id = await session_service.create_session(
            user_id="user_123", device_type="browser"
        )

        # Manually set last_active to 25 hours ago (expired)
        session_key = f"session:{session_id}"
        expired_time = datetime.utcnow() - timedelta(hours=25)
        await redis_client.hset(session_key, "last_active", expired_time.isoformat())

        # Should return None for expired session
        session_info = await session_service.validate_session(session_id)

        assert session_info is None

        # Session should be deleted
        exists = await redis_client.exists(session_key)
        assert not exists

    @pytest.mark.asyncio
    async def test_validate_session_not_expired(self, session_service):
        """Should return info for recently active session"""
        session_id = await session_service.create_session(
            user_id="user_123", device_type="browser"
        )

        session_info = await session_service.validate_session(session_id)

        assert session_info is not None
        assert not session_info.is_expired


class TestSessionRefresh:
    """Tests for refresh_session()"""

    @pytest.mark.asyncio
    async def test_refresh_existing_session(self, session_service):
        """Should update last_active timestamp"""
        session_id = await session_service.create_session(
            user_id="user_123", device_type="browser"
        )

        # Get initial last_active
        session1 = await session_service.validate_session(session_id)
        initial_last_active = session1.last_active

        # Wait a bit
        await asyncio.sleep(0.1)

        # Refresh session
        refreshed = await session_service.refresh_session(session_id)
        assert refreshed is True

        # last_active should be updated
        session2 = await session_service.validate_session(session_id)
        assert session2.last_active > initial_last_active

    @pytest.mark.asyncio
    async def test_refresh_nonexistent_session(self, session_service):
        """Should return False for invalid session"""
        refreshed = await session_service.refresh_session("sess_invalid_id")

        assert refreshed is False

    @pytest.mark.asyncio
    async def test_refresh_extends_ttl(self, session_service, redis_client):
        """Should extend TTL to 24 hours"""
        session_id = await session_service.create_session(
            user_id="user_123", device_type="browser"
        )

        # Set TTL to 1 hour for testing
        session_key = f"session:{session_id}"
        await redis_client.expire(session_key, 3600)

        # Refresh should extend to 24 hours
        await session_service.refresh_session(session_id)

        ttl = await redis_client.ttl(session_key)
        assert ttl > 3600  # Should be more than 1 hour
        assert ttl <= 86400  # Should be at most 24 hours

    @pytest.mark.asyncio
    async def test_refresh_extends_user_session_set_ttl(self, session_service, redis_client):
        """Should refresh TTL for user session set as well"""
        session_id = await session_service.create_session(
            user_id="user_123", device_type="browser"
        )

        user_sessions_key = "user_sessions:user_123"

        # Set shorter TTL to ensure refresh updates it
        await redis_client.expire(user_sessions_key, 300)

        await session_service.refresh_session(session_id)

        ttl = await redis_client.ttl(user_sessions_key)
        assert ttl > 300
        assert ttl <= 86400


class TestLogout:
    """Tests for logout()"""

    @pytest.mark.asyncio
    async def test_logout_single_session(self, session_service):
        """Should delete session and remove from user set"""
        session_id = await session_service.create_session(
            user_id="user_123", device_type="browser"
        )

        # Logout
        success = await session_service.logout(session_id)
        assert success is True

        # Session should no longer exist
        session_info = await session_service.validate_session(session_id)
        assert session_info is None

        # Should be removed from user's session set
        count = await session_service.get_session_count("user_123")
        assert count == 0

    @pytest.mark.asyncio
    async def test_logout_nonexistent_session(self, session_service):
        """Should return False for invalid session"""
        success = await session_service.logout("sess_invalid_id")

        assert success is False

    @pytest.mark.asyncio
    async def test_logout_preserves_other_sessions(self, session_service):
        """Should not affect other sessions for same user"""
        # Create 2 sessions
        session_id1 = await session_service.create_session(
            user_id="user_123", device_type="browser"
        )
        session_id2 = await session_service.create_session(
            user_id="user_123", device_type="mobile"
        )

        # Logout first session
        await session_service.logout(session_id1)

        # Second session should still exist
        session_info2 = await session_service.validate_session(session_id2)
        assert session_info2 is not None

        # Session count should be 1
        count = await session_service.get_session_count("user_123")
        assert count == 1


class TestLogoutAllDevices:
    """Tests for logout_all_devices()"""

    @pytest.mark.asyncio
    async def test_logout_all_devices(self, session_service):
        """Should delete all sessions for user"""
        # Create 3 sessions
        session_ids = []
        for device in ["browser", "mobile", "api"]:
            session_id = await session_service.create_session(
                user_id="user_123", device_type=device
            )
            session_ids.append(session_id)

        # Logout all devices
        count = await session_service.logout_all_devices("user_123")
        assert count == 3

        # All sessions should be gone
        for session_id in session_ids:
            session_info = await session_service.validate_session(session_id)
            assert session_info is None

        # Session count should be 0
        session_count = await session_service.get_session_count("user_123")
        assert session_count == 0

    @pytest.mark.asyncio
    async def test_logout_all_devices_no_sessions(self, session_service):
        """Should handle user with no sessions"""
        count = await session_service.logout_all_devices("user_no_sessions")

        assert count == 0

    @pytest.mark.asyncio
    async def test_logout_all_devices_preserves_other_users(self, session_service):
        """Should not affect other users' sessions"""
        # Create sessions for 2 users
        session_id1 = await session_service.create_session(
            user_id="user_123", device_type="browser"
        )
        session_id2 = await session_service.create_session(
            user_id="user_456", device_type="browser"
        )

        # Logout all devices for user_123
        await session_service.logout_all_devices("user_123")

        # user_123 session should be gone
        assert await session_service.validate_session(session_id1) is None

        # user_456 session should still exist
        assert await session_service.validate_session(session_id2) is not None


class TestListSessions:
    """Tests for list_sessions()"""

    @pytest.mark.asyncio
    async def test_list_sessions_multiple_devices(self, session_service):
        """Should list all active sessions"""
        # Create 3 sessions
        await session_service.create_session("user_123", "browser")
        await session_service.create_session("user_123", "mobile")
        await session_service.create_session("user_123", "api")

        sessions = await session_service.list_sessions("user_123")

        assert len(sessions) == 3
        device_types = {s.device_type for s in sessions}
        assert device_types == {"browser", "mobile", "api"}

    @pytest.mark.asyncio
    async def test_list_sessions_no_sessions(self, session_service):
        """Should return empty list for user with no sessions"""
        sessions = await session_service.list_sessions("user_no_sessions")

        assert sessions == []

    @pytest.mark.asyncio
    async def test_list_sessions_filters_expired(self, session_service, redis_client):
        """Should exclude expired sessions from list"""
        # Create 2 sessions
        session_id1 = await session_service.create_session(
            user_id="user_123", device_type="browser"
        )
        session_id2 = await session_service.create_session(
            user_id="user_123", device_type="mobile"
        )

        # Manually expire first session
        session_key1 = f"session:{session_id1}"
        expired_time = datetime.utcnow() - timedelta(hours=25)
        await redis_client.hset(session_key1, "last_active", expired_time.isoformat())

        # Should only return 1 valid session
        sessions = await session_service.list_sessions("user_123")

        assert len(sessions) == 1
        assert sessions[0].device_type == "mobile"


class TestSessionCount:
    """Tests for get_session_count()"""

    @pytest.mark.asyncio
    async def test_get_session_count(self, session_service):
        """Should return correct count"""
        # Create 3 sessions
        await session_service.create_session("user_123", "browser")
        await session_service.create_session("user_123", "mobile")
        await session_service.create_session("user_123", "api")

        count = await session_service.get_session_count("user_123")

        assert count == 3

    @pytest.mark.asyncio
    async def test_get_session_count_no_sessions(self, session_service):
        """Should return 0 for user with no sessions"""
        count = await session_service.get_session_count("user_no_sessions")

        assert count == 0


class TestCleanupExpiredSessions:
    """Tests for cleanup_expired_sessions()"""

    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions(self, session_service, redis_client):
        """Should remove expired session references from user set"""
        # Create 2 sessions
        session_id1 = await session_service.create_session(
            user_id="user_123", device_type="browser"
        )
        session_id2 = await session_service.create_session(
            user_id="user_123", device_type="mobile"
        )

        # Manually delete first session (simulate expiration)
        session_key1 = f"session:{session_id1}"
        await redis_client.delete(session_key1)

        # Cleanup should remove orphaned reference
        removed = await session_service.cleanup_expired_sessions("user_123")

        assert removed == 1

        # Session count should now be 1
        count = await session_service.get_session_count("user_123")
        assert count == 1

    @pytest.mark.asyncio
    async def test_cleanup_no_expired_sessions(self, session_service):
        """Should return 0 if no expired sessions"""
        # Create 2 valid sessions
        await session_service.create_session("user_123", "browser")
        await session_service.create_session("user_123", "mobile")

        # Cleanup should find nothing
        removed = await session_service.cleanup_expired_sessions("user_123")

        assert removed == 0

        # Session count should still be 2
        count = await session_service.get_session_count("user_123")
        assert count == 2


class TestEdgeCases:
    """Tests for edge cases and error scenarios"""

    @pytest.mark.asyncio
    async def test_session_info_is_expired_property(self, session_service):
        """Should correctly identify expired sessions"""
        session_id = await session_service.create_session(
            user_id="user_123", device_type="browser"
        )

        session_info = await session_service.validate_session(session_id)

        # Fresh session should not be expired
        assert not session_info.is_expired

        # Manually set last_active to 25 hours ago
        session_info.last_active = datetime.utcnow() - timedelta(hours=25)

        # Now should be expired
        assert session_info.is_expired

    @pytest.mark.asyncio
    async def test_concurrent_session_creation(self, session_service):
        """Should handle concurrent session creation"""
        # Create 5 sessions concurrently
        tasks = [
            session_service.create_session("user_123", f"device_{i}")
            for i in range(5)
        ]

        session_ids = await asyncio.gather(*tasks)

        # All should be unique
        assert len(set(session_ids)) == 5

        # Session count should be 5
        count = await session_service.get_session_count("user_123")
        assert count == 5
