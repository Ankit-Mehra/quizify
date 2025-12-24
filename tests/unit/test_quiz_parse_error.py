"""
Unit tests for QuizParseError handling in openai_service.

Tests cover:
1. Invalid JSON response handling (malformed JSON)
2. Valid JSON but incorrect schema handling (missing required fields)
3. Empty response handling
4. The specific error message returned to users
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.ai_services.llm_client_service import (
    generate_quiz_async,
    QuizParseError
)


class TestQuizParseError:
    """Tests for QuizParseError exception class."""
    
    def test_quiz_parse_error_creation(self):
        """Test QuizParseError can be created with message."""
        error = QuizParseError(message="Test error message")
        assert error.message == "Test error message"
        assert error.raw_response is None
        assert str(error) == "Test error message"
    
    def test_quiz_parse_error_with_raw_response(self):
        """Test QuizParseError stores raw response for debugging."""
        error = QuizParseError(
            message="Parse failed",
            raw_response='{"invalid": "json"}'
        )
        assert error.message == "Parse failed"
        assert error.raw_response == '{"invalid": "json"}'
    
    def test_quiz_parse_error_is_exception(self):
        """Test QuizParseError is a proper Exception subclass."""
        error = QuizParseError(message="Test")
        assert isinstance(error, Exception)
        
        # Should be raiseable
        with pytest.raises(QuizParseError) as exc_info:
            raise error
        assert exc_info.value.message == "Test"


class TestGenerateQuizAsyncErrorHandling:
    """Tests for error handling in generate_quiz_async."""
    
    @pytest.fixture
    def mock_openai_response(self):
        """Create a mock OpenAI response."""
        def _create_response(content):
            response = MagicMock()
            choice = MagicMock()
            message = MagicMock()
            message.content = content
            choice.message = message
            response.choices = [choice]
            return response
        return _create_response
    
    @pytest.mark.asyncio
    async def test_empty_response_returns_empty_list(self, mock_openai_response):
        """Test that empty content returns empty list without raising."""
        with patch('services.ai_services.llm_client_service.get_openai_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                return_value=mock_openai_response("")
            )
            mock_get_client.return_value = mock_client
            
            result = await generate_quiz_async(
                text="Some test content",
                num_questions=5,
                question_types=["multiple_choice"]
            )
            
            assert result == []
    
    @pytest.mark.asyncio
    async def test_none_response_returns_empty_list(self, mock_openai_response):
        """Test that None content returns empty list without raising."""
        with patch('services.ai_services.llm_client_service.get_openai_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                return_value=mock_openai_response(None)
            )
            mock_get_client.return_value = mock_client
            
            result = await generate_quiz_async(
                text="Some test content",
                num_questions=5,
                question_types=["multiple_choice"]
            )
            
            assert result == []
    
    @pytest.mark.asyncio
    async def test_malformed_json_raises_quiz_parse_error(self, mock_openai_response):
        """Test that malformed JSON raises QuizParseError."""
        malformed_json = "{ this is not valid json }"
        
        with patch('services.ai_services.llm_client_service.get_openai_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                return_value=mock_openai_response(malformed_json)
            )
            mock_get_client.return_value = mock_client
            
            with pytest.raises(QuizParseError) as exc_info:
                await generate_quiz_async(
                    text="Some test content",
                    num_questions=5,
                    question_types=["multiple_choice"]
                )
            
            assert "Failed to parse AI-generated quiz" in exc_info.value.message
            # Should include truncated raw response for debugging
            assert exc_info.value.raw_response is not None
    
    @pytest.mark.asyncio
    async def test_valid_json_missing_required_fields_raises_error(self, mock_openai_response):
        """Test that valid JSON with missing required fields raises QuizParseError."""
        # Valid JSON but missing 'quizzes' field required by QuizzesParsed
        invalid_schema_json = '{"wrong_field": "value"}'
        
        with patch('services.ai_services.llm_client_service.get_openai_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                return_value=mock_openai_response(invalid_schema_json)
            )
            mock_get_client.return_value = mock_client
            
            with pytest.raises(QuizParseError) as exc_info:
                await generate_quiz_async(
                    text="Some test content",
                    num_questions=5,
                    question_types=["multiple_choice"]
                )
            
            assert "Failed to parse AI-generated quiz" in exc_info.value.message
    
    @pytest.mark.asyncio
    async def test_user_friendly_error_message(self, mock_openai_response):
        """Test that error message is user-friendly (no technical details)."""
        malformed_json = "not json at all"
        
        with patch('services.ai_services.llm_client_service.get_openai_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                return_value=mock_openai_response(malformed_json)
            )
            mock_get_client.return_value = mock_client
            
            with pytest.raises(QuizParseError) as exc_info:
                await generate_quiz_async(
                    text="Some test content",
                    num_questions=5,
                    question_types=["multiple_choice"]
                )
            
            # Message should be user-friendly
            assert "Failed to parse AI-generated quiz" in exc_info.value.message
            assert "Please try again" in exc_info.value.message
            # Should NOT contain technical Pydantic error details
            assert "ValidationError" not in exc_info.value.message
    
    @pytest.mark.asyncio
    async def test_backtick_stripping_case_insensitive(self, mock_openai_response):
        """Test that markdown code blocks are stripped case-insensitively."""
        # This tests the case-insensitive backtick handling
        # Even with correct JSON wrapped in uppercase markers, should work
        valid_quiz_json = '''```JSON
{"quizzes": []}
```'''
        
        with patch('services.ai_services.llm_client_service.get_openai_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                return_value=mock_openai_response(valid_quiz_json)
            )
            mock_get_client.return_value = mock_client
            
            # Should not raise - the backticks should be stripped
            result = await generate_quiz_async(
                text="Some test content",
                num_questions=5,
                question_types=["multiple_choice"]
            )
            
            # Empty quizzes returns empty list
            assert result == []
