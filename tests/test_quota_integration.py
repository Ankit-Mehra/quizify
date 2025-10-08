"""
Integration tests for quota enforcement in quiz generation endpoints.
Tests both /api/quiz/generate/text and /api/quiz/generate/file endpoints.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import HTTPException
from fastapi.testclient import TestClient
from handlers.quiz_handlers import generate_quiz_from_text, generate_quiz_from_file_openai
from schemas.quiz import TextQuizRequest
import io


class TestQuotaEnforcementTextEndpoint:
    """Integration tests for quota enforcement on text generation endpoint."""
    
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.get_user_tier_info')
    @patch('handlers.quiz_handlers.generate_quizzes_single_async')
    @patch('handlers.quiz_handlers.save_quiz_to_database')
    @patch('handlers.quiz_handlers.save_file_to_supabase')
    @patch('handlers.quiz_handlers.save_metadata')
    async def test_text_endpoint_free_tier_under_limit_success(
        self, mock_save_metadata, mock_save_file, mock_save_quiz, 
        mock_generate, mock_get_tier_info
    ):
        """Test text endpoint allows quiz generation for free tier user under limit."""
        # Setup mocks
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'account_tier': 'free',
            'current_quiz_count': 3,
            'quota_limit': 5,
            'quota_exceeded': False
        }
        
        mock_question = MagicMock()
        mock_question.type = "multiple_choice"
        mock_question.question = "Test question?"
        mock_question.options = ["A", "B", "C", "D"]
        mock_question.correct_answer = "A"
        mock_question.explanation = "Test explanation"
        mock_question.source = "Test source"
        mock_generate.return_value = [mock_question]
        mock_save_quiz.return_value = "quiz-123"
        
        # Create request
        request_data = TextQuizRequest(
            title="Test Quiz",
            content="This is test content for generating a quiz about Python programming.",
            num_questions=5,
            question_type=["multiple_choice"]
        )
        
        # Call handler
        result = await generate_quiz_from_text(
            data=request_data,
            current_user_id='test-user-id',
            user_token='test-token'
        )
        
        # Assertions
        assert result['quiz_id'] == 'quiz-123'
        assert 'Quiz generated successfully' in result['message']
        mock_generate.assert_called_once()
        mock_save_quiz.assert_called_once()
        
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.get_user_tier_info')
    async def test_text_endpoint_free_tier_at_limit_forbidden(self, mock_get_tier_info):
        """Test text endpoint returns 403 for free tier user at limit."""
        # Setup mock
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'account_tier': 'free',
            'current_quiz_count': 5,
            'quota_limit': 5,
            'quota_exceeded': True
        }
        
        # Create request
        request_data = TextQuizRequest(
            title="Test Quiz",
            content="This is test content for generating a quiz.",
            num_questions=5,
            question_type=["multiple_choice"]
        )
        
        # Call handler and expect exception
        with pytest.raises(HTTPException) as exc_info:
            await generate_quiz_from_text(
                data=request_data,
                current_user_id='test-user-id',
                user_token='test-token'
            )
        
        # Assertions
        assert exc_info.value.status_code == 403
        detail = exc_info.value.detail
        assert detail['current_count'] == 5
        assert detail['quota_limit'] == 5
        assert detail['user_tier'] == 'free'
        assert 'Upgrade to basic' in detail['detail']
        
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.get_user_tier_info')
    async def test_text_endpoint_basic_tier_at_limit_forbidden(self, mock_get_tier_info):
        """Test text endpoint returns 403 for basic tier user at limit."""
        # Setup mock
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'account_tier': 'basic',
            'current_quiz_count': 100,
            'quota_limit': 100,
            'quota_exceeded': True
        }
        
        # Create request
        request_data = TextQuizRequest(
            title="Test Quiz",
            content="This is test content for generating a quiz.",
            num_questions=5,
            question_type=["multiple_choice"]
        )
        
        # Call handler and expect exception
        with pytest.raises(HTTPException) as exc_info:
            await generate_quiz_from_text(
                data=request_data,
                current_user_id='test-user-id',
                user_token='test-token'
            )
        
        # Assertions
        assert exc_info.value.status_code == 403
        detail = exc_info.value.detail
        assert detail['current_count'] == 100
        assert detail['quota_limit'] == 100
        assert detail['user_tier'] == 'basic'
        assert 'Upgrade to educator' in detail['detail']
        
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.get_user_tier_info')
    @patch('handlers.quiz_handlers.generate_quizzes_single_async')
    @patch('handlers.quiz_handlers.save_quiz_to_database')
    @patch('handlers.quiz_handlers.save_file_to_supabase')
    @patch('handlers.quiz_handlers.save_metadata')
    async def test_text_endpoint_educator_tier_under_limit_success(
        self, mock_save_metadata, mock_save_file, mock_save_quiz,
        mock_generate, mock_get_tier_info
    ):
        """Test text endpoint allows quiz generation for educator tier user under limit."""
        # Setup mocks
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'account_tier': 'educator',
            'current_quiz_count': 450,
            'quota_limit': 500,
            'quota_exceeded': False
        }
        
        mock_question = MagicMock()
        mock_question.type = "multiple_choice"
        mock_question.question = "Test question?"
        mock_question.options = ["A", "B", "C", "D"]
        mock_question.correct_answer = "A"
        mock_question.explanation = "Test explanation"
        mock_question.source = "Test source"
        mock_generate.return_value = [mock_question]
        mock_save_quiz.return_value = "quiz-456"
        
        # Create request
        request_data = TextQuizRequest(
            title="Test Quiz",
            content="This is test content for generating a quiz about advanced topics.",
            num_questions=10,
            question_type=["multiple_choice"]
        )
        
        # Call handler
        result = await generate_quiz_from_text(
            data=request_data,
            current_user_id='test-user-id',
            user_token='test-token'
        )
        
        # Assertions
        assert result['quiz_id'] == 'quiz-456'
        assert 'Quiz generated successfully' in result['message']
        mock_generate.assert_called_once()
        mock_save_quiz.assert_called_once()


class TestQuotaEnforcementFileEndpoint:
    """Integration tests for quota enforcement on file generation endpoint."""
    
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.get_user_tier_info')
    @patch('handlers.quiz_handlers.extract_text_from_plain_text')
    @patch('handlers.quiz_handlers.generate_quizzes_single_async')
    @patch('handlers.quiz_handlers.save_quiz_to_database')
    @patch('handlers.quiz_handlers.save_metadata')
    @patch('handlers.quiz_handlers.save_file_to_supabase')
    async def test_file_endpoint_free_tier_under_limit_success(
        self, mock_save_file, mock_save_metadata, mock_save_quiz,
        mock_generate, mock_extract, mock_get_tier_info
    ):
        """Test file endpoint allows quiz generation for free tier user under limit."""
        # Setup mocks
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'account_tier': 'free',
            'current_quiz_count': 2,
            'quota_limit': 5,
            'quota_exceeded': False
        }
        
        mock_extract.return_value = "This is extracted text from the file with enough content to generate quizzes."
        
        mock_question = MagicMock()
        mock_question.type = "multiple_choice"
        mock_question.question = "Test question?"
        mock_question.options = ["A", "B", "C", "D"]
        mock_question.correct_answer = "A"
        mock_question.explanation = "Test explanation"
        mock_question.source = "Test source"
        mock_generate.return_value = [mock_question]
        mock_save_quiz.return_value = "quiz-789"
        
        # Create mock file
        file_content = b"Test file content for quiz generation"
        mock_file = MagicMock()
        mock_file.filename = "test.txt"
        mock_file.content_type = "text/plain"
        mock_file.read = AsyncMock(return_value=file_content)
        mock_file.seek = AsyncMock()
        
        # Call handler
        result = await generate_quiz_from_file_openai(
            file=mock_file,
            title="Test File Quiz",
            num_questions=5,
            question_type=["multiple_choice"],
            current_user_id='test-user-id',
            user_token='test-token'
        )
        
        # Assertions
        assert result['quiz_id'] == 'quiz-789'
        assert 'Quiz generated successfully' in result['message']
        mock_generate.assert_called_once()
        mock_save_quiz.assert_called_once()
        
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.get_user_tier_info')
    async def test_file_endpoint_free_tier_at_limit_forbidden(self, mock_get_tier_info):
        """Test file endpoint returns 403 for free tier user at limit."""
        # Setup mock
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'account_tier': 'free',
            'current_quiz_count': 5,
            'quota_limit': 5,
            'quota_exceeded': True
        }
        
        # Create mock file
        file_content = b"Test file content"
        mock_file = MagicMock()
        mock_file.filename = "test.txt"
        mock_file.content_type = "text/plain"
        mock_file.read = AsyncMock(return_value=file_content)
        
        # Call handler and expect exception
        with pytest.raises(HTTPException) as exc_info:
            await generate_quiz_from_file_openai(
                file=mock_file,
                title="Test File Quiz",
                num_questions=5,
                question_type=["multiple_choice"],
                current_user_id='test-user-id',
                user_token='test-token'
            )
        
        # Assertions
        assert exc_info.value.status_code == 403
        detail = exc_info.value.detail
        assert detail['current_count'] == 5
        assert detail['quota_limit'] == 5
        assert detail['user_tier'] == 'free'
        
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.get_user_tier_info')
    async def test_file_endpoint_basic_tier_at_limit_forbidden(self, mock_get_tier_info):
        """Test file endpoint returns 403 for basic tier user at limit."""
        # Setup mock
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'account_tier': 'basic',
            'current_quiz_count': 100,
            'quota_limit': 100,
            'quota_exceeded': True
        }
        
        # Create mock file
        file_content = b"Test file content"
        mock_file = MagicMock()
        mock_file.filename = "test.txt"
        mock_file.content_type = "text/plain"
        mock_file.read = AsyncMock(return_value=file_content)
        
        # Call handler and expect exception
        with pytest.raises(HTTPException) as exc_info:
            await generate_quiz_from_file_openai(
                file=mock_file,
                title="Test File Quiz",
                num_questions=5,
                question_type=["multiple_choice"],
                current_user_id='test-user-id',
                user_token='test-token'
            )
        
        # Assertions
        assert exc_info.value.status_code == 403
        detail = exc_info.value.detail
        assert detail['current_count'] == 100
        assert detail['quota_limit'] == 100
        assert detail['user_tier'] == 'basic'


class TestQuotaCheckBeforeGeneration:
    """Tests to verify quota check happens before AI generation."""
    
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.get_user_tier_info')
    @patch('handlers.quiz_handlers.generate_quizzes_single_async')
    async def test_text_endpoint_quota_check_before_ai_call(
        self, mock_generate, mock_get_tier_info
    ):
        """Test that quota check happens before AI generation for text endpoint."""
        # Setup mock to indicate quota exceeded
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'account_tier': 'free',
            'current_quiz_count': 5,
            'quota_limit': 5,
            'quota_exceeded': True
        }
        
        # Create request
        request_data = TextQuizRequest(
            title="Test Quiz",
            content="This is test content for generating a quiz.",
            num_questions=5,
            question_type=["multiple_choice"]
        )
        
        # Call handler and expect exception
        with pytest.raises(HTTPException) as exc_info:
            await generate_quiz_from_text(
                data=request_data,
                current_user_id='test-user-id',
                user_token='test-token'
            )
        
        # Verify quota check failed with 403
        assert exc_info.value.status_code == 403
        
        # Verify AI generation was NOT called (no API waste)
        mock_generate.assert_not_called()
        
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.get_user_tier_info')
    @patch('handlers.quiz_handlers.extract_text_from_plain_text')
    @patch('handlers.quiz_handlers.generate_quizzes_single_async')
    async def test_file_endpoint_quota_check_before_ai_call(
        self, mock_generate, mock_extract, mock_get_tier_info
    ):
        """Test that quota check happens before AI generation for file endpoint."""
        # Setup mock to indicate quota exceeded
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'account_tier': 'basic',
            'current_quiz_count': 100,
            'quota_limit': 100,
            'quota_exceeded': True
        }
        
        # Create mock file
        file_content = b"Test file content"
        mock_file = MagicMock()
        mock_file.filename = "test.txt"
        mock_file.content_type = "text/plain"
        mock_file.read = AsyncMock(return_value=file_content)
        
        # Call handler and expect exception
        with pytest.raises(HTTPException) as exc_info:
            await generate_quiz_from_file_openai(
                file=mock_file,
                title="Test File Quiz",
                num_questions=5,
                question_type=["multiple_choice"],
                current_user_id='test-user-id',
                user_token='test-token'
            )
        
        # Verify quota check failed with 403
        assert exc_info.value.status_code == 403
        
        # Verify file extraction was NOT called (no processing waste)
        mock_extract.assert_not_called()
        
        # Verify AI generation was NOT called (no API waste)
        mock_generate.assert_not_called()
