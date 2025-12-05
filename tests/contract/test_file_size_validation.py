"""
Contract tests for file size validation on POST /api/quiz/generate/file endpoint.

Tests file size limits including:
- Files under 10MB (should pass)
- Files exactly 10MB (should pass)
- Files over 10MB (should return 413)
- Metadata includes file_size_bytes
"""

import pytest
from fastapi.testclient import TestClient
from main import app
import io

client = TestClient(app)

# File size constants
MB = 1024 * 1024
MAX_FILE_SIZE = 10 * MB  # 10MB


def create_test_file_of_size(size_bytes: int) -> bytes:
    """Create a text file of exactly the specified size in bytes."""
    # Create content that will result in approximately the desired size
    # We need enough text to pass MIN_CONTENT_LENGTH validation (50 chars)
    base_content = "Python is a high-level programming language. " * 5  # ~225 chars
    
    if size_bytes <= len(base_content):
        content = base_content[:size_bytes]
    else:
        # For larger files, repeat the content
        repetitions = (size_bytes // len(base_content)) + 1
        content = (base_content * repetitions)[:size_bytes]
    
    encoded = content.encode('utf-8')
    # Pad with spaces if needed to reach exact size
    if len(encoded) < size_bytes:
        encoded += b' ' * (size_bytes - len(encoded))
    return encoded[:size_bytes]  # Truncate if over due to encoding


@pytest.mark.contract
@pytest.mark.usefixtures("mock_supabase_client", "auth_bypass")
class TestFileSizeValidation:
    """Contract tests for file size validation."""
    
    def test_file_under_10mb_accepted(self, auth_headers):
        """
        Test that files under 10MB are accepted and processed.
        
        Expected:
        - Status code: 201
        - Response contains quiz_id
        """
        # Create 9MB file
        file_size = 9 * MB
        file_content = create_test_file_of_size(file_size)
        
        files = {
            "file": ("test_9mb.txt", io.BytesIO(file_content), "text/plain")
        }
        data = {
            "title": "9MB File Quiz",
            "num_questions": "3"
        }
        
        response = client.post("/api/quiz/generate/file", headers=auth_headers, files=files, data=data)
        
        assert response.status_code == 201, \
            f"Expected 201 for 9MB file, got {response.status_code}: {response.text}"
        
        response_data = response.json()
        assert "quiz_id" in response_data, f"Response missing quiz_id: {response_data}"
    
    def test_file_exactly_10mb_accepted(self, auth_headers):
        """
        Test that files exactly 10MB are accepted (boundary condition).
        
        Expected:
        - Status code: 201
        - Response contains quiz_id
        """
        # Create exactly 10MB file
        file_size = MAX_FILE_SIZE
        file_content = create_test_file_of_size(file_size)
        
        files = {
            "file": ("test_10mb.txt", io.BytesIO(file_content), "text/plain")
        }
        data = {
            "title": "10MB File Quiz",
            "num_questions": "3"
        }
        
        response = client.post("/api/quiz/generate/file", headers=auth_headers, files=files, data=data)
        
        assert response.status_code == 201, \
            f"Expected 201 for 10MB file, got {response.status_code}: {response.text}"
        
        response_data = response.json()
        assert "quiz_id" in response_data, f"Response missing quiz_id: {response_data}"
    
    def test_file_over_10mb_rejected_with_413(self, auth_headers):
        """
        Test that files over 10MB are rejected with HTTP 413.
        
        Expected:
        - Status code: 413 (Payload Too Large)
        - Error message specifies 10MB limit and actual file size
        """
        # Create 11MB file
        file_size = 11 * MB
        file_content = create_test_file_of_size(file_size)
        
        files = {
            "file": ("test_11mb.txt", io.BytesIO(file_content), "text/plain")
        }
        data = {
            "title": "11MB File Quiz",
            "num_questions": "3"
        }
        
        response = client.post("/api/quiz/generate/file", headers=auth_headers, files=files, data=data)
        
        assert response.status_code == 413, \
            f"Expected 413 for 11MB file, got {response.status_code}: {response.text}"
        
        response_data = response.json()
        assert "detail" in response_data, f"Error response missing detail: {response_data}"
        
        detail = response_data["detail"]
        assert "10MB" in detail or "10485760" in detail, \
            f"Error message should mention 10MB limit: {detail}"
        assert str(file_size) in detail, \
            f"Error message should mention actual file size ({file_size}): {detail}"
    
    def test_file_size_saved_in_metadata(self, auth_headers, mocker):
        """
        Test that file_size_bytes is included in saved metadata.
        
        Expected:
        - Metadata includes file_size_bytes field
        - Value matches actual file size
        """
        # Create 5MB file
        file_size = 5 * MB
        file_content = create_test_file_of_size(file_size)
        
        # Mock save_metadata to capture the metadata being saved
        mock_save_metadata = mocker.patch("handlers.quiz_handlers.save_metadata")
        
        files = {
            "file": ("test_5mb.txt", io.BytesIO(file_content), "text/plain")
        }
        data = {
            "title": "5MB File Quiz",
            "num_questions": "3"
        }
        
        response = client.post("/api/quiz/generate/file", headers=auth_headers, files=files, data=data)
        
        assert response.status_code == 201, \
            f"Expected 201, got {response.status_code}: {response.text}"
        
        # Verify save_metadata was called
        assert mock_save_metadata.called, "save_metadata should have been called"
        
        # Get the metadata that was passed to save_metadata (handle both positional and keyword args)
        call_args = mock_save_metadata.call_args
        metadata = call_args.args[0] if call_args and call_args.args else call_args.kwargs.get('metadata', {})
        
        # Verify file_size_bytes is present and correct
        assert "file_size_bytes" in metadata, f"Metadata missing file_size_bytes: {metadata}"
        assert metadata["file_size_bytes"] == file_size, \
            f"Expected file_size_bytes={file_size}, got {metadata['file_size_bytes']}"
    
    def test_empty_file_still_validates_size(self, auth_headers):
        """
        Test that empty files (0 bytes) are handled gracefully.
        
        Expected:
        - Status code: 400 (for insufficient content, not size)
        - File size validation passes (0 < 10MB)
        """
        file_content = b""
        
        files = {
            "file": ("test_empty.txt", io.BytesIO(file_content), "text/plain")
        }
        data = {
            "title": "Empty File Quiz",
            "num_questions": "3"
        }
        
        response = client.post("/api/quiz/generate/file", headers=auth_headers, files=files, data=data)
        
        # Should fail with 400 for insufficient content, not 413 for size
        assert response.status_code == 400, \
            f"Expected 400 for empty file (insufficient content), got {response.status_code}: {response.text}"
        
        response_data = response.json()
        detail = response_data.get("detail", "")
        # Should not be about file size (should be about content)
        detail_lower = detail.lower()
        assert "content" in detail_lower or "insufficient" in detail_lower, \
            f"Expected error about content, got: {detail}"
    
    def test_file_size_validation_works_for_pdf(self, auth_headers):
        """
        Test that file size validation works for PDF files (binary).
        
        Expected:
        - Large PDFs (>10MB) should be rejected with 413
        """
        # Create a mock "PDF" that's larger than 10MB
        # Note: This won't be a valid PDF, but we're testing size validation happens first
        file_size = 15 * MB
        file_content = b"PDF-like-content" * (file_size // 16)
        
        files = {
            "file": ("test_large.pdf", io.BytesIO(file_content), "application/pdf")
        }
        data = {
            "title": "Large PDF Quiz",
            "num_questions": "3"
        }
        
        response = client.post("/api/quiz/generate/file", headers=auth_headers, files=files, data=data)
        
        # Should fail with 413 for size (before PDF parsing fails)
        assert response.status_code == 413, \
            f"Expected 413 for oversized PDF, got {response.status_code}: {response.text}"
    
    def test_file_size_validation_works_for_docx(self, auth_headers):
        """
        Test that file size validation works for DOCX files.
        
        Expected:
        - Large DOCX (>10MB) should be rejected with 413
        """
        # Create a mock "DOCX" that's larger than 10MB
        # Note: This won't be a valid DOCX, but we're testing size validation happens first
        file_size = 12 * MB
        file_content = b"DOCX-content" * (file_size // 12)
        
        files = {
            "file": ("test_large.docx", io.BytesIO(file_content), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        }
        data = {
            "title": "Large DOCX Quiz",
            "num_questions": "3"
        }
        
        response = client.post("/api/quiz/generate/file", headers=auth_headers, files=files, data=data)
        
        # Should fail with 413 for size (before DOCX parsing fails)
        assert response.status_code == 413, \
            f"Expected 413 for oversized DOCX, got {response.status_code}: {response.text}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
