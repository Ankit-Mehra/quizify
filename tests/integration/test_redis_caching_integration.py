"""
Integration tests for Redis caching functionality.

These tests verify:
- Cache behavior with real memory fallback (or Redis if available)
- Cache-aside pattern integration
- TTL behavior
- Statistics tracking
"""

import pytest
from pydantic import BaseModel

from services.redis.cache import CacheService


class SampleModel(BaseModel):
    """Test model for integration testing"""
    id: str
    name: str
    value: int


@pytest.mark.asyncio
async def test_cache_service_end_to_end():
    """Test complete cache workflow"""
    cache = CacheService(prefix="integration_test")
    
    # 1. Set a value
    sample = SampleModel(id="test_1", name="Test Item", value=42)
    await cache.set("item:1", sample, ttl=60)
    
    # 2. Retrieve it
    retrieved = await cache.get("item:1", SampleModel)
    assert retrieved is not None
    assert retrieved.id == "test_1"
    assert retrieved.name == "Test Item"
    assert retrieved.value == 42
    
    # 3. Verify exists
    assert await cache.exists("item:1") is True
    
    # 4. Delete it
    deleted = await cache.delete("item:1")
    assert deleted is True
    
    # 5. Verify it's gone
    assert await cache.exists("item:1") is False
    assert await cache.get("item:1", SampleModel) is None


@pytest.mark.asyncio
async def test_cache_aside_pattern_integration():
    """Test get_or_fetch with real workflow"""
    cache = CacheService(prefix="integration_test")
    
    # Track fetch calls
    fetch_count = 0
    
    async def fetch_data():
        nonlocal fetch_count
        fetch_count += 1
        return SampleModel(id="item_2", name="Fetched Item", value=100)
    
    # First call - should fetch
    item1 = await cache.get_or_fetch(
        "item:2",
        fetch_data,
        SampleModel,
        ttl=60
    )
    assert item1.name == "Fetched Item"
    assert fetch_count == 1
    
    # Second call - should hit cache
    item2 = await cache.get_or_fetch(
        "item:2",
        fetch_data,
        SampleModel,
        ttl=60
    )
    assert item2.name == "Fetched Item"
    assert fetch_count == 1  # Fetch should NOT be called again


@pytest.mark.asyncio
async def test_pattern_deletion_integration():
    """Test deleting multiple keys by pattern"""
    cache = CacheService(prefix="integration_test")
    
    # Create multiple items
    for i in range(5):
        item = SampleModel(id=f"user_{i}", name=f"User {i}", value=i)
        await cache.set(f"user:{i}", item, ttl=60)
    
    # Create an item with different pattern
    other = SampleModel(id="admin_1", name="Admin", value=999)
    await cache.set("admin:1", other, ttl=60)
    
    # Verify all exist
    for i in range(5):
        assert await cache.exists(f"user:{i}") is True
    assert await cache.exists("admin:1") is True
    
    # Delete all user:* items
    deleted_count = await cache.delete_pattern("user:*")
    assert deleted_count == 5
    
    # Verify users are gone but admin remains
    for i in range(5):
        assert await cache.exists(f"user:{i}") is False
    assert await cache.exists("admin:1") is True


@pytest.mark.asyncio
async def test_cache_statistics_integration():
    """Test statistics tracking across operations"""
    cache = CacheService(prefix="integration_test")
    cache.reset_metrics()
    
    # Generate some hits and misses
    sample = SampleModel(id="stats_test", name="Stats", value=1)
    await cache.set("stats:1", sample, ttl=60)
    
    # Cache hits (2)
    await cache.get("stats:1", SampleModel)
    await cache.get("stats:1", SampleModel)
    
    # Cache miss (1)
    await cache.get("stats:nonexistent", SampleModel)
    
    # Check statistics
    stats = cache.get_stats()
    
    # Should have metrics from either Redis or memory
    redis_hits = stats.get("redis_cache_hits", 0)
    memory_hits = stats.get("memory_cache_hits", 0)
    redis_misses = stats.get("redis_cache_misses", 0)
    memory_misses = stats.get("memory_cache_misses", 0)
    
    total_hits = redis_hits + memory_hits
    total_misses = redis_misses + memory_misses
    
    # We expect 2 hits and 1 miss
    assert total_hits == 2, f"Expected 2 hits, got {total_hits}"
    assert total_misses == 1, f"Expected 1 miss, got {total_misses}"
    
    # Hit rate should be 2/3 = 0.667
    hit_rate = stats.get("redis_hit_rate", 0) or stats.get("memory_hit_rate", 0)
    assert 0.65 <= hit_rate <= 0.68, f"Expected hit rate ~0.667, got {hit_rate}"


@pytest.mark.asyncio
async def test_cache_prefix_isolation():
    """Test that different prefixes create isolated namespaces"""
    cache1 = CacheService(prefix="namespace1")
    cache2 = CacheService(prefix="namespace2")
    
    sample = SampleModel(id="test", name="Test", value=1)
    
    # Set in cache1
    await cache1.set("item:1", sample, ttl=60)
    
    # Should exist in cache1
    assert await cache1.exists("item:1") is True
    
    # Should NOT exist in cache2 (different prefix)
    assert await cache2.exists("item:1") is False
