"""
Contract tests for POST /api/quiz/generate/upload endpoint (PDF files).

Tests PDF-based quiz generation including:
- Valid PDF upload and quiz generation
- Corrupted PDF handling
- PDF with no extractable text
"""

import pytest
from fastapi.testclient import TestClient
from main import app
import os
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

client = TestClient(app)

TEST_EMAIL = f"test_quiz_pdf_{os.urandom(4).hex()}@example.com"
TEST_PASSWORD = "SecurePass123!"


def create_test_pdf_with_content(content: str) -> bytes:
    """Create a simple PDF with text content."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    
    # Add content line by line
    y = 750
    for line in content.split('\n'):
        if line.strip():
            c.drawString(100, y, line)
            y -= 15
    
    c.save()
    buffer.seek(0)
    return buffer.read()


def create_corrupted_pdf() -> bytes:
    """Create a more realistic corrupted PDF (valid header, broken content)."""
    # Start with a valid PDF header, then add random/truncated bytes to simulate corruption
    return b"%PDF-1.4\n%\xE2\xE3\xCF\xD3\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n" + os.urandom(32)


@pytest.fixture
def auth_token(mock_supabase_client, auth_bypass):
    """Create a test user and return auth token - requires auth_bypass for actual quiz requests."""
    signup_payload = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
        "name": "Quiz PDF Test User"
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


class TestQuizGeneratePDF:
    """Contract tests for PDF-based quiz generation."""
    
    def test_valid_pdf_generates_quiz_returns_201(self, auth_token):
        """
        Test that valid PDF upload generates quiz and returns HTTP 201.
        
        Expected:
        - Status code: 201
        - Response contains: quiz_id, questions
        """
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Create PDF with content
        pdf_content = """
        Python Programming Language
        
        Python is a high-level, interpreted programming language known for its simplicity and readability.
        It was created by Guido van Rossum and first released in 1991.
        
        Python supports multiple programming paradigms including procedural, object-oriented, and functional programming.
        It has a comprehensive standard library and a large ecosystem of third-party packages.
        
        Python is widely used in web development, data science, artificial intelligence, and automation.
        """
        
        pdf_bytes = create_test_pdf_with_content(pdf_content)
        
        files = {
            "file": ("test_quiz.pdf", io.BytesIO(pdf_bytes), "application/pdf")
        }
        data = {
            "title": "Python Basics Quiz",
            "num_questions": "5",
            "question_types": '["multiple_choice", "true_false"]'
        }
        
        response = client.post("/api/quiz/generate/upload", headers=headers, files=files, data=data)
        
        assert response.status_code == 201, \
            f"Expected 201 for valid PDF quiz generation, got {response.status_code}: {response.text}"
        
        response_data = response.json()
        assert "quiz_id" in response_data or "id" in response_data, f"Response missing quiz_id: {response_data}"
        assert "questions" in response_data, f"Response missing questions: {response_data}"
        
        questions = response_data["questions"]
        assert isinstance(questions, list), "Questions should be an array"
        assert len(questions) > 0, "Should generate at least some questions"
    
    def test_corrupted_pdf_returns_400(self, auth_token):
        """
        Test that corrupted/invalid PDF returns HTTP 400.
        
        Expected:
        - Status code: 400
        - Error message about invalid PDF
        """
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        corrupted_pdf = create_corrupted_pdf()
        
        files = {
            "file": ("corrupted.pdf", io.BytesIO(corrupted_pdf), "application/pdf")
        }
        data = {
            "title": "Corrupted PDF Quiz",
            "num_questions": "5",
            "question_types": '["multiple_choice"]'
        }
        
        response = client.post("/api/quiz/generate/upload", headers=headers, files=files, data=data)
        
        assert response.status_code == 400, \
            f"Expected 400 for corrupted PDF, got {response.status_code}: {response.text}"
        
        response_data = response.json()
        assert "detail" in response_data or "message" in response_data, \
            f"Error response missing detail/message: {response_data}"
    
    def test_pdf_with_no_text_returns_400(self, auth_token):
        """
        Test that PDF with no extractable text returns HTTP 400.
        
        Expected:
        - Status code: 400
        - Error message about insufficient content
        """
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Create PDF with minimal/no text
        empty_pdf = create_test_pdf_with_content("")
        
        files = {
            "file": ("empty.pdf", io.BytesIO(empty_pdf), "application/pdf")
        }
        data = {
            "title": "Empty PDF Quiz",
            "num_questions": "5",
            "question_types": '["multiple_choice"]'
        }
        
        response = client.post("/api/quiz/generate/upload", headers=headers, files=files, data=data)
        
        assert response.status_code == 400, \
            f"Expected 400 for empty PDF, got {response.status_code}: {response.text}"
    
    def test_unauthorized_request_returns_403_csrf(self):
        """
        Test that requests without authentication return HTTP 403 (CSRF protection).
        
        Note: POST requests without Authorization header or X-CSRF-Token are rejected
        by CSRF middleware before auth can run. This is correct security behavior.
        
        Expected:
        - Status code: 403
        """
        pdf_bytes = create_test_pdf_with_content("Test content")
        
        files = {
            "file": ("test.pdf", io.BytesIO(pdf_bytes), "application/pdf")
        }
        data = {
            "title": "Unauthorized Quiz",
            "num_questions": "5",
            "question_types": '["multiple_choice"]'
        }
        
        response = client.post("/api/quiz/generate/upload", files=files, data=data)
        
        assert response.status_code == 403, \
            f"Expected 403 without auth, got {response.status_code}: {response.text}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
