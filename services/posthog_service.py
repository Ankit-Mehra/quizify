"""
PostHog LLM Analytics Service.

Provides a centralized PostHog client for LLM observability and analytics.
Tracks token usage, latency, costs, and user interactions with AI features.

Features:
- Automatic token counting and cost tracking
- Latency measurement for LLM calls
- User-level analytics (via distinct_id)
- Trace correlation for multi-step AI workflows
- Privacy mode support for sensitive data
- Thread-safe singleton initialization
"""

import threading
from typing import Optional
from posthog import Posthog
from config import Config
from services.logger import app_logger as logger

# Global PostHog client instance with thread-safe initialization
_posthog_client: Optional[Posthog] = None
_posthog_lock = threading.Lock()


def get_posthog_client() -> Optional[Posthog]:
    """
    Get or create the PostHog client instance (thread-safe).
    
    Returns a singleton PostHog client configured with the project API key
    and host from environment variables. Returns None if PostHog is not
    configured (no API key) or if LLM analytics is disabled.
    
    Uses double-checked locking pattern for thread-safe lazy initialization.
    
    Returns:
        Optional[Posthog]: PostHog client instance or None if not configured
    """
    global _posthog_client
    
    # Fast path: return cached client if already initialized
    if _posthog_client is not None:
        return _posthog_client
    
    # Thread-safe initialization with lock
    with _posthog_lock:
        # Double-check after acquiring lock
        if _posthog_client is not None:
            return _posthog_client
        
        # Check if PostHog is configured and enabled
        if not Config.POSTHOG_API_KEY:
            logger.warning(
                "PostHog API key not configured. LLM analytics will be disabled. "
                "Set POSTHOG_API_KEY environment variable to enable."
            )
            return None
        
        if not Config.POSTHOG_LLM_ANALYTICS_ENABLED:
            logger.info("PostHog LLM analytics is disabled via POSTHOG_LLM_ANALYTICS_ENABLED=false")
            return None
        
        try:
            _posthog_client = Posthog(
                api_key=Config.POSTHOG_API_KEY,
                host=Config.POSTHOG_HOST,
                # Enable GeoIP lookup for event geolocation
                disable_geoip=False,
            )
            logger.info(f"PostHog LLM analytics initialized successfully (host: {Config.POSTHOG_HOST})")
            return _posthog_client
        except Exception as e:
            logger.error(f"Failed to initialize PostHog client: {e}")
            return None


def shutdown_posthog() -> None:
    """
    Shutdown the PostHog client gracefully (thread-safe).
    
    Should be called on application shutdown to ensure all events are flushed.
    Uses lock to prevent concurrent access during shutdown.
    """
    global _posthog_client
    
    with _posthog_lock:
        if _posthog_client is not None:
            try:
                _posthog_client.shutdown()
                logger.info("PostHog client shutdown successfully")
            except Exception as e:
                logger.error(f"Error shutting down PostHog client: {e}")
            finally:
                _posthog_client = None


def is_posthog_enabled() -> bool:
    """
    Check if PostHog LLM analytics is enabled and configured.
    
    Returns:
        bool: True if PostHog is ready to track events
    """
    return (
        Config.POSTHOG_LLM_ANALYTICS_ENABLED 
        and bool(Config.POSTHOG_API_KEY)
    )
