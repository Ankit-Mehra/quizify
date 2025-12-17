"""
Integration tests for URL-based quiz generation.
Tests quota enforcement and end-to-end flow with mocked scraping.
Available for all tiers with quota limits.
"""
import pytest
from unittest.mock import patch
from fastapi import HTTPException
from handlers.quiz_handlers import generate_quiz_from_url
from schemas.quiz import WebQuizRequest


class TestGenerateQuizFromUrl:
    """Integration tests for generate_quiz_from_url handler."""
    
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.save_metadata')
    @patch('handlers.quiz_handlers.save_quiz_to_database')
    @patch('handlers.quiz_handlers.generate_quizzes_single_async')
    @patch('handlers.quiz_handlers.scrape_content')
    @patch('handlers.quiz_handlers.validate_credits_available')
    @patch('handlers.quiz_handlers.get_user_tier_info_cached')
    async def test_free_tier_user_success(
        self,
        mock_get_tier_info,
        mock_validate_quota,
        mock_scrape,
        mock_generate,
        mock_save_quiz,
        mock_save_metadata,
    ):
        """Test that free tier users CAN generate quizzes from URLs (within quota)."""
        # Mock tier info
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'email': 'free@example.com',
            'account_tier': 'free',
            'current_quiz_count': 2,
            'quota_limit': 5,
            'quizzes_attempted': 2,
            'quota_exceeded': False
        }
        
        # Mock scraping
        mock_scrape.return_value = (
            "This is a long article about machine learning with many interesting concepts that would make great quiz questions. Machine learning is a subset of artificial intelligence.",
            None,
        )
        
        # Mock quiz generation
        mock_question = {
            'type': 'multiple_choice',
            'question': 'What is machine learning?',
            'options': ['AI subset', 'Database', 'Network', 'OS'],
            'correct_answer': 'AI subset',
            'explanation': 'ML is a subset of AI',
            'source': 'content'
        }
        mock_generate.return_value = [mock_question]
        
        # Mock database save - returns (quiz_id, saved_questions) tuple
        mock_save_quiz.return_value = ('quiz-id-123', [mock_question])
        
        request = WebQuizRequest(
            url="https://example.com/article",
            title="ML Quiz",
            num_questions=5,
            question_type=["multiple_choice"]
        )
        
        result = await generate_quiz_from_url(
            data=request,
            current_user_id='test-user-id',
            user_token='test-token'
        )
        
        # Result is now EnhancedQuizGenerationResponse object
        assert result.quiz_id == 'quiz-id-123'
        assert result.title == 'ML Quiz'
        assert 'Quiz generated successfully from URL' in result.message  # Message includes mode info
        assert result.source_url == 'https://example.com/article'
        
        # Verify calls - quota validated at both URL handler and unified generator level
        assert mock_validate_quota.call_count >= 1  # Called at least once
        mock_scrape.assert_called_once()
        mock_generate.assert_called_once()
        mock_save_quiz.assert_called_once()
        mock_save_metadata.assert_called_once()
        
        # Verify save_quiz_to_database was called with URL source info (stored in quizzes table, NOT metadata)
        quiz_call = mock_save_quiz.call_args
        assert quiz_call.kwargs['content_source_type'] == 'url'
        assert quiz_call.kwargs['content_source_reference'] == 'https://example.com/article'
    
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.save_metadata')
    @patch('handlers.quiz_handlers.save_quiz_to_database')
    @patch('handlers.quiz_handlers.generate_quizzes_single_async')
    @patch('handlers.quiz_handlers.scrape_content')
    @patch('handlers.quiz_handlers.validate_credits_available')
    @patch('handlers.quiz_handlers.get_user_tier_info_cached')
    async def test_basic_tier_user_success(
        self,
        mock_get_tier_info,
        mock_validate_quota,
        mock_scrape,
        mock_generate,
        mock_save_quiz,
        mock_save_metadata,
    ):
        """Test that basic tier users can generate quizzes from URLs."""
        # Mock tier info
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'email': 'basic@example.com',
            'account_tier': 'basic',
            'current_quiz_count': 10,
            'quota_limit': 100,
            'quizzes_attempted': 25,
            'quota_exceeded': False
        }
        
        # Mock scraping
        mock_scrape.return_value = (
            "This is a long article about machine learning with many interesting concepts that would make great quiz questions. Machine learning is a subset of artificial intelligence.",
            None,
        )
        
        # Mock quiz generation
        mock_question = {
            'type': 'multiple_choice',
            'question': 'What is machine learning?',
            'options': ['AI subset', 'Database', 'Network', 'OS'],
            'correct_answer': 'AI subset',
            'explanation': 'ML is a subset of AI',
            'source': 'content'
        }
        mock_generate.return_value = [mock_question]
        
        # Mock database save - returns (quiz_id, saved_questions) tuple
        mock_save_quiz.return_value = ('quiz-id-123', [mock_question])
        
        request = WebQuizRequest(
            url="https://example.com/article",
            title="ML Quiz",
            num_questions=5,
            question_type=["multiple_choice"]
        )
        
        result = await generate_quiz_from_url(
            data=request,
            current_user_id='test-user-id',
            user_token='test-token'
        )
        
        # Result is now EnhancedQuizGenerationResponse object
        assert result.quiz_id == 'quiz-id-123'
        assert result.title == 'ML Quiz'
        assert 'Quiz generated successfully from URL' in result.message  # Message includes mode info
        assert result.source_url == 'https://example.com/article'

        # Verify calls - quota validated at both URL handler and unified generator level
        assert mock_validate_quota.call_count >= 1  # Called at least once
        mock_scrape.assert_called_once()
        mock_generate.assert_called_once()
        mock_save_quiz.assert_called_once()
        mock_save_metadata.assert_called_once()
        
        # Verify save_quiz_to_database was called with URL source info (stored in quizzes table, NOT metadata)
        quiz_call = mock_save_quiz.call_args
        assert quiz_call.kwargs['content_source_type'] == 'url'
        assert quiz_call.kwargs['content_source_reference'] == 'https://example.com/article'
    
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.save_metadata')
    @patch('handlers.quiz_handlers.save_quiz_to_database')
    @patch('handlers.quiz_handlers.generate_quizzes_single_async')
    @patch('handlers.quiz_handlers.scrape_content')
    @patch('handlers.quiz_handlers.validate_credits_available')
    @patch('handlers.quiz_handlers.get_user_tier_info_cached')
    async def test_pro_tier_user_success(
        self, mock_get_tier_info, mock_validate_quota, 
        mock_scrape, mock_generate, mock_save_quiz, mock_save_metadata
    ):
        """Test that pro tier users can generate quizzes from URLs."""
        # Mock tier info
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'email': 'pro@example.com',
            'account_tier': 'pro',
            'current_quiz_count': 50,
            'quota_limit': 999999,
            'quizzes_attempted': 200,
            'quota_exceeded': False
        }
        
        # Mock scraping
        mock_scrape.return_value = (
            "Educational content about photosynthesis and how plants convert light energy into chemical energy.",
            None,
        )
        
        # Mock quiz generation
        mock_question = {
            'type': 'true_false',
            'question': 'Plants use photosynthesis?',
            'correct_answer': True,
            'explanation': 'Yes, plants convert light to chemical energy',
            'source': 'content'
        }
        mock_generate.return_value = [mock_question]
        
        # Mock database save - returns (quiz_id, saved_questions) tuple
        mock_save_quiz.return_value = ('quiz-id-456', [mock_question])
        
        request = WebQuizRequest(
            url="https://en.wikipedia.org/wiki/Photosynthesis",
            title="Photosynthesis Quiz",
            num_questions=8,
            question_type=["true_false", "multiple_choice"]
        )
        
        result = await generate_quiz_from_url(
            data=request,
            current_user_id='test-user-id',
            user_token='test-token'
        )
        
        # Result is now EnhancedQuizGenerationResponse object
        assert result.quiz_id == 'quiz-id-456'
        assert result.title == 'Photosynthesis Quiz'
        assert 'successfully' in result.message.lower()
    
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.validate_credits_available')
    @patch('handlers.quiz_handlers.get_user_tier_info_cached')
    async def test_free_tier_quota_exceeded(self, mock_get_tier_info, mock_validate_quota):
        """Test that quota enforcement applies to free tier users (5 quiz limit)."""
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'email': 'free@example.com',
            'account_tier': 'free',
            'current_quiz_count': 5,
            'quota_limit': 5,
            'quizzes_attempted': 5,
            'quota_exceeded': True
        }
        
        # Mock credit validation to raise exception (402 Payment Required)
        mock_validate_quota.side_effect = HTTPException(
            status_code=402,
            detail={
                "error": "insufficient_credits",
                "message": "Not enough credits. Upgrade to Pro or buy more credits.",
                "available_credits": 0,
                "required_credits": 0.5,
                "plan": "free"
            }
        )
        
        request = WebQuizRequest(
            url="https://example.com/article",
            title="Test Quiz",
            num_questions=5,
            question_type=["multiple_choice"]
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await generate_quiz_from_url(
                data=request,
                current_user_id='test-user-id',
                user_token='test-token'
            )

        assert exc_info.value.status_code == 402
        # Credit enforcement blocks before any processing
        mock_validate_quota.assert_called_once_with('test-user-id', request.mode)

    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.validate_credits_available')
    @patch('handlers.quiz_handlers.get_user_tier_info_cached')
    async def test_basic_tier_quota_exceeded(self, mock_get_tier_info, mock_validate_quota):
        """Test that quota enforcement still applies to basic tier users."""
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'email': 'basic@example.com',
            'account_tier': 'basic',
            'current_quiz_count': 100,
            'quota_limit': 100,
            'quizzes_attempted': 120,
            'quota_exceeded': True
        }
        
        # Mock credit validation to raise exception (402 Payment Required)
        mock_validate_quota.side_effect = HTTPException(
            status_code=402,
            detail={
                "error": "insufficient_credits",
                "message": "Not enough credits. Upgrade to Pro or buy more credits.",
                "available_credits": 0,
                "required_credits": 0.5,
                "plan": "pro"
            }
        )
        
        request = WebQuizRequest(
            url="https://example.com/article",
            title="Test Quiz",
            num_questions=5,
            question_type=["multiple_choice"]
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await generate_quiz_from_url(
                data=request,
                current_user_id='test-user-id',
                user_token='test-token'
            )
        
        assert exc_info.value.status_code == 402
    
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.scrape_content')
    @patch('handlers.quiz_handlers.validate_credits_available')
    @patch('handlers.quiz_handlers.get_user_tier_info_cached')
    async def test_invalid_url_rejected(
        self, mock_get_tier_info, mock_validate_quota, mock_scrape
    ):
        """Test that invalid URLs are rejected during scraping."""
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'email': 'basic@example.com',
            'account_tier': 'basic',
            'current_quiz_count': 10,
            'quota_limit': 100,
            'quizzes_attempted': 15,
            'quota_exceeded': False
        }
        
        # Mock scraping to raise validation error
        mock_scrape.side_effect = HTTPException(
            status_code=400,
            detail="Cannot scrape localhost URLs."
        )
        
        request = WebQuizRequest(
            url="http://localhost/data",
            title="Test Quiz",
            num_questions=5,
            question_type=["multiple_choice"]
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await generate_quiz_from_url(
                data=request,
                current_user_id='test-user-id',
                user_token='test-token'
            )
        
        assert exc_info.value.status_code == 400
        assert "localhost" in exc_info.value.detail.lower()
    
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.scrape_content')
    @patch('handlers.quiz_handlers.validate_credits_available')
    @patch('handlers.quiz_handlers.get_user_tier_info_cached')
    async def test_scraping_timeout_handled(
        self, mock_get_tier_info, mock_validate_quota, mock_scrape
    ):
        """Test that scraping timeouts are handled gracefully."""
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'email': 'basic@example.com',
            'account_tier': 'basic',
            'current_quiz_count': 10,
            'quota_limit': 100,
            'quizzes_attempted': 15,
            'quota_exceeded': False
        }
        
        # Mock scraping to raise timeout error
        mock_scrape.side_effect = HTTPException(
            status_code=408,
            detail="Request timeout. The page took longer than 30 seconds to load."
        )
        
        request = WebQuizRequest(
            url="https://slow-site.com/article",
            title="Test Quiz",
            num_questions=5,
            question_type=["multiple_choice"]
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await generate_quiz_from_url(
                data=request,
                current_user_id='test-user-id',
                user_token='test-token'
            )
        
        assert exc_info.value.status_code == 408
        assert "timeout" in exc_info.value.detail.lower()
    
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.scrape_content')
    @patch('handlers.quiz_handlers.validate_credits_available')
    @patch('handlers.quiz_handlers.get_user_tier_info_cached')
    async def test_insufficient_content_handled(
        self, mock_get_tier_info, mock_validate_quota, mock_scrape
    ):
        """Test that insufficient content extraction is handled."""
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'email': 'basic@example.com',
            'account_tier': 'basic',
            'current_quiz_count': 10,
            'quota_limit': 100,
            'quizzes_attempted': 15,
            'quota_exceeded': False
        }
        
        # Mock scraping to raise content too short error
        mock_scrape.side_effect = HTTPException(
            status_code=422,
            detail="Extracted content too short (minimum 100 characters)."
        )
        
        request = WebQuizRequest(
            url="https://example.com/short-page",
            title="Test Quiz",
            num_questions=5,
            question_type=["multiple_choice"]
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await generate_quiz_from_url(
                data=request,
                current_user_id='test-user-id',
                user_token='test-token'
            )
        
        assert exc_info.value.status_code == 422
        assert "too short" in exc_info.value.detail.lower()
