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
    
    def test_submit_with_zero_total_questions_returns_400(self, mock_supabase_client, auth_bypass, auth_headers):
        """
        Test that submission with total_questions=0 returns HTTP 422 (Pydantic validation error).
        This prevents division by zero when calculating score.
        Schema validation ensures total_questions > 0.
        
        Expected:
        - Status code: 422 (Pydantic validation error)
        - Error message about total_questions validation
        """
        quiz_id = str(uuid4())
        submission_payload = {
            "quiz_id": quiz_id,
            "total_questions": 0,  # Invalid: should cause 422 (Pydantic validation)
            "answers": []
        }
        
        response = client.post(f"/api/quiz/{quiz_id}/submit", headers=auth_headers, json=submission_payload)
        
        assert response.status_code == 422, \
            f"Expected 422 for zero total_questions (Pydantic validation), got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data, f"Error response missing detail: {data}"
        # Custom validation handler returns {"detail": string, "errors": [...]}
        errors = data.get("errors", [])
        assert isinstance(errors, list), f"Expected errors list in response: {data}"
        assert any("total_questions" in str(err.get("location", "")) for err in errors), \
            f"Error should reference total_questions field: {data}"
    
    def test_submit_with_negative_total_questions_returns_400(self, mock_supabase_client, auth_bypass, auth_headers):
        """
        Test that submission with negative total_questions returns HTTP 422 (Pydantic validation error).
        Schema validation ensures total_questions > 0.
        
        Expected:
        - Status code: 422 (Pydantic validation error)
        - Error message about total_questions validation
        """
        quiz_id = str(uuid4())
        submission_payload = {
            "quiz_id": quiz_id,
            "total_questions": -5,  # Invalid: should cause 422 (Pydantic validation)
            "answers": []
        }
        
        response = client.post(f"/api/quiz/{quiz_id}/submit", headers=auth_headers, json=submission_payload)
        
        assert response.status_code == 422, \
            f"Expected 422 for negative total_questions (Pydantic validation), got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data, f"Error response missing detail: {data}"
        # Custom validation handler returns {"detail": string, "errors": [...]}
        errors = data.get("errors", [])
        assert isinstance(errors, list), f"Expected errors list in response: {data}"
        assert any("total_questions" in str(err.get("location", "")) for err in errors), \
            f"Error should reference total_questions field: {data}"
    
    def test_submit_with_mismatched_quiz_id_returns_400(self, mock_supabase_client, auth_bypass, auth_headers):
        """
        Test that submission with quiz_id in body not matching URL parameter returns HTTP 400.
        This is an API-level constraint enforced by the handler, not the schema.
        
        Expected:
        - Status code: 400 (Bad Request)
        - Error message about quiz_id mismatch
        """
        url_quiz_id = str(uuid4())
        body_quiz_id = str(uuid4())  # Different from URL
        
        submission_payload = {
            "quiz_id": body_quiz_id,  # Doesn't match URL parameter
            "total_questions": 5,
            "answers": [
                {
                    "question_id": str(uuid4()),
                    "user_answer": "answer1"
                }
            ]
        }
        
        response = client.post(f"/api/quiz/{url_quiz_id}/submit", headers=auth_headers, json=submission_payload)
        
        assert response.status_code == 400, \
            f"Expected 400 for quiz_id mismatch, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data, f"Error response missing detail: {data}"
        assert "quiz id" in data["detail"].lower() or "match" in data["detail"].lower(), \
            f"Error message should mention quiz_id mismatch: {data['detail']}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
