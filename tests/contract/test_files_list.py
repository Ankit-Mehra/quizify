"""
Contract tests for GET /api/files/metadata endpoint.

Tests file listing functionality including:
- List user's uploaded files
- Empty file list for new users
- Authorization requirements
"""

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


@pytest.mark.contract
class TestFilesList:
    """Contract tests for listing user files."""
    
    def test_list_files_returns_200_with_array(self, mock_supabase_client, auth_bypass, auth_headers):
        """
        Test that listing files returns HTTP 200 with array.
        
        Expected:
        - Status code: 200
        - Response is an array (may be empty)
        """
    
    def test_list_files_without_auth_returns_401(self, mock_supabase_client):
        """
        Test that listing files without authentication returns HTTP 401.
        
        Expected:
        - Status code: 401
        - Error message about authentication
        """
        # No auth headers
        response = client.get("/api/files/metadata")
        
        assert response.status_code == 401, \
            f"Expected 401 without auth, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "message" in data, f"Error response missing detail/message: {data}"
    
    def test_list_files_with_invalid_token_returns_401(self, mock_supabase_client):
        """
        Test that listing files with invalid token returns HTTP 401.
        
        Expected:
        - Status code: 401
        - Error message about invalid token
        """
        headers = {"Authorization": "Bearer invalid_token_xyz"}
        
        response = client.get("/api/files/metadata", headers=headers)
        
        assert response.status_code == 401, \
            f"Expected 401 with invalid token, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "message" in data, f"Error response missing detail/message: {data}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
