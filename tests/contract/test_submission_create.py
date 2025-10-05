"""
Contract tests for POST /api/submission/submit endpoint.

Tests quiz submission functionality including:
- Valid submission with answers
- Authorization requirements
"""

import pytest
from fastapi.testclient import TestClient
from main import app
from dependencies.auth_dependencies import get_current_user_id

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
        submission_payload = {
            "quiz_id": "mock_quiz_123",
            "answers": {
                "q1": "answer1"
            }
        }
        
        response = client.post("/api/submission/submit", json=submission_payload)
        
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
        submission_payload = {
            "quiz_id": "mock_quiz_123",
            "answers": {
                "q1": "answer1"
            }
        }
        
        response = client.post("/api/submission/submit", headers=headers, json=submission_payload)
        
        assert response.status_code == 401, \
            f"Expected 401 with invalid token, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "message" in data, f"Error response missing detail/message: {data}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
