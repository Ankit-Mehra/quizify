"""
Contract tests for POST /api/auth/logout endpoint.

Tests the authentication logout functionality including:
- Successful logout with valid token
- Logout without authentication
"""

import pytest
from fastapi.testclient import TestClient
from main import app
import os

client = TestClient(app)

TEST_EMAIL = f"test_logout_{os.urandom(4).hex()}@example.com"
TEST_PASSWORD = "SecurePass123!"


@pytest.fixture(scope="module")
def authenticated_user():
    """Create and login a test user."""
    # Signup
    signup_payload = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
        "name": "Logout Test User"
    }
    signup_response = client.post("/api/auth/signup", json=signup_payload)
    assert signup_response.status_code == 201
    
    # Login
    login_payload = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    }
    login_response = client.post("/api/auth/login", json=login_payload)
    assert login_response.status_code == 200
    
    data = login_response.json()
    token = data.get("access_token") or data.get("accessToken") or data.get("token")
    
    return {"email": TEST_EMAIL, "token": token}


class TestAuthLogout:
    """Contract tests for user logout endpoint."""
    
    def test_successful_logout_returns_200(self, authenticated_user):
        """
        Test that logout with valid token returns HTTP 200.
        
        Expected:
        - Status code: 200
        - Success message
        """
        headers = {"Authorization": f"Bearer {authenticated_user['token']}"}
        
        response = client.post("/api/auth/logout", headers=headers)
        
        assert response.status_code == 200, \
            f"Expected 200 for successful logout, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Check for success message or confirmation
        assert "message" in data or "detail" in data or "status" in data, \
            f"Response should contain confirmation: {data}"
    
    def test_logout_without_auth_returns_401(self):
        """
        Test that logout without authentication returns HTTP 401.
        
        Expected:
        - Status code: 401
        - Error message about missing/invalid authentication
        """
        response = client.post("/api/auth/logout")
        
        assert response.status_code == 401, \
            f"Expected 401 for logout without auth, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "message" in data, \
            f"Error response missing detail/message: {data}"
    
    def test_logout_with_invalid_token_returns_401(self):
        """
        Test that logout with invalid/expired token returns HTTP 401.
        
        Expected:
        - Status code: 401
        - Error message about invalid token
        """
        headers = {"Authorization": "Bearer invalid_token_xyz123"}
        
        response = client.post("/api/auth/logout", headers=headers)
        
        assert response.status_code == 401, \
            f"Expected 401 for invalid token, got {response.status_code}: {response.text}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
