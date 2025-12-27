"""
Unit tests for QuizParseError handling in llm_client_service.

Tests cover:
1. Invalid JSON response handling (malformed JSON)
2. Valid JSON but incorrect schema handling (missing required fields)
3. Empty response handling
4. The specific error message returned to users
"""

import pytest
from unittest.mock import AsyncMock, patch

from services.ai_services.llm_client_service import (
    generate_quiz_async,
    QuizParseError
)
from services.llm import LLMGenerationResponse


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
    def mock_llm_response(self):
        """Create a mock LLM provider response."""
        def _create_response(content):
            return LLMGenerationResponse(
                content=content,
                model="gpt-4o-mini",
                usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
            )
        return _create_response
    
    def _create_mock_provider(self, response):
        """Create a mock LLM provider with the given response."""
        mock_provider = AsyncMock()
        mock_provider.provider_name = "openai"
        mock_provider.default_model = "gpt-4o-mini"
        mock_provider.generate = AsyncMock(return_value=response)
        return mock_provider
    
    @pytest.mark.asyncio
    async def test_empty_response_returns_empty_list(self, mock_llm_response):
        """Test that empty content returns empty list without raising."""
        with patch('services.llm.get_llm_provider') as mock_get_provider:
            mock_get_provider.return_value = self._create_mock_provider(mock_llm_response(""))
            
            result = await generate_quiz_async(
                text="Some test content",
                num_questions=5,
                question_types=["multiple_choice"]
            )
            
            assert result == []
    
    @pytest.mark.asyncio
    async def test_none_response_returns_empty_list(self, mock_llm_response):
        """Test that None content returns empty list without raising."""
        with patch('services.llm.get_llm_provider') as mock_get_provider:
            mock_get_provider.return_value = self._create_mock_provider(mock_llm_response(None))
            
            result = await generate_quiz_async(
                text="Some test content",
                num_questions=5,
                question_types=["multiple_choice"]
            )
            
            assert result == []
    
    @pytest.mark.asyncio
    async def test_malformed_json_raises_quiz_parse_error(self, mock_llm_response):
        """Test that malformed JSON raises QuizParseError."""
        malformed_json = "{ this is not valid json }"
        
        with patch('services.llm.get_llm_provider') as mock_get_provider:
            mock_get_provider.return_value = self._create_mock_provider(mock_llm_response(malformed_json))
            
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
    async def test_valid_json_missing_required_fields_raises_error(self, mock_llm_response):
        """Test that valid JSON with missing required fields raises QuizParseError."""
        # Valid JSON but missing 'quizzes' field required by QuizzesParsed
        invalid_schema_json = '{"wrong_field": "value"}'
        
        with patch('services.llm.get_llm_provider') as mock_get_provider:
            mock_get_provider.return_value = self._create_mock_provider(mock_llm_response(invalid_schema_json))
            
            with pytest.raises(QuizParseError) as exc_info:
                await generate_quiz_async(
                    text="Some test content",
                    num_questions=5,
                    question_types=["multiple_choice"]
                )
            
            assert "Failed to parse AI-generated quiz" in exc_info.value.message
    
    @pytest.mark.asyncio
    async def test_user_friendly_error_message(self, mock_llm_response):
        """Test that error message is user-friendly (no technical details)."""
        malformed_json = "not json at all"
        
        with patch('services.llm.get_llm_provider') as mock_get_provider:
            mock_get_provider.return_value = self._create_mock_provider(mock_llm_response(malformed_json))
            
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
    async def test_backtick_stripping_case_insensitive(self, mock_llm_response):
        """Test that markdown code blocks are stripped case-insensitively."""
        # This tests the case-insensitive backtick handling
        # Even with correct JSON wrapped in uppercase markers, should work
        valid_quiz_json = '''```JSON
{"quizzes": []}
```'''
        
        with patch('services.llm.get_llm_provider') as mock_get_provider:
            mock_get_provider.return_value = self._create_mock_provider(mock_llm_response(valid_quiz_json))
            
            # Should not raise - the backticks should be stripped
            result = await generate_quiz_async(
                text="Some test content",
                num_questions=5,
                question_types=["multiple_choice"]
            )
            
            # Empty quizzes returns empty list
            assert result == []
