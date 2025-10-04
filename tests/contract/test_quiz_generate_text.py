"""
Contract tests for POST /api/quiz/generate/text endpoint.

Tests text-based quiz generation including:
- Valid text input generating quiz
- Insufficient text rejection
- Invalid question types
- Out-of-range num_questions
"""

import pytest
from fastapi.testclient import TestClient
from main import app
import os

client = TestClient(app)

# Test data
VALID_TEXT = """
Artificial Intelligence (AI) is the simulation of human intelligence processes by machines, especially computer systems. 
These processes include learning (the acquisition of information and rules for using the information), 
reasoning (using rules to reach approximate or definite conclusions) and self-correction.

Machine learning is a subset of AI that provides systems the ability to automatically learn and improve from experience 
without being explicitly programmed. Deep learning is a subset of machine learning that uses neural networks with many layers.

Natural Language Processing (NLP) is a branch of AI that helps computers understand, interpret and manipulate human language.
"""

INSUFFICIENT_TEXT = "AI"

TEST_EMAIL = f"test_quiz_text_{os.urandom(4).hex()}@example.com"
TEST_PASSWORD = "SecurePass123!"


@pytest.fixture(scope="module")
def auth_token():
    """Create a test user and return auth token."""
    # Signup
    signup_payload = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
        "name": "Quiz Text Test User"
    }
    signup_response = client.post("/api/auth/signup", json=signup_payload)
    assert signup_response.status_code == 201
    
    # Login
    login_payload = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    }
    login_response = client.post("/api/auth/login", json=login_payload)
    assert login_response.status_code == 200
    
    data = login_response.json()
    token = data.get("access_token") or data.get("accessToken") or data.get("token")
    
    return token


class TestQuizGenerateText:
    """Contract tests for text-based quiz generation."""
    
    def test_valid_text_generates_quiz_returns_201(self, auth_token):
        """
        Test that valid text input generates a quiz and returns HTTP 201.
        
        Expected:
        - Status code: 201
        - Response contains: quiz_id, questions array
        - Questions match requested types
        """
        headers = {"Authorization": f"Bearer {auth_token}"}
        payload = {
            "text": VALID_TEXT,
            "title": "AI Fundamentals Quiz",
            "num_questions": 5,
            "question_types": ["multiple_choice", "true_false"]
        }
        
        response = client.post("/api/quiz/generate/text", headers=headers, json=payload)
        
        assert response.status_code == 201, \
            f"Expected 201 for valid quiz generation, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "quiz_id" in data or "id" in data, f"Response missing quiz_id: {data}"
        assert "questions" in data, f"Response missing questions: {data}"
        
        questions = data["questions"]
        assert isinstance(questions, list), "Questions should be an array"
        assert len(questions) > 0, "Should generate at least some questions"
        
        # Verify questions have expected structure
        for question in questions:
            assert "type" in question, f"Question missing type: {question}"
            assert "question" in question, f"Question missing question text: {question}"
            assert "correct_answer" in question, f"Question missing correct_answer: {question}"
    
    def test_insufficient_text_returns_400(self, auth_token):
        """
        Test that text with <10 characters returns HTTP 400.
        
        Expected:
        - Status code: 400
        - Error message about insufficient content
        """
        headers = {"Authorization": f"Bearer {auth_token}"}
        payload = {
            "text": INSUFFICIENT_TEXT,
            "title": "Short Quiz",
            "num_questions": 5,
            "question_types": ["multiple_choice"]
        }
        
        response = client.post("/api/quiz/generate/text", headers=headers, json=payload)
        
        assert response.status_code == 400, \
            f"Expected 400 for insufficient text, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "message" in data, f"Error response missing detail/message: {data}"
    
    def test_invalid_question_type_returns_422(self, auth_token):
        """
        Test that invalid question types return HTTP 422.
        
        Expected:
        - Status code: 422
        - Validation error about invalid question type
        """
        headers = {"Authorization": f"Bearer {auth_token}"}
        payload = {
            "text": VALID_TEXT,
            "title": "Invalid Type Quiz",
            "num_questions": 5,
            "question_types": ["invalid_type", "nonexistent_type"]
        }
        
        response = client.post("/api/quiz/generate/text", headers=headers, json=payload)
        
        assert response.status_code == 422, \
            f"Expected 422 for invalid question types, got {response.status_code}: {response.text}"
    
    def test_num_questions_out_of_range_returns_422(self, auth_token):
        """
        Test that num_questions outside 1-50 range returns HTTP 422.
        
        Expected:
        - Status code: 422
        - Validation error about invalid range
        """
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Test 0 questions
        payload_zero = {
            "text": VALID_TEXT,
            "title": "Zero Questions Quiz",
            "num_questions": 0,
            "question_types": ["multiple_choice"]
        }
        
        response = client.post("/api/quiz/generate/text", headers=headers, json=payload_zero)
        assert response.status_code == 422, \
            f"Expected 422 for 0 questions, got {response.status_code}: {response.text}"
        
        # Test 51 questions (over limit)
        payload_over = {
            "text": VALID_TEXT,
            "title": "Too Many Questions Quiz",
            "num_questions": 51,
            "question_types": ["multiple_choice"]
        }
        
        response = client.post("/api/quiz/generate/text", headers=headers, json=payload_over)
        assert response.status_code == 422, \
            f"Expected 422 for 51 questions, got {response.status_code}: {response.text}"
    
    def test_missing_required_fields_returns_422(self, auth_token):
        """
        Test that missing required fields returns HTTP 422.
        
        Expected:
        - Status code: 422
        - Validation error listing missing fields
        """
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Missing text
        payload_no_text = {
            "title": "No Text Quiz",
            "num_questions": 5,
            "question_types": ["multiple_choice"]
        }
        
        response = client.post("/api/quiz/generate/text", headers=headers, json=payload_no_text)
        assert response.status_code == 422, \
            f"Expected 422 for missing text, got {response.status_code}: {response.text}"
    
    def test_unauthorized_request_returns_401(self):
        """
        Test that requests without authentication return HTTP 401.
        
        Expected:
        - Status code: 401
        - Error about missing authentication
        """
        payload = {
            "text": VALID_TEXT,
            "title": "Unauthorized Quiz",
            "num_questions": 5,
            "question_types": ["multiple_choice"]
        }
        
        response = client.post("/api/quiz/generate/text", json=payload)
        
        assert response.status_code == 401, \
            f"Expected 401 without auth, got {response.status_code}: {response.text}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
