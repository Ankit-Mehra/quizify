"""
Unit tests for Contact Handler.

Tests the contact form submission logic including:
- Successful email sending
- Missing API key handling
- Resend API errors
- HTML escaping for XSS prevention
- Input validation
"""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from handlers.contact_handler import handle_contact_submission
from schemas.contact import ContactRequest, ContactResponse


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def valid_contact_request():
    """Create a valid contact form request."""
    return ContactRequest(
        name="John Doe",
        email="john@example.com",
        subject="Test Subject",
        message="This is a test message for the contact form."
    )


@pytest.fixture
def xss_contact_request():
    """Create a contact request with potential XSS content."""
    return ContactRequest(
        name="<script>alert('xss')</script>",
        email="test@example.com",
        subject="<img src=x onerror=alert('xss')>",
        message="<a href='javascript:alert(1)'>Click me</a>"
    )


# ============================================================================
# Success Tests
# ============================================================================

@pytest.mark.asyncio
async def test_handle_contact_submission_success(valid_contact_request):
    """Test successful contact form submission."""
    with patch("handlers.contact_handler.Config") as mock_config, \
         patch("handlers.contact_handler.resend") as mock_resend:
        
        # Configure mocks
        mock_config.RESEND_API_KEY = "re_test_key"
        mock_config.CONTACT_EMAIL = "admin@quizify.ca"
        mock_resend.Emails.send.return_value = {"id": "email_123"}
        
        # Execute
        result = await handle_contact_submission(valid_contact_request)
        
        # Verify
        assert isinstance(result, ContactResponse)
        assert result.success is True
        assert "successfully" in result.message.lower()
        
        # Verify email was sent
        mock_resend.Emails.send.assert_called_once()
        call_params = mock_resend.Emails.send.call_args[0][0]
        assert call_params["to"] == ["admin@quizify.ca"]
        assert call_params["reply_to"] == "john@example.com"
        assert "[Contact Form]" in call_params["subject"]


@pytest.mark.asyncio
async def test_handle_contact_submission_email_content(valid_contact_request):
    """Test that email content contains the submitted data."""
    with patch("handlers.contact_handler.Config") as mock_config, \
         patch("handlers.contact_handler.resend") as mock_resend:
        
        mock_config.RESEND_API_KEY = "re_test_key"
        mock_config.CONTACT_EMAIL = "admin@quizify.ca"
        mock_resend.Emails.send.return_value = {"id": "email_123"}
        
        await handle_contact_submission(valid_contact_request)
        
        call_params = mock_resend.Emails.send.call_args[0][0]
        
        # Check HTML content contains form data
        assert "John Doe" in call_params["html"]
        assert "john@example.com" in call_params["html"]
        assert "Test Subject" in call_params["html"]
        assert "test message" in call_params["text"]


# ============================================================================
# Error Handling Tests
# ============================================================================

@pytest.mark.asyncio
async def test_handle_contact_submission_missing_api_key(valid_contact_request):
    """Test handling when RESEND_API_KEY is not configured."""
    with patch("handlers.contact_handler.Config") as mock_config:
        mock_config.RESEND_API_KEY = None
        
        with pytest.raises(HTTPException) as exc_info:
            await handle_contact_submission(valid_contact_request)
        
        assert exc_info.value.status_code == 503
        assert "temporarily unavailable" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_handle_contact_submission_resend_error(valid_contact_request):
    """Test handling of Resend API errors."""
    with patch("handlers.contact_handler.Config") as mock_config, \
         patch("handlers.contact_handler.resend") as mock_resend:
        
        mock_config.RESEND_API_KEY = "re_test_key"
        mock_config.CONTACT_EMAIL = "admin@quizify.ca"
        
        # Create a mock exception class that can be caught
        class MockResendError(Exception):
            pass
        
        mock_resend.exceptions.ResendError = MockResendError
        mock_resend.Emails.send.side_effect = MockResendError("API Error")
        
        with pytest.raises(HTTPException) as exc_info:
            await handle_contact_submission(valid_contact_request)
        
        assert exc_info.value.status_code == 500
        assert "failed" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_handle_contact_submission_unexpected_error(valid_contact_request):
    """Test handling of unexpected errors."""
    with patch("handlers.contact_handler.Config") as mock_config, \
         patch("handlers.contact_handler.resend") as mock_resend:
        
        mock_config.RESEND_API_KEY = "re_test_key"
        mock_config.CONTACT_EMAIL = "admin@quizify.ca"
        
        # Create a mock exception class that will NOT be caught by ResendError handler
        class MockResendError(Exception):
            pass
        
        mock_resend.exceptions.ResendError = MockResendError
        # Raise a different exception type (not MockResendError)
        mock_resend.Emails.send.side_effect = ValueError("Unexpected error")
        
        with pytest.raises(HTTPException) as exc_info:
            await handle_contact_submission(valid_contact_request)
        
        assert exc_info.value.status_code == 500
        assert "unexpected error" in exc_info.value.detail.lower()


# ============================================================================
# Security Tests - HTML Escaping
# ============================================================================

@pytest.mark.asyncio
async def test_html_escaping_prevents_xss(xss_contact_request):
    """Test that user inputs are HTML-escaped to prevent XSS in emails.
    
    The key security concern is that tags like <script> and <a> are escaped
    so they render as literal text rather than being interpreted as HTML.
    The content inside (like 'javascript:') is still present but harmless
    since it's not inside an actual anchor tag.
    """
    with patch("handlers.contact_handler.Config") as mock_config, \
         patch("handlers.contact_handler.resend") as mock_resend:
        
        mock_config.RESEND_API_KEY = "re_test_key"
        mock_config.CONTACT_EMAIL = "admin@quizify.ca"
        mock_resend.Emails.send.return_value = {"id": "email_123"}
        
        await handle_contact_submission(xss_contact_request)
        
        call_params = mock_resend.Emails.send.call_args[0][0]
        html_content = call_params["html"]
        
        # Verify script tags are escaped (< becomes &lt;)
        # The raw <script> tag should not be present
        assert "<script>" not in html_content
        assert "&lt;script&gt;" in html_content
        
        # Verify the img tag is escaped (not rendered as actual HTML)
        # The raw <img tag should not be present
        assert "<img " not in html_content
        assert "&lt;img src=x" in html_content
        
        # Verify the anchor tag is escaped (not rendered as actual HTML)
        # The raw <a href should not be present
        assert "<a href" not in html_content
        assert "&lt;a href=" in html_content
        
        # The quotes are also escaped, making the href attribute harmless
        assert "&#x27;" in html_content  # Escaped single quotes


@pytest.mark.asyncio
async def test_plain_text_not_escaped(xss_contact_request):
    """Test that plain text email uses original content (no HTML rendering risk)."""
    with patch("handlers.contact_handler.Config") as mock_config, \
         patch("handlers.contact_handler.resend") as mock_resend:
        
        mock_config.RESEND_API_KEY = "re_test_key"
        mock_config.CONTACT_EMAIL = "admin@quizify.ca"
        mock_resend.Emails.send.return_value = {"id": "email_123"}
        
        await handle_contact_submission(xss_contact_request)
        
        call_params = mock_resend.Emails.send.call_args[0][0]
        text_content = call_params["text"]
        
        # Plain text should contain the original (unescaped) content
        # since plain text emails don't render HTML
        assert "<script>" in text_content
        assert "javascript:" in text_content


@pytest.mark.asyncio
async def test_special_characters_escaped():
    """Test that special HTML characters are properly escaped."""
    request = ContactRequest(
        name="John & Jane <Doe>",
        email="test@example.com",
        subject="Test \"Subject\" with 'quotes'",
        message="Message with <html> and & ampersand"
    )
    
    with patch("handlers.contact_handler.Config") as mock_config, \
         patch("handlers.contact_handler.resend") as mock_resend:
        
        mock_config.RESEND_API_KEY = "re_test_key"
        mock_config.CONTACT_EMAIL = "admin@quizify.ca"
        mock_resend.Emails.send.return_value = {"id": "email_123"}
        
        await handle_contact_submission(request)
        
        call_params = mock_resend.Emails.send.call_args[0][0]
        html_content = call_params["html"]
        
        # Verify proper escaping of HTML special characters
        assert "&amp;" in html_content  # & escaped
        assert "&lt;" in html_content  # < escaped
        assert "&gt;" in html_content  # > escaped


# ============================================================================
# Input Validation Tests (Pydantic schema validation)
# ============================================================================

def test_contact_request_valid():
    """Test that valid contact request passes validation."""
    request = ContactRequest(
        name="John Doe",
        email="john@example.com",
        subject="Test",
        message="Test message with minimum length"
    )
    assert request.name == "John Doe"
    assert request.email == "john@example.com"


def test_contact_request_invalid_email():
    """Test that invalid email is rejected."""
    from pydantic import ValidationError
    
    with pytest.raises(ValidationError) as exc_info:
        ContactRequest(
            name="John Doe",
            email="not-an-email",
            subject="Test",
            message="Test message"
        )
    
    assert "email" in str(exc_info.value).lower()


def test_contact_request_empty_name():
    """Test that empty name is rejected."""
    from pydantic import ValidationError
    
    with pytest.raises(ValidationError):
        ContactRequest(
            name="",
            email="john@example.com",
            subject="Test",
            message="Test message"
        )
