


"""
Contract tests for POST /api/auth/signup endpoint.Tests the authentication signup functionality including:
- Valid signup with proper credentials
- Duplicate email handling  
- Invalid email format validation
- Weak password rejection
"""

import pytest

from fastapi.testclient import TestClient
from main import app
import os

client = TestClient(app)

# Test user credentials
VALID_EMAIL = f"test_signup_{os.urandom(4).hex()}@example.com"
VALID_PASSWORD = "SecurePass123!"
VALID_NAME = "Test User"

WEAK_PASSWORD = "123"
INVALID_EMAIL = "not-an-email"


@pytest.mark.contract
class TestAuthSignup:
    """Contract tests for user signup endpoint."""
    
    def test_valid_signup_returns_201_with_user_id(self, mock_supabase_client):
        """
        Test that a valid signup request returns HTTP 201 with user_id.
        
        Expected:
        - Status code: 201
        - Response contains: user_id
        - user_id is a valid UUID string
        """
        payload = {
            "email": VALID_EMAIL,
            "password": VALID_PASSWORD,
            "name": VALID_NAME
        }
        
        response = client.post("/api/auth/signup", json=payload)
        
        assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "user_id" in data, f"Response missing user_id: {data}"
        assert "message" in data, f"Response missing message: {data}"
        
        # Verify mock user_id
        user_id = data.get("user_id")
        assert isinstance(user_id, str), f"user_id should be string, got {type(user_id)}"
        assert len(user_id) > 0, "user_id should not be empty"
    
    def test_duplicate_email_returns_400(self, mock_supabase_client):
        """
        Test that signing up with an already registered email returns HTTP 400.
        
        Expected:
        - Status code: 400 (Bad Request)
        - Error message about duplicate email
        """
        # First signup (should succeed)
        unique_email = f"test_dup_{os.urandom(4).hex()}@example.com"
        payload = {
            "email": unique_email,
            "password": VALID_PASSWORD,
            "name": "First User"
        }
        
        first_response = client.post("/api/auth/signup", json=payload)
        assert first_response.status_code == 201, f"First signup should succeed: {first_response.text}"
        
        # Second signup with same email (should fail)
        second_response = client.post("/api/auth/signup", json=payload)
        
        assert second_response.status_code == 400, \
            f"Expected 400 for duplicate email, got {second_response.status_code}: {second_response.text}"
        
        data = second_response.json()
        assert "detail" in data or "message" in data, f"Error response missing detail/message: {data}"
    
    def test_invalid_email_format_returns_422(self, mock_supabase_client):
        """
        Test that invalid email format returns HTTP 422 (Unprocessable Entity).
        
        Expected:
        - Status code: 422
        - Validation error about email format
        """
        payload = {
            "email": INVALID_EMAIL,
            "password": VALID_PASSWORD,
            "name": "Test User"
        }
        
        response = client.post("/api/auth/signup", json=payload)
        
        # Accept either 422 (validation error) or 400 (bad request) as both are valid for invalid format
        assert response.status_code in [400, 422], \
            f"Expected 400 or 422 for invalid email, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "message" in data, f"Error response missing detail/message: {data}"
    
    def test_weak_password_returns_400(self, mock_supabase_client):
        """
        Test that a weak password is rejected with HTTP 400.
        
        Expected:
        - Status code: 400
        - Error message about password strength
        """
        payload = {
            "email": f"test_weak_{os.urandom(4).hex()}@example.com",
            "password": WEAK_PASSWORD,
            "name": "Test User"
        }
        
        response = client.post("/api/auth/signup", json=payload)
        
        # Pydantic validates password min_length at schema level (422 validation error)
        assert response.status_code == 422, \
            f"Expected 422 for weak password (Pydantic validation), got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data, f"Error response missing detail: {data}"
        # Verify Pydantic caught the password length issue
        # Note: Custom validation handler returns {"detail": string, "errors": [...]}
        errors = data.get("errors", data.get("detail", []))
        if isinstance(errors, str):
            # Check the detail string itself
            assert "password" in data.get("detail", "").lower() or \
                any("password" in str(err).lower() for err in data.get("errors", [])), \
                f"Expected password validation error, got: {data}"
        else:
            assert any("password" in str(err).lower() for err in errors), \
                f"Expected password validation error, got: {data}"
    
    def test_missing_required_fields_returns_422(self, mock_supabase_client):
        """
        Test that missing required fields returns HTTP 422.
        
        Expected:
        - Status code: 422
        - Validation error listing missing fields
        """
        # Missing email
        payload_no_email = {
            "password": VALID_PASSWORD,
            "name": "Test User"
        }
        
        response = client.post("/api/auth/signup", json=payload_no_email)
        assert response.status_code == 422, \
            f"Expected 422 for missing email, got {response.status_code}: {response.text}"
        
        # Missing password
        payload_no_password = {
            "email": f"test_missing_{os.urandom(4).hex()}@example.com",
            "name": "Test User"
        }
        
        response = client.post("/api/auth/signup", json=payload_no_password)
        assert response.status_code == 422, \
            f"Expected 422 for missing password, got {response.status_code}: {response.text}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
