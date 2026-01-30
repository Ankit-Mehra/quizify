"""
Contract tests for GET /api/submission/{submission_id}/review endpoint.

Tests the submission review functionality including:
- Get detailed submission review with questions and explanations
- Authorization requirements (only owner can access)
- 404 for non-existent submissions
"""

import pytest
from fastapi.testclient import TestClient
from main import app
from uuid import uuid4

client = TestClient(app)

# Fixed UUIDs for testing consistency
MOCK_USER_UUID = "12345678-1234-1234-1234-123456789012"
OTHER_USER_UUID = "87654321-4321-4321-4321-210987654321"


@pytest.mark.contract
class TestSubmissionReviewGet:
    """Contract tests for getting detailed submission review."""
    
    def test_get_submission_review_successfully(self, mock_supabase_client, auth_bypass, auth_headers, mocker):
        """
        Test successful retrieval of submission review with detailed answers.
        
        Expected:
        - Status code: 200
        - Response includes submission summary and questions with explanations
        """
        submission_id = str(uuid4())
        quiz_id = str(uuid4())
        question_id = str(uuid4())
        
        # Create mock for get_submission_review DB function
        def mock_get_submission_review(sub_id, user_token=None):
            return {
                "submission_id": submission_id,
                "quiz_id": quiz_id,
                "quiz_title": "Test Quiz",
                "user_id": MOCK_USER_UUID,
                "score": 80,
                "correct_count": 4,
                "wrong_count": 1,
                "total_questions": 5,
                "submitted_at": "2026-01-27T10:00:00Z",
                "questions": [
                    {
                        "question_id": question_id,
                        "question_type": "multiple_choice",
                        "question": "What is the capital of France?",
                        "your_answer": "Paris",
                        "correct_answer": "Paris",
                        "is_correct": True,
                        "explanation": "Paris is the capital city of France.",
                        "options": ["Paris", "London", "Berlin", "Madrid"],
                        "distractor_explanations": None,
                        "bloom_level": "remember",
                        "difficulty": "easy",
                        "concept_name": "Geography"
                    }
                ]
            }
        
        # Update auth bypass to use proper UUID
        from dependencies.auth_dependencies import get_current_user_id
        
        def mock_user_id_uuid():
            return MOCK_USER_UUID
        
        app.dependency_overrides[get_current_user_id] = mock_user_id_uuid
        
        mocker.patch(
            "handlers.submission_handler.get_review_from_db",
            side_effect=mock_get_submission_review
        )
        
        response = client.get(f"/api/submission/{submission_id}/review", headers=auth_headers)
        
        # Restore original override
        app.dependency_overrides.clear()
        
        assert response.status_code == 200, \
            f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify response structure
        assert "submission_id" in data, "Response missing submission_id"
        assert "quiz_id" in data, "Response missing quiz_id"
        assert "quiz_title" in data, "Response missing quiz_title"
        assert "score" in data, "Response missing score"
        assert "correct_count" in data, "Response missing correct_count"
        assert "wrong_count" in data, "Response missing wrong_count"
        assert "total_questions" in data, "Response missing total_questions"
        assert "questions" in data, "Response missing questions"
        
        # Verify questions structure
        assert len(data["questions"]) > 0, "Expected at least one question in review"
        question = data["questions"][0]
        assert "question_id" in question, "Question missing question_id"
        assert "question_type" in question, "Question missing question_type"
        assert "question" in question, "Question missing question text"
        assert "your_answer" in question, "Question missing your_answer"
        assert "correct_answer" in question, "Question missing correct_answer"
        assert "is_correct" in question, "Question missing is_correct"
        assert "explanation" in question, "Question missing explanation"
    
    def test_get_submission_review_without_auth_returns_401(self, mock_supabase_client):
        """
        Test that getting submission review without authentication returns HTTP 401.
        
        Expected:
        - Status code: 401
        - Error message about authentication
        """
        submission_id = str(uuid4())
        
        response = client.get(f"/api/submission/{submission_id}/review")
        
        assert response.status_code == 401, \
            f"Expected 401 without auth, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "message" in data, f"Error response missing detail/message: {data}"
    
    def test_get_submission_review_with_invalid_token_returns_401(self, mock_supabase_client):
        """
        Test that getting submission review with invalid token returns HTTP 401.
        
        Expected:
        - Status code: 401
        - Error message about invalid token
        """
        headers = {"Authorization": "Bearer invalid_token_xyz"}
        submission_id = str(uuid4())
        
        response = client.get(f"/api/submission/{submission_id}/review", headers=headers)
        
        assert response.status_code == 401, \
            f"Expected 401 with invalid token, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "message" in data, f"Error response missing detail/message: {data}"
    
    def test_get_submission_review_not_found_returns_404(self, mock_supabase_client, auth_bypass, auth_headers, mocker):
        """
        Test that getting a non-existent submission returns HTTP 404.
        
        Expected:
        - Status code: 404
        - Error message about submission not found
        """
        from fastapi import HTTPException
        from dependencies.auth_dependencies import get_current_user_id
        
        submission_id = str(uuid4())
        
        def mock_user_id_uuid():
            return MOCK_USER_UUID
        
        app.dependency_overrides[get_current_user_id] = mock_user_id_uuid
        
        def mock_get_submission_review_not_found(sub_id, user_token=None):
            raise HTTPException(status_code=404, detail=f"Submission {sub_id} not found")
        
        mocker.patch(
            "handlers.submission_handler.get_review_from_db",
            side_effect=mock_get_submission_review_not_found
        )
        
        response = client.get(f"/api/submission/{submission_id}/review", headers=auth_headers)
        
        app.dependency_overrides.clear()
        
        assert response.status_code == 404, \
            f"Expected 404 for non-existent submission, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data, f"Error response missing detail: {data}"
        assert "not found" in data["detail"].lower(), f"Error message should mention 'not found': {data}"
    
    def test_get_submission_review_unauthorized_returns_403(self, mock_supabase_client, auth_bypass, auth_headers, mocker):
        """
        Test that accessing another user's submission returns HTTP 403.
        
        Expected:
        - Status code: 403
        - Error message about authorization
        """
        from dependencies.auth_dependencies import get_current_user_id
        
        submission_id = str(uuid4())
        
        def mock_user_id_uuid():
            return MOCK_USER_UUID
        
        app.dependency_overrides[get_current_user_id] = mock_user_id_uuid
        
        # Return submission belonging to a different user
        def mock_get_submission_review_other_user(sub_id, user_token=None):
            return {
                "submission_id": submission_id,
                "quiz_id": str(uuid4()),
                "quiz_title": "Other User's Quiz",
                "user_id": OTHER_USER_UUID,  # Different from MOCK_USER_UUID
                "score": 80,
                "correct_count": 4,
                "wrong_count": 1,
                "total_questions": 5,
                "submitted_at": "2026-01-27T10:00:00Z",
                "questions": []
            }
        
        mocker.patch(
            "handlers.submission_handler.get_review_from_db",
            side_effect=mock_get_submission_review_other_user
        )
        
        response = client.get(f"/api/submission/{submission_id}/review", headers=auth_headers)
        
        app.dependency_overrides.clear()
        
        assert response.status_code == 403, \
            f"Expected 403 for unauthorized access, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data, f"Error response missing detail: {data}"
        assert "authorized" in data["detail"].lower() or "permission" in data["detail"].lower(), \
            f"Error message should mention authorization: {data}"


@pytest.mark.contract
class TestSubmissionReviewResponseContract:
    """Contract tests for the SubmissionReviewResponse schema."""
    
    def test_response_includes_all_required_fields(self, mock_supabase_client, auth_bypass, auth_headers, mocker):
        """
        Test that the response includes all required fields per the schema.
        
        Expected:
        - All required fields present in response
        - Correct types for each field
        """
        from dependencies.auth_dependencies import get_current_user_id
        
        submission_id = str(uuid4())
        quiz_id = str(uuid4())
        
        def mock_user_id_uuid():
            return MOCK_USER_UUID
        
        app.dependency_overrides[get_current_user_id] = mock_user_id_uuid
        
        def mock_get_submission_review(sub_id, user_token=None):
            return {
                "submission_id": submission_id,
                "quiz_id": quiz_id,
                "quiz_title": "Test Quiz",
                "user_id": MOCK_USER_UUID,
                "score": 100,
                "correct_count": 5,
                "wrong_count": 0,
                "total_questions": 5,
                "submitted_at": "2026-01-27T10:00:00Z",
                "questions": [{
                    "question_id": str(uuid4()),
                    "question_type": "multiple_choice",
                    "question": "Test question",
                    "your_answer": "A",
                    "correct_answer": "A",
                    "is_correct": True,
                    "explanation": "Test explanation",
                    "options": None,
                    "distractor_explanations": None,
                    "bloom_level": None,
                    "difficulty": None,
                    "concept_name": None
                }]
            }
        
        mocker.patch(
            "handlers.submission_handler.get_review_from_db",
            side_effect=mock_get_submission_review
        )
        
        response = client.get(f"/api/submission/{submission_id}/review", headers=auth_headers)
        
        app.dependency_overrides.clear()
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify all required fields
        required_fields = [
            "submission_id", "quiz_id", "quiz_title", "user_id",
            "score", "correct_count", "wrong_count", "total_questions",
            "submitted_at", "questions"
        ]
        
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        # Verify types
        assert isinstance(data["score"], int), "score should be int"
        assert isinstance(data["correct_count"], int), "correct_count should be int"
        assert isinstance(data["wrong_count"], int), "wrong_count should be int"
        assert isinstance(data["total_questions"], int), "total_questions should be int"
        assert isinstance(data["questions"], list), "questions should be list"
    
    def test_question_review_detail_includes_optional_fields(self, mock_supabase_client, auth_bypass, auth_headers, mocker):
        """
        Test that question review details include optional enhanced fields.
        
        Expected:
        - Optional fields present (may be null)
        - bloom_level, difficulty, concept_name, options, distractor_explanations
        """
        from dependencies.auth_dependencies import get_current_user_id
        
        submission_id = str(uuid4())
        question_id = str(uuid4())
        
        def mock_user_id_uuid():
            return MOCK_USER_UUID
        
        app.dependency_overrides[get_current_user_id] = mock_user_id_uuid
        
        def mock_get_submission_review(sub_id, user_token=None):
            return {
                "submission_id": submission_id,
                "quiz_id": str(uuid4()),
                "quiz_title": "Enhanced Quiz",
                "user_id": MOCK_USER_UUID,
                "score": 100,
                "correct_count": 1,
                "wrong_count": 0,
                "total_questions": 1,
                "submitted_at": "2026-01-27T10:00:00Z",
                "questions": [
                    {
                        "question_id": question_id,
                        "question_type": "multiple_choice",
                        "question": "What is 2+2?",
                        "your_answer": "4",
                        "correct_answer": "4",
                        "is_correct": True,
                        "explanation": "Basic arithmetic",
                        "options": ["3", "4", "5", "6"],
                        "distractor_explanations": {"3": "Incorrect", "5": "Close", "6": "Too high"},
                        "bloom_level": "remember",
                        "difficulty": "easy",
                        "concept_name": "Addition"
                    }
                ]
            }
        
        mocker.patch(
            "handlers.submission_handler.get_review_from_db",
            side_effect=mock_get_submission_review
        )
        
        response = client.get(f"/api/submission/{submission_id}/review", headers=auth_headers)
        
        app.dependency_overrides.clear()
        
        assert response.status_code == 200
        data = response.json()
        
        question = data["questions"][0]
        
        # Optional fields should be present (even if null for some questions)
        optional_fields = ["options", "distractor_explanations", "bloom_level", "difficulty", "concept_name"]
        for field in optional_fields:
            assert field in question, f"Optional field should be present: {field}"

    def test_matching_question_includes_left_right_fields(self, mock_supabase_client, auth_bypass, auth_headers, mocker):
        """
        Test that matching question review details include left and right arrays.
        
        Expected:
        - left and right fields present for matching questions
        - Fields contain string arrays for human-readable answer display
        - Enables frontend to show "OpenAI → Chrome" instead of raw indices "3, 1"
        """
        from dependencies.auth_dependencies import get_current_user_id
        
        submission_id = str(uuid4())
        question_id = str(uuid4())
        
        def mock_user_id_uuid():
            return MOCK_USER_UUID
        
        app.dependency_overrides[get_current_user_id] = mock_user_id_uuid
        
        def mock_get_submission_review(sub_id, user_token=None):
            return {
                "submission_id": submission_id,
                "quiz_id": str(uuid4()),
                "quiz_title": "Matching Quiz",
                "user_id": MOCK_USER_UUID,
                "score": 75,
                "correct_count": 3,
                "wrong_count": 1,
                "total_questions": 4,
                "submitted_at": "2026-01-27T10:00:00Z",
                "questions": [
                    {
                        "question_id": question_id,
                        "question_type": "matching",
                        "question": "Match the companies with their products",
                        "your_answer": [3, 1, 1, 0],  # User's matching indices
                        "correct_answer": [0, 1, 2, 3],  # Correct matching indices
                        "is_correct": False,
                        "explanation": "Match each company to its primary product.",
                        "options": None,
                        "distractor_explanations": None,
                        "bloom_level": "understand",
                        "difficulty": "medium",
                        "concept_name": "Tech Companies",
                        # Matching-specific fields for human-readable display
                        "left": ["OpenAI", "Google", "Microsoft", "Forrester"],
                        "right": ["Atlas", "Chrome", "Edge", "Research"]
                    }
                ]
            }
        
        mocker.patch(
            "handlers.submission_handler.get_review_from_db",
            side_effect=mock_get_submission_review
        )
        
        response = client.get(f"/api/submission/{submission_id}/review", headers=auth_headers)
        
        app.dependency_overrides.clear()
        
        assert response.status_code == 200
        data = response.json()
        
        question = data["questions"][0]
        
        # Verify matching question type
        assert question["question_type"] == "matching", "Question type should be 'matching'"
        
        # Verify left and right fields are present
        assert "left" in question, "Matching question should include 'left' field"
        assert "right" in question, "Matching question should include 'right' field"
        
        # Verify left and right contain the expected arrays
        assert question["left"] == ["OpenAI", "Google", "Microsoft", "Forrester"], \
            "left field should contain item labels"
        assert question["right"] == ["Atlas", "Chrome", "Edge", "Research"], \
            "right field should contain option labels"
        
        # Verify answer indices are present for matching
        assert isinstance(question["your_answer"], list), "your_answer should be a list of indices"
        assert isinstance(question["correct_answer"], list), "correct_answer should be a list of indices"

    def test_non_matching_question_has_null_left_right(self, mock_supabase_client, auth_bypass, auth_headers, mocker):
        """
        Test that non-matching questions have null left and right fields.
        
        Expected:
        - left and right fields are null for multiple_choice, true_false, fill_blank
        """
        from dependencies.auth_dependencies import get_current_user_id
        
        submission_id = str(uuid4())
        
        def mock_user_id_uuid():
            return MOCK_USER_UUID
        
        app.dependency_overrides[get_current_user_id] = mock_user_id_uuid
        
        def mock_get_submission_review(sub_id, user_token=None):
            return {
                "submission_id": submission_id,
                "quiz_id": str(uuid4()),
                "quiz_title": "MCQ Quiz",
                "user_id": MOCK_USER_UUID,
                "score": 100,
                "correct_count": 1,
                "wrong_count": 0,
                "total_questions": 1,
                "submitted_at": "2026-01-27T10:00:00Z",
                "questions": [
                    {
                        "question_id": str(uuid4()),
                        "question_type": "multiple_choice",
                        "question": "What is 2+2?",
                        "your_answer": "4",
                        "correct_answer": "4",
                        "is_correct": True,
                        "explanation": "Basic math",
                        "options": ["3", "4", "5", "6"],
                        "distractor_explanations": None,
                        "bloom_level": None,
                        "difficulty": "easy",
                        "concept_name": None,
                        "left": None,  # Null for non-matching
                        "right": None  # Null for non-matching
                    }
                ]
            }
        
        mocker.patch(
            "handlers.submission_handler.get_review_from_db",
            side_effect=mock_get_submission_review
        )
        
        response = client.get(f"/api/submission/{submission_id}/review", headers=auth_headers)
        
        app.dependency_overrides.clear()
        
        assert response.status_code == 200
        data = response.json()
        
        question = data["questions"][0]
        
        # Verify non-matching question type
        assert question["question_type"] == "multiple_choice"
        
        # Verify left and right are null for non-matching questions
        assert question.get("left") is None, "left should be null for non-matching questions"
        assert question.get("right") is None, "right should be null for non-matching questions"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
