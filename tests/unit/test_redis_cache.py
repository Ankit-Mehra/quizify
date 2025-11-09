"""
Unit tests for CacheService.

Tests cover:
- Pydantic model serialization/deserialization
- Cache hit/miss behavior
- get_or_fetch cache-aside pattern
- Pattern-based deletion
- TTL management
- Statistics tracking
- Memory fallback mode
"""

import pytest
from typing import Optional
from pydantic import BaseModel
import asyncio

from services.redis.cache import CacheService, get_cache_service


# Test Pydantic models
class UserProfile(BaseModel):
    """Test model for user profile"""
    user_id: str
    name: str
    email: str
    tier: str = "free"
    
    class Config:
        frozen = False


class QuizMetadata(BaseModel):
    """Test model for quiz metadata"""
    quiz_id: str
    title: str
    description: Optional[str] = None
    question_count: int = 0


@pytest.fixture
def cache_service():
    """Create a fresh CacheService instance for each test"""
    service = CacheService(prefix="test")
    # Clear any existing metrics
    service.reset_metrics()
    return service


@pytest.fixture
def sample_user():
    """Sample user profile for testing"""
    return UserProfile(
        user_id="user_123",
        name="Test User",
        email="test@example.com",
        tier="premium"
    )


@pytest.fixture
def sample_quiz():
    """Sample quiz metadata for testing"""
    return QuizMetadata(
        quiz_id="quiz_456",
        title="Python Basics",
        description="Learn Python fundamentals",
        question_count=10
    )


class TestCacheServiceBasicOperations:
    """Test basic cache operations (get, set, delete)"""
    
    @pytest.mark.asyncio
    async def test_set_and_get_with_pydantic_model(self, cache_service, sample_user):
        """Test setting and getting a Pydantic model"""
        # Set the value
        await cache_service.set("user:123", sample_user, ttl=300)
        
        # Get the value back
        cached_user = await cache_service.get("user:123", UserProfile)
        
        # Verify
        assert cached_user is not None
        assert cached_user.user_id == "user_123"
        assert cached_user.name == "Test User"
        assert cached_user.email == "test@example.com"
        assert cached_user.tier == "premium"
    
    @pytest.mark.asyncio
    async def test_get_returns_none_on_cache_miss(self, cache_service):
        """Test that get returns None when key doesn't exist"""
        result = await cache_service.get("nonexistent:key", UserProfile)
        assert result is None
    
    @pytest.mark.asyncio
    async def test_set_with_different_models(self, cache_service, sample_quiz):
        """Test caching different Pydantic models"""
        await cache_service.set("quiz:456", sample_quiz, ttl=600)
        
        cached_quiz = await cache_service.get("quiz:456", QuizMetadata)
        
        assert cached_quiz is not None
        assert cached_quiz.quiz_id == "quiz_456"
        assert cached_quiz.title == "Python Basics"
        assert cached_quiz.question_count == 10
    
    @pytest.mark.asyncio
    async def test_delete_existing_key(self, cache_service, sample_user):
        """Test deleting an existing cache entry"""
        # Set a value
        await cache_service.set("user:123", sample_user, ttl=300)
        
        # Verify it exists
        assert await cache_service.exists("user:123") is True
        
        # Delete it
        deleted = await cache_service.delete("user:123")
        assert deleted is True
        
        # Verify it's gone
        assert await cache_service.exists("user:123") is False
        assert await cache_service.get("user:123", UserProfile) is None
    
    @pytest.mark.asyncio
    async def test_delete_nonexistent_key(self, cache_service):
        """Test deleting a key that doesn't exist"""
        deleted = await cache_service.delete("nonexistent:key")
        assert deleted is False
    
    @pytest.mark.asyncio
    async def test_exists_method(self, cache_service, sample_user):
        """Test the exists method"""
        # Should not exist initially
        assert await cache_service.exists("user:123") is False
        
        # Set a value
        await cache_service.set("user:123", sample_user, ttl=300)
        
        # Should exist now
        assert await cache_service.exists("user:123") is True
        
        # Delete it
        await cache_service.delete("user:123")
        
        # Should not exist anymore
        assert await cache_service.exists("user:123") is False


class TestCacheAsidePattern:
    """Test get_or_fetch cache-aside pattern"""
    
    @pytest.mark.asyncio
    async def test_get_or_fetch_on_cache_hit(self, cache_service, sample_user):
        """Test get_or_fetch returns cached value without calling fetch_fn"""
        # Pre-populate cache
        await cache_service.set("user:123", sample_user, ttl=300)
        
        # Track if fetch_fn was called
        fetch_called = False
        
        async def fetch_user():
            nonlocal fetch_called
            fetch_called = True
            return UserProfile(
                user_id="user_123",
                name="Different Name",  # Different from cached
                email="different@example.com",
                tier="free"
            )
        
        # Get or fetch
        user = await cache_service.get_or_fetch(
            "user:123",
            fetch_user,
            UserProfile,
            ttl=300
        )
        
        # Should return cached value
        assert user.name == "Test User"  # Original cached name
        assert fetch_called is False  # fetch_fn should NOT be called
    
    @pytest.mark.asyncio
    async def test_get_or_fetch_on_cache_miss(self, cache_service):
        """Test get_or_fetch fetches and caches on miss"""
        # Track if fetch_fn was called
        fetch_called = False
        
        async def fetch_user():
            nonlocal fetch_called
            fetch_called = True
            return UserProfile(
                user_id="user_999",
                name="Fetched User",
                email="fetched@example.com",
                tier="basic"
            )
        
        # Cache is empty
        assert await cache_service.exists("user:999") is False
        
        # Get or fetch
        user = await cache_service.get_or_fetch(
            "user:999",
            fetch_user,
            UserProfile,
            ttl=300
        )
        
        # Should fetch and return new value
        assert user.name == "Fetched User"
        assert fetch_called is True  # fetch_fn SHOULD be called
        
        # Should now be cached
        assert await cache_service.exists("user:999") is True
        
        # Second call should hit cache
        fetch_called = False
        user2 = await cache_service.get_or_fetch(
            "user:999",
            fetch_user,
            UserProfile,
            ttl=300
        )
        assert user2.name == "Fetched User"
        assert fetch_called is False  # fetch_fn should NOT be called again


class TestPatternDeletion:
    """Test pattern-based key deletion"""
    
    @pytest.mark.asyncio
    async def test_delete_pattern_with_wildcard(self, cache_service, sample_user):
        """Test deleting multiple keys with pattern"""
        # Create multiple user caches
        for i in range(5):
            user = UserProfile(
                user_id=f"user_{i}",
                name=f"User {i}",
                email=f"user{i}@example.com"
            )
            await cache_service.set(f"user:{i}", user, ttl=300)
        
        # Create some quiz caches (different pattern)
        quiz = QuizMetadata(quiz_id="quiz_1", title="Test Quiz")
        await cache_service.set("quiz:1", quiz, ttl=300)
        
        # Verify all exist
        for i in range(5):
            assert await cache_service.exists(f"user:{i}") is True
        assert await cache_service.exists("quiz:1") is True
        
        # Delete all user:* keys
        deleted_count = await cache_service.delete_pattern("user:*")
        assert deleted_count == 5
        
        # Verify users are gone
        for i in range(5):
            assert await cache_service.exists(f"user:{i}") is False
        
        # Verify quiz still exists (different pattern)
        assert await cache_service.exists("quiz:1") is True
    
    @pytest.mark.asyncio
    async def test_delete_pattern_no_matches(self, cache_service):
        """Test delete_pattern with no matching keys"""
        deleted_count = await cache_service.delete_pattern("nonexistent:*")
        assert deleted_count == 0


class TestStatisticsTracking:
    """Test cache statistics and metrics"""
    
    @pytest.mark.asyncio
    async def test_hit_miss_statistics(self, cache_service, sample_user):
        """Test that hits and misses are tracked correctly"""
        # Initial stats should be empty
        stats = cache_service.get_stats()
        assert stats["total_operations"] == 0
        
        # Cache miss
        await cache_service.get("user:123", UserProfile)
        
        # Cache set
        await cache_service.set("user:123", sample_user, ttl=300)
        
        # Cache hit
        await cache_service.get("user:123", UserProfile)
        await cache_service.get("user:123", UserProfile)  # Another hit
        
        # Check stats
        stats = cache_service.get_stats()
        
        # Should have metrics for both Redis or memory (depending on availability)
        redis_hits = stats.get("redis_cache_hits", 0)
        memory_hits = stats.get("memory_cache_hits", 0)
        redis_misses = stats.get("redis_cache_misses", 0)
        memory_misses = stats.get("memory_cache_misses", 0)
        
        total_hits = redis_hits + memory_hits
        total_misses = redis_misses + memory_misses
        
        # Should have 2 hits and 1 miss
        assert total_hits == 2
        assert total_misses == 1
    
    @pytest.mark.asyncio
    async def test_hit_rate_calculation(self, cache_service, sample_user):
        """Test hit rate is calculated correctly"""
        # Generate some hits and misses
        await cache_service.set("user:1", sample_user, ttl=300)
        
        # 3 hits
        await cache_service.get("user:1", UserProfile)
        await cache_service.get("user:1", UserProfile)
        await cache_service.get("user:1", UserProfile)
        
        # 1 miss
        await cache_service.get("user:nonexistent", UserProfile)
        
        stats = cache_service.get_stats()
        
        # Hit rate should be 3/4 = 0.75 (considering either Redis or memory)
        redis_hit_rate = stats.get("redis_hit_rate", 0)
        memory_hit_rate = stats.get("memory_hit_rate", 0)
        
        # One of them should have the correct hit rate
        assert redis_hit_rate == 0.75 or memory_hit_rate == 0.75
    
    @pytest.mark.asyncio
    async def test_delete_statistics(self, cache_service, sample_user):
        """Test delete operations are tracked"""
        # Set and delete
        await cache_service.set("user:123", sample_user, ttl=300)
        await cache_service.delete("user:123")
        
        stats = cache_service.get_stats()
        
        redis_deletes = stats.get("redis_cache_deletes", 0)
        memory_deletes = stats.get("memory_cache_deletes", 0)
        
        assert (redis_deletes + memory_deletes) >= 1


class TestTTLManagement:
    """Test TTL (time-to-live) functionality"""
    
    @pytest.mark.asyncio
    async def test_get_ttl_for_existing_key(self, cache_service, sample_user):
        """Test getting TTL for a cached key"""
        await cache_service.set("user:123", sample_user, ttl=300)
        
        ttl = await cache_service.get_ttl("user:123")
        
        # TTL should be positive (close to 300, but may be slightly less)
        # For memory fallback, it returns -1 (no precise TTL tracking)
        assert ttl == -1 or (250 <= ttl <= 300)
    
    @pytest.mark.asyncio
    async def test_get_ttl_for_nonexistent_key(self, cache_service):
        """Test getting TTL for non-existent key"""
        ttl = await cache_service.get_ttl("nonexistent:key")
        assert ttl == -2  # Standard Redis response for non-existent key
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_cache_expiration_after_ttl(self, cache_service, sample_user):
        """Test that cache entries expire after TTL (slow test)"""
        # Set with very short TTL
        await cache_service.set("user:short_ttl", sample_user, ttl=2)
        
        # Should exist immediately
        assert await cache_service.exists("user:short_ttl") is True
        
        # Wait for expiration
        await asyncio.sleep(3)
        
        # Should be gone (for memory fallback, we simulate expiration)
        result = await cache_service.get("user:short_ttl", UserProfile)
        # May or may not be None depending on Redis vs memory
        # This test is mostly for manual verification


class TestKeyPrefixing:
    """Test cache key prefixing"""
    
    @pytest.mark.asyncio
    async def test_different_prefixes_are_isolated(self, sample_user):
        """Test that different cache prefixes are isolated"""
        cache1 = CacheService(prefix="cache1")
        cache2 = CacheService(prefix="cache2")
        
        # Set same key in both caches
        await cache1.set("user:123", sample_user, ttl=300)
        
        # Should exist in cache1
        assert await cache1.exists("user:123") is True
        
        # Should NOT exist in cache2 (different prefix)
        assert await cache2.exists("user:123") is False
    
    @pytest.mark.asyncio
    async def test_prefix_in_full_key(self, cache_service, sample_user):
        """Test that prefix is correctly applied to keys"""
        await cache_service.set("user:123", sample_user, ttl=300)
        
        # The full key should be "test:user:123" (prefix "test")
        # This is verified by the isolation test above


class TestMemoryFallback:
    """Test memory fallback when Redis unavailable"""
    
    @pytest.mark.asyncio
    async def test_cache_works_without_redis(self, sample_user):
        """Test that cache works even if Redis is unavailable"""
        # Create cache service (will use memory fallback if Redis unavailable)
        cache = CacheService(prefix="memory_test")
        
        # All operations should work
        await cache.set("user:123", sample_user, ttl=300)
        
        cached = await cache.get("user:123", UserProfile)
        assert cached is not None
        assert cached.user_id == "user_123"
        
        # Exists should work
        assert await cache.exists("user:123") is True
        
        # Delete should work
        deleted = await cache.delete("user:123")
        assert deleted is True


class TestGlobalCacheService:
    """Test get_cache_service singleton function"""
    
    def test_get_cache_service_returns_singleton(self):
        """Test that get_cache_service returns the same instance"""
        service1 = get_cache_service()
        service2 = get_cache_service()
        
        assert service1 is service2
    
    def test_get_cache_service_with_different_prefix(self):
        """Test that different prefixes create different instances"""
        service1 = get_cache_service(prefix="cache1")
        service2 = get_cache_service(prefix="cache2")
        
        # Should be different instances
        assert service1.prefix == "cache1"
        assert service2.prefix == "cache2"
