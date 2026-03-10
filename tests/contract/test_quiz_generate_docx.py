"""
Contract tests for POST /api/quiz/generate/upload endpoint (DOCX files).

Tests DOCX-based quiz generation including:
- Valid DOCX upload and quiz generation
- Corrupted DOCX handling
"""

import pytest
from fastapi.testclient import TestClient
from main import app
import os
import io
from docx import Document

client = TestClient(app)

TEST_EMAIL = f"test_quiz_docx_{os.urandom(4).hex()}@example.com"
TEST_PASSWORD = "SecurePass123!"


def create_test_docx_with_content(content: str) -> bytes:
    """Create a DOCX file with text content."""
    doc = Document()
    
    # Add content paragraphs
    for paragraph in content.split('\n'):
        if paragraph.strip():
            doc.add_paragraph(paragraph)
    
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer.read()


def create_corrupted_docx() -> bytes:
    """Create an invalid/corrupted DOCX."""
    return b"This is not a valid DOCX file"


@pytest.fixture
def auth_token(mock_supabase_client, auth_bypass):
    """Create a test user and return auth token - requires auth_bypass for actual quiz requests."""
    signup_payload = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
        "name": "Quiz DOCX Test User"
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


class TestQuizGenerateDOCX:
    """Contract tests for DOCX-based quiz generation."""
    
    def test_valid_docx_generates_quiz_returns_201(self, auth_token):
        """
        Test that valid DOCX upload generates quiz and returns HTTP 201.
        
        Expected:
        - Status code: 201
        - Response contains: quiz_id, questions
        """
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Create DOCX with content
        docx_content = """
        JavaScript Programming Language
        
        JavaScript is a versatile, high-level programming language primarily used for web development.
        It was created by Brendan Eich in 1995 and has become one of the core technologies of the web.
        
        JavaScript enables interactive web pages and is an essential part of web applications.
        It supports event-driven, functional, and imperative programming styles.
        
        Modern JavaScript includes features like async/await, arrow functions, and modules.
        Popular frameworks include React, Angular, and Vue.js.
        """
        
        docx_bytes = create_test_docx_with_content(docx_content)
        
        files = {
            "file": ("test_quiz.docx", io.BytesIO(docx_bytes), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        }
        data = {
            "title": "JavaScript Basics Quiz",
            "num_questions": "5",
            "question_types": '["multiple_choice", "true_false"]'
        }
        
        response = client.post("/api/quiz/generate/upload", headers=headers, files=files, data=data)
        
        assert response.status_code == 201, \
            f"Expected 201 for valid DOCX quiz generation, got {response.status_code}: {response.text}"
        
        response_data = response.json()
        assert "quiz_id" in response_data or "id" in response_data, f"Response missing quiz_id: {response_data}"
        assert "questions" in response_data, f"Response missing questions: {response_data}"
        
        questions = response_data["questions"]
        assert isinstance(questions, list), "Questions should be an array"
        assert len(questions) > 0, "Should generate at least some questions"
        
        # Verify question structure
        for question in questions:
            assert "type" in question, f"Question missing type: {question}"
            assert "question" in question, f"Question missing question text: {question}"
            assert "correct_answer" in question, f"Question missing correct_answer: {question}"
    
    def test_corrupted_docx_returns_400(self, auth_token):
        """
        Test that corrupted/invalid DOCX returns HTTP 400.
        
        Expected:
        - Status code: 400
        - Error message about invalid DOCX
        """
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        corrupted_docx = create_corrupted_docx()
        
        files = {
            "file": ("corrupted.docx", io.BytesIO(corrupted_docx), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        }
        data = {
            "title": "Corrupted DOCX Quiz",
            "num_questions": "5",
            "question_types": '["multiple_choice"]'
        }
        
        response = client.post("/api/quiz/generate/upload", headers=headers, files=files, data=data)
        
        assert response.status_code == 400, \
            f"Expected 400 for corrupted DOCX, got {response.status_code}: {response.text}"
        
        response_data = response.json()
        assert "detail" in response_data or "message" in response_data, \
            f"Error response missing detail/message: {response_data}"
    
    def test_empty_docx_returns_400(self, auth_token):
        """
        Test that DOCX with no extractable text returns HTTP 400.
        
        Expected:
        - Status code: 400
        - Error message about insufficient content
        """
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Create empty DOCX
        empty_docx = create_test_docx_with_content("")
        
        files = {
            "file": ("empty.docx", io.BytesIO(empty_docx), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        }
        data = {
            "title": "Empty DOCX Quiz",
            "num_questions": "5",
            "question_types": '["multiple_choice"]'
        }
        
        response = client.post("/api/quiz/generate/upload", headers=headers, files=files, data=data)
        
        assert response.status_code == 400, \
            f"Expected 400 for empty DOCX, got {response.status_code}: {response.text}"
    
    def test_unauthorized_request_returns_403_csrf(self):
        """
        Test that requests without authentication return HTTP 403 (CSRF protection).
        
        Note: POST requests without Authorization header or X-CSRF-Token are rejected
        by CSRF middleware before auth can run. This is correct security behavior.
        
        Expected:
        - Status code: 403
        """
        docx_bytes = create_test_docx_with_content("Test content for authorization check")
        
        files = {
            "file": ("test.docx", io.BytesIO(docx_bytes), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
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
