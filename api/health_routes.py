"""
Health check routes for monitoring application and service status.

Provides endpoints for:
- Basic application health check
- Redis connectivity health check
- Redis comprehensive monitoring (with cache metrics)
- Future: Database health, external service checks, etc.
"""

import time
from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import JSONResponse
from services.redis.client import check_redis_health, get_redis_client
from services.redis.cache import get_cache_service
from dependencies.auth_dependencies import get_current_user_id
from handlers.admin_handlers import is_admin
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
# SERVICE HEALTH CHECKS (ADMIN ONLY)
# ============================================================================

@router.get(
    "/health/redis",
    dependencies=[Depends(get_current_user_id)],
    openapi_extra={"security": [{"BearerAuth": []}]}
)
async def redis_health_check(current_user_id: str = Depends(get_current_user_id)):
    """
    Comprehensive Redis health check with cache metrics (ADMIN ONLY).
    
    **SECURITY**: Requires admin role. Exposes sensitive Redis metrics and cache statistics.
    
    Verifies Redis connectivity, measures latency, and provides cache statistics
    including hit rates, memory usage, and operation counts.
    
    Returns:
        JSONResponse with detailed Redis health information:
            - status: "healthy" | "unhealthy" | "degraded"
            - connected: true | false
            - fallback_mode: true | false
            - latency_ms: Connection latency
            - memory: Memory usage metrics
            - cache_stats: Hit/miss rates and operation counts
            - performance: Operations per second
            
    Status Codes:
        200: Redis connected and healthy
        401: Unauthorized (no valid token)
        403: Forbidden (not admin)
        503: Redis unavailable (app using memory fallback)
    """
    # Check admin authorization
    if not is_admin(current_user_id):
        logger.warning(f"Non-admin user {current_user_id[:8]}... attempted to access Redis health metrics")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    redis_client = get_redis_client()
    
    # Check if Redis is available
    if not redis_client:
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "connected": False,
                "fallback_mode": True,
                "message": "Redis unavailable - using memory fallback"
            }
        )
    
    try:
        # Measure PING latency
        start = time.time()
        await redis_client.ping()
        latency_ms = round((time.time() - start) * 1000, 2)
        
        # Get Redis memory info
        info = await redis_client.info("memory")
        used_mb = info.get("used_memory", 0) / 1024 / 1024
        maxmemory = info.get("maxmemory", 0)
        maxmemory_mb = maxmemory / 1024 / 1024 if maxmemory > 0 else 256
        memory_percent = round((used_mb / maxmemory_mb) * 100, 2)
        
        # Get Redis stats (keyspace hits/misses)
        stats_info = await redis_client.info("stats")
        keyspace_hits = stats_info.get("keyspace_hits", 0)
        keyspace_misses = stats_info.get("keyspace_misses", 0)
        total_ops = keyspace_hits + keyspace_misses
        redis_hit_rate = round((keyspace_hits / total_ops * 100) if total_ops > 0 else 0, 2)
        
        # Get application cache service stats
        cache_service = get_cache_service(prefix="cache")
        app_stats = cache_service.get_stats()
        
        # Calculate overall application cache hit rate
        app_cache_hits = app_stats.get("redis_cache_hits", 0)
        app_cache_misses = app_stats.get("redis_cache_misses", 0)
        app_total = app_cache_hits + app_cache_misses
        app_hit_rate = round((app_cache_hits / app_total * 100) if app_total > 0 else 0, 2)
        
        # Get performance metrics
        perf_info = await redis_client.info("stats")
        ops_per_sec = perf_info.get("instantaneous_ops_per_sec", 0)
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "healthy",
                "connected": True,
                "fallback_mode": False,
                "latency_ms": latency_ms,
                "memory": {
                    "used_mb": round(used_mb, 2),
                    "max_mb": round(maxmemory_mb, 2),
                    "used_percent": memory_percent
                },
                "cache_stats": {
                    "redis_keyspace_hits": keyspace_hits,
                    "redis_keyspace_misses": keyspace_misses,
                    "redis_hit_rate_percent": redis_hit_rate,
                    "app_cache_hits": app_cache_hits,
                    "app_cache_misses": app_cache_misses,
                    "app_hit_rate_percent": app_hit_rate,
                    "total_app_operations": app_total
                },
                "performance": {
                    "ops_per_sec": ops_per_sec,
                    "total_commands_processed": perf_info.get("total_commands_processed", 0)
                }
            }
        )
        
    except Exception as e:
        # Log full error internally, return generic message to client
        logger.error(f"Failed to get Redis health metrics: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "connected": False,
                "fallback_mode": True,
                "error": "Failed to retrieve Redis health metrics"
            }
        )


# ============================================================================
# REDIS DETAILED INFO (Debug endpoint - ADMIN ONLY)
# ============================================================================

@router.get(
    "/health/redis/info",
    dependencies=[Depends(get_current_user_id)],
    openapi_extra={"security": [{"BearerAuth": []}]}
)
async def redis_detailed_info(current_user_id: str = Depends(get_current_user_id)):
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

    # Check admin authorization
    if not is_admin(current_user_id):
        logger.warning(f"Non-admin user {current_user_id[:8]}... attempted to access Redis health metrics")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

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

