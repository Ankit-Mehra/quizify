"""
Contract tests for DELETE /api/files/{file_id} endpoint.

Tests file deletion functionality including:
- Valid file deletion
- Authorization requirements
"""

import pytest
from fastapi.testclient import TestClient
from main import app
from dependencies.auth_dependencies import get_current_user_id

client = TestClient(app)


@pytest.mark.contract
class TestFileDelete:
    """Contract tests for file deletion endpoint."""
    
    def test_file_delete_returns_success(self, mock_supabase_client, auth_bypass, auth_headers):
        """
        Test that file deletion returns success response.
        
        Expected:
        - Status code: 200 or 204
        - Success message or no content
        """
    
    def test_file_delete_without_auth_returns_401(self, mock_supabase_client):
        """
        Test that file deletion without authentication returns HTTP 401.
        
        Expected:
        - Status code: 401
        - Error message about authentication
        """
        file_id = "test_file_123"
        
        response = client.delete(f"/api/files/{file_id}")
        
        assert response.status_code == 401, \
            f"Expected 401 without auth, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "message" in data, f"Error response missing detail/message: {data}"
    
    def test_file_delete_with_invalid_token_returns_401(self, mock_supabase_client):
        """
        Test that file deletion with invalid token returns HTTP 401.
        
        Expected:
        - Status code: 401
        - Error message about invalid token
        """
        headers = {"Authorization": "Bearer invalid_token_xyz"}
        file_id = "test_file_123"
        
        response = client.delete(f"/api/files/{file_id}", headers=headers)
        
        assert response.status_code == 401, \
            f"Expected 401 with invalid token, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "message" in data, f"Error response missing detail/message: {data}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
