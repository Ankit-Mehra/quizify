"""
Contract tests for POST /api/files/upload endpoint.

Tests file upload functionality including:
- Valid file upload
- Unsupported file type rejection
- Upload without authentication
"""

import pytest
from fastapi.testclient import TestClient
from main import app
import os
import io
from docx import Document

client = TestClient(app)

TEST_EMAIL = f"test_file_upload_{os.urandom(4).hex()}@example.com"
TEST_PASSWORD = "SecurePass123!"


def create_test_docx() -> bytes:
    """Create a simple test DOCX file."""
    doc = Document()
    doc.add_paragraph("Test file content for upload testing.")
    
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer.read()


def create_test_text_file() -> bytes:
    """Create a simple text file."""
    return b"This is a test text file for upload testing."


@pytest.fixture(scope="module")
def auth_token():
    """Create a test user and return auth token."""
    signup_payload = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
        "name": "File Upload Test User"
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


class TestFileUpload:
    """Contract tests for file upload endpoint."""
    
    def test_valid_docx_upload_returns_201(self, auth_token):
        """
        Test that valid DOCX file upload returns HTTP 201 with file_id.
        
        Expected:
        - Status code: 201 (or 200)
        - Response contains: file_id
        - file_id is a valid string
        """
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        docx_bytes = create_test_docx()
        
        files = {
            "file": ("test_upload.docx", io.BytesIO(docx_bytes), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        }
        
        response = client.post("/api/files/upload", headers=headers, files=files)
        
        assert response.status_code in [200, 201], \
            f"Expected 200 or 201 for valid upload, got {response.status_code}: {response.text}"
        
        data = response.json()
        file_id = data.get("file_id") or data.get("id")
        
        assert file_id is not None, f"Response missing file_id: {data}"
        assert isinstance(file_id, str), f"file_id should be string, got {type(file_id)}"
        assert len(file_id) > 0, "file_id should not be empty"
    
    def test_valid_text_file_upload_returns_201(self, auth_token):
        """
        Test that valid text file upload returns HTTP 201.
        
        Expected:
        - Status code: 201 (or 200)
        - Response contains: file_id
        """
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        text_bytes = create_test_text_file()
        
        files = {
            "file": ("test_upload.txt", io.BytesIO(text_bytes), "text/plain")
        }
        
        response = client.post("/api/files/upload", headers=headers, files=files)
        
        assert response.status_code in [200, 201], \
            f"Expected 200 or 201 for text file upload, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "file_id" in data or "id" in data, f"Response missing file_id: {data}"
    
    def test_unsupported_file_type_returns_400(self, auth_token):
        """
        Test that unsupported file type returns HTTP 400.
        
        Expected:
        - Status code: 400
        - Error message about unsupported file type
        """
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Try uploading an executable file (not supported)
        files = {
            "file": ("malicious.exe", io.BytesIO(b"fake exe content"), "application/x-msdownload")
        }
        
        response = client.post("/api/files/upload", headers=headers, files=files)
        
        # Should reject unsupported file types
        assert response.status_code == 400, \
            f"Expected 400 for unsupported file type, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "message" in data, \
            f"Error response missing detail/message: {data}"
    
    def test_upload_without_auth_returns_401(self):
        """
        Test that file upload without authentication returns HTTP 401.
        
        Expected:
        - Status code: 401
        - Error about missing authentication
        """
        text_bytes = create_test_text_file()
        
        files = {
            "file": ("unauthorized.txt", io.BytesIO(text_bytes), "text/plain")
        }
        
        response = client.post("/api/files/upload", files=files)
        
        assert response.status_code == 401, \
            f"Expected 401 without auth, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "message" in data, \
            f"Error response missing detail/message: {data}"
    
    def test_upload_empty_file_returns_400(self, auth_token):
        """
        Test that uploading empty file returns HTTP 400.
        
        Expected:
        - Status code: 400
        - Error about empty/invalid file
        """
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        files = {
            "file": ("empty.txt", io.BytesIO(b""), "text/plain")
        }
        
        response = client.post("/api/files/upload", headers=headers, files=files)
        
        # Should reject empty files
        assert response.status_code == 400, \
            f"Expected 400 for empty file, got {response.status_code}: {response.text}"
    
    def test_upload_with_invalid_token_returns_401(self):
        """
        Test that upload with invalid token returns HTTP 401.
        
        Expected:
        - Status code: 401
        - Error about invalid authentication
        """
        headers = {"Authorization": "Bearer invalid_token_xyz123"}
        
        text_bytes = create_test_text_file()
        files = {
            "file": ("test.txt", io.BytesIO(text_bytes), "text/plain")
        }
        
        response = client.post("/api/files/upload", headers=headers, files=files)
        
        assert response.status_code == 401, \
            f"Expected 401 for invalid token, got {response.status_code}: {response.text}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
