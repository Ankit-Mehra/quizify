"""
Test question structure validation in orchestration service.

The _validate_question_structure method catches malformed LLM responses
BEFORE expensive verification calls, saving tokens and improving error messages.
"""
import pytest
from services.ai_services.orchestration_service import QuizOrchestrationService


class TestQuestionStructureValidation:
    """Test the pre-validation of LLM responses."""
    
    @pytest.fixture
    def service(self):
        """Create orchestration service instance."""
        return QuizOrchestrationService()
    
    # === Multiple Choice ===
    
    def test_mcq_valid_structure(self, service):
        """Valid MCQ should pass validation."""
        result = {
            "question": "What is 2+2?",
            "options": ["A) 3", "B) 4", "C) 5", "D) 6"],
            "correct_answer": "B"
        }
        # Should not raise
        service._validate_question_structure(result, "multiple_choice")
    
    def test_mcq_missing_options(self, service):
        """MCQ with missing options should fail."""
        result = {
            "question": "What is 2+2?",
            "options": None,
            "correct_answer": "B"
        }
        with pytest.raises(ValueError, match="MCQ requires at least 2 options"):
            service._validate_question_structure(result, "multiple_choice")
    
    def test_mcq_empty_options(self, service):
        """MCQ with empty options should fail."""
        result = {
            "question": "What is 2+2?",
            "options": [],
            "correct_answer": "B"
        }
        with pytest.raises(ValueError, match="MCQ requires at least 2 options"):
            service._validate_question_structure(result, "multiple_choice")
    
    def test_mcq_one_option(self, service):
        """MCQ with only one option should fail."""
        result = {
            "question": "What is 2+2?",
            "options": ["A) 4"],
            "correct_answer": "A"
        }
        with pytest.raises(ValueError, match="MCQ requires at least 2 options"):
            service._validate_question_structure(result, "multiple_choice")
    
    def test_mcq_missing_correct_answer(self, service):
        """MCQ with missing correct_answer should fail."""
        result = {
            "question": "What is 2+2?",
            "options": ["A) 3", "B) 4"],
            "correct_answer": None
        }
        with pytest.raises(ValueError, match="MCQ correct_answer is missing"):
            service._validate_question_structure(result, "multiple_choice")
    
    # === Fill Blank ===
    
    def test_fill_blank_valid_structure(self, service):
        """Valid fill_blank should pass validation."""
        result = {
            "question": "The sky is _____.",
            "options": ["blue", "red", "green", "yellow"],
            "correct_answer": "blue"
        }
        service._validate_question_structure(result, "fill_blank")
    
    def test_fill_blank_missing_options(self, service):
        """Fill_blank with missing options should fail."""
        result = {
            "question": "The sky is _____.",
            "options": None,
            "correct_answer": "blue"
        }
        with pytest.raises(ValueError, match="Fill-blank requires options"):
            service._validate_question_structure(result, "fill_blank")
    
    def test_fill_blank_missing_correct_answer(self, service):
        """Fill_blank with missing correct_answer should fail."""
        result = {
            "question": "The sky is _____.",
            "options": ["blue", "red"],
            "correct_answer": None
        }
        with pytest.raises(ValueError, match="Fill-blank correct_answer is missing"):
            service._validate_question_structure(result, "fill_blank")
    
    # === Matching ===
    
    def test_matching_valid_structure(self, service):
        """Valid matching should pass validation."""
        result = {
            "question": "Match the capitals to countries",
            "left": ["France", "Germany", "Italy", "Spain"],
            "right": ["Paris", "Berlin", "Rome", "Madrid"],
            "correct_answer": [0, 1, 2, 3]
        }
        service._validate_question_structure(result, "matching")
    
    def test_matching_missing_left(self, service):
        """Matching with missing left should fail."""
        result = {
            "question": "Match the items",
            "left": None,
            "right": ["A", "B", "C", "D"],
            "correct_answer": [0, 1, 2, 3]
        }
        with pytest.raises(ValueError, match="requires 'left' list"):
            service._validate_question_structure(result, "matching")
    
    def test_matching_empty_left(self, service):
        """Matching with empty left should fail."""
        result = {
            "question": "Match the items",
            "left": [],
            "right": ["A", "B", "C", "D"],
            "correct_answer": [0, 1, 2, 3]
        }
        with pytest.raises(ValueError, match="requires 'left' list"):
            service._validate_question_structure(result, "matching")
    
    def test_matching_missing_right(self, service):
        """Matching with missing right should fail."""
        result = {
            "question": "Match the items",
            "left": ["A", "B", "C", "D"],
            "right": None,
            "correct_answer": [0, 1, 2, 3]
        }
        with pytest.raises(ValueError, match="requires 'right' list"):
            service._validate_question_structure(result, "matching")
    
    def test_matching_empty_right(self, service):
        """Matching with empty right should fail."""
        result = {
            "question": "Match the items",
            "left": ["A", "B", "C", "D"],
            "right": [],
            "correct_answer": [0, 1, 2, 3]
        }
        with pytest.raises(ValueError, match="requires 'right' list"):
            service._validate_question_structure(result, "matching")
    
    def test_matching_mismatched_lengths(self, service):
        """Matching with different left/right lengths should fail."""
        result = {
            "question": "Match the items",
            "left": ["A", "B", "C"],
            "right": ["X", "Y"],
            "correct_answer": [0, 1, 2]
        }
        with pytest.raises(ValueError, match="must have same length"):
            service._validate_question_structure(result, "matching")
    
    def test_matching_missing_correct_answer(self, service):
        """Matching with missing correct_answer should fail."""
        result = {
            "question": "Match the items",
            "left": ["A", "B", "C", "D"],
            "right": ["W", "X", "Y", "Z"],
            "correct_answer": None
        }
        with pytest.raises(ValueError, match="must be a list of indices"):
            service._validate_question_structure(result, "matching")
    
    def test_matching_wrong_correct_answer_type(self, service):
        """Matching with non-list correct_answer should fail."""
        result = {
            "question": "Match the items",
            "left": ["A", "B", "C", "D"],
            "right": ["W", "X", "Y", "Z"],
            "correct_answer": "0,1,2,3"  # String instead of list
        }
        with pytest.raises(ValueError, match="must be a list of indices"):
            service._validate_question_structure(result, "matching")
    
    def test_matching_wrong_correct_answer_length(self, service):
        """Matching with wrong correct_answer length should fail."""
        result = {
            "question": "Match the items",
            "left": ["A", "B", "C", "D"],
            "right": ["W", "X", "Y", "Z"],
            "correct_answer": [0, 1, 2]  # Only 3 indices for 4 items
        }
        with pytest.raises(ValueError, match="must match items"):
            service._validate_question_structure(result, "matching")
    
    # === True/False ===
    
    def test_true_false_valid_structure(self, service):
        """Valid true_false should pass validation."""
        result = {
            "question": "The sky is blue.",
            "correct_answer": True
        }
        service._validate_question_structure(result, "true_false")
    
    def test_true_false_false_answer(self, service):
        """True_false with False answer should pass."""
        result = {
            "question": "The sky is green.",
            "correct_answer": False
        }
        service._validate_question_structure(result, "true_false")
    
    def test_true_false_missing_correct_answer(self, service):
        """True_false with missing correct_answer should fail."""
        result = {
            "question": "The sky is blue.",
            "correct_answer": None
        }
        with pytest.raises(ValueError, match="correct_answer is missing"):
            service._validate_question_structure(result, "true_false")
    
    # === General ===
    
    def test_missing_question_text(self, service):
        """Any question type with missing question text should fail."""
        result = {
            "question": "",
            "options": ["A", "B", "C", "D"],
            "correct_answer": "A"
        }
        with pytest.raises(ValueError, match="Question text is missing"):
            service._validate_question_structure(result, "multiple_choice")
    
    def test_none_question_text(self, service):
        """Any question type with None question text should fail."""
        result = {
            "question": None,
            "options": ["A", "B", "C", "D"],
            "correct_answer": "A"
        }
        with pytest.raises(ValueError, match="Question text is missing"):
            service._validate_question_structure(result, "multiple_choice")
