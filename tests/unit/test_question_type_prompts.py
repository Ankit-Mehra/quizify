"""
Tests for question-type-specific verification prompts.

This test suite validates that:
1. Fill-in-blank questions use VERIFY_AND_EXPLAIN_FILL_BLANK_PROMPT
2. True/false questions use VERIFY_AND_EXPLAIN_TRUE_FALSE_PROMPT
3. Matching questions use VERIFY_AND_EXPLAIN_MATCHING_PROMPT
4. MCQ questions use VERIFY_AND_EXPLAIN_PROMPT (default)
5. distractor_explanations field is correctly populated for MCQ and fill_blank
6. distractor_explanations is None/empty for true_false and matching
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# Mock out Supabase calls for all tests in this module
@pytest.fixture(autouse=True)
def mock_supabase_for_tests(mocker):
    """Mock Supabase client to prevent database calls during prompt routing tests."""
    # Reset OpenAI client to avoid stale mocks from integration tests
    import services.ai_services.llm_client_service as llm_service
    llm_service._client = None
    llm_service._http_client = None
    
    # Mock get_supabase_service to return None (triggers test mode in track_llm_call)
    mocker.patch("services.db_services.supabase_llm_analytics.get_supabase_service", return_value=None)
    # Mock config to prevent stale module-level state from integration tests
    mocker.patch.object(
        __import__('config', fromlist=['config']).config,
        'get_supabase_client',
        return_value=None
    )
    # Also mock the email cache lookup to return None
    mocker.patch(
        "services.ai_services.llm_client_service._get_user_email_cached",
        return_value=None
    )


class TestFillBlankPromptRouting:
    """Test fill-in-blank questions use correct prompt."""
    
    @pytest.fixture
    def fill_blank_question_data(self):
        """Sample fill-in-blank question."""
        return {
            "type": "fill_blank",
            "question": "At the end of a sprint, the team conducts a _____ to reflect on improvements.",
            "options": ["retrospective", "review", "planning", "standup"],
            "correct_answer": "retrospective"
        }
    
    @pytest.fixture
    def mock_openai_response_with_distractors(self):
        """Mock OpenAI response including distractor_explanations."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '''{
            "is_accurate": true,
            "confidence_score": 0.95,
            "issues": [],
            "explanation": "The term 'retrospective' correctly fills the blank because it refers to the specific Scrum ceremony held at the end of each sprint where the team reflects on their process.",
            "distractor_explanations": {
                "review": "Sprint review focuses on demonstrating completed work to stakeholders, not team process improvement.",
                "planning": "Sprint planning happens at the start of a sprint to plan upcoming work, not at the end.",
                "standup": "Daily standup is a short status meeting during the sprint, not an end-of-sprint reflection."
            }
        }'''
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 150
        mock_response.usage.completion_tokens = 80
        return mock_response
    
    @pytest.mark.asyncio
    async def test_fill_blank_uses_correct_prompt(self, fill_blank_question_data, mock_openai_response_with_distractors):
        """Verify fill_blank questions route to VERIFY_AND_EXPLAIN_FILL_BLANK_PROMPT."""
        # Create mock Groq client (OpenAI-compatible)
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_openai_response_with_distractors)
        
        # Patch BEFORE importing ExplanationService
        with patch('services.ai_services.explanation_service.get_groq_client', return_value=mock_client):
            # Must reimport to get the patched version
            from services.ai_services.explanation_service import ExplanationService
            service = ExplanationService()
            
            is_valid, confidence, issues, explanation, distractor_explanations = await service.verify_and_explain(
                question_data=fill_blank_question_data,
                context="A retrospective is a Scrum ceremony for team improvement.",
                user_id="test-user-123",
                trace_id="test-trace-456"
            )
            
            # Verify the call was made
            mock_client.chat.completions.create.assert_called_once()
            
            # Check the prompt contains fill-blank specific content
            call_args = mock_client.chat.completions.create.call_args
            messages = call_args.kwargs.get("messages", [])
            user_message = next((m for m in messages if m.get("role") == "user"), None)
            
            assert user_message is not None
            prompt_content = user_message.get("content", "")
            
            # Verify fill-blank specific prompt elements
            assert "fill" in prompt_content.lower() or "blank" in prompt_content.lower()
            assert "retrospective" in prompt_content
            assert "options" in prompt_content.lower() or "Options:" in prompt_content
            
            # Verify results
            assert is_valid is True
            assert confidence == 0.95
            assert "retrospective" in explanation.lower()
            
            # Verify distractor_explanations is populated
            assert distractor_explanations is not None
            assert isinstance(distractor_explanations, dict)
            assert "review" in distractor_explanations
            assert "planning" in distractor_explanations
            assert "standup" in distractor_explanations
    
    def test_fill_blank_prompt_has_options_placeholder(self):
        """Verify VERIFY_AND_EXPLAIN_FILL_BLANK_PROMPT includes {options} placeholder."""
        from services.ai_services.explanation_service import VERIFY_AND_EXPLAIN_FILL_BLANK_PROMPT
        
        assert "{options}" in VERIFY_AND_EXPLAIN_FILL_BLANK_PROMPT
        assert "{correct_answer}" in VERIFY_AND_EXPLAIN_FILL_BLANK_PROMPT
        assert "{question}" in VERIFY_AND_EXPLAIN_FILL_BLANK_PROMPT
        assert "{context}" in VERIFY_AND_EXPLAIN_FILL_BLANK_PROMPT


class TestTrueFalsePromptRouting:
    """Test true/false questions use correct prompt."""
    
    @pytest.fixture
    def true_false_question_data(self):
        """Sample true/false question."""
        return {
            "type": "true_false",
            "question": "Scrum requires a dedicated Scrum Master role.",
            "correct_answer": "True"
        }
    
    @pytest.fixture
    def mock_openai_response_no_distractors(self):
        """Mock OpenAI response without distractor_explanations."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '''{
            "is_accurate": true,
            "confidence_score": 0.90,
            "issues": [],
            "explanation": "This statement is TRUE. The Scrum framework explicitly defines the Scrum Master as one of the three core roles."
        }'''
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 40
        return mock_response
    
    @pytest.mark.asyncio
    async def test_true_false_uses_correct_prompt(self, true_false_question_data, mock_openai_response_no_distractors):
        """Verify true_false questions route to VERIFY_AND_EXPLAIN_TRUE_FALSE_PROMPT."""
        # Create mock Groq client (OpenAI-compatible)
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_openai_response_no_distractors)
        
        # Patch at the import location in explanation_service
        with patch('services.ai_services.explanation_service.get_groq_client', return_value=mock_client):
            from services.ai_services.explanation_service import ExplanationService
            service = ExplanationService()
            
            is_valid, confidence, issues, explanation, distractor_explanations = await service.verify_and_explain(
                question_data=true_false_question_data,
                context="Scrum has three roles: Product Owner, Scrum Master, and Development Team.",
                user_id="test-user-123",
                trace_id="test-trace-456"
            )
            
            # Verify the call was made
            mock_client.chat.completions.create.assert_called_once()
            
            # Check the prompt contains true/false specific content
            call_args = mock_client.chat.completions.create.call_args
            messages = call_args.kwargs.get("messages", [])
            user_message = next((m for m in messages if m.get("role") == "user"), None)
            
            assert user_message is not None
            prompt_content = user_message.get("content", "")
            
            # Verify true/false specific prompt elements
            assert "true" in prompt_content.lower() or "false" in prompt_content.lower()
            assert "statement" in prompt_content.lower()
            
            # Verify results
            assert is_valid is True
            assert confidence == 0.90
            assert "true" in explanation.lower() or "false" in explanation.lower()
            
            # Verify distractor_explanations is None or empty (no distractors for true/false)
            assert distractor_explanations is None or distractor_explanations == {} or distractor_explanations == []
    
    def test_true_false_prompt_structure(self):
        """Verify VERIFY_AND_EXPLAIN_TRUE_FALSE_PROMPT has correct placeholders."""
        from services.ai_services.explanation_service import VERIFY_AND_EXPLAIN_TRUE_FALSE_PROMPT
        
        assert "{question}" in VERIFY_AND_EXPLAIN_TRUE_FALSE_PROMPT
        assert "{correct_answer}" in VERIFY_AND_EXPLAIN_TRUE_FALSE_PROMPT
        assert "{context}" in VERIFY_AND_EXPLAIN_TRUE_FALSE_PROMPT
        
        # Should NOT have options or distractor_explanations in the prompt
        # (Those are for MCQ/fill_blank)
        prompt_lower = VERIFY_AND_EXPLAIN_TRUE_FALSE_PROMPT.lower()
        assert "options" not in prompt_lower or "no options" in prompt_lower


class TestDistractorExplanationsField:
    """Test distractor_explanations field behavior across question types."""
    
    @pytest.fixture
    def mock_mcq_response(self):
        """Mock MCQ response with distractor_explanations."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '''{
            "is_accurate": true,
            "confidence_score": 0.95,
            "issues": [],
            "explanation": "The mitochondria produces ATP through cellular respiration.",
            "distractor_explanations": {
                "nucleus": "Controls cell activities but doesn't generate energy.",
                "ribosome": "Synthesizes proteins, not energy.",
                "chloroplast": "Only in plant cells, produces glucose not ATP."
            }
        }'''
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 60
        return mock_response
    
    @pytest.mark.asyncio
    async def test_mcq_returns_distractor_explanations(self, mock_mcq_response):
        """Verify MCQ questions return populated distractor_explanations."""
        mcq_question = {
            "type": "multiple_choice",
            "question": "Which organelle is the powerhouse of the cell?",
            "options": ["mitochondria", "nucleus", "ribosome", "chloroplast"],
            "correct_answer": "mitochondria"
        }
        
        # Create mock Groq client (OpenAI-compatible)
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_mcq_response)
        
        # Patch at the import location in explanation_service
        with patch('services.ai_services.explanation_service.get_groq_client', return_value=mock_client):
            from services.ai_services.explanation_service import ExplanationService
            service = ExplanationService()
            
            is_valid, confidence, issues, explanation, distractor_explanations = await service.verify_and_explain(
                question_data=mcq_question,
                context="Mitochondria produce ATP.",
                user_id="test-user",
                trace_id="test-trace"
            )
            
            # Verify distractor_explanations is populated
            assert distractor_explanations is not None
            assert isinstance(distractor_explanations, dict)
            assert len(distractor_explanations) == 3
            assert "nucleus" in distractor_explanations
            assert "ribosome" in distractor_explanations
            assert "chloroplast" in distractor_explanations
    
    @pytest.mark.asyncio
    async def test_matching_returns_no_distractor_explanations(self):
        """Verify matching questions return None/empty distractor_explanations."""
        from services.ai_services.explanation_service import ExplanationService
        
        matching_question = {
            "type": "matching",
            "question": "Match terms with definitions.",
            "left": ["Term1", "Term2"],
            "right": ["Def1", "Def2"],
            "correct_answer": [0, 1]
        }
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '''{
            "is_accurate": true,
            "confidence_score": 0.90,
            "issues": [],
            "explanation": "The matching pairs are correct."
        }'''
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 80
        mock_response.usage.completion_tokens = 30
        
        service = ExplanationService()
        
        with patch.object(service.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response
            
            is_valid, confidence, issues, explanation, distractor_explanations = await service.verify_and_explain(
                question_data=matching_question,
                context="Some context.",
                user_id="test-user",
                trace_id="test-trace"
            )
            
            # Verify distractor_explanations is None or empty
            assert distractor_explanations is None or distractor_explanations == {} or distractor_explanations == []


class TestQuestionBaseSchema:
    """Test QuestionBase schema handles distractor_explanations correctly."""
    
    def test_schema_accepts_distractor_explanations(self):
        """Verify QuestionBase schema accepts distractor_explanations field."""
        from schemas.quiz import QuestionBase
        import uuid
        
        # Should not raise validation error
        question = QuestionBase(
            id=str(uuid.uuid4()),
            type="multiple_choice",
            question="Test question?",
            correct_answer="A",
            bloom_level="Remember",
            difficulty="easy",
            explanation="Test explanation",
            distractor_explanations={"B": "Wrong because X", "C": "Wrong because Y"}
        )
        
        assert question.distractor_explanations is not None
        assert len(question.distractor_explanations) == 2
    
    def test_schema_accepts_none_distractor_explanations(self):
        """Verify QuestionBase schema accepts None for distractor_explanations."""
        from schemas.quiz import QuestionBase
        import uuid
        
        # Should not raise validation error
        question = QuestionBase(
            id=str(uuid.uuid4()),
            type="true_false",
            question="Test question?",
            correct_answer="True",
            bloom_level="Remember",
            difficulty="easy",
            explanation="Test explanation",
            distractor_explanations=None
        )
        
        assert question.distractor_explanations is None
    
    def test_schema_accepts_missing_distractor_explanations(self):
        """Verify QuestionBase schema works without distractor_explanations (backward compat)."""
        from schemas.quiz import QuestionBase
        import uuid
        
        # Should not raise validation error - field is optional
        question = QuestionBase(
            id=str(uuid.uuid4()),
            type="matching",
            question="Test question?",
            correct_answer=[0, 1],
            bloom_level="Apply",
            difficulty="medium",
            explanation="Test explanation"
            # distractor_explanations intentionally omitted
        )
        
        assert question.distractor_explanations is None
