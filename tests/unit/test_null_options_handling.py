"""
Test that Pydantic validators handle LLM returning null for required list fields.

This is a defensive fix for the issue where GPT sometimes returns {"options": null}
for fill_blank questions despite prompts requiring a list.
"""
from schemas.quiz import (
    FillBlankQuestion,
    MCQQuestion,
    MatchingQuestion,
    Quizzes,
)
from schemas.quizzes_parsed import (
    FillBlankQuestionParsed,
    MCQQuestionParsed,
    MatchingQuestionParsed,
)


class TestQuizSchemaValidators:
    """Test that quiz schemas handle null options gracefully."""
    
    def test_fill_blank_null_options_defaults_to_empty_list(self):
        """FillBlankQuestion should accept null options and default to empty list."""
        data = {
            "type": "fill_blank",
            "question": "The sky is ____",
            "options": None,  # LLM sometimes returns this
            "correct_answer": "blue",
            "explanation": "The sky appears blue",
            "source": "Test",
        }
        question = FillBlankQuestion(**data)
        assert question.options == []
        
    def test_mcq_null_options_defaults_to_empty_list(self):
        """MCQQuestion should accept null options and default to empty list."""
        data = {
            "type": "multiple_choice",
            "question": "What color is the sky?",
            "options": None,
            "correct_answer": "blue",
            "explanation": "The sky appears blue",
            "source": "Test",
        }
        question = MCQQuestion(**data)
        assert question.options == []
        
    def test_matching_null_fields_default_to_empty_list(self):
        """MatchingQuestion should accept null for left, right, correct_answer."""
        data = {
            "type": "matching",
            "question": "Match the items",
            "left": None,
            "right": None,
            "correct_answer": None,
            "explanation": "Match correctly",
            "source": "Test",
        }
        question = MatchingQuestion(**data)
        assert question.left == []
        assert question.right == []
        assert question.correct_answer == []
        
    def test_fill_blank_with_valid_options_unchanged(self):
        """FillBlankQuestion should preserve valid options."""
        data = {
            "type": "fill_blank",
            "question": "The sky is ____",
            "options": ["blue", "red", "green", "yellow"],
            "correct_answer": "blue",
            "explanation": "The sky appears blue",
            "source": "Test",
        }
        question = FillBlankQuestion(**data)
        assert question.options == ["blue", "red", "green", "yellow"]


class TestQuizzesParsedValidators:
    """Test that parsed schemas (for structured output) handle null gracefully."""
    
    def test_fill_blank_parsed_null_options(self):
        """FillBlankQuestionParsed should handle null options."""
        data = {
            "type": "fill_blank",
            "question": "The sky is ____",
            "options": None,
            "correct_answer": "blue",
            "explanation": "The sky appears blue",
            "source": "Test",
        }
        question = FillBlankQuestionParsed(**data)
        assert question.options == []
        
    def test_mcq_parsed_null_options(self):
        """MCQQuestionParsed should handle null options."""
        data = {
            "type": "multiple_choice",
            "question": "What color is the sky?",
            "options": None,
            "correct_answer": "blue",
            "explanation": "The sky appears blue",
            "source": "Test",
        }
        question = MCQQuestionParsed(**data)
        assert question.options == []
        
    def test_matching_parsed_null_fields(self):
        """MatchingQuestionParsed should handle null for left, right, correct_answer."""
        data = {
            "type": "matching",
            "question": "Match the items",
            "left": None,
            "right": None,
            "correct_answer": None,
            "explanation": "Match correctly",
            "source": "Test",
        }
        question = MatchingQuestionParsed(**data)
        assert question.left == []
        assert question.right == []
        assert question.correct_answer == []


class TestQuizzesModelValidateJson:
    """Test that Quizzes.model_validate_json handles null options in JSON."""
    
    def test_fill_blank_json_with_null_options(self):
        """Quizzes.model_validate_json should handle fill_blank with null options."""
        json_str = '''
        {
            "quizzes": [{
                "type": "fill_blank",
                "question": "The sky is ____",
                "options": null,
                "correct_answer": "blue",
                "explanation": "Blue sky",
                "source": "Test"
            }]
        }
        '''
        result = Quizzes.model_validate_json(json_str)
        assert len(result.quizzes) == 1
        assert result.quizzes[0].options == []
        
    def test_mcq_json_with_null_options(self):
        """Quizzes.model_validate_json should handle MCQ with null options."""
        json_str = '''
        {
            "quizzes": [{
                "type": "multiple_choice",
                "question": "What is 2+2?",
                "options": null,
                "correct_answer": "4",
                "explanation": "Math",
                "source": "Test"
            }]
        }
        '''
        result = Quizzes.model_validate_json(json_str)
        assert len(result.quizzes) == 1
        assert result.quizzes[0].options == []
        
    def test_matching_json_with_null_fields(self):
        """Quizzes.model_validate_json should handle matching with null fields."""
        json_str = '''
        {
            "quizzes": [{
                "type": "matching",
                "question": "Match items",
                "left": null,
                "right": null,
                "correct_answer": null,
                "explanation": "Match",
                "source": "Test"
            }]
        }
        '''
        result = Quizzes.model_validate_json(json_str)
        assert len(result.quizzes) == 1
        assert result.quizzes[0].left == []
        assert result.quizzes[0].right == []
        assert result.quizzes[0].correct_answer == []
