"""
Unit tests for submission scoring logic in submission_handler.

Tests the scoring behavior when questions are skipped:
- Score calculation when some questions are skipped (deleted/invalid)
- total_questions reflects evaluated_count, not original request
- HTTP 500 when no questions can be evaluated
"""

import pytest
from uuid import uuid4
from fastapi import HTTPException
from handlers.submission_handler import submit_quiz
from schemas.submission import QuizSubmissionRequest, AnswerSubmission


class TestSubmitQuizSkippedQuestions:
    """Tests for scoring logic when questions are skipped."""
    
    @pytest.fixture
    def mock_dependencies(self, mocker):
        """Set up common mocks for submission tests."""
        # Mock quiz validation
        mocker.patch(
            "handlers.submission_handler.get_quiz_from_database",
            return_value={"id": str(uuid4()), "title": "Test Quiz"}
        )
        
        # Mock save functions
        mocker.patch("handlers.submission_handler.save_submission", return_value=None)
        mocker.patch("handlers.submission_handler.save_answer", return_value=None)
        mocker.patch("handlers.submission_handler.invalidate_user_submissions_cache", return_value=None)
        mocker.patch("handlers.submission_handler.invalidate_quiz_submissions_cache", return_value=None)
        
        return mocker
    
    @pytest.mark.asyncio
    async def test_score_calculated_from_evaluated_questions_only(self, mock_dependencies):
        """
        Test that score is calculated based on evaluated questions, not total_questions.
        
        When some questions are skipped (not in question_map), the score should be
        calculated as correct / (correct + wrong), not correct / total_questions.
        """
        quiz_id = uuid4()
        q1_id = uuid4()
        q2_id = uuid4()
        q3_id = uuid4()  # This one will be "missing" from question_map
        
        # Mock get_question to return only 2 of 3 questions
        def mock_get_question(question_ids, user_token=None):
            return [
                {
                    "id": str(q1_id),
                    "type": "multiple_choice",
                    "question": "Question 1",
                    "options": ["A", "B", "C", "D"],
                    "correct_answer": "A"
                },
                {
                    "id": str(q2_id),
                    "type": "multiple_choice",
                    "question": "Question 2",
                    "options": ["A", "B", "C", "D"],
                    "correct_answer": "B"
                }
                # q3_id is NOT returned - simulating deleted question
            ]
        
        mock_dependencies.patch(
            "handlers.submission_handler.get_question",
            side_effect=mock_get_question
        )
        
        submission = QuizSubmissionRequest(
            quiz_id=quiz_id,
            total_questions=3,
            answers=[
                AnswerSubmission(question_id=q1_id, user_answer="A"),  # Correct
                AnswerSubmission(question_id=q2_id, user_answer="C"),  # Wrong
                AnswerSubmission(question_id=q3_id, user_answer="X"),  # Skipped (question not found)
            ]
        )
        
        result = await submit_quiz(quiz_id, submission, "12345678-1234-1234-1234-123456789012", "mock_token")
        
        # Score should be 1 correct out of 2 evaluated = 50%
        # NOT 1 correct out of 3 total = 33%
        assert result["score"] == 50, f"Expected score 50 (1/2), got {result['score']}"
        assert result["correct_count"] == 1
        assert result["wrong_count"] == 1
        # total_questions should reflect evaluated count, not original request
        assert result["total_questions"] == 2, f"Expected total_questions=2 (evaluated), got {result['total_questions']}"
    
    @pytest.mark.asyncio
    async def test_all_questions_skipped_returns_500(self, mock_dependencies):
        """
        Test that HTTP 500 is raised when no questions can be evaluated.
        
        This happens when all questions in the submission are missing from the database
        (e.g., all questions were deleted after the quiz was started).
        """
        quiz_id = uuid4()
        q1_id = uuid4()
        q2_id = uuid4()
        
        # Mock get_question to return empty list (no questions found)
        mock_dependencies.patch(
            "handlers.submission_handler.get_question",
            return_value=[]  # No questions returned
        )
        
        # Mock parse_question_models to return empty list
        mock_dependencies.patch(
            "handlers.submission_handler.parse_question_models",
            return_value=[]
        )
        
        submission = QuizSubmissionRequest(
            quiz_id=quiz_id,
            total_questions=2,
            answers=[
                AnswerSubmission(question_id=q1_id, user_answer="A"),
                AnswerSubmission(question_id=q2_id, user_answer="B"),
            ]
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await submit_quiz(quiz_id, submission, "12345678-1234-1234-1234-123456789012", "mock_token")
        
        assert exc_info.value.status_code == 500
        assert "unable to evaluate" in exc_info.value.detail.lower()
    
    @pytest.mark.asyncio
    async def test_partial_questions_skipped_logs_warning(self, mock_dependencies, caplog):
        """
        Test that a warning is logged when some questions are skipped.
        """
        import logging
        
        # Enable log propagation for the 'app' logger to capture with caplog
        app_logger = logging.getLogger('app')
        original_propagate = app_logger.propagate
        app_logger.propagate = True
        
        quiz_id = uuid4()
        q1_id = uuid4()
        q2_id = uuid4()  # Will be missing
        
        # Mock get_question to return only 1 of 2 questions
        def mock_get_question(question_ids, user_token=None):
            return [
                {
                    "id": str(q1_id),
                    "type": "true_false",
                    "question": "Question 1",
                    "options": None,
                    "correct_answer": True
                }
            ]
        
        mock_dependencies.patch(
            "handlers.submission_handler.get_question",
            side_effect=mock_get_question
        )
        
        submission = QuizSubmissionRequest(
            quiz_id=quiz_id,
            total_questions=2,
            answers=[
                AnswerSubmission(question_id=q1_id, user_answer="True"),  # Found
                AnswerSubmission(question_id=q2_id, user_answer="False"),  # Skipped
            ]
        )
        
        with caplog.at_level(logging.WARNING, logger='app'):
            result = await submit_quiz(quiz_id, submission, "12345678-1234-1234-1234-123456789012", "mock_token")
        
        # Restore original propagate setting
        app_logger.propagate = original_propagate
        
        # Verify warning was logged about skipped questions
        assert any("skipped" in record.message.lower() for record in caplog.records), \
            f"Expected warning about skipped questions. Records: {[r.message for r in caplog.records]}"
        
        # Result should still be valid
        assert result["total_questions"] == 1
        assert result["correct_count"] == 1
    
    @pytest.mark.asyncio
    async def test_all_answers_correct_with_skips_scores_100(self, mock_dependencies):
        """
        Test that score is 100% when all evaluated answers are correct,
        even if some questions were skipped.
        """
        quiz_id = uuid4()
        q1_id = uuid4()
        q2_id = uuid4()
        q3_id = uuid4()  # Will be skipped
        
        def mock_get_question(question_ids, user_token=None):
            return [
                {
                    "id": str(q1_id),
                    "type": "multiple_choice",
                    "question": "Question 1",
                    "options": ["A", "B"],
                    "correct_answer": "A"
                },
                {
                    "id": str(q2_id),
                    "type": "multiple_choice",
                    "question": "Question 2",
                    "options": ["X", "Y"],
                    "correct_answer": "Y"
                }
            ]
        
        mock_dependencies.patch(
            "handlers.submission_handler.get_question",
            side_effect=mock_get_question
        )
        
        submission = QuizSubmissionRequest(
            quiz_id=quiz_id,
            total_questions=3,
            answers=[
                AnswerSubmission(question_id=q1_id, user_answer="A"),  # Correct
                AnswerSubmission(question_id=q2_id, user_answer="Y"),  # Correct
                AnswerSubmission(question_id=q3_id, user_answer="Z"),  # Skipped
            ]
        )
        
        result = await submit_quiz(quiz_id, submission, "12345678-1234-1234-1234-123456789012", "mock_token")
        
        # 2 correct out of 2 evaluated = 100%
        assert result["score"] == 100
        assert result["correct_count"] == 2
        assert result["wrong_count"] == 0
        assert result["total_questions"] == 2


class TestSubmitQuizScoreRounding:
    """Tests for score rounding behavior."""
    
    @pytest.fixture
    def mock_dependencies(self, mocker):
        """Set up common mocks for submission tests."""
        mocker.patch(
            "handlers.submission_handler.get_quiz_from_database",
            return_value={"id": str(uuid4()), "title": "Test Quiz"}
        )
        mocker.patch("handlers.submission_handler.save_submission", return_value=None)
        mocker.patch("handlers.submission_handler.save_answer", return_value=None)
        mocker.patch("handlers.submission_handler.invalidate_user_submissions_cache", return_value=None)
        mocker.patch("handlers.submission_handler.invalidate_quiz_submissions_cache", return_value=None)
        return mocker
    
    @pytest.mark.asyncio
    async def test_score_rounds_to_nearest_integer(self, mock_dependencies):
        """
        Test that score is rounded to nearest integer.
        1 correct out of 3 = 33.33...% -> rounds to 33
        """
        quiz_id = uuid4()
        q1_id, q2_id, q3_id = uuid4(), uuid4(), uuid4()
        
        def mock_get_question(question_ids, user_token=None):
            return [
                {"id": str(q1_id), "type": "multiple_choice", "question": "Q1", "options": ["A", "B"], "correct_answer": "A"},
                {"id": str(q2_id), "type": "multiple_choice", "question": "Q2", "options": ["A", "B"], "correct_answer": "A"},
                {"id": str(q3_id), "type": "multiple_choice", "question": "Q3", "options": ["A", "B"], "correct_answer": "A"},
            ]
        
        mock_dependencies.patch("handlers.submission_handler.get_question", side_effect=mock_get_question)
        
        submission = QuizSubmissionRequest(
            quiz_id=quiz_id,
            total_questions=3,
            answers=[
                AnswerSubmission(question_id=q1_id, user_answer="A"),  # Correct
                AnswerSubmission(question_id=q2_id, user_answer="B"),  # Wrong
                AnswerSubmission(question_id=q3_id, user_answer="B"),  # Wrong
            ]
        )
        
        result = await submit_quiz(quiz_id, submission, "12345678-1234-1234-1234-123456789012", "mock_token")
        
        # 1/3 = 33.33...% -> rounds to 33
        assert result["score"] == 33


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
