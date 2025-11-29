"""
Unit tests for Google Auth Service state token utilities.

Tests the HMAC-signed state token generation and validation for OAuth CSRF protection.
"""

import time
from unittest.mock import patch

from services.google_auth_service import (
    STATE_TOKEN_EXPIRY_SECONDS,
    generate_secure_state_token,
    validate_secure_state_token,
)


# ============================================================================
# Token Generation Tests
# ============================================================================

def test_generate_secure_state_token_format():
    """Test that generated token has correct format: timestamp:user_id:redirect_b64:signature."""
    token = generate_secure_state_token("user-123")
    
    parts = token.split(":")
    assert len(parts) == 4, "Token should have 4 parts separated by colons"
    
    timestamp_str, user_id, redirect_b64, signature = parts
    
    # Timestamp should be a valid integer
    timestamp = int(timestamp_str)
    assert timestamp > 0
    
    # User ID should match
    assert user_id == "user-123"
    
    # redirect_b64 should be empty (no redirect_url provided)
    assert redirect_b64 == ""
    
    # Signature should be a hex string (SHA256 = 64 hex chars)
    assert len(signature) == 64
    assert all(c in "0123456789abcdef" for c in signature)


def test_generate_secure_state_token_with_redirect_url():
    """Test that generated token includes redirect_url correctly."""
    import base64
    
    token = generate_secure_state_token("user-123", redirect_url="/quizzes/abc123")
    
    parts = token.split(":")
    assert len(parts) == 4, "Token should have 4 parts separated by colons"
    
    timestamp_str, user_id, redirect_b64, signature = parts
    
    # User ID should match
    assert user_id == "user-123"
    
    # redirect_b64 should decode to the original URL
    decoded_url = base64.urlsafe_b64decode(redirect_b64.encode()).decode()
    assert decoded_url == "/quizzes/abc123"


def test_generate_secure_state_token_unique_signatures():
    """Test that different user IDs produce different signatures."""
    token1 = generate_secure_state_token("user-1")
    token2 = generate_secure_state_token("user-2")
    
    sig1 = token1.split(":")[3]
    sig2 = token2.split(":")[3]
    
    assert sig1 != sig2, "Different users should have different signatures"


def test_generate_secure_state_token_timestamp_is_current():
    """Test that the timestamp is approximately current time."""
    before = int(time.time())
    token = generate_secure_state_token("user-123")
    after = int(time.time())
    
    timestamp = int(token.split(":")[0])
    
    assert before <= timestamp <= after, "Timestamp should be current time"


# ============================================================================
# Token Validation - Success Cases
# ============================================================================

def test_validate_secure_state_token_success():
    """Test successful validation of a freshly generated token."""
    token = generate_secure_state_token("user-123")
    
    user_id, redirect_url, error = validate_secure_state_token(token)
    
    assert error == "", f"Should not have error, got: {error}"
    assert user_id == "user-123"
    assert redirect_url is None  # No redirect_url was provided


def test_validate_secure_state_token_with_redirect():
    """Test validation returns redirect_url correctly."""
    token = generate_secure_state_token("user-123", redirect_url="/quizzes/test")
    
    user_id, redirect_url, error = validate_secure_state_token(token)
    
    assert error == ""
    assert user_id == "user-123"
    assert redirect_url == "/quizzes/test"


def test_validate_secure_state_token_with_uuid():
    """Test validation with a UUID user ID."""
    uuid = "550e8400-e29b-41d4-a716-446655440000"
    token = generate_secure_state_token(uuid)
    
    user_id, redirect_url, error = validate_secure_state_token(token)
    
    assert error == ""
    assert user_id == uuid


def test_validate_secure_state_token_round_trip():
    """Test multiple round trips with different user IDs."""
    test_ids = [
        "simple-id",
        "user@example.com",
        "123456",
        "00000000-0000-0000-0000-000000000000",
        "special!@#$%chars",
    ]
    
    for test_id in test_ids:
        token = generate_secure_state_token(test_id)
        user_id, redirect_url, error = validate_secure_state_token(token)
        assert error == "", f"Failed for ID: {test_id}"
        assert user_id == test_id, f"User ID mismatch for: {test_id}"


def test_validate_secure_state_token_round_trip_with_redirects():
    """Test round trips with various redirect URLs."""
    test_cases = [
        ("/quizzes/123", "/quizzes/123"),
        ("/settings", "/settings"),
        ("/dashboard?tab=quizzes", "/dashboard?tab=quizzes"),
        ("/quiz/abc123/export", "/quiz/abc123/export"),
    ]
    
    for input_url, expected_url in test_cases:
        token = generate_secure_state_token("user-123", redirect_url=input_url)
        user_id, redirect_url, error = validate_secure_state_token(token)
        assert error == "", f"Failed for URL: {input_url}"
        assert redirect_url == expected_url, f"URL mismatch for: {input_url}"


# ============================================================================
# Token Validation - Invalid Format
# ============================================================================

def test_validate_empty_token():
    """Test that empty token returns invalid_state error."""
    user_id, redirect_url, error = validate_secure_state_token("")
    
    assert user_id is None
    assert redirect_url is None
    assert error == "invalid_state"


def test_validate_none_token():
    """Test that None token returns invalid_state error."""
    user_id, redirect_url, error = validate_secure_state_token(None)
    
    assert user_id is None
    assert redirect_url is None
    assert error == "invalid_state"


def test_validate_token_wrong_format_one_part():
    """Test token with only one part."""
    user_id, redirect_url, error = validate_secure_state_token("just-one-part")
    
    assert user_id is None
    assert redirect_url is None
    assert error == "invalid_state"


def test_validate_token_wrong_format_two_parts():
    """Test token with only two parts."""
    user_id, redirect_url, error = validate_secure_state_token("part1:part2")
    
    assert user_id is None
    assert redirect_url is None
    assert error == "invalid_state"


def test_validate_token_old_format_three_parts():
    """Test token with old 3-part format is still valid (backwards compatibility)."""
    # Old format: timestamp:user_id:signature
    import hashlib
    import hmac
    from services.google_auth_service import _get_state_secret
    
    timestamp = int(time.time())
    payload = f"{timestamp}:user-123"
    signature = hmac.new(
        _get_state_secret(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    old_format_token = f"{payload}:{signature}"
    
    user_id, redirect_url, error = validate_secure_state_token(old_format_token)
    
    assert error == ""
    assert user_id == "user-123"
    assert redirect_url is None  # Old format has no redirect_url


def test_validate_token_wrong_format_five_parts():
    """Test token with too many parts is rejected."""
    user_id, redirect_url, error = validate_secure_state_token("p1:p2:p3:p4:p5")
    
    assert user_id is None
    assert redirect_url is None
    assert error == "invalid_state"


def test_validate_token_invalid_timestamp():
    """Test token with non-numeric timestamp."""
    user_id, redirect_url, error = validate_secure_state_token("not-a-number:user-123::abcdef1234")
    
    assert user_id is None
    assert redirect_url is None
    assert error == "invalid_state"


# ============================================================================
# Token Validation - Signature Tampering
# ============================================================================

def test_validate_token_tampered_signature():
    """Test that a tampered signature is rejected."""
    token = generate_secure_state_token("user-123")
    parts = token.split(":")
    
    # Tamper with the signature
    tampered_token = f"{parts[0]}:{parts[1]}:{parts[2]}:{'0' * 64}"
    
    user_id, redirect_url, error = validate_secure_state_token(tampered_token)
    
    assert user_id is None
    assert error == "invalid_state"


def test_validate_token_tampered_user_id():
    """Test that changing the user ID invalidates the signature."""
    token = generate_secure_state_token("user-123")
    parts = token.split(":")
    
    # Tamper with the user ID
    tampered_token = f"{parts[0]}:hacker-456:{parts[2]}:{parts[3]}"
    
    user_id, redirect_url, error = validate_secure_state_token(tampered_token)
    
    assert user_id is None
    assert error == "invalid_state"


def test_validate_token_tampered_timestamp():
    """Test that changing the timestamp invalidates the signature."""
    token = generate_secure_state_token("user-123")
    parts = token.split(":")
    
    # Tamper with the timestamp
    new_timestamp = str(int(parts[0]) + 1)
    tampered_token = f"{new_timestamp}:{parts[1]}:{parts[2]}:{parts[3]}"
    
    user_id, redirect_url, error = validate_secure_state_token(tampered_token)
    
    assert user_id is None
    assert error == "invalid_state"


def test_validate_token_tampered_redirect_url():
    """Test that changing the redirect_url invalidates the signature."""
    import base64
    
    token = generate_secure_state_token("user-123", redirect_url="/quizzes/123")
    parts = token.split(":")
    
    # Tamper with the redirect_url to a malicious URL
    malicious_b64 = base64.urlsafe_b64encode(b"https://evil.com").decode()
    tampered_token = f"{parts[0]}:{parts[1]}:{malicious_b64}:{parts[3]}"
    
    user_id, redirect_url, error = validate_secure_state_token(tampered_token)
    
    assert user_id is None
    assert redirect_url is None
    assert error == "invalid_state"


# ============================================================================
# Token Validation - Expiration
# ============================================================================

def test_validate_token_expired():
    """Test that an expired token returns state_expired error."""
    # Generate a token
    token = generate_secure_state_token("user-123")
    
    # Mock time to be in the future (after expiry)
    future_time = time.time() + STATE_TOKEN_EXPIRY_SECONDS + 60
    
    with patch("services.google_auth_service.time.time", return_value=future_time):
        user_id, redirect_url, error = validate_secure_state_token(token)
    
    assert user_id is None
    assert error == "state_expired"


def test_validate_token_custom_expiry():
    """Test validation with custom max_age_seconds."""
    token = generate_secure_state_token("user-123")
    
    # Should pass with default expiry
    user_id, redirect_url, error = validate_secure_state_token(token)
    assert error == ""
    
    # Mock time to be 100 seconds in the future
    future_time = time.time() + 100
    
    with patch("services.google_auth_service.time.time", return_value=future_time):
        # Should fail with 60 second expiry
        user_id, redirect_url, error = validate_secure_state_token(token, max_age_seconds=60)
        assert error == "state_expired"
        
        # Should pass with 120 second expiry
        user_id, redirect_url, error = validate_secure_state_token(token, max_age_seconds=120)
        assert error == ""
        assert user_id == "user-123"


def test_validate_token_just_before_expiry():
    """Test that a token just before expiry is valid."""
    token = generate_secure_state_token("user-123")
    
    # Mock time to be 1 second before expiry
    future_time = time.time() + STATE_TOKEN_EXPIRY_SECONDS - 1
    
    with patch("services.google_auth_service.time.time", return_value=future_time):
        user_id, redirect_url, error = validate_secure_state_token(token)
    
    assert error == ""
    assert user_id == "user-123"


def test_validate_token_exactly_at_expiry():
    """Test that a token exactly at expiry is expired."""
    token = generate_secure_state_token("user-123")
    parts = token.split(":")
    timestamp = int(parts[0])
    
    # Mock time to be exactly at expiry boundary + 1 second
    future_time = timestamp + STATE_TOKEN_EXPIRY_SECONDS + 1
    
    with patch("services.google_auth_service.time.time", return_value=future_time):
        user_id, redirect_url, error = validate_secure_state_token(token)
    
    assert error == "state_expired"


# ============================================================================
# Token Validation - Clock Skew Handling
# ============================================================================

def test_validate_token_small_clock_skew_allowed():
    """Test that small clock skew (< 30 seconds) is allowed."""
    # Create a token and manually set timestamp to 10 seconds in the future
    current = int(time.time())
    future_timestamp = current + 10
    
    # Build a token with a future timestamp to simulate clock skew
    import hashlib
    import hmac
    from services.google_auth_service import _get_state_secret
    
    payload = f"{future_timestamp}:user-123:"
    signature = hmac.new(
        _get_state_secret(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    future_token = f"{payload}:{signature}"
    
    # Validation should pass (10 second skew is within 30 second tolerance)
    user_id, redirect_url, error = validate_secure_state_token(future_token)
    
    assert error == ""
    assert user_id == "user-123"


def test_validate_token_large_clock_skew_rejected():
    """Test that large clock skew (> 30 seconds future) is rejected."""
    # Create a token with timestamp 60 seconds in the future
    current = int(time.time())
    future_timestamp = current + 60
    
    import hashlib
    import hmac
    from services.google_auth_service import _get_state_secret
    
    payload = f"{future_timestamp}:user-123:"
    signature = hmac.new(
        _get_state_secret(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    future_token = f"{payload}:{signature}"
    
    # Validation should fail (60 second skew exceeds 30 second tolerance)
    user_id, redirect_url, error = validate_secure_state_token(future_token)
    
    assert user_id is None
    assert error == "invalid_state"
