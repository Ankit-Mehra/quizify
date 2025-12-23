"""
PostHog OpenTelemetry Logging Service.

Integrates Python's standard logging with PostHog's log management
using OpenTelemetry OTLP exporter. This allows viewing application
logs directly in PostHog alongside analytics, LLM traces, and errors.

Features:
- Sends Python logs to PostHog via OpenTelemetry
- Supports all log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Adds structured attributes to logs
- Batches log records for efficient transmission
- Graceful shutdown with log flushing
- Thread-safe singleton initialization

Usage:
    from services.posthog_logging import setup_posthog_logging, shutdown_posthog_logging
    
    # On app startup
    setup_posthog_logging()
    
    # On app shutdown
    shutdown_posthog_logging()

References:
    https://posthog.com/docs/logs/installation?tab=Python
"""

import logging
import threading
from typing import Optional

from config import Config

# OpenTelemetry imports with graceful fallback
try:
    from opentelemetry._logs import set_logger_provider
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    from opentelemetry.sdk.resources import Resource
    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    OPENTELEMETRY_AVAILABLE = False


# Module-level state
_logger_provider: Optional["LoggerProvider"] = None
_logging_handler: Optional["LoggingHandler"] = None
_posthog_logging_lock = threading.Lock()
_posthog_logging_initialized = False

# Logger for this module (uses standard logging, not PostHog to avoid circular deps)
_module_logger = logging.getLogger("posthog_logging")

# Application logger names to attach PostHog handler to
# Includes both centralized loggers (services/logger.py) and __name__ pattern loggers
# Used in both setup and shutdown to ensure consistent handler management
_APP_LOGGER_NAMES = [
    # Centralized loggers from services/logger.py
    "app", "db_services", "ai_services", "middleware",
    # __name__ pattern loggers used in various modules
    "services.db_services.supabase_file",
    "services.redis.sessions",
    "services.share_service",
    "services.llm.gemini_provider",  # Replaced gemini_service
    "services.llm.groq_provider",
    "services.exporters.csv_anki_exporter",
    "services.exporters.csv_quizify_exporter",
    "services.exporters.docx_exporter",
    "services.exporters.pdf_exporter",
    "services.exporters.moodle_xml_exporter",
    "services.exporters.tier_validator",
    "schemas.quiz",
    "schemas.quizzes_parsed",
]


def is_posthog_logging_available() -> bool:
    """
    Check if PostHog logging can be enabled.
    
    Returns True if:
    - OpenTelemetry packages are installed
    - PostHog API key is configured
    - PostHog logging is enabled via config
    """
    if not OPENTELEMETRY_AVAILABLE:
        return False
    
    if not Config.POSTHOG_API_KEY:
        return False
    
    # Use existing LLM analytics flag to also control logs
    # Or add a separate POSTHOG_LOGS_ENABLED if needed
    if not Config.POSTHOG_LLM_ANALYTICS_ENABLED:
        return False
    
    return True


def setup_posthog_logging(
    service_name: str = "quizify-api",
    min_log_level: int = logging.INFO
) -> bool:
    """
    Initialize PostHog OpenTelemetry logging.
    
    Sets up an OpenTelemetry LoggerProvider with OTLP exporter pointed
    at PostHog's log ingestion endpoint. Attaches a LoggingHandler to
    the root Python logger to forward logs to PostHog.
    
    Args:
        service_name: Service identifier shown in PostHog logs (default: "quizify-api")
        min_log_level: Minimum log level to send to PostHog (default: INFO)
                      Use logging.DEBUG for verbose, logging.WARNING for less noise
    
    Returns:
        bool: True if successfully initialized, False otherwise
    
    Note:
        - Call this once during application startup
        - Thread-safe with singleton pattern
        - Logs below min_log_level are not sent to PostHog (but still logged locally)
    """
    global _logger_provider, _logging_handler, _posthog_logging_initialized
    
    # Fast path: already initialized
    if _posthog_logging_initialized:
        return True
    
    with _posthog_logging_lock:
        # Double-check after acquiring lock
        if _posthog_logging_initialized:
            return True
        
        if not is_posthog_logging_available():
            if not OPENTELEMETRY_AVAILABLE:
                _module_logger.warning(
                    "OpenTelemetry packages not installed. PostHog logging disabled. "
                    "Install with: pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp"
                )
            elif not Config.POSTHOG_API_KEY:
                _module_logger.info("PostHog API key not configured. PostHog logging disabled.")
            else:
                _module_logger.info("PostHog LLM analytics disabled. PostHog logging also disabled.")
            return False
        
        try:
            # Build PostHog OTLP endpoint URL
            # PostHog expects logs at: https://us.i.posthog.com/i/v1/logs
            posthog_host = Config.POSTHOG_HOST.rstrip("/")
            logs_endpoint = f"{posthog_host}/i/v1/logs"
            
            # Create resource with service metadata
            resource = Resource.create({
                "service.name": service_name,
                "service.version": "1.0.0",
                "deployment.environment": "production" if not Config.TESTING else "test",
            })
            
            # Create OTLP exporter with PostHog authentication
            # Using Authorization header as per PostHog docs
            otlp_exporter = OTLPLogExporter(
                endpoint=logs_endpoint,
                headers={"Authorization": f"Bearer {Config.POSTHOG_API_KEY}"}
            )
            
            # Create logger provider with batch processor
            # BatchLogRecordProcessor batches logs for efficient network usage
            _logger_provider = LoggerProvider(resource=resource)
            _logger_provider.add_log_record_processor(
                BatchLogRecordProcessor(otlp_exporter)
            )
            
            # Set as global OpenTelemetry logger provider
            set_logger_provider(_logger_provider)
            
            # Create logging handler that bridges Python logging -> OpenTelemetry
            _logging_handler = LoggingHandler(
                level=min_log_level,
                logger_provider=_logger_provider
            )
            
            # Attach to root logger to capture logs from loggers with propagate=True
            root_logger = logging.getLogger()
            root_logger.addHandler(_logging_handler)
            
            # Also attach to application-specific loggers that have propagate=False
            # These loggers are defined in services/logger.py and won't propagate to root
            for logger_name in _APP_LOGGER_NAMES:
                app_logger = logging.getLogger(logger_name)
                # Add handler even if logger has no handlers yet (will be used when logs are emitted)
                if _logging_handler not in app_logger.handlers:
                    app_logger.addHandler(_logging_handler)
            
            # Note: We don't use atexit.register() here because shutdown_posthog_logging()
            # is called explicitly in main.py lifespan. Using atexit would be redundant
            # and could cause issues with shutdown ordering.
            
            _posthog_logging_initialized = True
            _module_logger.info(
                f"PostHog OpenTelemetry logging initialized "
                f"(endpoint: {logs_endpoint}, level: {logging.getLevelName(min_log_level)})"
            )
            return True
            
        except Exception as e:
            _module_logger.error(f"Failed to initialize PostHog logging: {e}")
            # Clean up partial initialization to allow retry
            _logger_provider = None
            _logging_handler = None
            return False


def shutdown_posthog_logging() -> None:
    """
    Shutdown PostHog logging and flush pending logs.
    
    Call this on application shutdown to ensure all buffered
    log records are sent to PostHog before the process exits.
    
    Thread-safe and idempotent (safe to call multiple times).
    Each cleanup step is wrapped in its own try-except to ensure
    we attempt all cleanup operations even if one fails.
    """
    global _logger_provider, _logging_handler, _posthog_logging_initialized
    
    with _posthog_logging_lock:
        if not _posthog_logging_initialized:
            return
        
        handler_removed = False
        provider_shutdown = False
        
        # Step 1: Remove handler from root logger and application-specific loggers
        try:
            if _logging_handler is not None:
                # Remove from root logger
                root_logger = logging.getLogger()
                root_logger.removeHandler(_logging_handler)
                
                # Remove from application-specific loggers
                for logger_name in _APP_LOGGER_NAMES:
                    app_logger = logging.getLogger(logger_name)
                    if _logging_handler in app_logger.handlers:
                        app_logger.removeHandler(_logging_handler)
                
                _logging_handler = None
                handler_removed = True
        except Exception as e:
            _module_logger.error(f"Error removing logging handler: {e}")
        
        # Step 2: Shutdown provider (flushes pending logs)
        try:
            if _logger_provider is not None:
                _logger_provider.shutdown()
                _logger_provider = None
                provider_shutdown = True
        except Exception as e:
            _module_logger.error(f"Error shutting down logger provider: {e}")
        
        # Always mark as uninitialized to allow re-initialization
        _posthog_logging_initialized = False
        
        if handler_removed and provider_shutdown:
            _module_logger.info("PostHog logging shutdown successfully")
        elif handler_removed or provider_shutdown:
            _module_logger.warning("PostHog logging shutdown completed with errors")
        else:
            _module_logger.error("PostHog logging shutdown failed")


def get_posthog_logger(name: str) -> logging.Logger:
    """
    Get a logger that will send logs to PostHog (if propagation is enabled).
    
    This returns a standard Python logger. Logs will reach PostHog only if:
    1. The logger's propagate attribute is True (default), OR
    2. The PostHog handler is added directly to this logger
    
    Note: Loggers with propagate=False (like those in services/logger.py) won't
    automatically send logs to PostHog through the root handler.
    
    Args:
        name: Logger name (typically __name__ or module path)
        
    Returns:
        logging.Logger: Standard Python logger
    """
    return logging.getLogger(name)


def log_with_attributes(
    logger: logging.Logger,
    level: int,
    message: str,
    **attributes
) -> None:
    """
    Log a message with structured attributes that appear in PostHog.
    
    OpenTelemetry captures the 'extra' dict as log attributes,
    making them searchable and filterable in PostHog.
    
    Args:
        logger: Python logger instance
        level: Log level (logging.INFO, logging.ERROR, etc.)
        message: Log message
        **attributes: Key-value pairs to attach as log attributes
        
    Example:
        log_with_attributes(
            logger, logging.INFO, "Quiz generated",
            user_id="123", quiz_id="abc", question_count=10
        )
    """
    logger.log(level, message, extra=attributes)
