"""
Integration tests for URL-based quiz generation.
Tests tier checking, quota enforcement, and end-to-end flow with mocked scraping.
"""
import pytest
from unittest.mock import patch, AsyncMock
from fastapi import HTTPException
from handlers.quiz_handlers import generate_quiz_from_url
from schemas.quiz import WebQuizRequest


class TestGenerateQuizFromUrl:
    """Integration tests for generate_quiz_from_url handler."""
    
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.get_user_tier_info')
    async def test_free_tier_user_rejected(self, mock_get_tier_info):
        """Test that free tier users are rejected with 403."""
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'email': 'free@example.com',
            'account_tier': 'free',
            'current_quiz_count': 2,
            'quota_limit': 5,
            'quota_exceeded': False
        }
        
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
        
        assert exc_info.value.status_code == 403
        detail = exc_info.value.detail
        assert detail['user_tier'] == 'free'
        assert detail['required_tier'] == 'basic'
        assert 'premium feature' in detail['detail'].lower()
    
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.save_metadata')
    @patch('handlers.quiz_handlers.save_quiz_to_database')
    @patch('handlers.quiz_handlers.generate_quizzes_single_async')
    @patch('handlers.quiz_handlers.scrape_content')
    @patch('handlers.quiz_handlers.validate_user_quota')
    @patch('handlers.quiz_handlers.get_user_tier_info')
    async def test_basic_tier_user_success(
        self, mock_get_tier_info, mock_validate_quota, 
        mock_scrape, mock_generate, mock_save_quiz, mock_save_metadata
    ):
        """Test that basic tier users can generate quizzes from URLs."""
        # Mock tier info
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'email': 'basic@example.com',
            'account_tier': 'basic',
            'current_quiz_count': 10,
            'quota_limit': 100,
            'quota_exceeded': False
        }
        
        # Mock scraping
        mock_scrape.return_value = "This is a long article about machine learning with many interesting concepts that would make great quiz questions. Machine learning is a subset of artificial intelligence."
        
        # Mock quiz generation
        mock_question = type('MockQuestion', (), {
            'type': 'multiple_choice',
            'question': 'What is machine learning?',
            'options': ['AI subset', 'Database', 'Network', 'OS'],
            'correct_answer': 'AI subset',
            'explanation': 'ML is a subset of AI',
            'source': 'content'
        })()
        mock_generate.return_value = [mock_question]
        
        # Mock database save
        mock_save_quiz.return_value = 'quiz-id-123'
        
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
        
        assert result['quiz_id'] == 'quiz-id-123'
        assert result['title'] == 'ML Quiz'
        assert result['message'] == 'Quiz generated successfully from URL'
        assert result['source_url'] == 'https://example.com/article'
        
        # Verify calls
        mock_validate_quota.assert_called_once_with('test-user-id')
        mock_scrape.assert_called_once()
        mock_generate.assert_called_once()
        mock_save_quiz.assert_called_once()
        mock_save_metadata.assert_called_once()
        
        # Verify metadata includes URL info
        metadata_call = mock_save_metadata.call_args[0][0]
        assert metadata_call['content_source_type'] == 'url'
        assert metadata_call['content_source_reference'] == 'https://example.com/article'
    
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.save_metadata')
    @patch('handlers.quiz_handlers.save_quiz_to_database')
    @patch('handlers.quiz_handlers.generate_quizzes_single_async')
    @patch('handlers.quiz_handlers.scrape_content')
    @patch('handlers.quiz_handlers.validate_user_quota')
    @patch('handlers.quiz_handlers.get_user_tier_info')
    async def test_educator_tier_user_success(
        self, mock_get_tier_info, mock_validate_quota, 
        mock_scrape, mock_generate, mock_save_quiz, mock_save_metadata
    ):
        """Test that educator tier users can generate quizzes from URLs."""
        # Mock tier info
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'email': 'educator@example.com',
            'account_tier': 'educator',
            'current_quiz_count': 50,
            'quota_limit': 500,
            'quota_exceeded': False
        }
        
        # Mock scraping
        mock_scrape.return_value = "Educational content about photosynthesis and how plants convert light energy into chemical energy."
        
        # Mock quiz generation
        mock_question = type('MockQuestion', (), {
            'type': 'true_false',
            'question': 'Plants use photosynthesis?',
            'correct_answer': True,
            'explanation': 'Yes, plants convert light to chemical energy',
            'source': 'content'
        })()
        mock_generate.return_value = [mock_question]
        
        # Mock database save
        mock_save_quiz.return_value = 'quiz-id-456'
        
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
        
        assert result['quiz_id'] == 'quiz-id-456'
        assert result['title'] == 'Photosynthesis Quiz'
        assert 'successfully' in result['message'].lower()
    
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.validate_user_quota')
    @patch('handlers.quiz_handlers.get_user_tier_info')
    async def test_basic_tier_quota_exceeded(self, mock_get_tier_info, mock_validate_quota):
        """Test that quota enforcement still applies to basic tier users."""
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'email': 'basic@example.com',
            'account_tier': 'basic',
            'current_quiz_count': 100,
            'quota_limit': 100,
            'quota_exceeded': True
        }
        
        # Mock quota validation to raise exception
        mock_validate_quota.side_effect = HTTPException(
            status_code=403,
            detail={
                "detail": "Quiz quota exceeded for basic tier (100/100).",
                "current_count": 100,
                "quota_limit": 100,
                "user_tier": "basic"
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
        
        assert exc_info.value.status_code == 403
        detail = exc_info.value.detail
        assert detail['quota_limit'] == 100
        assert detail['current_count'] == 100
    
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.scrape_content')
    @patch('handlers.quiz_handlers.validate_user_quota')
    @patch('handlers.quiz_handlers.get_user_tier_info')
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
    @patch('handlers.quiz_handlers.validate_user_quota')
    @patch('handlers.quiz_handlers.get_user_tier_info')
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
    @patch('handlers.quiz_handlers.validate_user_quota')
    @patch('handlers.quiz_handlers.get_user_tier_info')
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
