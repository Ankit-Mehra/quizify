"""
Integration tests for Redis connectivity.

These tests require a real Redis instance running.
Run with: pytest tests/integration/test_redis_integration.py -v -m integration

Setup:
    docker-compose up -d redis
"""

import pytest
import os
import redis.asyncio as redis


@pytest.fixture
async def redis_client():
    """Create real Redis client for integration testing"""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    client = redis.from_url(redis_url, decode_responses=True)
    
    # Clean up any existing test data
    await client.flushdb()
    
    yield client
    
    # Cleanup after tests
    await client.flushdb()
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_redis_connection(redis_client):
    """Test basic Redis connection and ping"""
    result = await redis_client.ping()
    assert result is True


@pytest.mark.asyncio
@pytest.mark.integration
async def test_redis_set_and_get(redis_client):
    """Test basic set and get operations"""
    # Set a value
    await redis_client.set("test_key", "test_value")
    
    # Get the value
    value = await redis_client.get("test_key")
    assert value == "test_value"
    
    # Delete the key
    await redis_client.delete("test_key")
    
    # Verify deleted
    value = await redis_client.get("test_key")
    assert value is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_redis_expiration(redis_client):
    """Test TTL (time to live) functionality"""
    # Set a value with 1 second expiration
    await redis_client.setex("expire_key", 1, "expire_value")
    
    # Verify it exists
    value = await redis_client.get("expire_key")
    assert value == "expire_value"
    
    # Check TTL
    ttl = await redis_client.ttl("expire_key")
    assert ttl > 0
    assert ttl <= 1
    
    # Wait for expiration
    import asyncio
    await asyncio.sleep(1.5)
    
    # Verify expired
    value = await redis_client.get("expire_key")
    assert value is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_redis_increment_operations(redis_client):
    """Test atomic increment/decrement operations"""
    # Increment from 0
    count = await redis_client.incr("counter")
    assert count == 1
    
    # Increment again
    count = await redis_client.incr("counter")
    assert count == 2
    
    # Decrement
    count = await redis_client.decr("counter")
    assert count == 1
    
    # Cleanup
    await redis_client.delete("counter")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_redis_hash_operations(redis_client):
    """Test hash data structure operations"""
    # Set hash fields
    await redis_client.hset("user:123", mapping={
        "name": "John Doe",
        "email": "john@example.com",
        "age": "30"
    })
    
    # Get all fields
    user_data = await redis_client.hgetall("user:123")
    assert user_data["name"] == "John Doe"
    assert user_data["email"] == "john@example.com"
    assert user_data["age"] == "30"
    
    # Get single field
    name = await redis_client.hget("user:123", "name")
    assert name == "John Doe"
    
    # Delete hash
    await redis_client.delete("user:123")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_redis_connection_pool():
    """Test that connection pooling works correctly"""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    
    # Create client with connection pool
    client = redis.from_url(
        redis_url,
        max_connections=10,
        decode_responses=True
    )
    
    # Perform multiple operations
    for i in range(20):
        await client.set(f"pool_test_{i}", f"value_{i}")
        value = await client.get(f"pool_test_{i}")
        assert value == f"value_{i}"
    
    # Cleanup
    for i in range(20):
        await client.delete(f"pool_test_{i}")
    
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_redis_scan_pattern_matching(redis_client):
    """Test pattern-based key scanning"""
    # Create multiple keys with pattern
    for i in range(5):
        await redis_client.set(f"browser_session:user123:{i}", f"session_{i}")
    
    # Scan for matching keys
    keys = []
    async for key in redis_client.scan_iter(match="browser_session:user123:*"):
        keys.append(key)
    
    assert len(keys) == 5
    
    # Cleanup
    for key in keys:
        await redis_client.delete(key)
