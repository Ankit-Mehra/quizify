"""
Contract tests for POST /api/quiz/generate/text endpoint.

Tests text-based quiz generation functionality including:
- Valid text quiz generation
- Authorization requirements
"""

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


@pytest.mark.contract
class TestQuizGenerateText:
    """Contract tests for text quiz generation."""
    
    def test_generate_text_quiz_successfully(self, mock_supabase_client, auth_bypass, auth_headers):
        """
        Test successful text quiz generation.
        
        Expected:
        - Status code: 200 or 201
        - Response includes quiz_id, title, message
        """
        quiz_payload = {
            "title": "Test Quiz",
            "content": "Python is a high-level programming language created by Guido van Rossum.",
            "num_questions": 3
        }
        
        response = client.post("/api/quiz/generate/text", headers=auth_headers, json=quiz_payload)
        
        assert response.status_code in [200, 201], \
            f"Expected 200/201 for quiz generation, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "quiz_id" in data, f"Response missing quiz_id: {data}"
        assert "title" in data, f"Response missing title: {data}"
        assert "message" in data, f"Response missing message: {data}"
    
    def test_generate_quiz_without_auth_returns_401(self, mock_supabase_client):
        """
        Test that quiz generation without authentication returns HTTP 401.
        
        Expected:
        - Status code: 401
        - Error message about authentication
        """
        quiz_payload = {
            "title": "Test Quiz",
            "content": "Test content",
            "num_questions": 3
        }
        
        response = client.post("/api/quiz/generate/text", json=quiz_payload)
        
        assert response.status_code == 401, \
            f"Expected 401 without auth, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "message" in data, f"Error response missing detail/message: {data}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
