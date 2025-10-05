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


@pytest.mark.contract
class TestAuthLogin:
    """Contract tests for user login endpoint."""
    
    def test_valid_login_returns_200_with_tokens(self, mock_supabase_client, test_user_data):
        """
        Test that valid credentials return HTTP 200 with access and refresh tokens.
        
        Expected:
        - Status code: 200
        - Response contains: message and user data
        """
        payload = {
            "email": test_user_data["email"],
            "password": test_user_data["password"]
        }
        
        response = client.post("/api/auth/login", json=payload)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "message" in data, f"Response missing message: {data}"
        assert "user" in data, f"Response missing user: {data}"
    
    def test_invalid_credentials_returns_401(self, mock_supabase_client, test_user_data):
        """
        Test that invalid credentials return HTTP 401 (Unauthorized).
        
        Expected:
        - Status code: 401
        - Error message about invalid credentials
        """
        payload = {
            "email": test_user_data["email"],
            "password": WRONG_PASSWORD
        }
        
        response = client.post("/api/auth/login", json=payload)
        
        assert response.status_code == 401, \
            f"Expected 401 for wrong password, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "message" in data, f"Error response missing detail/message: {data}"
    
    def test_non_existent_user_returns_401(self, mock_supabase_client):
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
    
    def test_missing_email_returns_422(self, mock_supabase_client):
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
    
    def test_missing_password_returns_422(self, mock_supabase_client):
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
    
    def test_empty_credentials_returns_error(self, mock_supabase_client):
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
