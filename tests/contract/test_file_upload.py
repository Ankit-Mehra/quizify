"""
Contract tests for POST /api/files/upload endpoint.

Tests file upload functionality including:
- Valid file upload
- Authorization requirements
"""

import pytest
from fastapi.testclient import TestClient
from main import app
from dependencies.auth_dependencies import get_current_user_id
import io

client = TestClient(app)


def create_test_text_file() -> bytes:
    """Create a simple text file."""
    return b"This is a test text file for upload testing."


@pytest.mark.contract
class TestFileUpload:
    """Contract tests for file upload endpoint."""
    
    def test_valid_file_upload_returns_success(self, mock_supabase_client, auth_bypass, auth_headers):
        """
        Test that valid file upload returns success response.
        
        Expected:
        - Status code: 200 or 201
        - Response contains file information
        """
        text_bytes = create_test_text_file()
        
        files = {
            "file": ("test_upload.txt", io.BytesIO(text_bytes), "text/plain")
        }
        
        response = client.post("/api/files/upload", headers=auth_headers, files=files)
        
        assert response.status_code in [200, 201], \
            f"Expected 200/201 for file upload, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Response should contain some file information
        assert data is not None, "Response should not be None"
    
    def test_file_upload_without_auth_returns_401(self, mock_supabase_client):
        """
        Test that file upload without authentication returns HTTP 401.
        
        Expected:
        - Status code: 401
        - Error message about authentication
        """
        text_bytes = create_test_text_file()
        
        files = {
            "file": ("test_upload.txt", io.BytesIO(text_bytes), "text/plain")
        }
        
        response = client.post("/api/files/upload", files=files)
        
        assert response.status_code == 401, \
            f"Expected 401 without auth, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "message" in data, f"Error response missing detail/message: {data}"
    
    def test_file_upload_with_invalid_token_returns_401(self, mock_supabase_client):
        """
        Test that file upload with invalid token returns HTTP 401.
        
        Expected:
        - Status code: 401
        - Error message about invalid token
        """
        headers = {"Authorization": "Bearer invalid_token_xyz"}
        text_bytes = create_test_text_file()
        
        files = {
            "file": ("test_upload.txt", io.BytesIO(text_bytes), "text/plain")
        }
        
        response = client.post("/api/files/upload", headers=headers, files=files)
        
        assert response.status_code == 401, \
            f"Expected 401 with invalid token, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "message" in data, f"Error response missing detail/message: {data}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
