"""
Unit tests for Redis client functionality.

Tests cover:
- Client initialization with various configurations
- Health check functionality
- Connection error handling
- Fallback behavior when Redis unavailable
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from services.redis.client import get_redis_client, check_redis_health


@pytest.fixture
def mock_redis_config(monkeypatch):
    """Mock Redis configuration"""
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    monkeypatch.setenv("REDIS_ENABLED", "true")
    monkeypatch.setenv("REDIS_MAX_CONNECTIONS", "20")


@pytest.mark.asyncio
async def test_redis_client_returns_none_when_disabled(monkeypatch):
    """Test that Redis client is None when REDIS_ENABLED=false"""
    # Reset the module-level redis_client
    import services.redis.client as client_module
    client_module.redis_client = None
    
    # Mock config to disable Redis
    with patch("services.redis.client.app_config") as mock_config:
        mock_config.REDIS_ENABLED = False
        mock_config.REDIS_URL = "redis://localhost:6379"
        
        client = get_redis_client()
        assert client is None


@pytest.mark.asyncio
async def test_health_check_when_redis_not_initialized():
    """Test health check returns error when Redis client not initialized"""
    # Reset the module-level redis_client
    import services.redis.client as client_module
    client_module.redis_client = None
    
    health = await check_redis_health()
    
    assert health["connected"] is False
    assert "error" in health
    assert "not initialized" in health["error"]


@pytest.mark.asyncio
async def test_health_check_when_redis_ping_fails():
    """Test health check returns error when ping fails"""
    import services.redis.client as client_module
    
    # Mock a redis client that fails on ping
    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(side_effect=Exception("Connection refused"))
    client_module.redis_client = mock_client
    
    health = await check_redis_health()
    
    assert health["connected"] is False
    assert "error" in health
    assert "Connection refused" in health["error"]
    
    # Cleanup
    client_module.redis_client = None


@pytest.mark.asyncio
async def test_health_check_when_redis_connected():
    """Test health check returns success when Redis connected"""
    import services.redis.client as client_module
    
    # Mock a redis client that succeeds
    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(return_value=True)
    client_module.redis_client = mock_client
    
    health = await check_redis_health()
    
    assert health["connected"] is True
    assert "latency_ms" in health
    assert health["latency_ms"] >= 0
    assert "error" not in health
    
    # Cleanup
    client_module.redis_client = None


@pytest.mark.asyncio
async def test_get_redis_client_returns_cached_instance():
    """Test that get_redis_client returns the same instance"""
    import services.redis.client as client_module
    
    # Set up a mock client
    mock_client = AsyncMock()
    client_module.redis_client = mock_client
    
    client1 = get_redis_client()
    client2 = get_redis_client()
    
    assert client1 is client2
    assert client1 is mock_client
    
    # Cleanup
    client_module.redis_client = None


@pytest.mark.asyncio
async def test_lifespan_handles_redis_connection_error_gracefully():
    """Test that app can start even if Redis connection fails"""
    from fastapi import FastAPI
    from services.redis.client import lifespan
    import services.redis.client as client_module
    
    # Reset client
    client_module.redis_client = None
    
    app = FastAPI()
    
    # Mock config to enable Redis but make connection fail
    with patch("services.redis.client.app_config") as mock_config, \
         patch("services.redis.client.redis") as mock_redis_module:
        
        mock_config.REDIS_ENABLED = True
        mock_config.REDIS_URL = "redis://localhost:6379"
        mock_config.REDIS_MAX_CONNECTIONS = 20
        mock_config.REDIS_SOCKET_TIMEOUT = 5
        mock_config.REDIS_SOCKET_CONNECT_TIMEOUT = 5
        mock_config.REDIS_HEALTH_CHECK_INTERVAL = 30
        
        # Make from_url succeed but ping fail
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client.aclose = AsyncMock()
        mock_redis_module.from_url = MagicMock(return_value=mock_client)
        mock_redis_module.RedisError = Exception
        
        # Lifespan should not raise exception
        async with lifespan(app):
            # Client should be None after failed connection
            assert client_module.redis_client is None


@pytest.mark.asyncio  
async def test_lifespan_closes_redis_on_shutdown():
    """Test that Redis connection is closed on app shutdown"""
    from fastapi import FastAPI
    from services.redis.client import lifespan
    import services.redis.client as client_module
    
    app = FastAPI()
    
    # Mock successful connection
    with patch("services.redis.client.app_config") as mock_config, \
         patch("services.redis.client.redis") as mock_redis_module:
        
        mock_config.REDIS_ENABLED = True
        mock_config.REDIS_URL = "redis://localhost:6379"
        mock_config.REDIS_MAX_CONNECTIONS = 20
        mock_config.REDIS_SOCKET_TIMEOUT = 5
        mock_config.REDIS_SOCKET_CONNECT_TIMEOUT = 5
        mock_config.REDIS_HEALTH_CHECK_INTERVAL = 30
        
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.aclose = AsyncMock()
        mock_redis_module.from_url = MagicMock(return_value=mock_client)
        
        async with lifespan(app):
            # Client should be initialized
            assert client_module.redis_client is not None
        
        # After exiting context, aclose should be called
        mock_client.aclose.assert_called_once()
        
        # Cleanup
        client_module.redis_client = None
