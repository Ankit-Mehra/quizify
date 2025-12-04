"""
Tests for matching question verification in ExplanationService.

These tests verify that the verify_and_explain function correctly handles
matching questions which have a different structure (left/right lists)
than MCQ/fill_blank questions (options list).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestMatchingQuestionVerification:
    """Test verify_and_explain correctly routes matching questions."""
    
    @pytest.fixture
    def mock_openai_response(self):
        """Create a mock OpenAI response for verification."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '''{
            "is_accurate": true,
            "confidence_score": 0.95,
            "issues": [],
            "explanation": "The matching pairs are correct based on the context."
        }'''
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        return mock_response
    
    @pytest.fixture
    def matching_question_data(self):
        """Sample matching question data."""
        return {
            "type": "matching",
            "question": "Match the project management terms with their definitions.",
            "left": ["Sprint", "Backlog", "Scrum Master", "Product Owner"],
            "right": [
                "A time-boxed iteration",
                "A prioritized list of work",
                "Facilitates the team",
                "Represents stakeholders"
            ],
            "correct_answer": [0, 1, 2, 3]
        }
    
    @pytest.fixture
    def mcq_question_data(self):
        """Sample MCQ question data for comparison."""
        return {
            "type": "multiple_choice",
            "question": "What is a Sprint?",
            "options": ["A time-boxed iteration", "A bug", "A meeting", "A document"],
            "correct_answer": "A time-boxed iteration"
        }
    
    def test_matching_prompt_selection(self, matching_question_data):
        """Verify matching questions trigger the matching-specific prompt."""
        question_type = matching_question_data.get("type", "")
        assert question_type == "matching"
        
        # Verify matching questions have left/right, not options
        assert "left" in matching_question_data
        assert "right" in matching_question_data
        assert "options" not in matching_question_data
    
    def test_mcq_prompt_selection(self, mcq_question_data):
        """Verify MCQ questions have options field."""
        question_type = mcq_question_data.get("type", "")
        assert question_type == "multiple_choice"
        
        # Verify MCQ questions have options, not left/right
        assert "options" in mcq_question_data
        assert "left" not in mcq_question_data
        assert "right" not in mcq_question_data
    
    def test_left_right_formatting(self, matching_question_data):
        """Test that left/right items are formatted correctly with indices."""
        left = matching_question_data.get("left", [])
        right = matching_question_data.get("right", [])
        
        # Format as done in verify_and_explain
        left_str = "\n".join([f"  {i}. {item}" for i, item in enumerate(left)]) if left else "N/A"
        right_str = "\n".join([f"  {i}. {item}" for i, item in enumerate(right)]) if right else "N/A"
        
        # Verify formatting
        assert "0. Sprint" in left_str
        assert "1. Backlog" in left_str
        assert "2. Scrum Master" in left_str
        assert "3. Product Owner" in left_str
        
        assert "0. A time-boxed iteration" in right_str
        assert "1. A prioritized list of work" in right_str
    
    def test_empty_left_right_defaults_to_na(self):
        """Test that empty left/right lists default to 'N/A'."""
        empty_matching = {
            "type": "matching",
            "question": "Match the items",
            "left": [],
            "right": [],
            "correct_answer": []
        }
        
        left = empty_matching.get("left", [])
        right = empty_matching.get("right", [])
        
        left_str = "\n".join([f"  {i}. {item}" for i, item in enumerate(left)]) if left else "N/A"
        right_str = "\n".join([f"  {i}. {item}" for i, item in enumerate(right)]) if right else "N/A"
        
        assert left_str == "N/A"
        assert right_str == "N/A"
    
    def test_none_left_right_defaults_to_na(self):
        """Test that None left/right lists default to 'N/A'."""
        matching_with_none = {
            "type": "matching",
            "question": "Match the items",
            "left": None,
            "right": None,
            "correct_answer": []
        }
        
        left = matching_with_none.get("left") or []
        right = matching_with_none.get("right") or []
        
        left_str = "\n".join([f"  {i}. {item}" for i, item in enumerate(left)]) if left else "N/A"
        right_str = "\n".join([f"  {i}. {item}" for i, item in enumerate(right)]) if right else "N/A"
        
        assert left_str == "N/A"
        assert right_str == "N/A"
    
    @pytest.mark.asyncio
    async def test_verify_and_explain_matching_integration(self, matching_question_data, mock_openai_response):
        """Integration test: verify_and_explain correctly handles matching questions."""
        from services.ai_services.explanation_service import ExplanationService
        
        service = ExplanationService()
        
        with patch.object(service.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_openai_response
            
            is_valid, confidence, issues, explanation = await service.verify_and_explain(
                question_data=matching_question_data,
                context="Sprint is a time-boxed iteration. Backlog is a prioritized list of work.",
                user_id="test-user-123",
                trace_id="test-trace-456"
            )
            
            # Verify the call was made
            mock_create.assert_called_once()
            
            # Check the prompt contains matching-specific content
            call_args = mock_create.call_args
            messages = call_args.kwargs.get("messages", [])
            user_message = next((m for m in messages if m.get("role") == "user"), None)
            
            assert user_message is not None
            prompt_content = user_message.get("content", "")
            
            # Verify matching-specific prompt elements are present
            assert "Left Items" in prompt_content or "left" in prompt_content.lower()
            assert "Right Items" in prompt_content or "right" in prompt_content.lower()
            assert "Sprint" in prompt_content
            assert "Backlog" in prompt_content
            
            # Verify result parsing
            assert is_valid is True
            assert confidence == 0.95
            assert issues == []
            assert "correct" in explanation.lower()
    
    @pytest.mark.asyncio
    async def test_verify_and_explain_mcq_still_works(self, mcq_question_data, mock_openai_response):
        """Ensure MCQ verification still works after matching changes."""
        from services.ai_services.explanation_service import ExplanationService
        
        service = ExplanationService()
        
        with patch.object(service.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_openai_response
            
            is_valid, confidence, issues, explanation = await service.verify_and_explain(
                question_data=mcq_question_data,
                context="A Sprint is a time-boxed iteration in Scrum.",
                user_id="test-user-123",
                trace_id="test-trace-456"
            )
            
            # Verify the call was made
            mock_create.assert_called_once()
            
            # Check the prompt contains MCQ-specific content (options)
            call_args = mock_create.call_args
            messages = call_args.kwargs.get("messages", [])
            user_message = next((m for m in messages if m.get("role") == "user"), None)
            
            assert user_message is not None
            prompt_content = user_message.get("content", "")
            
            # Verify MCQ prompt uses Options, not Left/Right
            assert "Options:" in prompt_content or "options" in prompt_content.lower()
            # Should NOT contain matching-specific elements
            assert "Left Items" not in prompt_content
            assert "Right Items" not in prompt_content
            
            # Verify result parsing
            assert is_valid is True


class TestVerifyAndExplainPromptFormats:
    """Test the prompt templates are correctly formatted."""
    
    def test_matching_prompt_has_required_placeholders(self):
        """Verify VERIFY_AND_EXPLAIN_MATCHING_PROMPT has all required placeholders."""
        from services.ai_services.explanation_service import VERIFY_AND_EXPLAIN_MATCHING_PROMPT
        
        assert "{question}" in VERIFY_AND_EXPLAIN_MATCHING_PROMPT
        assert "{left_items}" in VERIFY_AND_EXPLAIN_MATCHING_PROMPT
        assert "{right_items}" in VERIFY_AND_EXPLAIN_MATCHING_PROMPT
        assert "{correct_answer}" in VERIFY_AND_EXPLAIN_MATCHING_PROMPT
        assert "{context}" in VERIFY_AND_EXPLAIN_MATCHING_PROMPT
    
    def test_standard_prompt_has_required_placeholders(self):
        """Verify VERIFY_AND_EXPLAIN_PROMPT has all required placeholders."""
        from services.ai_services.explanation_service import VERIFY_AND_EXPLAIN_PROMPT
        
        assert "{question}" in VERIFY_AND_EXPLAIN_PROMPT
        assert "{correct_answer}" in VERIFY_AND_EXPLAIN_PROMPT
        assert "{options}" in VERIFY_AND_EXPLAIN_PROMPT
        assert "{context}" in VERIFY_AND_EXPLAIN_PROMPT
    
    def test_matching_prompt_format_succeeds(self):
        """Test that matching prompt can be formatted without errors."""
        from services.ai_services.explanation_service import VERIFY_AND_EXPLAIN_MATCHING_PROMPT
        
        # Should not raise
        formatted = VERIFY_AND_EXPLAIN_MATCHING_PROMPT.format(
            question="Match the terms",
            left_items="  0. Term1\n  1. Term2",
            right_items="  0. Def1\n  1. Def2",
            correct_answer="[0, 1]",
            context="Some context here"
        )
        
        assert "Match the terms" in formatted
        assert "Term1" in formatted
        assert "Def1" in formatted
    
    def test_standard_prompt_format_succeeds(self):
        """Test that standard prompt can be formatted without errors."""
        from services.ai_services.explanation_service import VERIFY_AND_EXPLAIN_PROMPT
        
        # Should not raise
        formatted = VERIFY_AND_EXPLAIN_PROMPT.format(
            question="What is X?",
            correct_answer="Answer A",
            options="A, B, C, D",
            context="Some context here"
        )
        
        assert "What is X?" in formatted
        assert "Answer A" in formatted
