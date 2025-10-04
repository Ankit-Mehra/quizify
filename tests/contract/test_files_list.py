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
import os
import io

client = TestClient(app)

TEST_EMAIL = f"test_files_list_{os.urandom(4).hex()}@example.com"
TEST_PASSWORD = "SecurePass123!"


@pytest.fixture(scope="module")
def auth_token():
    """Create a test user and return auth token."""
    signup_payload = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
        "name": "Files List Test User"
    }
    signup_response = client.post("/api/auth/signup", json=signup_payload)
    assert signup_response.status_code == 201
    
    login_payload = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    }
    login_response = client.post("/api/auth/login", json=login_payload)
    assert login_response.status_code == 200
    
    data = login_response.json()
    token = data.get("access_token") or data.get("accessToken") or data.get("token")
    
    return token


class TestFilesList:
    """Contract tests for listing user files."""
    
    def test_list_files_returns_200_with_array(self, auth_token):
        """
        Test that listing files returns HTTP 200 with array.
        
        Expected:
        - Status code: 200
        - Response is an array (may be empty)
        """
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        response = client.get("/api/files/metadata", headers=headers)
        
        assert response.status_code == 200, \
            f"Expected 200 for files list, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Response should be either an array directly or contain a files array
        if isinstance(data, list):
            files_list = data
        elif isinstance(data, dict):
            files_list = data.get("files", data.get("data", []))
        else:
            pytest.fail(f"Unexpected response format: {type(data)}")
        
        assert isinstance(files_list, list), f"Files should be an array, got {type(files_list)}"
    
    def test_empty_file_list_for_new_user(self):
        """
        Test that new user with no uploads gets empty list.
        
        Expected:
        - Status code: 200
        - Empty array or array with count 0
        """
        # Create a fresh user
        new_email = f"test_empty_list_{os.urandom(4).hex()}@example.com"
        signup_payload = {
            "email": new_email,
            "password": TEST_PASSWORD,
            "name": "Empty List User"
        }
        signup_response = client.post("/api/auth/signup", json=signup_payload)
        assert signup_response.status_code == 201
        
        login_payload = {
            "email": new_email,
            "password": TEST_PASSWORD
        }
        login_response = client.post("/api/auth/login", json=login_payload)
        assert login_response.status_code == 200
        
        token = login_response.json().get("access_token") or login_response.json().get("accessToken") or login_response.json().get("token")
        
        headers = {"Authorization": f"Bearer {token}"}
        
        response = client.get("/api/files/metadata", headers=headers)
        
        assert response.status_code == 200, \
            f"Expected 200 for empty files list, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        if isinstance(data, list):
            assert len(data) == 0, "New user should have empty file list"
        elif isinstance(data, dict):
            files_list = data.get("files", data.get("data", []))
            assert len(files_list) == 0, "New user should have empty file list"
    
    def test_list_files_after_upload(self, auth_token):
        """
        Test that uploaded files appear in the list.
        
        Expected:
        - After upload, file appears in list
        - File metadata includes expected fields
        """
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Upload a test file
        test_content = b"Test file content for listing verification"
        files = {
            "file": ("list_test.txt", io.BytesIO(test_content), "text/plain")
        }
        
        upload_response = client.post("/api/files/upload", headers=headers, files=files)
        assert upload_response.status_code in [200, 201], f"Upload failed: {upload_response.text}"
        
        upload_data = upload_response.json()
        uploaded_file_id = upload_data.get("file_id") or upload_data.get("id")
        
        # Get files list
        list_response = client.get("/api/files/metadata", headers=headers)
        assert list_response.status_code == 200
        
        list_data = list_response.json()
        
        if isinstance(list_data, list):
            files_list = list_data
        else:
            files_list = list_data.get("files", list_data.get("data", []))
        
        # Find our uploaded file
        our_file = next((f for f in files_list if f.get("id") == uploaded_file_id or f.get("file_id") == uploaded_file_id), None)
        
        assert our_file is not None, f"Uploaded file {uploaded_file_id} not found in list"
        
        # Verify file has expected metadata fields
        assert "id" in our_file or "file_id" in our_file, "File should have ID"
        # Additional fields may vary by implementation
    
    def test_list_files_without_auth_returns_401(self):
        """
        Test that listing files without authentication returns HTTP 401.
        
        Expected:
        - Status code: 401
        - Error about missing authentication
        """
        response = client.get("/api/files/metadata")
        
        assert response.status_code == 401, \
            f"Expected 401 without auth, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "message" in data, \
            f"Error response missing detail/message: {data}"
    
    def test_list_files_with_invalid_token_returns_401(self):
        """
        Test that invalid token returns HTTP 401.
        
        Expected:
        - Status code: 401
        - Error about invalid authentication
        """
        headers = {"Authorization": "Bearer invalid_token_xyz123"}
        
        response = client.get("/api/files/metadata", headers=headers)
        
        assert response.status_code == 401, \
            f"Expected 401 for invalid token, got {response.status_code}: {response.text}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
