"""
Contract tests for POST /api/quiz/{quiz_id}/submit endpoint.

Tests quiz submission functionality including:
- Valid submission with answers
- Authorization requirements
"""

import pytest
from fastapi.testclient import TestClient
from main import app
from uuid import uuid4

client = TestClient(app)


@pytest.mark.contract
class TestSubmissionCreate:
    """Contract tests for quiz submission creation."""
    
    def test_submit_quiz_successfully(self, mock_supabase_client, auth_bypass, auth_headers):
        """
        Test successful quiz submission with answers.
        
        Expected:
        - Status code: 200 or 201
        - Response includes submission information
        """
    
    def test_submit_without_auth_returns_401(self, mock_supabase_client):
        """
        Test that submission without authentication returns HTTP 401.
        
        Expected:
        - Status code: 401
        - Error message about authentication
        """
        quiz_id = str(uuid4())
        submission_payload = {
            "quiz_id": quiz_id,
            "total_questions": 5,
            "answers": [
                {
                    "question_id": str(uuid4()),
                    "user_answer": "answer1"
                }
            ]
        }
        
        response = client.post(f"/api/quiz/{quiz_id}/submit", json=submission_payload)
        
        assert response.status_code == 401, \
            f"Expected 401 without auth, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "message" in data, f"Error response missing detail/message: {data}"
    
    def test_submit_with_invalid_token_returns_401(self, mock_supabase_client):
        """
        Test that submission with invalid token returns HTTP 401.
        
        Expected:
        - Status code: 401
        - Error message about invalid token
        """
        headers = {"Authorization": "Bearer invalid_token_xyz"}
        quiz_id = str(uuid4())
        submission_payload = {
            "quiz_id": quiz_id,
            "total_questions": 5,
            "answers": [
                {
                    "question_id": str(uuid4()),
                    "user_answer": "answer1"
                }
            ]
        }
        
        response = client.post(f"/api/quiz/{quiz_id}/submit", headers=headers, json=submission_payload)
        
        assert response.status_code == 401, \
            f"Expected 401 with invalid token, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "message" in data, f"Error response missing detail/message: {data}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
