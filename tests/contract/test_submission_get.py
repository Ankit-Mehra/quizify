"""
Contract tests for GET /api/submission/{submission_id} endpoint.

Tests submission retrieval functionality including:
- Retrieve existing submission
- Retrieve non-existent submission
- Authorization requirements
- Access control for other users' submissions
"""

import pytest
from fastapi.testclient import TestClient
from main import app
import os

client = TestClient(app)

TEST_EMAIL = f"test_submission_get_{os.urandom(4).hex()}@example.com"
TEST_PASSWORD = "SecurePass123!"


@pytest.fixture(scope="module")
def auth_token():
    """Create a test user and return auth token."""
    signup_payload = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
        "name": "Submission Get Test User"
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


@pytest.fixture(scope="module")
def submission_id(auth_token):
    """Generate a quiz and create a submission for testing."""
    headers = {"Authorization": f"Bearer {auth_token}"}
    
    # Generate a quiz
    quiz_payload = {
        "text_content": """
        Python is a high-level programming language. It was created by Guido van Rossum in 1991.
        Python supports multiple programming paradigms including procedural, object-oriented, and functional programming.
        The language emphasizes code readability with its use of significant whitespace.
        """,
        "num_questions": 3,
        "quiz_type": "multiple_choice"
    }
    
    quiz_response = client.post("/api/quiz/generate/text", headers=headers, json=quiz_payload)
    assert quiz_response.status_code == 201
    
    quiz_data = quiz_response.json()
    quiz_id = quiz_data.get("id") or quiz_data.get("quiz_id")
    questions = quiz_data.get("questions", [])
    
    # Create answers
    answers = []
    for question in questions:
        q_id = question.get("id") or question.get("question_id")
        
        if question.get("type") == "multiple_choice":
            answers.append({
                "question_id": q_id,
                "user_answer": question.get("options", ["A"])[0]
            })
        else:
            answers.append({
                "question_id": q_id,
                "user_answer": "test answer"
            })
    
    # Submit the quiz
    submission_payload = {
        "quiz_id": quiz_id,
        "total_questions": len(questions),
        "answers": answers
    }
    
    submit_response = client.post("/api/submission/submit", headers=headers, json=submission_payload)
    assert submit_response.status_code in [200, 201]
    
    submit_data = submit_response.json()
    return submit_data.get("id") or submit_data.get("submission_id")


class TestSubmissionGet:
    """Contract tests for submission retrieval."""
    
    def test_get_submission_successfully(self, auth_token, submission_id):
        """
        Test successful retrieval of existing submission.
        
        Expected:
        - Status code: 200
        - Response includes submission details (id, quiz_id, score, etc.)
        """
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        response = client.get(f"/api/submission/{submission_id}", headers=headers)
        
        assert response.status_code == 200, \
            f"Expected 200 for submission retrieval, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify response structure
        assert "id" in data or "submission_id" in data, "Response should contain submission ID"
        assert "quiz_id" in data, "Response should contain quiz_id"
        assert "score" in data, "Response should contain score"
        assert "correct_count" in data, "Response should contain correct count"
        assert "wrong_count" in data, "Response should contain wrong count"
        assert "total_questions" in data, "Response should contain total questions"
        assert "user_id" in data, "Response should contain user_id"
        assert "submitted_at" in data, "Response should contain submitted_at timestamp"
    
    def test_get_nonexistent_submission_returns_404(self, auth_token):
        """
        Test retrieving non-existent submission returns HTTP 404.
        
        Expected:
        - Status code: 404
        - Error about submission not found
        """
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        fake_submission_id = "00000000-0000-0000-0000-000000000000"
        
        response = client.get(f"/api/submission/{fake_submission_id}", headers=headers)
        
        assert response.status_code == 404, \
            f"Expected 404 for non-existent submission, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "message" in data, \
            f"Error response missing detail/message: {data}"
    
    def test_get_other_users_submission_returns_403(self, auth_token, other_user_token, submission_id):
        """
        Test that retrieving another user's submission returns HTTP 403.
        
        Expected:
        - Status code: 403 or 404
        - Error about access denied or not found
        """
        # User 2 tries to access User 1's submission
        headers_user2 = {"Authorization": f"Bearer {other_user_token}"}
        
        response = client.get(f"/api/submission/{submission_id}", headers=headers_user2)
        
        assert response.status_code in [403, 404], \
            f"Expected 403 or 404 for other user's submission, got {response.status_code}: {response.text}"
    
    def test_get_submission_without_auth_returns_401(self, submission_id):
        """
        Test that retrieving submission without authentication returns HTTP 401.
        
        Expected:
        - Status code: 401
        - Error about missing authentication
        """
        response = client.get(f"/api/submission/{submission_id}")
        
        assert response.status_code == 401, \
            f"Expected 401 without auth, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "message" in data, \
            f"Error response missing detail/message: {data}"
    
    def test_get_submission_with_invalid_token_returns_401(self, submission_id):
        """
        Test that invalid token returns HTTP 401.
        
        Expected:
        - Status code: 401
        - Error about invalid authentication
        """
        headers = {"Authorization": "Bearer invalid_token_xyz123"}
        
        response = client.get(f"/api/submission/{submission_id}", headers=headers)
        
        assert response.status_code == 401, \
            f"Expected 401 for invalid token, got {response.status_code}: {response.text}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
