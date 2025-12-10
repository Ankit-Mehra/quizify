"""
Cron API Routes - Scheduled task endpoints.

These endpoints are designed to be called by external schedulers (Railway cron, 
Supabase pg_cron, GitHub Actions, etc.) and are protected by API key authentication.

Endpoints:
- POST /cron/reset-monthly-credits: Reset monthly credit allowances for users past period_end
"""

from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, status
from config import Config
from services.billing_service import reset_expired_monthly_credits
from services.logger import app_logger as logger

router = APIRouter(prefix="/cron", tags=["cron"])


def verify_cron_api_key(x_cron_api_key: Optional[str] = Header(default=None, alias="X-Cron-API-Key")) -> bool:
    """
    Verify the cron API key for scheduled task authentication.
    
    The API key should be set in CRON_API_KEY environment variable and
    passed in the X-Cron-API-Key header.
    
    Raises:
        HTTPException 401: If API key is missing or invalid
    """
    import os
    expected_key = getattr(Config, "CRON_API_KEY", None)
    
    if not expected_key:
        # Defensive production detection:
        # - RAILWAY_ENVIRONMENT: Set automatically by Railway ("production", "staging", etc.)
        # - ENV: Common convention for environment name
        # - RAILWAY_PROJECT_ID: Exists if running on Railway at all
        # If ANY of these indicate non-local environment, require the key
        railway_env = os.getenv("RAILWAY_ENVIRONMENT", "")
        env = os.getenv("ENV", "")
        is_railway = os.getenv("RAILWAY_PROJECT_ID") is not None
        
        is_production = (
            railway_env.lower() in ("production", "prod") or
            env.lower() in ("production", "prod") or
            is_railway  # If on Railway at all, require key
        )
        
        if is_production:
            # CRITICAL: Block unauthenticated requests in production/Railway
            logger.error("SECURITY: CRON_API_KEY not configured in production - blocking request")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Cron endpoint not configured"
            )
        else:
            # INTENTIONAL: Allow in local development only (no Railway env vars)
            # DEPLOYMENT NOTE: Always set CRON_API_KEY in Railway/production environments
            # See docs/ENV_VARIABLES_GUIDE.md for configuration requirements
            logger.warning("CRON_API_KEY not configured - allowing request (local development only)")
            return True
    
    # Use constant-time comparison to prevent timing attacks
    import secrets
    if not x_cron_api_key or not secrets.compare_digest(x_cron_api_key, expected_key):
        logger.warning("Invalid cron API key attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    
    return True


@router.post("/reset-monthly-credits")
async def reset_monthly_credits(
    _: bool = Depends(verify_cron_api_key)
):
    """
    Reset monthly FREE credit allowances for free-tier users past their period_end.
    
    This endpoint should be called daily by a cron job. It will:
    1. Find FREE users where current_period_end < now() (or null)
    2. Reset free_credit_units_remaining to free_credit_units_monthly
    3. Update period_start/end to calendar month boundaries
    
    **Important**: Pro users with active subscriptions are SKIPPED.
    Their credits and periods are managed by Stripe webhooks (invoice.paid)
    to stay in sync with their Stripe billing cycles.
    
    **Authentication**: Requires X-Cron-API-Key header
    
    Returns:
        reset_count: Number of free users reset
        error_count: Number of errors encountered  
        errors: First 10 errors for debugging
    """
    # Verify API key from header (passed via dependency injection in params)
    # Since we can't use Depends() with Header alias properly, verify manually
    
    # The API key is already validated by the Header parameter if CRON_API_KEY is set
    # For now, we'll rely on the service being internal or add validation in a middleware
    
    expected_key = getattr(Config, "CRON_API_KEY", None)
    if not expected_key:
        # Allow if not configured (for development/testing)
        logger.warning("CRON_API_KEY not configured - allowing request")
    
    logger.info("Starting monthly credit reset cron job")
    
    try:
        result = await reset_expired_monthly_credits()
        
        logger.info(f"Monthly credit reset complete: {result['reset_count']} users, {result['error_count']} errors")
        
        return {
            "status": "success",
            "reset_count": result["reset_count"],
            "error_count": result["error_count"],
            "errors": result.get("errors", [])
        }
        
    except Exception as e:
        logger.error(f"Monthly credit reset failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Credit reset failed: {str(e)}"
        )
