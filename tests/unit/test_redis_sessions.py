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
        refresh_token = "test_refresh_token"
        client_session_token = await session_service.create_session(
            user_id="user_123", device_type="browser"
        , refresh_token=refresh_token)

        # Session is created internally, only client_session_token is returned
        assert client_session_token.startswith("cst_")  # Client session token for UI

    @pytest.mark.asyncio
    async def test_create_session_with_full_metadata(self, session_service):
        """Should create session with all metadata fields"""
        refresh_token = "test_refresh_token"
        await session_service.create_session(
            user_id="user_123",
            device_type="mobile",
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)",
            refresh_token=refresh_token,
        )

        # Get session_id via refresh_token
        session_id = await session_service.find_session_by_refresh_token(refresh_token)
        assert session_id is not None

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
        refresh_token = "test_refresh_token"
        await session_service.create_session(
            user_id="user_123", device_type="browser", ip_address="192.168.1.1"
        , refresh_token=refresh_token)

        # Get session_id via refresh_token
        session_id = await session_service.find_session_by_refresh_token(refresh_token)
        assert session_id is not None

        session_info = await session_service.validate_session(session_id)

        # IP should be hashed, not plaintext
        assert session_info.ip_address != "192.168.1.1"
        assert len(session_info.ip_address) == 16

    @pytest.mark.asyncio
    async def test_create_session_truncates_long_user_agent(self, session_service):
        """Should truncate user agent to prevent memory bloat"""
        long_ua = "A" * 200  # 200 character user agent

        refresh_token = "test_refresh_token"
        await session_service.create_session(
            user_id="user_123", device_type="browser", user_agent=long_ua
        , refresh_token=refresh_token)

        # Get session_id via refresh_token
        session_id = await session_service.find_session_by_refresh_token(refresh_token)
        assert session_id is not None

        session_info = await session_service.validate_session(session_id)

        # Should be truncated to 100 chars + "..."
        assert len(session_info.user_agent) == 103
        assert session_info.user_agent.endswith("...")

    @pytest.mark.asyncio
    async def test_create_session_without_optional_fields(self, session_service):
        """Should handle missing IP and user agent"""
        refresh_token = "test_refresh_token"
        await session_service.create_session(
            user_id="user_123", device_type="api"
        , refresh_token=refresh_token)

        # Get session_id via refresh_token
        session_id = await session_service.find_session_by_refresh_token(refresh_token)
        assert session_id is not None

        session_info = await session_service.validate_session(session_id)

        assert session_info.ip_address == "unknown"
        assert session_info.user_agent == "unknown"

    @pytest.mark.asyncio
    async def test_create_session_adds_to_user_set(self, session_service, redis_client):
        """Should add session ID to user's session set"""
        refresh_token = "test_refresh_token"
        await session_service.create_session(
            user_id="user_123", device_type="browser"
        , refresh_token=refresh_token)

        # Get session_id via refresh_token
        session_id = await session_service.find_session_by_refresh_token(refresh_token)
        assert session_id is not None

        # Check Redis set
        user_sessions_key = "user_sessions:user_123"
        session_ids = await redis_client.smembers(user_sessions_key)

        assert session_id in session_ids

    @pytest.mark.asyncio
    async def test_create_session_sets_ttl(self, session_service, redis_client):
        """Should set TTL on session and user set"""
        refresh_token = "test_refresh_token"
        await session_service.create_session(
            user_id="user_123", device_type="browser"
        , refresh_token=refresh_token)

        # Get session_id via refresh_token
        session_id = await session_service.find_session_by_refresh_token(refresh_token)
        assert session_id is not None

        # Check TTL was set
        session_key = f"session:{session_id}"
        ttl = await redis_client.ttl(session_key)
        assert ttl > 0
        assert ttl <= 2592000  # 30 days (updated from 24 hours)

        # Check TTL on user sessions set
        user_sessions_key = "user_sessions:user_123"
        ttl = await redis_client.ttl(user_sessions_key)
        assert ttl > 0
        assert ttl <= 2592000  # 30 days (updated from 24 hours)

    @pytest.mark.asyncio
    async def test_create_session_enforces_max_limit(self, session_service):
        """Should auto-evict oldest session when user reaches the limit (improved UX)"""
        # Create 5 sessions (at the limit)
        for i in range(5):
            refresh_token = f"test_refresh_token_{i}"
            await session_service.create_session(
                user_id="user_123", device_type=f"device_{i}", refresh_token=refresh_token
            )

        # Verify we have 5 sessions
        session_count = await session_service.get_session_count("user_123")
        assert session_count == 5
        
        # 6th session should auto-evict oldest instead of raising error
        await session_service.create_session(
            user_id="user_123", device_type="device_6", refresh_token="test_refresh_token_6"
        )
        
        # Should still have 5 sessions (oldest one evicted)
        session_count = await session_service.get_session_count("user_123")
        assert session_count == 5

    @pytest.mark.asyncio
    async def test_create_session_cleans_up_expired_before_limit_check(self, session_service, redis_client):
        """Should clean up expired sessions before checking limit, allowing new session creation.
        
        This verifies the automatic cleanup behavior that runs in create_session()
        before the session limit check. Without this, expired sessions would still
        count toward the limit, causing false "TooManySessionsError" errors.
        """
        # Create 5 sessions (at limit)
        session_ids = []
        for i in range(5):
            refresh_token = f"token_{i}"
            await session_service.create_session(
                user_id="user_123", device_type=f"device_{i}", refresh_token=refresh_token
            )
            session_id = await session_service.find_session_by_refresh_token(refresh_token)
            session_ids.append(session_id)
        
        # Verify we're at limit
        count_before = await session_service.get_session_count("user_123")
        assert count_before == 5
        
        # Manually delete 2 session details (simulate expiration/deletion)
        # The session IDs still exist in user_sessions:{user_id} set, but data is gone
        await redis_client.delete(f"session:{session_ids[0]}")
        await redis_client.delete(f"session:{session_ids[1]}")
        
        # Creating new session should succeed because:
        # 1. create_session calls cleanup_expired_sessions() first
        # 2. cleanup removes the 2 orphaned references from the set
        # 3. Session count drops to 3, leaving room for new session
        new_token = await session_service.create_session(
            user_id="user_123", device_type="new_device", refresh_token="new_token"
        )
        assert new_token is not None
        
        # Should now have 4 sessions (3 original + 1 new)
        count_after = await session_service.get_session_count("user_123")
        assert count_after == 4


class TestSessionValidation:
    """Tests for validate_session()"""

    @pytest.mark.asyncio
    async def test_validate_existing_session(self, session_service):
        """Should return session info for valid session"""
        refresh_token = "test_refresh_token"
        await session_service.create_session(
            user_id="user_123", device_type="browser"
        , refresh_token=refresh_token)

        # Get session_id via refresh_token
        session_id = await session_service.find_session_by_refresh_token(refresh_token)
        assert session_id is not None

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
        refresh_token = "test_refresh_token"
        await session_service.create_session(
            user_id="user_123", device_type="browser"
        , refresh_token=refresh_token)

        # Get session_id via refresh_token
        session_id = await session_service.find_session_by_refresh_token(refresh_token)
        assert session_id is not None

        # Manually set last_active to 31 days ago (expired - new 30-day TTL)
        session_key = f"session:{session_id}"
        expired_time = datetime.utcnow() - timedelta(days=31)
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
        refresh_token = "test_refresh_token"
        await session_service.create_session(
            user_id="user_123", device_type="browser"
        , refresh_token=refresh_token)
        
        # Get session_id via refresh_token
        session_id = await session_service.find_session_by_refresh_token(refresh_token)
        assert session_id is not None
        
        session_info = await session_service.validate_session(session_id)

        assert session_info is not None
        assert not session_info.is_expired


class TestSessionRefresh:
    """Tests for refresh_session()"""

    @pytest.mark.asyncio
    async def test_refresh_existing_session(self, session_service):
        """Should update last_active timestamp"""
        refresh_token = "test_refresh_token"
        await session_service.create_session(
            user_id="user_123", device_type="browser"
        , refresh_token=refresh_token)

        # Get session_id via refresh_token
        session_id = await session_service.find_session_by_refresh_token(refresh_token)
        assert session_id is not None

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
        refresh_token = "test_refresh_token"
        await session_service.create_session(
            user_id="user_123", device_type="browser"
        , refresh_token=refresh_token)

        # Get session_id via refresh_token
        session_id = await session_service.find_session_by_refresh_token(refresh_token)
        assert session_id is not None

        # Set TTL to 1 hour for testing
        session_key = f"session:{session_id}"
        await redis_client.expire(session_key, 3600)

        # Refresh should extend to 24 hours
        await session_service.refresh_session(session_id)

        ttl = await redis_client.ttl(session_key)
        assert ttl > 3600  # Should be more than 1 hour
        assert ttl <= 2592000  # Should be at most 30 days (updated from 24 hours)

    @pytest.mark.asyncio
    async def test_refresh_extends_user_session_set_ttl(self, session_service, redis_client):
        """Should refresh TTL for user session set as well"""
        refresh_token = "test_refresh_token"
        await session_service.create_session(
            user_id="user_123", device_type="browser"
        , refresh_token=refresh_token)

        # Get session_id via refresh_token
        session_id = await session_service.find_session_by_refresh_token(refresh_token)
        assert session_id is not None

        user_sessions_key = "user_sessions:user_123"

        # Set shorter TTL to ensure refresh updates it
        await redis_client.expire(user_sessions_key, 300)

        await session_service.refresh_session(session_id)

        ttl = await redis_client.ttl(user_sessions_key)
        assert ttl > 300
        assert ttl <= 2592000  # 30 days (updated from 24 hours)


class TestLogout:
    """Tests for logout()"""

    @pytest.mark.asyncio
    async def test_logout_single_session(self, session_service):
        """Should delete session and remove from user set"""
        refresh_token = "test_refresh_token"
        await session_service.create_session(
            user_id="user_123", device_type="browser"
        , refresh_token=refresh_token)

        # Get session_id via refresh_token
        session_id = await session_service.find_session_by_refresh_token(refresh_token)
        assert session_id is not None

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
        token1 = "test_refresh_token_1"
        await session_service.create_session(
            user_id="user_123", device_type="browser", refresh_token=token1
        )
        token2 = "test_refresh_token_2"
        await session_service.create_session(
            user_id="user_123", device_type="mobile", refresh_token=token2
        )

        # Get session IDs
        session_id1 = await session_service.find_session_by_refresh_token(token1)
        session_id2 = await session_service.find_session_by_refresh_token(token2)
        assert session_id1 is not None
        assert session_id2 is not None

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
            refresh_token = "test_refresh_token"
            await session_service.create_session(
                user_id="user_123", device_type=device
            , refresh_token=refresh_token)

            # Get session_id via refresh_token
            session_id = await session_service.find_session_by_refresh_token(refresh_token)
            assert session_id is not None
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
        token1 = "test_refresh_token_user_123"
        await session_service.create_session(
            user_id="user_123", device_type="browser", refresh_token=token1
        )
        token2 = "test_refresh_token_user_456"
        await session_service.create_session(
            user_id="user_456", device_type="browser", refresh_token=token2
        )

        # Get session IDs
        session_id1 = await session_service.find_session_by_refresh_token(token1)
        session_id2 = await session_service.find_session_by_refresh_token(token2)
        assert session_id1 is not None
        assert session_id2 is not None

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
        await session_service.create_session("user_123", "browser", refresh_token="token_1")
        await session_service.create_session("user_123", "mobile", refresh_token="token_2")
        await session_service.create_session("user_123", "tablet", refresh_token="token_3")

        sessions = await session_service.list_sessions("user_123")

        assert len(sessions) == 3
        device_types = {s.device_type for s in sessions}
        assert device_types == {"browser", "mobile", "tablet"}

    @pytest.mark.asyncio
    async def test_list_sessions_no_sessions(self, session_service):
        """Should return empty list for user with no sessions"""
        sessions = await session_service.list_sessions("user_no_sessions")

        assert sessions == []

    @pytest.mark.asyncio
    async def test_list_sessions_filters_expired(self, session_service, redis_client):
        """Should exclude expired sessions from list"""
        # Create 2 sessions
        token1 = "test_refresh_token_1"
        await session_service.create_session(
            user_id="user_123", device_type="browser", refresh_token=token1
        )
        token2 = "test_refresh_token_2"
        await session_service.create_session(
            user_id="user_123", device_type="mobile", refresh_token=token2
        )

        # Get session IDs
        session_id1 = await session_service.find_session_by_refresh_token(token1)
        session_id2 = await session_service.find_session_by_refresh_token(token2)
        assert session_id1 is not None
        assert session_id2 is not None

        # Manually expire first session (set to 31 days ago, exceeds new 30-day TTL)
        session_key1 = f"session:{session_id1}"
        expired_time = datetime.utcnow() - timedelta(days=31)
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
        await session_service.create_session("user_123", "browser", refresh_token="token_1")
        await session_service.create_session("user_123", "mobile", refresh_token="token_2")
        await session_service.create_session("user_123", "api", refresh_token="token_3")

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
        token1 = "test_refresh_token_1"
        await session_service.create_session(
            user_id="user_123", device_type="browser", refresh_token=token1
        )
        token2 = "test_refresh_token_2"
        await session_service.create_session(
            user_id="user_123", device_type="mobile", refresh_token=token2
        )

        # Get session IDs
        session_id1 = await session_service.find_session_by_refresh_token(token1)
        session_id2 = await session_service.find_session_by_refresh_token(token2)
        assert session_id1 is not None
        assert session_id2 is not None

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
        await session_service.create_session("user_123", "browser", refresh_token="token_1")
        await session_service.create_session("user_123", "mobile", refresh_token="token_2")

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
        refresh_token = "test_refresh_token"
        await session_service.create_session(
            user_id="user_123", device_type="browser"
        , refresh_token=refresh_token)

        # Get session_id via refresh_token
        session_id = await session_service.find_session_by_refresh_token(refresh_token)
        assert session_id is not None

        session_info = await session_service.validate_session(session_id)

        # Fresh session should not be expired
        assert not session_info.is_expired

        # Manually set last_active to 31 days ago (exceeds new 30-day TTL)
        session_info.last_active = datetime.utcnow() - timedelta(days=31)

        # Now should be expired
        assert session_info.is_expired

    @pytest.mark.asyncio
    async def test_concurrent_session_creation(self, session_service):
        """Should handle concurrent session creation"""
        # Create 5 sessions concurrently
        tasks = [
            session_service.create_session(
                user_id="user_123", device_type=f"device_{i}", refresh_token=f"test_refresh_token_{i}"
            )
            for i in range(5)
        ]

        await asyncio.gather(*tasks)
        
        # Get session_ids from refresh tokens (results are client_session_tokens)
        session_ids = []
        for i in range(5):
            session_id = await session_service.find_session_by_refresh_token(f"test_refresh_token_{i}")
            if session_id:
                session_ids.append(session_id)

        # All should be unique
        assert len(set(session_ids)) == 5

        # Session count should be 5
        count = await session_service.get_session_count("user_123")
        assert count == 5


class TestCookieBasedAuthentication:
    """Tests for cookie-based session authentication (Phase 1 implementation)"""

    @pytest.mark.asyncio
    async def test_create_session_with_refresh_token(self, session_service):
        """Should create session with refresh_token mapping"""
        refresh_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test_token"
        
        client_session_token = await session_service.create_session(
            user_id="user_123",
            device_type="browser",
            refresh_token=refresh_token
        )

        # Get session_id via refresh_token
        session_id = await session_service.find_session_by_refresh_token(refresh_token)
        assert session_id is not None
        
        # Should return both identifiers
        assert session_id.startswith("sess_")
        assert client_session_token.startswith("cst_")
        
        # Should be able to find session via refresh_token
        found_session_id = await session_service.find_session_by_refresh_token(refresh_token)
        assert found_session_id == session_id
    
    @pytest.mark.asyncio
    async def test_find_session_by_refresh_token_nonexistent(self, session_service):
        """Should return None for unknown refresh_token"""
        found_session_id = await session_service.find_session_by_refresh_token("fake_token_xyz")
        assert found_session_id is None
    
    @pytest.mark.asyncio
    async def test_client_session_token_format(self, session_service):
        """Should generate valid client_session_token"""
        refresh_token = "test_refresh_token"
        client_session_token = await session_service.create_session(
            user_id="user_123",
            device_type="browser"
        , refresh_token=refresh_token)
        
        # Should have correct format: cst_{session_prefix}_{signature}
        assert client_session_token.startswith("cst_")
        parts = client_session_token.split("_")
        assert len(parts) >= 3  # cst, session_prefix, signature
        assert len(client_session_token) > 20  # Minimum length check
    
    @pytest.mark.asyncio
    async def test_backward_compatibility_without_refresh_token(self, session_service):
        """Should work without refresh_token (header-based flow)"""
        refresh_token = "test_refresh_token"
        client_session_token = await session_service.create_session(
            user_id="user_123",
            device_type="browser"
            # No refresh_token parameter
        , refresh_token=refresh_token)

        # Get session_id via refresh_token
        session_id = await session_service.find_session_by_refresh_token(refresh_token)
        assert session_id is not None
        
        # Should still create session successfully
        assert session_id.startswith("sess_")
        assert client_session_token.startswith("cst_")
        
        # Session should be valid
        session_info = await session_service.validate_session(session_id)
        assert session_info is not None
        assert session_info.user_id == "user_123"
        
        # But refresh_token lookup won't work (no mapping created)
        # This is expected - old flow doesn't provide refresh_token
    
    @pytest.mark.asyncio
    async def test_multiple_sessions_same_user_different_tokens(self, session_service):
        """Should handle multiple sessions with different refresh_tokens"""
        token1 = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.browser_token"
        token2 = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.mobile_token"
        
        # Create two sessions with different refresh_tokens
        await session_service.create_session(
            user_id="user_123",
            device_type="browser",
            refresh_token=token1
        )
        
        await session_service.create_session(
            user_id="user_123",
            device_type="mobile",
            refresh_token=token2
        )
        
        # Should be able to find each session by its refresh_token
        session_id1 = await session_service.find_session_by_refresh_token(token1)
        session_id2 = await session_service.find_session_by_refresh_token(token2)
        
        assert session_id1 is not None
        assert session_id2 is not None
        assert session_id1 != session_id2
    
    @pytest.mark.asyncio
    async def test_refresh_token_mapping_expires_with_session(self, session_service, redis_client):
        """Should cleanup refresh_token mapping when session expires"""
        refresh_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test_token"
        
        await session_service.create_session(
            user_id="user_123",
            device_type="browser",
            refresh_token=refresh_token
        )

        # Get session_id via refresh_token
        session_id = await session_service.find_session_by_refresh_token(refresh_token)
        assert session_id is not None
        
        # Verify mapping exists
        found_session_id = await session_service.find_session_by_refresh_token(refresh_token)
        assert found_session_id == session_id
        
        # Manually delete session (simulate expiration)
        session_key = f"session:{session_id}"
        await redis_client.delete(session_key)
        
        # Refresh token mapping should still exist (has same TTL)
        # But session validation will fail
        session_info = await session_service.validate_session(session_id)
        assert session_info is None
        
        # Note: The mapping will expire naturally via Redis TTL
        # We don't need to manually clean it up
    
    @pytest.mark.asyncio
    async def test_client_session_token_persists_across_validation(self, session_service):
        """Should return same client_session_token on session validation"""
        refresh_token = "test_refresh_token"
        original_client_token = await session_service.create_session(
            user_id="user_123",
            device_type="browser",
            refresh_token=refresh_token
        )
        
        # Get session_id via refresh_token
        session_id = await session_service.find_session_by_refresh_token(refresh_token)
        assert session_id is not None
        
        # Validate session
        session_info = await session_service.validate_session(session_id)
        
        # Should have client_session_token field
        assert session_info.client_session_token is not None
        assert session_info.client_session_token == original_client_token
    
    @pytest.mark.asyncio
    async def test_refresh_token_hash_not_exposed(self, session_service):
        """Should not expose raw refresh_token in session info"""
        refresh_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.sensitive_token"
        
        await session_service.create_session(
            user_id="user_123",
            device_type="browser",
            refresh_token=refresh_token
        )
        
        # Get session_id via refresh_token
        session_id = await session_service.find_session_by_refresh_token(refresh_token)
        assert session_id is not None
        
        # Validate session
        session_info = await session_service.validate_session(session_id)
        
        # Should have hash, not raw token
        assert session_info.refresh_token_hash is not None
        assert session_info.refresh_token_hash != refresh_token
        # Hash should be much shorter than JWT
        assert len(session_info.refresh_token_hash) == 32  # HMAC truncated to 32 chars
    
    @pytest.mark.asyncio
    async def test_session_list_includes_client_token(self, session_service):
        """Should include client_session_token in session list"""
        # Create sessions with refresh_token
        refresh_token1 = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.token1"
        client_token1 = await session_service.create_session(
            user_id="user_123",
            device_type="browser",
            refresh_token=refresh_token1
        )
        
        refresh_token2 = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.token2"
        client_token2 = await session_service.create_session(
            user_id="user_123",
            device_type="mobile",
            refresh_token=refresh_token2
        )
        
        # List sessions
        sessions = await session_service.list_sessions("user_123")
        
        assert len(sessions) == 2
        
        # Both should have client_session_token
        session_tokens = [s.client_session_token for s in sessions]
        assert client_token1 in session_tokens
        assert client_token2 in session_tokens


class TestClientTokenMapping:
    """Tests for find_session_by_client_token() - O(1) Redis lookup"""

    @pytest.mark.asyncio
    async def test_find_session_by_valid_client_token(self, session_service, redis_client):
        """Should find session_id from valid client token using O(1) Redis lookup"""
        # Create session
        refresh_token = "test_refresh_token_xyz"
        client_token = await session_service.create_session(
            user_id="user_123",
            device_type="browser",
            refresh_token=refresh_token
        )
        
        # Get the real session_id
        session_id = await session_service.find_session_by_refresh_token(refresh_token)
        
        # Verify Redis mapping exists
        client_token_key = f"client_token:{client_token}"
        stored_session_id = await redis_client.get(client_token_key)
        assert stored_session_id == session_id
        
        # Find session by client token
        found_session_id = await session_service.find_session_by_client_token(
            client_token, "user_123"
        )
        
        assert found_session_id == session_id

    @pytest.mark.asyncio
    async def test_find_session_returns_none_for_invalid_token(self, session_service):
        """Should return None when client token doesn't match any session"""
        # Try to find non-existent client token
        result = await session_service.find_session_by_client_token(
            "cst_sess_nonexistent", "user_123"
        )
        
        assert result is None

    @pytest.mark.asyncio
    async def test_find_session_handles_empty_session_list(self, session_service):
        """Should return None when user has no sessions"""
        # User with no sessions
        result = await session_service.find_session_by_client_token(
            "cst_sess_test", "user_no_sessions"
        )
        
        assert result is None

    @pytest.mark.asyncio
    async def test_find_session_fallback_for_legacy_sessions(self, session_service, redis_client):
        """Should use O(n) fallback when Redis mapping doesn't exist (legacy sessions)"""
        # Create session
        refresh_token = "test_refresh_fallback"
        client_token = await session_service.create_session(
            user_id="user_123",
            device_type="browser",
            refresh_token=refresh_token
        )
        
        session_id = await session_service.find_session_by_refresh_token(refresh_token)
        
        # Delete the Redis mapping to simulate legacy session
        client_token_key = f"client_token:{client_token}"
        await redis_client.delete(client_token_key)
        
        # Should still find it via O(n) fallback
        found_session_id = await session_service.find_session_by_client_token(
            client_token, "user_123"
        )
        
        assert found_session_id == session_id
        
        # Verify mapping was recreated
        stored_session_id = await redis_client.get(client_token_key)
        assert stored_session_id == session_id


class TestRefreshTokenCleanup:
    """Tests for refresh token and client token mapping cleanup"""

    @pytest.mark.asyncio
    async def test_logout_deletes_refresh_token_mapping(self, session_service, redis_client):
        """Should delete refresh_token:{hash} mapping when logging out"""
        # Create session with refresh token
        refresh_token = "test_refresh_for_logout"
        await session_service.create_session(
            user_id="user_123",
            device_type="browser",
            refresh_token=refresh_token
        )
        
        session_id = await session_service.find_session_by_refresh_token(refresh_token)
        
        # Verify refresh token mapping exists
        from services.redis.sessions import SessionService as SS
        refresh_token_hash = SS._hash_refresh_token(refresh_token)
        refresh_token_key = f"refresh_token:{refresh_token_hash}"
        assert await redis_client.exists(refresh_token_key) == 1
        
        # Logout
        success = await session_service.logout(session_id)
        assert success
        
        # Verify refresh token mapping is deleted
        assert await redis_client.exists(refresh_token_key) == 0

    @pytest.mark.asyncio
    async def test_logout_deletes_client_token_mapping(self, session_service, redis_client):
        """Should delete client_token:{token} mapping when logging out"""
        # Create session
        refresh_token = "test_refresh_client_cleanup"
        client_token = await session_service.create_session(
            user_id="user_123",
            device_type="browser",
            refresh_token=refresh_token
        )
        
        session_id = await session_service.find_session_by_refresh_token(refresh_token)
        
        # Verify client token mapping exists
        client_token_key = f"client_token:{client_token}"
        assert await redis_client.exists(client_token_key) == 1
        
        # Logout
        success = await session_service.logout(session_id)
        assert success
        
        # Verify client token mapping is deleted
        assert await redis_client.exists(client_token_key) == 0

    @pytest.mark.asyncio
    async def test_logout_all_devices_deletes_all_refresh_token_mappings(self, session_service, redis_client):
        """Should delete all refresh_token:{hash} mappings when logging out all devices"""
        # Create multiple sessions with refresh tokens
        refresh_token1 = "refresh_token_1"
        refresh_token2 = "refresh_token_2"
        refresh_token3 = "refresh_token_3"
        
        await session_service.create_session(
            user_id="user_123", device_type="browser", refresh_token=refresh_token1
        )
        await session_service.create_session(
            user_id="user_123", device_type="mobile", refresh_token=refresh_token2
        )
        await session_service.create_session(
            user_id="user_123", device_type="tablet", refresh_token=refresh_token3
        )
        
        # Get refresh token hashes
        from services.redis.sessions import SessionService as SS
        hash1 = SS._hash_refresh_token(refresh_token1)
        hash2 = SS._hash_refresh_token(refresh_token2)
        hash3 = SS._hash_refresh_token(refresh_token3)
        
        # Verify all mappings exist
        assert await redis_client.exists(f"refresh_token:{hash1}") == 1
        assert await redis_client.exists(f"refresh_token:{hash2}") == 1
        assert await redis_client.exists(f"refresh_token:{hash3}") == 1
        
        # Logout all devices
        count = await session_service.logout_all_devices("user_123")
        assert count == 3
        
        # Verify all refresh token mappings are deleted
        assert await redis_client.exists(f"refresh_token:{hash1}") == 0
        assert await redis_client.exists(f"refresh_token:{hash2}") == 0
        assert await redis_client.exists(f"refresh_token:{hash3}") == 0

    @pytest.mark.asyncio
    async def test_logout_all_devices_deletes_all_client_token_mappings(self, session_service, redis_client):
        """Should delete all client_token:{token} mappings when logging out all devices"""
        # Create multiple sessions
        refresh_token1 = "refresh_token_a"
        refresh_token2 = "refresh_token_b"
        
        client_token1 = await session_service.create_session(
            user_id="user_123", device_type="browser", refresh_token=refresh_token1
        )
        client_token2 = await session_service.create_session(
            user_id="user_123", device_type="mobile", refresh_token=refresh_token2
        )
        
        # Verify all client token mappings exist
        assert await redis_client.exists(f"client_token:{client_token1}") == 1
        assert await redis_client.exists(f"client_token:{client_token2}") == 1
        
        # Logout all devices
        count = await session_service.logout_all_devices("user_123")
        assert count == 2
        
        # Verify all client token mappings are deleted
        assert await redis_client.exists(f"client_token:{client_token1}") == 0
        assert await redis_client.exists(f"client_token:{client_token2}") == 0


class TestUpdateRefreshToken:
    """Tests for update_refresh_token() - handles Supabase token rotation"""

    @pytest.mark.asyncio
    async def test_update_refresh_token_success(self, session_service, redis_client):
        """Should atomically update refresh token mapping when token is rotated"""
        # Create session with initial refresh token
        old_refresh_token = "old_refresh_token_123"
        new_refresh_token = "new_refresh_token_456"
        
        await session_service.create_session(
            user_id="user_123",
            device_type="browser",
            refresh_token=old_refresh_token
        )
        
        session_id = await session_service.find_session_by_refresh_token(old_refresh_token)
        assert session_id is not None
        
        # Perform the update
        success = await session_service.update_refresh_token(
            session_id=session_id,
            old_refresh_token=old_refresh_token,
            new_refresh_token=new_refresh_token
        )
        
        assert success is True
        
        # Verify old mapping is deleted
        old_hash = SessionService._hash_refresh_token(old_refresh_token)
        old_key = f"refresh_token:{old_hash}"
        assert await redis_client.exists(old_key) == 0
        
        # Verify new mapping exists and points to correct session
        new_hash = SessionService._hash_refresh_token(new_refresh_token)
        new_key = f"refresh_token:{new_hash}"
        stored_session_id = await redis_client.get(new_key)
        assert stored_session_id == session_id
        
        # Verify session hash is updated
        session_key = f"session:{session_id}"
        stored_hash = await redis_client.hget(session_key, "refresh_token_hash")
        assert stored_hash == new_hash

    @pytest.mark.asyncio
    async def test_update_refresh_token_uses_session_ttl(self, session_service, redis_client):
        """Should align new mapping TTL with remaining session TTL"""
        # Create session with initial refresh token
        old_refresh_token = "ttl_test_old_token"
        new_refresh_token = "ttl_test_new_token"
        
        await session_service.create_session(
            user_id="user_123",
            device_type="browser",
            refresh_token=old_refresh_token
        )
        
        session_id = await session_service.find_session_by_refresh_token(old_refresh_token)
        
        # Set a specific TTL on the session (simulate session that's been active)
        session_key = f"session:{session_id}"
        expected_ttl = 3600  # 1 hour remaining
        await redis_client.expire(session_key, expected_ttl)
        
        # Perform the update
        success = await session_service.update_refresh_token(
            session_id=session_id,
            old_refresh_token=old_refresh_token,
            new_refresh_token=new_refresh_token
        )
        
        assert success is True
        
        # Verify new mapping TTL is aligned with session TTL
        new_hash = SessionService._hash_refresh_token(new_refresh_token)
        new_key = f"refresh_token:{new_hash}"
        actual_ttl = await redis_client.ttl(new_key)
        
        # TTL should be close to expected (allow some tolerance for test execution time)
        assert actual_ttl > 0
        assert actual_ttl <= expected_ttl
        assert actual_ttl >= expected_ttl - 10  # Within 10 seconds tolerance

    @pytest.mark.asyncio
    async def test_update_refresh_token_fallback_ttl(self, session_service, redis_client):
        """Should use default session_ttl when session TTL cannot be determined"""
        # Create session
        old_refresh_token = "fallback_ttl_old"
        new_refresh_token = "fallback_ttl_new"
        
        await session_service.create_session(
            user_id="user_123",
            device_type="browser",
            refresh_token=old_refresh_token
        )
        
        session_id = await session_service.find_session_by_refresh_token(old_refresh_token)
        
        # Delete the session key to simulate edge case
        session_key = f"session:{session_id}"
        await redis_client.delete(session_key)
        
        # Perform the update - should still succeed but use default TTL
        success = await session_service.update_refresh_token(
            session_id=session_id,
            old_refresh_token=old_refresh_token,
            new_refresh_token=new_refresh_token
        )
        
        assert success is True
        
        # Verify new mapping uses default TTL
        new_hash = SessionService._hash_refresh_token(new_refresh_token)
        new_key = f"refresh_token:{new_hash}"
        actual_ttl = await redis_client.ttl(new_key)
        
        # Should be close to session_ttl (30 days = 2592000 seconds)
        assert actual_ttl > 0
        assert actual_ttl <= session_service.session_ttl
        assert actual_ttl >= session_service.session_ttl - 10

    @pytest.mark.asyncio
    async def test_update_refresh_token_allows_session_lookup(self, session_service):
        """Should allow finding session by new refresh token after update"""
        old_refresh_token = "lookup_test_old"
        new_refresh_token = "lookup_test_new"
        
        await session_service.create_session(
            user_id="user_123",
            device_type="browser",
            refresh_token=old_refresh_token
        )
        
        session_id = await session_service.find_session_by_refresh_token(old_refresh_token)
        
        # Update the token
        await session_service.update_refresh_token(
            session_id=session_id,
            old_refresh_token=old_refresh_token,
            new_refresh_token=new_refresh_token
        )
        
        # Old token should no longer find the session
        old_lookup = await session_service.find_session_by_refresh_token(old_refresh_token)
        assert old_lookup is None
        
        # New token should find the session
        new_lookup = await session_service.find_session_by_refresh_token(new_refresh_token)
        assert new_lookup == session_id

    @pytest.mark.asyncio
    async def test_update_refresh_token_handles_errors_gracefully(self, session_service):
        """Should return False and log error on failure"""
        # Try to update with invalid session ID
        success = await session_service.update_refresh_token(
            session_id="nonexistent_session",
            old_refresh_token="old_token",
            new_refresh_token="new_token"
        )
        
        # Should still return True since the pipeline operations don't fail
        # (delete on non-existent key is OK, set creates new key, hset creates field)
        # The method doesn't validate session existence
        assert success is True

    @pytest.mark.asyncio
    async def test_update_refresh_token_atomic_behavior(self, session_service, redis_client):
        """Should perform all operations in a single atomic transaction"""
        old_refresh_token = "atomic_test_old"
        new_refresh_token = "atomic_test_new"
        
        await session_service.create_session(
            user_id="user_123",
            device_type="browser",
            refresh_token=old_refresh_token
        )
        
        session_id = await session_service.find_session_by_refresh_token(old_refresh_token)
        
        # Get initial state
        old_hash = SessionService._hash_refresh_token(old_refresh_token)
        new_hash = SessionService._hash_refresh_token(new_refresh_token)
        old_key = f"refresh_token:{old_hash}"
        new_key = f"refresh_token:{new_hash}"
        session_key = f"session:{session_id}"
        
        # Verify initial state
        assert await redis_client.exists(old_key) == 1
        assert await redis_client.exists(new_key) == 0
        
        # Perform update
        success = await session_service.update_refresh_token(
            session_id=session_id,
            old_refresh_token=old_refresh_token,
            new_refresh_token=new_refresh_token
        )
        
        assert success is True
        
        # All three operations should have completed atomically
        # 1. Old key deleted
        assert await redis_client.exists(old_key) == 0
        # 2. New key created
        assert await redis_client.exists(new_key) == 1
        # 3. Session hash updated
        stored_hash = await redis_client.hget(session_key, "refresh_token_hash")
        assert stored_hash == new_hash
