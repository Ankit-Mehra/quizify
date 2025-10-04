"""
Contract tests for DELETE /api/files/{file_id} endpoint.

Tests file deletion functionality including:
- Successful file deletion
- Deletion of non-existent files
- Authorization requirements
- Access control for other users' files
"""

import pytest
from fastapi.testclient import TestClient
from main import app
import os
import io

client = TestClient(app)

TEST_EMAIL = f"test_file_delete_{os.urandom(4).hex()}@example.com"
TEST_PASSWORD = "SecurePass123!"


@pytest.fixture(scope="module")
def auth_token():
    """Create a test user and return auth token."""
    signup_payload = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
        "name": "File Delete Test User"
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


@pytest.fixture(scope="module")
def other_user_token():
    """Create another test user for access control tests."""
    other_email = f"test_other_user_{os.urandom(4).hex()}@example.com"
    signup_payload = {
        "email": other_email,
        "password": TEST_PASSWORD,
        "name": "Other User"
    }
    signup_response = client.post("/api/auth/signup", json=signup_payload)
    assert signup_response.status_code == 201
    
    login_payload = {
        "email": other_email,
        "password": TEST_PASSWORD
    }
    login_response = client.post("/api/auth/login", json=login_payload)
    assert login_response.status_code == 200
    
    data = login_response.json()
    token = data.get("access_token") or data.get("accessToken") or data.get("token")
    
    return token


class TestFileDelete:
    """Contract tests for file deletion."""
    
    def test_delete_file_successfully(self, auth_token):
        """
        Test successful file deletion.
        
        Expected:
        - Status code: 200 or 204
        - File no longer accessible after deletion
        """
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Upload a file first
        test_content = b"Test file to be deleted"
        files = {
            "file": ("delete_test.txt", io.BytesIO(test_content), "text/plain")
        }
        
        upload_response = client.post("/api/files/upload", headers=headers, files=files)
        assert upload_response.status_code in [200, 201], f"Upload failed: {upload_response.text}"
        
        upload_data = upload_response.json()
        file_id = upload_data.get("file_id") or upload_data.get("id")
        
        # Delete the file
        delete_response = client.delete(f"/api/files/{file_id}", headers=headers)
        
        assert delete_response.status_code in [200, 204], \
            f"Expected 200 or 204 for successful deletion, got {delete_response.status_code}: {delete_response.text}"
        
        # Verify file is no longer accessible
        get_response = client.get(f"/api/files/{file_id}", headers=headers)
        assert get_response.status_code == 404, \
            f"Deleted file should return 404, got {get_response.status_code}"
    
    def test_delete_nonexistent_file_returns_404(self, auth_token):
        """
        Test deleting a non-existent file returns HTTP 404.
        
        Expected:
        - Status code: 404
        - Error message about file not found
        """
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        fake_file_id = "00000000-0000-0000-0000-000000000000"
        
        response = client.delete(f"/api/files/{fake_file_id}", headers=headers)
        
        assert response.status_code == 404, \
            f"Expected 404 for non-existent file, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "message" in data, \
            f"Error response missing detail/message: {data}"
    
    def test_delete_other_users_file_returns_403(self, auth_token, other_user_token):
        """
        Test that deleting another user's file returns HTTP 403.
        
        Expected:
        - Status code: 403
        - Error about insufficient permissions
        """
        # User 1 uploads a file
        headers_user1 = {"Authorization": f"Bearer {auth_token}"}
        
        test_content = b"User 1's file"
        files = {
            "file": ("user1_file.txt", io.BytesIO(test_content), "text/plain")
        }
        
        upload_response = client.post("/api/files/upload", headers=headers_user1, files=files)
        assert upload_response.status_code in [200, 201]
        
        upload_data = upload_response.json()
        file_id = upload_data.get("file_id") or upload_data.get("id")
        
        # User 2 tries to delete User 1's file
        headers_user2 = {"Authorization": f"Bearer {other_user_token}"}
        
        delete_response = client.delete(f"/api/files/{file_id}", headers=headers_user2)
        
        assert delete_response.status_code in [403, 404], \
            f"Expected 403 or 404 for other user's file, got {delete_response.status_code}: {delete_response.text}"
    
    def test_delete_without_auth_returns_401(self):
        """
        Test that deleting without authentication returns HTTP 401.
        
        Expected:
        - Status code: 401
        - Error about missing authentication
        """
        fake_file_id = "00000000-0000-0000-0000-000000000000"
        
        response = client.delete(f"/api/files/{fake_file_id}")
        
        assert response.status_code == 401, \
            f"Expected 401 without auth, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "message" in data, \
            f"Error response missing detail/message: {data}"
    
    def test_delete_with_invalid_token_returns_401(self):
        """
        Test that invalid token returns HTTP 401.
        
        Expected:
        - Status code: 401
        - Error about invalid authentication
        """
        headers = {"Authorization": "Bearer invalid_token_xyz123"}
        fake_file_id = "00000000-0000-0000-0000-000000000000"
        
        response = client.delete(f"/api/files/{fake_file_id}", headers=headers)
        
        assert response.status_code == 401, \
            f"Expected 401 for invalid token, got {response.status_code}: {response.text}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
