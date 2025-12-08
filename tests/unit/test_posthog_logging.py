"""
Unit tests for PostHog OpenTelemetry logging service.

Tests the logging initialization, configuration, and shutdown behavior.
"""

import logging
from unittest.mock import patch, MagicMock
import pytest

from services.posthog_logging import (
    is_posthog_logging_available,
    setup_posthog_logging,
    shutdown_posthog_logging,
    get_posthog_logger,
    log_with_attributes,
    OPENTELEMETRY_AVAILABLE,
)
import services.posthog_logging as posthog_module


@pytest.fixture(autouse=True)
def reset_posthog_global_state():
    """
    Reset PostHog logging global state before and after each test.
    
    This prevents test pollution from shared global state.
    """
    # Store original state
    original_initialized = posthog_module._posthog_logging_initialized
    original_provider = posthog_module._logger_provider
    original_handler = posthog_module._logging_handler
    
    # Reset before test
    posthog_module._posthog_logging_initialized = False
    posthog_module._logger_provider = None
    posthog_module._logging_handler = None
    
    yield
    
    # Restore original state after test
    posthog_module._posthog_logging_initialized = original_initialized
    posthog_module._logger_provider = original_provider
    posthog_module._logging_handler = original_handler


class TestPostHogLoggingAvailability:
    """Tests for checking PostHog logging availability."""

    def test_opentelemetry_packages_installed(self):
        """OpenTelemetry packages should be installed."""
        assert OPENTELEMETRY_AVAILABLE is True

    @patch("services.posthog_logging.Config")
    def test_not_available_without_api_key(self, mock_config):
        """Should return False when PostHog API key is not set."""
        mock_config.POSTHOG_API_KEY = ""
        mock_config.POSTHOG_LLM_ANALYTICS_ENABLED = True
        
        assert is_posthog_logging_available() is False

    @patch("services.posthog_logging.Config")
    def test_not_available_when_analytics_disabled(self, mock_config):
        """Should return False when PostHog LLM analytics is disabled."""
        mock_config.POSTHOG_API_KEY = "test-key"
        mock_config.POSTHOG_LLM_ANALYTICS_ENABLED = False
        
        assert is_posthog_logging_available() is False

    @patch("services.posthog_logging.Config")
    def test_available_when_configured(self, mock_config):
        """Should return True when properly configured."""
        mock_config.POSTHOG_API_KEY = "test-key"
        mock_config.POSTHOG_LLM_ANALYTICS_ENABLED = True
        
        assert is_posthog_logging_available() is True


class TestPostHogLoggingSetup:
    """Tests for PostHog logging setup."""

    @patch("services.posthog_logging.is_posthog_logging_available")
    def test_setup_returns_false_when_not_available(self, mock_available):
        """Should return False when PostHog logging is not available."""
        mock_available.return_value = False
        
        result = setup_posthog_logging()
        assert result is False

    @patch("services.posthog_logging.is_posthog_logging_available")
    @patch("services.posthog_logging.Config")
    @patch("services.posthog_logging.OTLPLogExporter")
    @patch("services.posthog_logging.LoggerProvider")
    @patch("services.posthog_logging.BatchLogRecordProcessor")
    @patch("services.posthog_logging.Resource")
    @patch("services.posthog_logging.set_logger_provider")
    @patch("services.posthog_logging.LoggingHandler")
    def test_setup_initializes_correctly(
        self, 
        mock_handler_class,
        mock_set_provider,
        mock_resource_class,
        mock_batch_processor_class,
        mock_provider_class,
        mock_exporter_class,
        mock_config,
        mock_available
    ):
        """Should initialize OpenTelemetry logging correctly."""
        mock_available.return_value = True
        mock_config.POSTHOG_API_KEY = "test-api-key"
        mock_config.POSTHOG_HOST = "https://us.i.posthog.com"
        mock_config.TESTING = False
        
        mock_provider = MagicMock()
        mock_provider_class.return_value = mock_provider
        
        mock_handler = MagicMock()
        mock_handler_class.return_value = mock_handler
        
        mock_resource = MagicMock()
        mock_resource_class.create.return_value = mock_resource
        
        mock_processor = MagicMock()
        mock_batch_processor_class.return_value = mock_processor
        
        result = setup_posthog_logging(service_name="test-service")
        
        assert result is True
        
        # Verify exporter was created with correct endpoint
        mock_exporter_class.assert_called_once()
        call_kwargs = mock_exporter_class.call_args[1]
        assert "https://us.i.posthog.com/i/v1/logs" in call_kwargs["endpoint"]
        assert "Authorization" in call_kwargs["headers"]
        assert "Bearer test-api-key" in call_kwargs["headers"]["Authorization"]
        
        # Verify batch processor was created
        mock_batch_processor_class.assert_called_once()
        
        # Verify resource was created
        mock_resource_class.create.assert_called_once()
        
        # Verify provider was set
        mock_set_provider.assert_called_once_with(mock_provider)

    def test_setup_is_idempotent(self):
        """Setup should be idempotent (safe to call multiple times)."""
        # If already initialized, should return True without reinitializing
        posthog_module._posthog_logging_initialized = True
        
        result = setup_posthog_logging()
        assert result is True


class TestPostHogLoggingShutdown:
    """Tests for PostHog logging shutdown."""

    def test_shutdown_when_not_initialized(self):
        """Shutdown should be safe to call when not initialized."""
        # Global state already reset by fixture
        # Should not raise
        shutdown_posthog_logging()

    def test_shutdown_removes_handler_and_provider(self):
        """Shutdown should remove handler and provider."""
        mock_handler = MagicMock()
        mock_provider = MagicMock()
        
        posthog_module._posthog_logging_initialized = True
        posthog_module._logging_handler = mock_handler
        posthog_module._logger_provider = mock_provider
        
        # Add mock handler to root logger
        root_logger = logging.getLogger()
        root_logger.addHandler(mock_handler)
        
        shutdown_posthog_logging()
        
        # Verify global state is cleaned up
        assert posthog_module._posthog_logging_initialized is False
        assert posthog_module._logger_provider is None
        assert posthog_module._logging_handler is None
        
        # Verify provider shutdown was called
        mock_provider.shutdown.assert_called_once()
        
        # Verify handler was removed from root logger
        assert mock_handler not in root_logger.handlers


class TestPostHogLoggerHelpers:
    """Tests for logger helper functions."""

    def test_get_posthog_logger_returns_logger(self):
        """get_posthog_logger should return a standard Python logger."""
        logger = get_posthog_logger("test-module")
        
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test-module"

    def test_log_with_attributes_logs_message(self):
        """log_with_attributes should log with extra attributes."""
        logger = MagicMock(spec=logging.Logger)
        
        log_with_attributes(
            logger,
            logging.INFO,
            "Test message",
            user_id="123",
            action="test"
        )
        
        logger.log.assert_called_once_with(
            logging.INFO,
            "Test message",
            extra={"user_id": "123", "action": "test"}
        )
