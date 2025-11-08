"""
Unit tests for Redis-based browser slot management.

Tests cover:
- Slot acquisition and release
- Concurrent slot limits
- Distributed coordination
- Memory fallback behavior
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from services.redis.browser_slots import BrowserSlotManager


@pytest.fixture
def slot_manager():
    """Create a fresh BrowserSlotManager instance for each test"""
    manager = BrowserSlotManager()
    manager._memory_store.clear()  # Clear any previous state
    return manager


@pytest.mark.asyncio
async def test_acquire_slot_memory_success(slot_manager):
    """Test successful slot acquisition in memory mode"""
    user_id = "test_user_123"
    
    # Acquire first slot
    await slot_manager._acquire_slot_memory(user_id)
    count = await slot_manager._get_slot_count_memory(user_id)
    assert count == 1
    
    # Acquire second slot
    await slot_manager._acquire_slot_memory(user_id)
    count = await slot_manager._get_slot_count_memory(user_id)
    assert count == 2


@pytest.mark.asyncio
async def test_acquire_slot_memory_exceeds_limit(slot_manager):
    """Test that exceeding max slots raises HTTPException"""
    user_id = "test_user_123"
    
    # Acquire up to max slots (default is 3)
    for i in range(slot_manager._max_slots):
        await slot_manager._acquire_slot_memory(user_id)
    
    # Try to acquire one more - should fail
    with pytest.raises(HTTPException) as exc_info:
        await slot_manager._acquire_slot_memory(user_id)
    
    assert exc_info.value.status_code == 429
    assert "Too many concurrent browser sessions" in exc_info.value.detail


@pytest.mark.asyncio
async def test_release_slot_memory_success(slot_manager):
    """Test successful slot release in memory mode"""
    user_id = "test_user_123"
    
    # Acquire 2 slots
    await slot_manager._acquire_slot_memory(user_id)
    await slot_manager._acquire_slot_memory(user_id)
    
    # Release 1 slot
    await slot_manager._release_slot_memory(user_id)
    count = await slot_manager._get_slot_count_memory(user_id)
    assert count == 1
    
    # Release final slot
    await slot_manager._release_slot_memory(user_id)
    count = await slot_manager._get_slot_count_memory(user_id)
    assert count == 0


@pytest.mark.asyncio
async def test_release_slot_memory_cleanup(slot_manager):
    """Test that memory store is cleaned up when count reaches 0"""
    user_id = "test_user_123"
    
    # Acquire and release
    await slot_manager._acquire_slot_memory(user_id)
    await slot_manager._release_slot_memory(user_id)
    
    # Key should be removed from memory store
    assert user_id not in slot_manager._memory_store


@pytest.mark.asyncio
async def test_multiple_users_independent_slots(slot_manager):
    """Test that different users have independent slot counts"""
    user1 = "user_1"
    user2 = "user_2"
    
    # Acquire slots for different users
    await slot_manager._acquire_slot_memory(user1)
    await slot_manager._acquire_slot_memory(user1)
    await slot_manager._acquire_slot_memory(user2)
    
    # Check independent counts
    count1 = await slot_manager._get_slot_count_memory(user1)
    count2 = await slot_manager._get_slot_count_memory(user2)
    
    assert count1 == 2
    assert count2 == 1


@pytest.mark.asyncio
async def test_acquire_slot_with_redis():
    """Test slot acquisition with mocked Redis client"""
    manager = BrowserSlotManager()
    
    # Mock Redis client
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)  # Lock acquired
    mock_redis.get = AsyncMock(return_value=None)  # No existing slots
    mock_redis.eval = AsyncMock()  # Lock release
    
    with patch.object(manager, '_get_redis_client', return_value=mock_redis):
        await manager._acquire_slot_redis("test_user")
        
        # Verify Redis calls
        assert mock_redis.set.call_count >= 2  # Lock + slot count
        assert mock_redis.get.called


@pytest.mark.asyncio
async def test_acquire_slot_redis_exceeds_limit():
    """Test that Redis mode enforces slot limits"""
    manager = BrowserSlotManager()
    
    # Mock Redis with max slots already used
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)  # Lock acquired
    mock_redis.get = AsyncMock(return_value=str(manager._max_slots))  # At limit
    mock_redis.eval = AsyncMock()
    
    with patch.object(manager, '_get_redis_client', return_value=mock_redis):
        with pytest.raises(HTTPException) as exc_info:
            await manager._acquire_slot_redis("test_user")
        
        assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_release_slot_with_redis():
    """Test slot release with mocked Redis client using Lua script"""
    manager = BrowserSlotManager()
    
    # Mock Redis - now using Lua script for atomic decrement
    mock_redis = AsyncMock()
    mock_redis.eval = AsyncMock(return_value=1)  # Returns new count after decrement
    
    with patch.object(manager, '_get_redis_client', return_value=mock_redis):
        await manager._release_slot_redis("test_user")
        
        # Should call eval (Lua script) instead of get/set
        mock_redis.eval.assert_called_once()


@pytest.mark.asyncio
async def test_release_slot_redis_deletes_when_zero():
    """Test that Lua script deletes Redis key when count reaches 0"""
    manager = BrowserSlotManager()
    
    # Mock Redis - Lua script returns 0 when key is deleted
    mock_redis = AsyncMock()
    mock_redis.eval = AsyncMock(return_value=0)  # Returns 0 when count reaches zero
    
    with patch.object(manager, '_get_redis_client', return_value=mock_redis):
        await manager._release_slot_redis("test_user")
        
        # Should call eval (Lua script handles deletion internally)
        mock_redis.eval.assert_called_once()


@pytest.mark.asyncio
async def test_fallback_to_memory_when_redis_unavailable():
    """Test automatic fallback to memory when Redis unavailable"""
    manager = BrowserSlotManager()
    
    # Mock Redis client to return None (unavailable)
    with patch.object(manager, '_get_redis_client', return_value=None):
        # Should use memory fallback
        await manager.acquire_slot("test_user")
        count = await manager.get_slot_count("test_user")
        
        assert count == 1
        assert "test_user" in manager._memory_store


@pytest.mark.asyncio
async def test_concurrent_slot_acquisition():
    """Test concurrent slot acquisition doesn't exceed limit"""
    manager = BrowserSlotManager()
    user_id = "concurrent_user"
    
    # Try to acquire more slots than allowed concurrently
    async def acquire_slot_safe():
        try:
            await manager._acquire_slot_memory(user_id)
            return True
        except HTTPException:
            return False
    
    # Run concurrent acquisitions
    results = await asyncio.gather(*[acquire_slot_safe() for _ in range(5)])
    
    # Only max_slots should succeed
    successful = sum(results)
    assert successful == manager._max_slots
    
    # Final count should equal max
    count = await manager._get_slot_count_memory(user_id)
    assert count == manager._max_slots


@pytest.mark.asyncio
async def test_slot_key_generation(slot_manager):
    """Test that slot keys are generated correctly"""
    user_id = "test_user_123"
    
    slot_key = slot_manager._get_slot_key(user_id)
    assert slot_key == "browser_slots:test_user_123"
    
    lock_key = slot_manager._get_lock_key(user_id)
    assert lock_key == "browser_slots:lock:test_user_123"
