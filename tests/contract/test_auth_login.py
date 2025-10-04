"""
Contract tests for POST /api/auth/login endpoint.

Tests the authentication login functionality including:
- Valid login with correct credentials
- Invalid credentials rejection
- Missing fields validation
"""

import pytest
from fastapi.testclient import TestClient
from main import app
import os

client = TestClient(app)

# Test credentials
TEST_EMAIL = f"test_login_{os.urandom(4).hex()}@example.com"
TEST_PASSWORD = "SecurePass123!"
WRONG_PASSWORD = "WrongPassword123!"


@pytest.fixture(scope="module")
def registered_user():
    """Create a test user for login tests."""
    payload = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
        "name": "Login Test User"
    }
    
    response = client.post("/api/auth/signup", json=payload)
    assert response.status_code == 201, f"Failed to create test user: {response.text}"
    
    return {"email": TEST_EMAIL, "password": TEST_PASSWORD}


class TestAuthLogin:
    """Contract tests for user login endpoint."""
    
    def test_valid_login_returns_200_with_tokens(self, registered_user):
        """
        Test that valid credentials return HTTP 200 with access and refresh tokens.
        
        Expected:
        - Status code: 200
        - Response contains: access_token, refresh_token (or similar token fields)
        - Tokens are non-empty strings
        """
        payload = {
            "email": registered_user["email"],
            "password": registered_user["password"]
        }
        
        response = client.post("/api/auth/login", json=payload)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Check for token fields (different APIs may use different naming conventions)
        has_access_token = "access_token" in data or "accessToken" in data or "token" in data
        
        assert has_access_token, f"Response missing access token: {data}"
        
        # Get the access token value (handle different naming conventions)
        token = data.get("access_token") or data.get("accessToken") or data.get("token")
        assert isinstance(token, str), f"Token should be string, got {type(token)}"
        assert len(token) > 0, "Token should not be empty"
    
    def test_invalid_credentials_returns_401(self, registered_user):
        """
        Test that invalid credentials return HTTP 401 (Unauthorized).
        
        Expected:
        - Status code: 401
        - Error message about invalid credentials
        """
        payload = {
            "email": registered_user["email"],
            "password": WRONG_PASSWORD
        }
        
        response = client.post("/api/auth/login", json=payload)
        
        assert response.status_code == 401, \
            f"Expected 401 for wrong password, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "message" in data, f"Error response missing detail/message: {data}"
    
    def test_non_existent_user_returns_401(self):
        """
        Test that login with non-existent email returns HTTP 401.
        
        Expected:
        - Status code: 401
        - Error message about invalid credentials
        """
        payload = {
            "email": f"nonexistent_{os.urandom(4).hex()}@example.com",
            "password": TEST_PASSWORD
        }
        
        response = client.post("/api/auth/login", json=payload)
        
        assert response.status_code == 401, \
            f"Expected 401 for non-existent user, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "message" in data, f"Error response missing detail/message: {data}"
    
    def test_missing_email_returns_422(self):
        """
        Test that missing email field returns HTTP 422 (Unprocessable Entity).
        
        Expected:
        - Status code: 422
        - Validation error about missing email
        """
        payload = {
            "password": TEST_PASSWORD
        }
        
        response = client.post("/api/auth/login", json=payload)
        
        assert response.status_code == 422, \
            f"Expected 422 for missing email, got {response.status_code}: {response.text}"
    
    def test_missing_password_returns_422(self):
        """
        Test that missing password field returns HTTP 422 (Unprocessable Entity).
        
        Expected:
        - Status code: 422
        - Validation error about missing password
        """
        payload = {
            "email": TEST_EMAIL
        }
        
        response = client.post("/api/auth/login", json=payload)
        
        assert response.status_code == 422, \
            f"Expected 422 for missing password, got {response.status_code}: {response.text}"
    
    def test_empty_credentials_returns_error(self):
        """
        Test that empty email/password returns appropriate error.
        
        Expected:
        - Status code: 400, 401, or 422
        - Error message about invalid input
        """
        payload = {
            "email": "",
            "password": ""
        }
        
        response = client.post("/api/auth/login", json=payload)
        
        assert response.status_code in [400, 401, 422], \
            f"Expected 400/401/422 for empty credentials, got {response.status_code}: {response.text}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
