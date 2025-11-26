"""
Unit tests for BillingRateLimiter and WebhookIdempotencyStore

Tests both Redis-backed and memory fallback implementations for:
- Rate limiting on billing endpoints
- Webhook idempotency to prevent duplicate processing
"""

import asyncio
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch

# Import the class under test
import sys
sys.path.insert(0, ".")


class TestBillingRateLimiter:
    """Tests for the BillingRateLimiter class."""

    @pytest.fixture
    def rate_limiter(self):
        """Create a rate limiter with small limits for testing."""
        from api.billing_routes import BillingRateLimiter
        return BillingRateLimiter(max_requests=3, window_seconds=60)

    @pytest.fixture
    def fast_rate_limiter(self):
        """Create a rate limiter with very short window for timing tests."""
        from api.billing_routes import BillingRateLimiter
        return BillingRateLimiter(max_requests=2, window_seconds=1)

    # =========================================================================
    # Memory Fallback Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_memory_fallback_allows_requests_under_limit(self, rate_limiter):
        """Should allow requests when under the limit (memory mode)."""
        with patch("services.redis.client.get_redis_client", return_value=None):
            user_id = "test-user-001"
            
            # First 3 requests should be allowed
            assert await rate_limiter.is_rate_limited(user_id) is False
            assert await rate_limiter.is_rate_limited(user_id) is False
            assert await rate_limiter.is_rate_limited(user_id) is False

    @pytest.mark.asyncio
    async def test_memory_fallback_blocks_when_limit_exceeded(self, rate_limiter):
        """Should block requests when limit is exceeded (memory mode)."""
        with patch("services.redis.client.get_redis_client", return_value=None):
            user_id = "test-user-002"
            
            # Exhaust the limit
            for _ in range(3):
                await rate_limiter.is_rate_limited(user_id)
            
            # 4th request should be blocked
            assert await rate_limiter.is_rate_limited(user_id) is True

    @pytest.mark.asyncio
    async def test_memory_fallback_isolates_users(self, rate_limiter):
        """Should track limits separately per user (memory mode)."""
        with patch("services.redis.client.get_redis_client", return_value=None):
            user1 = "user-alpha"
            user2 = "user-beta"
            
            # Exhaust limit for user1
            for _ in range(3):
                await rate_limiter.is_rate_limited(user1)
            
            # user1 should be blocked
            assert await rate_limiter.is_rate_limited(user1) is True
            
            # user2 should still be allowed
            assert await rate_limiter.is_rate_limited(user2) is False

    @pytest.mark.asyncio
    async def test_memory_fallback_window_expiry(self, fast_rate_limiter):
        """Should reset limit after window expires (memory mode)."""
        with patch("services.redis.client.get_redis_client", return_value=None):
            user_id = "test-user-003"
            
            # Exhaust the limit
            await fast_rate_limiter.is_rate_limited(user_id)
            await fast_rate_limiter.is_rate_limited(user_id)
            
            # Should be blocked now
            assert await fast_rate_limiter.is_rate_limited(user_id) is True
            
            # Wait for window to expire
            await asyncio.sleep(1.1)
            
            # Should be allowed again
            assert await fast_rate_limiter.is_rate_limited(user_id) is False

    # =========================================================================
    # Redis Mode Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_redis_mode_allows_requests_under_limit(self, rate_limiter):
        """Should allow requests when under the limit (Redis mode)."""
        # Create mock Redis client
        mock_redis = MagicMock()
        mock_pipeline = MagicMock()
        # Pipeline order: ZREMRANGEBYSCORE, ZADD, ZCARD, EXPIRE
        mock_pipeline.execute = AsyncMock(return_value=[
            None,  # ZREMRANGEBYSCORE result
            None,  # ZADD result
            1,     # ZCARD result (1 request = current request)
            None,  # EXPIRE result
        ])
        mock_redis.pipeline.return_value = mock_pipeline
        
        with patch("services.redis.client.get_redis_client", return_value=mock_redis):
            user_id = "redis-user-001"
            result = await rate_limiter.is_rate_limited(user_id)
            
            assert result is False
            mock_redis.pipeline.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_mode_blocks_when_limit_exceeded(self, rate_limiter):
        """Should block requests when limit is exceeded (Redis mode)."""
        mock_redis = MagicMock()
        mock_pipeline = MagicMock()
        # Pipeline order: ZREMRANGEBYSCORE, ZADD, ZCARD, EXPIRE
        mock_pipeline.execute = AsyncMock(return_value=[
            None,  # ZREMRANGEBYSCORE result
            None,  # ZADD result
            4,     # ZCARD result (4 requests > 3 limit)
            None,  # EXPIRE result
        ])
        mock_redis.pipeline.return_value = mock_pipeline
        
        with patch("services.redis.client.get_redis_client", return_value=mock_redis):
            user_id = "redis-user-002"
            result = await rate_limiter.is_rate_limited(user_id)
            
            assert result is True

    @pytest.mark.asyncio
    async def test_redis_mode_allows_at_exactly_limit(self, rate_limiter):
        """Should allow requests when exactly at limit (not exceeded)."""
        mock_redis = MagicMock()
        mock_pipeline = MagicMock()
        # Pipeline order: ZREMRANGEBYSCORE, ZADD, ZCARD, EXPIRE
        mock_pipeline.execute = AsyncMock(return_value=[
            None,  # ZREMRANGEBYSCORE result
            None,  # ZADD result
            3,     # ZCARD result (3 requests = exactly at limit)
            None,  # EXPIRE result
        ])
        mock_redis.pipeline.return_value = mock_pipeline
        
        with patch("services.redis.client.get_redis_client", return_value=mock_redis):
            user_id = "redis-user-exact"
            result = await rate_limiter.is_rate_limited(user_id)
            
            # At exactly limit should be allowed (> check, not >=)
            assert result is False

    @pytest.mark.asyncio
    async def test_redis_mode_uses_correct_key(self, rate_limiter):
        """Should use correct Redis key format with user ID."""
        mock_redis = MagicMock()
        mock_pipeline = MagicMock()
        # Pipeline order: ZREMRANGEBYSCORE, ZADD, ZCARD, EXPIRE
        mock_pipeline.execute = AsyncMock(return_value=[None, None, 1, None])
        mock_redis.pipeline.return_value = mock_pipeline
        
        with patch("services.redis.client.get_redis_client", return_value=mock_redis):
            user_id = "test-user-key"
            await rate_limiter.is_rate_limited(user_id)
            
            # Check that zremrangebyscore was called with correct key
            expected_key = f"billing:rate_limit:{user_id}"
            calls = mock_pipeline.zremrangebyscore.call_args_list
            assert len(calls) == 1
            assert calls[0][0][0] == expected_key

    @pytest.mark.asyncio
    async def test_redis_fallback_on_error(self, rate_limiter):
        """Should fallback to memory when Redis fails."""
        mock_redis = MagicMock()
        mock_pipeline = MagicMock()
        mock_pipeline.execute = AsyncMock(side_effect=Exception("Redis connection lost"))
        mock_redis.pipeline.return_value = mock_pipeline
        
        with patch("services.redis.client.get_redis_client", return_value=mock_redis):
            user_id = "fallback-user"
            
            # Should not raise, should use memory fallback
            result = await rate_limiter.is_rate_limited(user_id)
            
            # First request should be allowed
            assert result is False

    # =========================================================================
    # Edge Cases
    # =========================================================================

    @pytest.mark.asyncio
    async def test_handles_empty_user_id(self, rate_limiter):
        """Should handle empty user ID gracefully."""
        with patch("services.redis.client.get_redis_client", return_value=None):
            # Empty user ID - should still work, just use empty string as key
            result = await rate_limiter.is_rate_limited("")
            assert result is False

    @pytest.mark.asyncio
    async def test_concurrent_requests_memory(self, rate_limiter):
        """Should handle concurrent requests with thread safety (memory mode)."""
        with patch("services.redis.client.get_redis_client", return_value=None):
            user_id = "concurrent-user"
            
            # Make 5 concurrent requests (limit is 3)
            tasks = [rate_limiter.is_rate_limited(user_id) for _ in range(5)]
            results = await asyncio.gather(*tasks)
            
            # Should have 3 allowed (False) and 2 blocked (True)
            allowed_count = results.count(False)
            blocked_count = results.count(True)
            
            assert allowed_count == 3
            assert blocked_count == 2


class TestWebhookIdempotencyStore:
    """Tests for the WebhookIdempotencyStore class."""

    @pytest.fixture
    def idempotency_store(self):
        """Create a fresh idempotency store."""
        from api.billing_routes import WebhookIdempotencyStore
        return WebhookIdempotencyStore(max_size=5, ttl_seconds=2)

    def test_first_event_not_duplicate(self, idempotency_store):
        """First occurrence of an event should not be marked as duplicate."""
        event_id = "evt_test_001"
        assert idempotency_store.is_duplicate(event_id) is False

    def test_second_event_is_duplicate(self, idempotency_store):
        """Second occurrence of same event should be marked as duplicate."""
        event_id = "evt_test_002"
        
        # First time - not duplicate
        assert idempotency_store.is_duplicate(event_id) is False
        
        # Second time - is duplicate
        assert idempotency_store.is_duplicate(event_id) is True

    def test_different_events_not_duplicates(self, idempotency_store):
        """Different event IDs should not be considered duplicates."""
        event1 = "evt_alpha"
        event2 = "evt_beta"
        
        assert idempotency_store.is_duplicate(event1) is False
        assert idempotency_store.is_duplicate(event2) is False

    def test_ttl_expiry(self, idempotency_store):
        """Events should expire after TTL."""
        event_id = "evt_expires"
        
        # First time - not duplicate
        assert idempotency_store.is_duplicate(event_id) is False
        
        # Wait for TTL
        time.sleep(2.1)
        
        # Should not be duplicate anymore (expired)
        assert idempotency_store.is_duplicate(event_id) is False

    def test_lru_eviction(self, idempotency_store):
        """Oldest events should be evicted when store is full."""
        # Add 5 events (at capacity)
        for i in range(5):
            idempotency_store.is_duplicate(f"evt_{i}")
        
        # All 5 are now tracked
        # Add 6th event - should evict evt_0 (oldest)
        idempotency_store.is_duplicate("evt_5")
        
        # evt_0 should no longer be tracked (evicted)
        # Next call should NOT mark it as duplicate (adds it as new)
        assert idempotency_store.is_duplicate("evt_0") is False
        
        # Note: Adding evt_0 back caused evt_1 to be evicted
        # So we check evt_2 instead which should still be tracked
        assert idempotency_store.is_duplicate("evt_2") is True

    def test_thread_safety(self, idempotency_store):
        """Should handle concurrent access safely."""
        import threading
        
        event_id = "evt_concurrent"
        results = []
        
        def check_duplicate():
            result = idempotency_store.is_duplicate(event_id)
            results.append(result)
        
        # Create 10 threads checking the same event
        threads = [threading.Thread(target=check_duplicate) for _ in range(10)]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Exactly one should be False (first), rest should be True
        false_count = results.count(False)
        assert false_count == 1

    # =========================================================================
    # Redis Mode Tests (is_duplicate_async)
    # =========================================================================

    @pytest.mark.asyncio
    async def test_redis_async_first_event_not_duplicate(self, idempotency_store):
        """First occurrence via Redis should not be duplicate."""
        mock_redis = MagicMock()
        mock_redis.set = AsyncMock(return_value=True)  # SET NX returns True for new key
        
        with patch("services.redis.client.get_redis_client", return_value=mock_redis):
            event_id = "evt_redis_001"
            result = await idempotency_store.is_duplicate_async(event_id)
            
            assert result is False
            mock_redis.set.assert_called_once()
            # Verify SET was called with nx=True
            call_kwargs = mock_redis.set.call_args[1]
            assert call_kwargs.get("nx") is True

    @pytest.mark.asyncio
    async def test_redis_async_second_event_is_duplicate(self, idempotency_store):
        """Second occurrence via Redis should be marked as duplicate."""
        mock_redis = MagicMock()
        # SET NX returns False (or None) when key already exists
        mock_redis.set = AsyncMock(return_value=False)
        
        with patch("services.redis.client.get_redis_client", return_value=mock_redis):
            event_id = "evt_redis_002"
            result = await idempotency_store.is_duplicate_async(event_id)
            
            assert result is True

    @pytest.mark.asyncio
    async def test_redis_async_none_response_is_duplicate(self, idempotency_store):
        """SET NX returning None should be treated as duplicate."""
        mock_redis = MagicMock()
        # Some Redis clients return None instead of False
        mock_redis.set = AsyncMock(return_value=None)
        
        with patch("services.redis.client.get_redis_client", return_value=mock_redis):
            event_id = "evt_redis_003"
            result = await idempotency_store.is_duplicate_async(event_id)
            
            assert result is True

    @pytest.mark.asyncio
    async def test_redis_async_uses_correct_key_and_ttl(self, idempotency_store):
        """Should use correct Redis key format and TTL."""
        mock_redis = MagicMock()
        mock_redis.set = AsyncMock(return_value=True)
        
        with patch("services.redis.client.get_redis_client", return_value=mock_redis):
            event_id = "evt_key_test"
            await idempotency_store.is_duplicate_async(event_id)
            
            expected_key = f"webhook:idempotency:{event_id}"
            call_args = mock_redis.set.call_args
            assert call_args[0][0] == expected_key
            assert call_args[1].get("ex") == idempotency_store._ttl_seconds

    @pytest.mark.asyncio
    async def test_redis_async_fallback_on_error(self, idempotency_store):
        """Should fallback to memory when Redis fails."""
        mock_redis = MagicMock()
        mock_redis.set = AsyncMock(side_effect=Exception("Redis connection lost"))
        
        with patch("services.redis.client.get_redis_client", return_value=mock_redis):
            event_id = "evt_fallback"
            
            # Should not raise, should use memory fallback
            result = await idempotency_store.is_duplicate_async(event_id)
            
            # First time should not be duplicate
            assert result is False
            assert idempotency_store._using_fallback is True

    @pytest.mark.asyncio
    async def test_redis_async_fallback_when_no_redis(self, idempotency_store):
        """Should use memory fallback when Redis client is None."""
        with patch("services.redis.client.get_redis_client", return_value=None):
            event_id = "evt_no_redis"
            
            # First call - not duplicate
            result1 = await idempotency_store.is_duplicate_async(event_id)
            assert result1 is False
            
            # Second call - should be duplicate (memory fallback working)
            result2 = await idempotency_store.is_duplicate_async(event_id)
            assert result2 is True
            
            assert idempotency_store._using_fallback is True

    @pytest.mark.asyncio
    async def test_redis_async_recovery_from_fallback(self, idempotency_store):
        """Should recover from fallback when Redis becomes available."""
        mock_redis = MagicMock()
        mock_redis.set = AsyncMock(return_value=True)
        
        # First, simulate fallback mode
        with patch("services.redis.client.get_redis_client", return_value=None):
            await idempotency_store.is_duplicate_async("evt_fallback_test")
            assert idempotency_store._using_fallback is True
        
        # Now Redis is back
        with patch("services.redis.client.get_redis_client", return_value=mock_redis):
            await idempotency_store.is_duplicate_async("evt_recovery_test")
            # Should have recovered
            assert idempotency_store._using_fallback is False


class TestRateLimitDependency:
    """Tests for the check_rate_limit FastAPI dependency."""

    @pytest.mark.asyncio
    async def test_allows_request_under_limit(self):
        """Should return user_id when not rate limited."""
        from api.billing_routes import _billing_rate_limiter
        
        with patch.object(_billing_rate_limiter, "is_rate_limited", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = False
            
            from api.billing_routes import check_rate_limit
            result = await check_rate_limit("test-user")
            
            assert result == "test-user"

    @pytest.mark.asyncio
    async def test_raises_429_when_limited(self):
        """Should raise HTTPException 429 when rate limited."""
        from api.billing_routes import _billing_rate_limiter
        from fastapi import HTTPException
        
        with patch.object(_billing_rate_limiter, "is_rate_limited", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = True
            
            from api.billing_routes import check_rate_limit
            
            with pytest.raises(HTTPException) as exc_info:
                await check_rate_limit("limited-user")
            
            assert exc_info.value.status_code == 429
            assert "Too many requests" in str(exc_info.value.detail)
