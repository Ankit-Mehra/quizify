"""
Contact Routes - API endpoints for contact form.

Public endpoint for landing page contact form submission.
Includes rate limiting to prevent spam abuse.
"""

import time
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, Request

from handlers.contact_handler import handle_contact_submission
from schemas.contact import ContactRequest, ContactResponse
from services.logger import app_logger as logger


router = APIRouter(prefix="/contact", tags=["Contact"])


# ============================================================================
# Rate Limiter for Contact Form (IP-based, Redis-backed with memory fallback)
# ============================================================================

class ContactRateLimiter:
    """
    IP-based rate limiter for contact form submissions.
    
    Uses Redis if available, falls back to in-memory tracking.
    This prevents spam abuse on the public contact endpoint.
    
    Default: 5 submissions per hour per IP address.
    """
    
    def __init__(self, max_requests: int = 5, window_seconds: int = 3600):
        """
        Initialize the rate limiter.
        
        Args:
            max_requests: Maximum requests per window (default: 5)
            window_seconds: Time window in seconds (default: 3600 = 1 hour)
        """
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._prefix = "contact:rate_limit:"
        
        # Memory fallback storage
        self._memory_requests: dict[str, list[float]] = {}
        self._memory_lock = Lock()
        self._using_fallback = False
    
    async def is_rate_limited(self, client_ip: str) -> bool:
        """
        Check if an IP address is rate limited.
        
        Uses Redis if available, falls back to memory otherwise.
        
        Args:
            client_ip: Client IP address to check
            
        Returns:
            True if rate limited, False otherwise
        """
        from services.redis.client import get_redis_client
        
        redis_client = get_redis_client()
        
        if redis_client:
            try:
                result = await self._check_redis(redis_client, client_ip)
                if self._using_fallback:
                    logger.info("CONTACT_RATE_LIMIT: Recovered - Redis connection restored")
                self._using_fallback = False
                return result
            except Exception as e:
                if not self._using_fallback:
                    logger.warning(f"CONTACT_RATE_LIMIT: Entering memory fallback mode - {e}")
                self._using_fallback = True
        else:
            if not self._using_fallback:
                logger.warning("CONTACT_RATE_LIMIT: Starting in memory fallback mode - Redis unavailable")
            self._using_fallback = True
        
        return self._check_memory(client_ip)
    
    async def _check_redis(self, redis_client, client_ip: str) -> bool:
        """Redis-based rate limiting using sorted sets for sliding window."""
        key = f"{self._prefix}{client_ip}"
        current_time = time.time()
        window_start = current_time - self._window_seconds
        
        # Use pipeline for atomic operations
        pipe = redis_client.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zadd(key, {str(current_time): current_time})
        pipe.zcard(key)
        pipe.expire(key, self._window_seconds * 2)
        
        results = await pipe.execute()
        current_count = results[2]
        
        if current_count > self._max_requests:
            logger.debug(f"Contact rate limit exceeded for IP {client_ip[:16]}... (Redis): {current_count}/{self._max_requests}")
            return True
        
        return False
    
    def _check_memory(self, client_ip: str) -> bool:
        """Memory fallback for rate limiting."""
        with self._memory_lock:
            current_time = time.time()
            window_start = current_time - self._window_seconds
            
            if client_ip not in self._memory_requests:
                self._memory_requests[client_ip] = []
            
            # Remove old requests
            self._memory_requests[client_ip] = [
                ts for ts in self._memory_requests[client_ip]
                if ts > window_start
            ]
            
            # Check limit
            if len(self._memory_requests[client_ip]) >= self._max_requests:
                logger.debug(f"Contact rate limit exceeded for IP {client_ip[:16]}... (memory): {len(self._memory_requests[client_ip])}/{self._max_requests}")
                return True
            
            # Record request
            self._memory_requests[client_ip].append(current_time)
            return False


# Global rate limiter for contact form
# 5 submissions per hour per IP address
_contact_rate_limiter = ContactRateLimiter(max_requests=5, window_seconds=3600)


def get_client_ip(request: Request) -> str:
    """
    Extract client IP from request, accounting for reverse proxies.
    
    Checks X-Forwarded-For header first (for Railway/nginx proxies),
    falls back to request.client.host.
    """
    # Check for forwarded header (Railway, nginx, etc.)
    x_forwarded_for = request.headers.get("x-forwarded-for")
    if x_forwarded_for:
        # First IP in the list is the original client
        return x_forwarded_for.split(",")[0].strip()
    
    # Fallback to direct connection IP
    return request.client.host if request.client else "unknown"


async def check_contact_rate_limit(request: Request) -> str:
    """FastAPI dependency to check rate limit before processing."""
    client_ip = get_client_ip(request)
    
    if await _contact_rate_limiter.is_rate_limited(client_ip):
        logger.warning(f"Contact form rate limit exceeded for IP {client_ip[:16]}...")
        raise HTTPException(
            status_code=429,
            detail="Too many contact form submissions. Please try again later."
        )
    
    return client_ip


@router.post(
    "",
    response_model=ContactResponse,
    summary="Submit Contact Form",
    description="Submit a message from the landing page contact form. No authentication required. Rate limited to 5 submissions per hour per IP.",
    responses={
        200: {"description": "Message sent successfully"},
        422: {"description": "Validation error (invalid email, message too short, etc.)"},
        429: {"description": "Rate limit exceeded"},
        500: {"description": "Failed to send email"},
        503: {"description": "Email service not configured"}
    }
)
async def submit_contact_form(
    request: ContactRequest,
    client_ip: str = Depends(check_contact_rate_limit)
) -> ContactResponse:
    """
    Submit a contact form message.
    
    This endpoint is public (no authentication required) and is used by the
    landing page contact form. Messages are sent to admin@quizify.ca via Resend.
    
    Rate limited to 5 submissions per hour per IP address to prevent spam.
    """
    return await handle_contact_submission(request)
