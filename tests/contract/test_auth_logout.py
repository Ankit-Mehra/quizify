"""
Contract tests for POST /api/auth/logout endpoint.

Tests the authentication logout functionality including:
- Successful logout with valid token
- Logout without authentication
"""

import pytest
from fastapi.testclient import TestClient
from main import app
from dependencies.auth_dependencies import get_current_user_id

client = TestClient(app)


@pytest.mark.contract
class TestAuthLogout:
    """Contract tests for user logout endpoint."""
    
    def test_successful_logout_returns_200(self, mock_supabase_client, auth_headers):
        """
        Test that logout with valid token returns HTTP 200.
        
        Expected:
        - Status code: 200
        - Success message
        """
        # Override auth dependency
        def override_get_current_user_id():
            return "mock_user_123"
        
        app.dependency_overrides[get_current_user_id] = override_get_current_user_id
        
        try:
            response = client.post("/api/auth/logout", headers=auth_headers)
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
            
            data = response.json()
            assert "message" in data, f"Response missing message: {data}"
            assert data["message"] == "Successfully logged out", f"Unexpected message: {data['message']}"
        finally:
            app.dependency_overrides.clear()
    
    def test_logout_without_auth_returns_401(self, mock_supabase_client):
        """
        Test that logout without authentication returns HTTP 401.
        
        Expected:
        - Status code: 401
        - Error message about missing authentication
        """
        # No headers provided - should fail auth
        response = client.post("/api/auth/logout")
        
        assert response.status_code == 401, \
            f"Expected 401 without auth, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "message" in data, f"Error response missing detail/message: {data}"
    
    def test_logout_with_invalid_token_returns_401(self, mock_supabase_client):
        """
        Test that logout with invalid token returns HTTP 401.
        
        Expected:
        - Status code: 401
        - Error message about invalid token
        """
        headers = {"Authorization": "Bearer invalid_token_123"}
        
        response = client.post("/api/auth/logout", headers=headers)
        
        assert response.status_code == 401, \
            f"Expected 401 with invalid token, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "message" in data, f"Error response missing detail/message: {data}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
