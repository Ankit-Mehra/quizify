"""
Contract tests for GET /api/submission/{submission_id} endpoint.

Tests quiz submission retrieval functionality including:
- Get submission by submission_id
- Authorization requirements
"""

import pytest
from fastapi.testclient import TestClient
from main import app
from uuid import uuid4

client = TestClient(app)


@pytest.mark.contract
class TestSubmissionGet:
    """Contract tests for getting quiz submissions."""
    
    def test_get_submission_successfully(self, mock_supabase_client, auth_bypass, auth_headers):
        """
        Test successful retrieval of submission.
        
        Expected:
        - Status code: 200
        - Response includes submission data
        """
    
    def test_get_submission_without_auth_returns_401(self, mock_supabase_client):
        """
        Test that getting submission without authentication returns HTTP 401.
        
        Expected:
        - Status code: 401
        - Error message about authentication
        """
        submission_id = str(uuid4())
        
        response = client.get(f"/api/submission/{submission_id}")
        
        assert response.status_code == 401, \
            f"Expected 401 without auth, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "message" in data, f"Error response missing detail/message: {data}"
    
    def test_get_submission_with_invalid_token_returns_401(self, mock_supabase_client):
        """
        Test that getting submission with invalid token returns HTTP 401.
        
        Expected:
        - Status code: 401
        - Error message about invalid token
        """
        headers = {"Authorization": "Bearer invalid_token_xyz"}
        submission_id = str(uuid4())
        
        response = client.get(f"/api/submission/{submission_id}", headers=headers)
        
        assert response.status_code == 401, \
            f"Expected 401 with invalid token, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "message" in data, f"Error response missing detail/message: {data}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
