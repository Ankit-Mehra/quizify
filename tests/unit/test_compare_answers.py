"""
Unit tests for the compare_answers function in submission_handler.

Tests type-specific answer comparison:
- Matching questions with JSON/list inputs (including malformed JSON)
- True/false answers as strings and booleans
- Multiple choice/fill blank with varied casing and whitespace
"""

import pytest
from handlers.submission_handler import compare_answers


class TestCompareAnswersMatching:
    """Tests for matching question type comparison."""
    
    def test_matching_json_string_to_list(self):
        """Test matching with JSON string user answer and list correct answer."""
        user_answer = "[1, 0, 3, 2]"
        correct_answer = [1, 0, 3, 2]
        
        result = compare_answers(user_answer, correct_answer, "matching")
        
        assert result is True
    
    def test_matching_list_to_list(self):
        """Test matching with both answers as lists."""
        user_answer = [1, 0, 3, 2]
        correct_answer = [1, 0, 3, 2]
        
        result = compare_answers(user_answer, correct_answer, "matching")
        
        assert result is True
    
    def test_matching_json_string_to_json_string(self):
        """Test matching with both answers as JSON strings."""
        user_answer = "[1, 0, 3, 2]"
        correct_answer = "[1, 0, 3, 2]"
        
        result = compare_answers(user_answer, correct_answer, "matching")
        
        assert result is True
    
    def test_matching_wrong_order(self):
        """Test matching with incorrect order returns False."""
        user_answer = [0, 1, 3, 2]  # Wrong order
        correct_answer = [1, 0, 3, 2]
        
        result = compare_answers(user_answer, correct_answer, "matching")
        
        assert result is False
    
    def test_matching_json_with_spaces(self):
        """Test matching with JSON string containing extra spaces."""
        user_answer = "[ 1 , 0 , 3 , 2 ]"
        correct_answer = [1, 0, 3, 2]
        
        result = compare_answers(user_answer, correct_answer, "matching")
        
        assert result is True
    
    def test_matching_comma_separated_string(self):
        """Test matching with comma-separated string format."""
        user_answer = "1,0,3,2"
        correct_answer = [1, 0, 3, 2]
        
        result = compare_answers(user_answer, correct_answer, "matching")
        
        assert result is True
    
    def test_matching_comma_separated_with_spaces(self):
        """Test matching with comma-separated format and spaces."""
        user_answer = "1, 0, 3, 2"
        correct_answer = [1, 0, 3, 2]
        
        result = compare_answers(user_answer, correct_answer, "matching")
        
        assert result is True
    
    def test_matching_malformed_json_returns_false(self):
        """Test matching with malformed JSON returns False (not error)."""
        user_answer = "[1, 0, 3, 2"  # Missing closing bracket
        correct_answer = [1, 0, 3, 2]
        
        # Should try comma parsing which will also fail due to brackets
        result = compare_answers(user_answer, correct_answer, "matching")
        
        # Should return False, not raise exception
        assert result is False
    
    def test_matching_non_integer_string_returns_false(self):
        """Test matching with non-integer values returns False."""
        user_answer = "a, b, c, d"
        correct_answer = [1, 0, 3, 2]
        
        result = compare_answers(user_answer, correct_answer, "matching")
        
        assert result is False
    
    def test_matching_empty_list(self):
        """Test matching with empty lists."""
        user_answer = []
        correct_answer = []
        
        result = compare_answers(user_answer, correct_answer, "matching")
        
        assert result is True
    
    def test_matching_different_lengths(self):
        """Test matching with different length lists."""
        user_answer = [1, 0, 3]
        correct_answer = [1, 0, 3, 2]
        
        result = compare_answers(user_answer, correct_answer, "matching")
        
        assert result is False
    
    def test_matching_string_integers_in_list(self):
        """Test matching with string integers in list."""
        user_answer = ["1", "0", "3", "2"]  # Strings that represent integers
        correct_answer = [1, 0, 3, 2]
        
        result = compare_answers(user_answer, correct_answer, "matching")
        
        assert result is True


class TestCompareAnswersTrueFalse:
    """Tests for true/false question type comparison."""
    
    def test_true_false_both_true_booleans(self):
        """Test true/false with both as True booleans."""
        result = compare_answers(True, True, "true_false")
        assert result is True
    
    def test_true_false_both_false_booleans(self):
        """Test true/false with both as False booleans."""
        result = compare_answers(False, False, "true_false")
        assert result is True
    
    def test_true_false_boolean_mismatch(self):
        """Test true/false with mismatched booleans."""
        result = compare_answers(True, False, "true_false")
        assert result is False
    
    def test_true_false_string_true_to_boolean_true(self):
        """Test true/false with 'True' string and True boolean."""
        result = compare_answers("True", True, "true_false")
        assert result is True
    
    def test_true_false_string_true_lowercase(self):
        """Test true/false with lowercase 'true' string."""
        result = compare_answers("true", True, "true_false")
        assert result is True
    
    def test_true_false_string_true_uppercase(self):
        """Test true/false with uppercase 'TRUE' string."""
        result = compare_answers("TRUE", True, "true_false")
        assert result is True
    
    def test_true_false_string_false_to_boolean_false(self):
        """Test true/false with 'False' string and False boolean."""
        result = compare_answers("False", False, "true_false")
        assert result is True
    
    def test_true_false_string_false_lowercase(self):
        """Test true/false with lowercase 'false' string."""
        result = compare_answers("false", False, "true_false")
        assert result is True
    
    def test_true_false_both_strings(self):
        """Test true/false with both as strings."""
        assert compare_answers("True", "True", "true_false") is True
        assert compare_answers("False", "False", "true_false") is True
        assert compare_answers("true", "false", "true_false") is False
    
    def test_true_false_string_with_whitespace(self):
        """Test true/false with whitespace around string."""
        result = compare_answers("  True  ", True, "true_false")
        assert result is True
    
    def test_true_false_mixed_case_both_sides(self):
        """Test true/false with mixed case on both sides."""
        result = compare_answers("TrUe", "TRUE", "true_false")
        assert result is True


class TestCompareAnswersMultipleChoice:
    """Tests for multiple choice question type comparison."""
    
    def test_multiple_choice_exact_match(self):
        """Test multiple choice with exact match."""
        result = compare_answers("Paris", "Paris", "multiple_choice")
        assert result is True
    
    def test_multiple_choice_case_insensitive(self):
        """Test multiple choice is case-insensitive."""
        result = compare_answers("paris", "Paris", "multiple_choice")
        assert result is True
    
    def test_multiple_choice_all_uppercase(self):
        """Test multiple choice with all uppercase answer."""
        result = compare_answers("PARIS", "Paris", "multiple_choice")
        assert result is True
    
    def test_multiple_choice_with_leading_whitespace(self):
        """Test multiple choice with leading whitespace."""
        result = compare_answers("  Paris", "Paris", "multiple_choice")
        assert result is True
    
    def test_multiple_choice_with_trailing_whitespace(self):
        """Test multiple choice with trailing whitespace."""
        result = compare_answers("Paris  ", "Paris", "multiple_choice")
        assert result is True
    
    def test_multiple_choice_with_both_whitespace(self):
        """Test multiple choice with whitespace on both sides."""
        result = compare_answers("  Paris  ", "  Paris  ", "multiple_choice")
        assert result is True
    
    def test_multiple_choice_wrong_answer(self):
        """Test multiple choice with wrong answer."""
        result = compare_answers("London", "Paris", "multiple_choice")
        assert result is False
    
    def test_multiple_choice_with_special_characters(self):
        """Test multiple choice with special characters."""
        result = compare_answers("Option A (correct)", "Option A (correct)", "multiple_choice")
        assert result is True


class TestCompareAnswersFillBlank:
    """Tests for fill-in-the-blank question type comparison."""
    
    def test_fill_blank_exact_match(self):
        """Test fill blank with exact match."""
        result = compare_answers("photosynthesis", "photosynthesis", "fill_blank")
        assert result is True
    
    def test_fill_blank_case_insensitive(self):
        """Test fill blank is case-insensitive."""
        result = compare_answers("Photosynthesis", "photosynthesis", "fill_blank")
        assert result is True
    
    def test_fill_blank_with_whitespace(self):
        """Test fill blank with extra whitespace."""
        result = compare_answers("  photosynthesis  ", "photosynthesis", "fill_blank")
        assert result is True
    
    def test_fill_blank_wrong_answer(self):
        """Test fill blank with wrong answer."""
        result = compare_answers("respiration", "photosynthesis", "fill_blank")
        assert result is False
    
    def test_fill_blank_with_numbers(self):
        """Test fill blank with numeric answer."""
        result = compare_answers("42", "42", "fill_blank")
        assert result is True
    
    def test_fill_blank_number_as_int(self):
        """Test fill blank with number as integer converts to string."""
        result = compare_answers(42, "42", "fill_blank")
        assert result is True


class TestCompareAnswersEdgeCases:
    """Tests for edge cases in compare_answers."""
    
    def test_unknown_question_type_uses_string_comparison(self):
        """Test unknown question type falls back to string comparison."""
        result = compare_answers("answer", "answer", "unknown_type")
        assert result is True
    
    def test_empty_strings_match(self):
        """Test empty strings are equal."""
        result = compare_answers("", "", "multiple_choice")
        assert result is True
    
    def test_none_type_handling_matching(self):
        """Test None type in matching question returns False."""
        result = compare_answers(None, [1, 2, 3], "matching")
        assert result is False
    
    def test_none_correct_answer_matching(self):
        """Test None as correct answer in matching returns False."""
        result = compare_answers([1, 2, 3], None, "matching")
        assert result is False
    
    def test_integer_converted_to_string_for_fill_blank(self):
        """Test integers are converted to strings for comparison."""
        # This tests the str() conversion in the else branch
        result = compare_answers(100, "100", "fill_blank")
        assert result is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
