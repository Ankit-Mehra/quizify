"""
PostHog LLM Analytics Service.

Provides a centralized PostHog client for LLM observability and analytics.
Tracks token usage, latency, costs, and user interactions with AI features.

Features:
- Automatic token counting and cost tracking
- Latency measurement for LLM calls
- User-level analytics (via distinct_id)
- Trace correlation for multi-step AI workflows
- Thread-safe singleton initialization

Note: Once initialized, the client configuration cannot change without
restarting the application. This is intentional for performance.
"""

import threading
from typing import Optional, Union
from posthog import Posthog
from config import Config
from services.logger import app_logger as logger


# Sentinel object to cache "disabled" state and avoid repeated lock acquisition
class _PostHogDisabled:
    """Sentinel indicating PostHog is explicitly disabled."""
    pass


_POSTHOG_DISABLED = _PostHogDisabled()

# Global PostHog client instance with thread-safe initialization
# Can be: None (not yet checked), Posthog instance, or _POSTHOG_DISABLED sentinel
_posthog_client: Optional[Union[Posthog, _PostHogDisabled]] = None
_posthog_lock = threading.Lock()
# Track if PostHog wrapper was successfully initialized (for kwargs check)
_posthog_wrapper_active: bool = False


def get_posthog_client() -> Optional[Posthog]:
    """
    Get or create the PostHog client instance (thread-safe).
    
    Returns a singleton PostHog client configured with the project API key
    and host from environment variables. Returns None if PostHog is not
    configured (no API key) or if LLM analytics is disabled.
    
    Uses double-checked locking pattern for thread-safe lazy initialization.
    Caches "disabled" state to avoid repeated lock acquisition and logging.
    
    Returns:
        Optional[Posthog]: PostHog client instance or None if not configured
    """
    global _posthog_client, _posthog_wrapper_active
    
    # Fast path: return cached client or None if disabled
    if _posthog_client is not None:
        if isinstance(_posthog_client, _PostHogDisabled):
            return None
        return _posthog_client
    
    # Thread-safe initialization with lock
    with _posthog_lock:
        # Double-check after acquiring lock
        if _posthog_client is not None:
            if isinstance(_posthog_client, _PostHogDisabled):
                return None
            return _posthog_client
        
        # Check if PostHog is configured and enabled
        if not Config.POSTHOG_API_KEY:
            logger.warning(
                "PostHog API key not configured. LLM analytics will be disabled. "
                "Set POSTHOG_API_KEY environment variable to enable."
            )
            _posthog_client = _POSTHOG_DISABLED
            return None
        
        if not Config.POSTHOG_LLM_ANALYTICS_ENABLED:
            logger.info("PostHog LLM analytics is disabled via POSTHOG_LLM_ANALYTICS_ENABLED=false")
            _posthog_client = _POSTHOG_DISABLED
            return None
        
        try:
            _posthog_client = Posthog(
                api_key=Config.POSTHOG_API_KEY,
                host=Config.POSTHOG_HOST,
                # Enable GeoIP lookup for event geolocation
                disable_geoip=False,
            )
            _posthog_wrapper_active = True
            logger.info(f"PostHog LLM analytics initialized successfully (host: {Config.POSTHOG_HOST})")
            return _posthog_client
        except Exception as e:
            logger.error(f"Failed to initialize PostHog client: {e}")
            _posthog_client = _POSTHOG_DISABLED
            return None


def is_posthog_wrapper_active() -> bool:
    """
    Check if PostHog wrapper was successfully initialized.
    
    This is different from is_posthog_enabled() - it checks if the wrapper
    is actually active and ready to accept PostHog-specific kwargs.
    
    Returns:
        bool: True if PostHog wrapper is active and kwargs should be added
    """
    # Trigger initialization if not done yet
    get_posthog_client()
    return _posthog_wrapper_active


def shutdown_posthog() -> None:
    """
    Shutdown the PostHog client gracefully (thread-safe).
    
    Should be called on application shutdown to ensure all events are flushed.
    Uses lock to prevent concurrent access during shutdown.
    """
    global _posthog_client, _posthog_wrapper_active
    
    with _posthog_lock:
        if _posthog_client is not None and not isinstance(_posthog_client, _PostHogDisabled):
            try:
                _posthog_client.shutdown()
                logger.info("PostHog client shutdown successfully")
            except Exception as e:
                logger.error(f"Error shutting down PostHog client: {e}")
            finally:
                _posthog_client = None
                _posthog_wrapper_active = False
        else:
            _posthog_client = None
            _posthog_wrapper_active = False


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
