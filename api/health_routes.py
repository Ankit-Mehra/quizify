"""
Health check routes for monitoring application and service status.

Provides endpoints for:
- Basic application health check
- Redis connectivity health check
- Future: Database health, external service checks, etc.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from services.redis.client import check_redis_health

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

