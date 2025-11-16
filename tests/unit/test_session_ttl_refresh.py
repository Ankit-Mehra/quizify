"""
Tests for session TTL refresh bug fix.

This test suite validates that when refresh_session() is called,
ALL Redis keys associated with the session get their TTL extended,
not just the session hash itself.

Critical bug: Previously only session:{id} TTL was extended,
causing refresh_token:{hash} and client_token:{token} mappings
to expire after 30 days, leading to mass logout.
"""

import pytest
from fakeredis import aioredis as fakeredis
from services.redis.sessions import SessionService
from config import Config


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


class TestSessionTTLRefresh:
    """Tests for ensuring all Redis keys get TTL extended on session refresh."""

    @pytest.mark.asyncio
    async def test_refresh_session_extends_all_redis_key_ttls(self, session_service, redis_client):
        """
        CRITICAL: Verify refresh_session() extends TTL on all 3 Redis keys.
        
        Bug: Previously only session:{id} got TTL extended, causing
        refresh_token:{hash} and client_token:{token} to expire after 30 days,
        resulting in mass logout across all devices.
        """
        # Create session with refresh token
        refresh_token = "test_refresh_token_ttl"
        client_token = await session_service.create_session(
            user_id="user_123",
            device_type="browser",
            refresh_token=refresh_token
        )
        
        # Get session_id for direct Redis operations
        session_id = await session_service.find_session_by_refresh_token(refresh_token)
        assert session_id is not None
        
        # Get initial TTLs for all 3 keys
        session_key = f"session:{session_id}"
        
        from services.redis.sessions import SessionService as SS
        refresh_token_hash = SS._hash_refresh_token(refresh_token)
        refresh_token_key = f"refresh_token:{refresh_token_hash}"
        
        client_token_key = f"client_token:{client_token}"
        
        # Verify all keys exist
        assert await redis_client.exists(session_key) == 1
        assert await redis_client.exists(refresh_token_key) == 1
        assert await redis_client.exists(client_token_key) == 1
        
        # Get initial TTLs (should be ~30 days = 2592000 seconds)
        initial_session_ttl = await redis_client.ttl(session_key)
        initial_refresh_ttl = await redis_client.ttl(refresh_token_key)
        initial_client_ttl = await redis_client.ttl(client_token_key)
        
        # All should have similar TTL (within a few seconds)
        assert abs(initial_session_ttl - initial_refresh_ttl) < 5
        assert abs(initial_session_ttl - initial_client_ttl) < 5
        
        # Manually reduce TTL to simulate time passing (set to 1 hour = 3600 seconds)
        await redis_client.expire(session_key, 3600)
        await redis_client.expire(refresh_token_key, 3600)
        await redis_client.expire(client_token_key, 3600)
        
        # Verify TTLs are now reduced
        reduced_session_ttl = await redis_client.ttl(session_key)
        reduced_refresh_ttl = await redis_client.ttl(refresh_token_key)
        reduced_client_ttl = await redis_client.ttl(client_token_key)
        
        assert reduced_session_ttl < 3700  # ~1 hour
        assert reduced_refresh_ttl < 3700
        assert reduced_client_ttl < 3700
        
        # Call refresh_session() - this should extend ALL TTLs back to 30 days
        success = await session_service.refresh_session(session_id)
        assert success is True
        
        # Verify ALL 3 keys now have extended TTL (~30 days)
        extended_session_ttl = await redis_client.ttl(session_key)
        extended_refresh_ttl = await redis_client.ttl(refresh_token_key)
        extended_client_ttl = await redis_client.ttl(client_token_key)
        
        # All should be extended to ~30 days (within 5 seconds of each other)
        expected_ttl = Config.REDIS_SESSION_TTL
        assert extended_session_ttl > expected_ttl - 10  # Account for execution time
        assert extended_refresh_ttl > expected_ttl - 10  # CRITICAL: Was not extended before fix
        assert extended_client_ttl > expected_ttl - 10  # CRITICAL: Was not extended before fix
        
        # Verify all keys have similar TTL (within 5 seconds)
        assert abs(extended_session_ttl - extended_refresh_ttl) < 5
        assert abs(extended_session_ttl - extended_client_ttl) < 5

    @pytest.mark.asyncio
    async def test_refresh_session_extends_user_sessions_set_ttl(self, session_service, redis_client):
        """Verify refresh_session() also extends TTL on user_sessions:{user_id} set."""
        # Create session
        refresh_token = "test_refresh_user_set"
        await session_service.create_session(
            user_id="user_456",
            device_type="mobile",
            refresh_token=refresh_token
        )
        
        session_id = await session_service.find_session_by_refresh_token(refresh_token)
        user_sessions_key = "user_sessions:user_456"
        
        # Verify user sessions set exists
        assert await redis_client.exists(user_sessions_key) == 1
        
        # Reduce TTL to simulate time passing
        await redis_client.expire(user_sessions_key, 3600)
        reduced_ttl = await redis_client.ttl(user_sessions_key)
        assert reduced_ttl < 3700
        
        # Refresh session
        success = await session_service.refresh_session(session_id)
        assert success is True
        
        # Verify user sessions set TTL was extended
        extended_ttl = await redis_client.ttl(user_sessions_key)
        expected_ttl = Config.REDIS_SESSION_TTL
        assert extended_ttl > expected_ttl - 10

    @pytest.mark.asyncio
    async def test_refresh_session_handles_missing_mappings_gracefully(self, session_service, redis_client):
        """
        Verify refresh_session() works even if some mappings are missing.
        
        This handles edge cases like:
        - Legacy sessions without client_token mapping
        - Sessions where refresh_token mapping was manually deleted
        """
        # Create session
        refresh_token = "test_refresh_missing_mappings"
        client_token = await session_service.create_session(
            user_id="user_789",
            device_type="tablet",
            refresh_token=refresh_token
        )
        
        session_id = await session_service.find_session_by_refresh_token(refresh_token)
        
        # Manually delete the client_token mapping (simulate legacy session)
        client_token_key = f"client_token:{client_token}"
        await redis_client.delete(client_token_key)
        
        # Verify mapping is gone
        assert await redis_client.exists(client_token_key) == 0
        
        # Refresh session should still succeed
        success = await session_service.refresh_session(session_id)
        assert success is True
        
        # Session should still be valid
        session_info = await session_service.validate_session(session_id)
        assert session_info is not None
        assert session_info.user_id == "user_789"

    @pytest.mark.asyncio
    async def test_refresh_session_without_refresh_token(self, session_service, redis_client):
        """
        Verify refresh_session() works for sessions created without refresh tokens.
        
        This handles sessions created via alternative auth methods that don't
        use the refresh_token cookie flow.
        """
        # Create session WITHOUT refresh token
        client_token = await session_service.create_session(
            user_id="user_no_refresh",
            device_type="browser",
            refresh_token=None  # No refresh token
        )
        
        # Find session via client token instead
        session_id = await session_service.find_session_by_client_token(client_token, "user_no_refresh")
        assert session_id is not None
        
        # Reduce session TTL
        session_key = f"session:{session_id}"
        await redis_client.expire(session_key, 3600)
        
        # Refresh session should still work
        success = await session_service.refresh_session(session_id)
        assert success is True
        
        # Verify session TTL was extended
        extended_ttl = await redis_client.ttl(session_key)
        expected_ttl = Config.REDIS_SESSION_TTL
        assert extended_ttl > expected_ttl - 10
