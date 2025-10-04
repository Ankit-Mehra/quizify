"""
Contract tests for POST /api/submission/submit endpoint.

Tests quiz submission functionality including:
- Valid submission with answers
- Invalid quiz_id
- Missing or invalid answers
- Authorization requirements
"""

import pytest
from fastapi.testclient import TestClient
from main import app
import os

client = TestClient(app)

TEST_EMAIL = f"test_submission_{os.urandom(4).hex()}@example.com"
TEST_PASSWORD = "SecurePass123!"


@pytest.fixture(scope="module")
def auth_token():
    """Create a test user and return auth token."""
    signup_payload = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
        "name": "Submission Test User"
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
def quiz_data(auth_token):
    """Generate a quiz and return quiz data for submission tests."""
    headers = {"Authorization": f"Bearer {auth_token}"}
    
    quiz_payload = {
        "text_content": """
        Python is a high-level programming language. It was created by Guido van Rossum in 1991.
        Python supports multiple programming paradigms including procedural, object-oriented, and functional programming.
        The language emphasizes code readability with its use of significant whitespace.
        Python has a comprehensive standard library and a large ecosystem of third-party packages.
        """,
        "num_questions": 3,
        "quiz_type": "multiple_choice"
    }
    
    response = client.post("/api/quiz/generate/text", headers=headers, json=quiz_payload)
    assert response.status_code == 201, f"Quiz generation failed: {response.text}"
    
    quiz = response.json()
    return quiz


class TestSubmissionCreate:
    """Contract tests for quiz submission creation."""
    
    def test_submit_quiz_successfully(self, auth_token, quiz_data):
        """
        Test successful quiz submission with answers.
        
        Expected:
        - Status code: 200 or 201
        - Response includes submission_id, score, correct/wrong counts
        """
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        quiz_id = quiz_data.get("id") or quiz_data.get("quiz_id")
        questions = quiz_data.get("questions", [])
        
        # Prepare answers for all questions
        answers = []
        for question in questions:
            q_id = question.get("id") or question.get("question_id")
            
            # Provide answers based on question type
            if question.get("type") == "multiple_choice":
                # Pick first option
                answers.append({
                    "question_id": q_id,
                    "user_answer": question.get("options", ["A"])[0]
                })
            elif question.get("type") == "true_false":
                answers.append({
                    "question_id": q_id,
                    "user_answer": True
                })
            elif question.get("type") == "multiple_select":
                answers.append({
                    "question_id": q_id,
                    "user_answer": [0, 1]  # Select first two options
                })
            else:
                # Default text answer
                answers.append({
                    "question_id": q_id,
                    "user_answer": "test answer"
                })
        
        submission_payload = {
            "quiz_id": quiz_id,
            "total_questions": len(questions),
            "answers": answers
        }
        
        response = client.post("/api/submission/submit", headers=headers, json=submission_payload)
        
        assert response.status_code in [200, 201], \
            f"Expected 200/201 for submission, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify response structure
        assert "id" in data or "submission_id" in data, "Response should contain submission ID"
        assert "score" in data, "Response should contain score"
        assert "correct_count" in data, "Response should contain correct count"
        assert "wrong_count" in data, "Response should contain wrong count"
        assert "total_questions" in data, "Response should contain total questions"
    
    def test_submit_with_invalid_quiz_id_returns_404(self, auth_token):
        """
        Test submission with non-existent quiz_id returns HTTP 404.
        
        Expected:
        - Status code: 404
        - Error about quiz not found
        """
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        submission_payload = {
            "quiz_id": "00000000-0000-0000-0000-000000000000",
            "total_questions": 3,
            "answers": [
                {
                    "question_id": "00000000-0000-0000-0000-000000000001",
                    "user_answer": "test"
                }
            ]
        }
        
        response = client.post("/api/submission/submit", headers=headers, json=submission_payload)
        
        assert response.status_code in [404, 400], \
            f"Expected 404/400 for invalid quiz_id, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "message" in data, \
            f"Error response missing detail/message: {data}"
    
    def test_submit_with_missing_answers_returns_422(self, auth_token, quiz_data):
        """
        Test submission with missing answers field returns HTTP 422.
        
        Expected:
        - Status code: 422
        - Validation error
        """
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        quiz_id = quiz_data.get("id") or quiz_data.get("quiz_id")
        
        # Missing answers field
        submission_payload = {
            "quiz_id": quiz_id,
            "total_questions": 3
        }
        
        response = client.post("/api/submission/submit", headers=headers, json=submission_payload)
        
        assert response.status_code == 422, \
            f"Expected 422 for missing answers, got {response.status_code}: {response.text}"
    
    def test_submit_with_empty_answers_returns_400(self, auth_token, quiz_data):
        """
        Test submission with empty answers array returns HTTP 400 or 422.
        
        Expected:
        - Status code: 400 or 422
        - Error about missing answers
        """
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        quiz_id = quiz_data.get("id") or quiz_data.get("quiz_id")
        
        submission_payload = {
            "quiz_id": quiz_id,
            "total_questions": 3,
            "answers": []
        }
        
        response = client.post("/api/submission/submit", headers=headers, json=submission_payload)
        
        assert response.status_code in [400, 422], \
            f"Expected 400/422 for empty answers, got {response.status_code}: {response.text}"
    
    def test_submit_without_auth_returns_401(self, quiz_data):
        """
        Test that submission without authentication returns HTTP 401.
        
        Expected:
        - Status code: 401
        - Error about missing authentication
        """
        quiz_id = quiz_data.get("id") or quiz_data.get("quiz_id")
        
        submission_payload = {
            "quiz_id": quiz_id,
            "total_questions": 3,
            "answers": [
                {
                    "question_id": "00000000-0000-0000-0000-000000000001",
                    "user_answer": "test"
                }
            ]
        }
        
        response = client.post("/api/submission/submit", json=submission_payload)
        
        assert response.status_code == 401, \
            f"Expected 401 without auth, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "message" in data, \
            f"Error response missing detail/message: {data}"
    
    def test_submit_with_invalid_token_returns_401(self, quiz_data):
        """
        Test that invalid token returns HTTP 401.
        
        Expected:
        - Status code: 401
        - Error about invalid authentication
        """
        headers = {"Authorization": "Bearer invalid_token_xyz123"}
        
        quiz_id = quiz_data.get("id") or quiz_data.get("quiz_id")
        
        submission_payload = {
            "quiz_id": quiz_id,
            "total_questions": 3,
            "answers": [
                {
                    "question_id": "00000000-0000-0000-0000-000000000001",
                    "user_answer": "test"
                }
            ]
        }
        
        response = client.post("/api/submission/submit", headers=headers, json=submission_payload)
        
        assert response.status_code == 401, \
            f"Expected 401 for invalid token, got {response.status_code}: {response.text}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
