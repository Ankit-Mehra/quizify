"""
Health check routes for monitoring application and service status.

Provides endpoints for:
- Basic application health check
- Redis connectivity health check
- Future: Database health, external service checks, etc.
"""

import time
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from services.redis.client import check_redis_health, get_redis_client
from dependencies.auth_dependencies import get_current_user
from services.logger import app_logger as logger

router = APIRouter(tags=["Health"])


# ============================================================================
# APPLICATION HEALTH CHECKS
# ============================================================================

@router.get("/health")
async def health_check():
    """
    Basic health check endpoint.
    
    Returns a simple status to verify the application is running.
    Timestamp is optional - keeping response minimal for fast checks.
    
    Returns:
        dict: {"status": "ok"}
        
    Status Codes:
        200: Application is running normally
    """
    return {"status": "ok"}


# ============================================================================
# SERVICE HEALTH CHECKS
# ============================================================================

@router.get("/health/redis")
async def redis_health_check():
    """
    Redis connection health check.
    
    Verifies Redis connectivity and measures latency.
    Returns HTTP 200 if connected, 503 if unavailable.
    
    Returns:
        JSONResponse: 
            - 200 OK: {"connected": true, "latency_ms": X.XX}
            - 503 Service Unavailable: {"connected": false, "error": "..."}
            
    Status Codes:
        200: Redis connected and healthy
        503: Redis unavailable (app using memory fallback)
    """
    health = await check_redis_health()
    status_code = 200 if health.get("connected") else 503
    
    return JSONResponse(
        status_code=status_code,
        content=health
    )


# ============================================================================
# REDIS DETAILED INFO (Debug endpoint - ADMIN ONLY)
# ============================================================================

@router.get(
    "/health/redis/info",
    dependencies=[Depends(get_current_user)],
    openapi_extra={"security": [{"BearerAuth": []}]}
)
async def redis_detailed_info(current_user: dict = Depends(get_current_user)):
    """
    Get detailed Redis server information for debugging (ADMIN ONLY).
    
    **SECURITY**: Requires authentication. Exposes sensitive Redis metrics.
    
    Shows memory usage, configuration, performance metrics, and network info.
    Useful for diagnosing performance issues in production.
    
    Returns:
        dict: Detailed Redis server information or error
        
    Status Codes:
        200: Redis info retrieved successfully
        401: Unauthorized (no valid token)
        503: Redis unavailable
    """
    redis_client = get_redis_client()
    
    if not redis_client:
        return JSONResponse(
            status_code=503,
            content={"error": "Redis client not initialized"}
        )
    
    try:
        # Measure PING latency
        start = time.time()
        await redis_client.ping()
        ping_latency = (time.time() - start) * 1000
        
        # Get Redis INFO
        info = await redis_client.info()
        
        # Use unique test key to avoid collisions between concurrent requests
        test_key = f"_latency_test:{time.time_ns()}"
        
        # Measure SET operation latency
        start = time.time()
        await redis_client.set(test_key, "test", ex=1)  # 1 second expiration
        set_latency = (time.time() - start) * 1000
        
        # Measure GET operation latency
        start = time.time()
        await redis_client.get(test_key)
        get_latency = (time.time() - start) * 1000
        
        return {
            "connected": True,
            "redis_version": info.get("redis_version"),
            "redis_mode": info.get("redis_mode"),
            "uptime_in_days": info.get("uptime_in_days"),
            
            # Memory info
            "memory": {
                "used_memory_human": info.get("used_memory_human"),
                "used_memory_peak_human": info.get("used_memory_peak_human"),
                "maxmemory_human": info.get("maxmemory_human"),
                "maxmemory_policy": info.get("maxmemory_policy"),
                "mem_fragmentation_ratio": info.get("mem_fragmentation_ratio")
            },
            
            # Performance metrics
            "performance": {
                "ping_latency_ms": round(ping_latency, 2),
                "set_latency_ms": round(set_latency, 2),
                "get_latency_ms": round(get_latency, 2),
                "connected_clients": info.get("connected_clients"),
                "total_commands_processed": info.get("total_commands_processed"),
                "instantaneous_ops_per_sec": info.get("instantaneous_ops_per_sec")
            },
            
            # Data info
            "data": {
                "total_keys": await redis_client.dbsize(),
                "keyspace_hits": info.get("keyspace_hits"),
                "keyspace_misses": info.get("keyspace_misses"),
                "evicted_keys": info.get("evicted_keys")
            },
            
            # Network info
            "network": {
                "total_net_input_bytes": info.get("total_net_input_bytes"),
                "total_net_output_bytes": info.get("total_net_output_bytes"),
                "rejected_connections": info.get("rejected_connections")
            }
        }
        
    except Exception as e:
        # Log full error internally, return generic message to client
        logger.error(f"Failed to get Redis info: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=503,
            content={
                "error": "Failed to retrieve Redis diagnostics",
                "connected": False
            }
        )


# ============================================================================
# FUTURE HEALTH CHECKS (Placeholder for Epic 2+)
# ============================================================================
# 
# @router.get("/health/database")
# async def database_health_check():
#     """Check Supabase database connectivity"""
#     pass
# 
# @router.get("/health/storage")
# async def storage_health_check():
#     """Check Supabase storage availability"""
#     pass
# 
# @router.get("/health/ai")
# async def ai_service_health_check():
#     """Check OpenAI API connectivity"""
#     pass
#

