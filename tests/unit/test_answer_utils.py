"""
Unit tests for the is_unattempted function and helper functions in answer_utils.

Tests type-specific unattempted detection:
- Matching questions: empty list, all -1 values, valid answers
- True/false questions: boolean values, string values, empty/invalid
- Multiple choice/fill blank: empty strings, whitespace, valid answers
- Edge cases: None, type mismatches, unknown question types
"""

from services.answer_utils import (
    is_unattempted,
    _is_matching_unattempted,
    _is_true_false_unattempted,
    _is_text_answer_unattempted,
)


class TestIsUnattemptedMatching:
    """Tests for matching question type unattempted detection."""
    
    def test_matching_none_is_unattempted(self):
        """Test that None is detected as unattempted."""
        result = is_unattempted(None, "matching")
        assert result is True
    
    def test_matching_empty_list_is_unattempted(self):
        """Test that empty list is detected as unattempted."""
        result = is_unattempted([], "matching")
        assert result is True
    
    def test_matching_all_negative_ones_is_unattempted(self):
        """Test that all -1 values (common frontend pattern) is unattempted."""
        result = is_unattempted([-1, -1, -1, -1], "matching")
        assert result is True
    
    def test_matching_json_string_all_negative_ones_is_unattempted(self):
        """Test that JSON string with all -1 values is unattempted."""
        result = is_unattempted("[-1, -1, -1, -1]", "matching")
        assert result is True
    
    def test_matching_comma_separated_all_negative_ones_is_unattempted(self):
        """Test that comma-separated -1 values is unattempted."""
        result = is_unattempted("-1, -1, -1, -1", "matching")
        assert result is True
    
    def test_matching_valid_list_is_attempted(self):
        """Test that valid list with indices is NOT unattempted."""
        result = is_unattempted([0, 1, 2, 3], "matching")
        assert result is False
    
    def test_matching_mixed_values_with_negative_one_is_attempted(self):
        """Test that list with some -1 but not all is attempted."""
        result = is_unattempted([0, -1, 2, 3], "matching")
        assert result is False
    
    def test_matching_all_zeros_is_attempted(self):
        """Test that all zeros (first option selected) is attempted."""
        result = is_unattempted([0, 0, 0, 0], "matching")
        assert result is False
    
    def test_matching_json_string_valid_is_attempted(self):
        """Test that valid JSON string is NOT unattempted."""
        result = is_unattempted("[1, 0, 3, 2]", "matching")
        assert result is False
    
    def test_matching_comma_separated_valid_is_attempted(self):
        """Test that comma-separated valid values is NOT unattempted."""
        result = is_unattempted("1, 0, 3, 2", "matching")
        assert result is False
    
    def test_matching_malformed_json_is_unattempted(self):
        """Test that malformed JSON is treated as unattempted."""
        result = is_unattempted("[1, 0, 3", "matching")  # Missing bracket
        assert result is True
    
    def test_matching_non_integer_string_is_unattempted(self):
        """Test that non-integer values are unattempted."""
        result = is_unattempted("a, b, c, d", "matching")
        assert result is True
    
    def test_matching_empty_string_is_unattempted(self):
        """Test that empty string is unattempted."""
        result = is_unattempted("", "matching")
        assert result is True
    
    def test_matching_invalid_type_is_unattempted(self):
        """Test that invalid type (e.g., int) is unattempted."""
        result = is_unattempted(123, "matching")
        assert result is True


class TestIsUnattemptedTrueFalse:
    """Tests for true_false question type unattempted detection."""
    
    def test_true_false_none_is_unattempted(self):
        """Test that None is unattempted."""
        result = is_unattempted(None, "true_false")
        assert result is True
    
    def test_true_false_boolean_true_is_attempted(self):
        """Test that boolean True is a valid answer (NOT unattempted)."""
        result = is_unattempted(True, "true_false")
        assert result is False
    
    def test_true_false_boolean_false_is_attempted(self):
        """Test that boolean False is a valid answer (NOT unattempted)."""
        result = is_unattempted(False, "true_false")
        assert result is False
    
    def test_true_false_string_true_is_attempted(self):
        """Test that string 'true' is a valid answer."""
        result = is_unattempted("true", "true_false")
        assert result is False
    
    def test_true_false_string_false_is_attempted(self):
        """Test that string 'false' is a valid answer."""
        result = is_unattempted("false", "true_false")
        assert result is False
    
    def test_true_false_string_TRUE_uppercase_is_attempted(self):
        """Test that uppercase 'TRUE' is a valid answer."""
        result = is_unattempted("TRUE", "true_false")
        assert result is False
    
    def test_true_false_string_FALSE_uppercase_is_attempted(self):
        """Test that uppercase 'FALSE' is a valid answer."""
        result = is_unattempted("FALSE", "true_false")
        assert result is False
    
    def test_true_false_string_with_whitespace_is_attempted(self):
        """Test that 'true' with whitespace is valid."""
        result = is_unattempted("  true  ", "true_false")
        assert result is False
    
    def test_true_false_empty_string_is_unattempted(self):
        """Test that empty string is unattempted."""
        result = is_unattempted("", "true_false")
        assert result is True
    
    def test_true_false_whitespace_only_is_unattempted(self):
        """Test that whitespace-only string is unattempted."""
        result = is_unattempted("   ", "true_false")
        assert result is True
    
    def test_true_false_invalid_string_is_unattempted(self):
        """Test that invalid string like 'yes' is unattempted."""
        result = is_unattempted("yes", "true_false")
        assert result is True
    
    def test_true_false_number_is_unattempted(self):
        """Test that number (not boolean) is unattempted."""
        result = is_unattempted(1, "true_false")
        assert result is True
    
    def test_true_false_zero_is_unattempted(self):
        """Test that 0 is unattempted (not same as False boolean)."""
        result = is_unattempted(0, "true_false")
        assert result is True


class TestIsUnattemptedMultipleChoice:
    """Tests for multiple_choice question type unattempted detection."""
    
    def test_multiple_choice_none_is_unattempted(self):
        """Test that None is unattempted."""
        result = is_unattempted(None, "multiple_choice")
        assert result is True
    
    def test_multiple_choice_empty_string_is_unattempted(self):
        """Test that empty string is unattempted."""
        result = is_unattempted("", "multiple_choice")
        assert result is True
    
    def test_multiple_choice_whitespace_only_is_unattempted(self):
        """Test that whitespace-only string is unattempted."""
        result = is_unattempted("   ", "multiple_choice")
        assert result is True
    
    def test_multiple_choice_valid_answer_is_attempted(self):
        """Test that valid answer is NOT unattempted."""
        result = is_unattempted("Option A", "multiple_choice")
        assert result is False
    
    def test_multiple_choice_single_char_is_attempted(self):
        """Test that single character answer is attempted."""
        result = is_unattempted("A", "multiple_choice")
        assert result is False


class TestIsUnattemptedFillBlank:
    """Tests for fill_blank question type unattempted detection."""
    
    def test_fill_blank_none_is_unattempted(self):
        """Test that None is unattempted."""
        result = is_unattempted(None, "fill_blank")
        assert result is True
    
    def test_fill_blank_empty_string_is_unattempted(self):
        """Test that empty string is unattempted."""
        result = is_unattempted("", "fill_blank")
        assert result is True
    
    def test_fill_blank_whitespace_only_is_unattempted(self):
        """Test that whitespace-only string is unattempted."""
        result = is_unattempted("   ", "fill_blank")
        assert result is True
    
    def test_fill_blank_tabs_and_newlines_is_unattempted(self):
        """Test that tabs and newlines are unattempted."""
        result = is_unattempted("\t\n  ", "fill_blank")
        assert result is True
    
    def test_fill_blank_valid_answer_is_attempted(self):
        """Test that valid answer is NOT unattempted."""
        result = is_unattempted("photosynthesis", "fill_blank")
        assert result is False
    
    def test_fill_blank_numeric_string_is_attempted(self):
        """Test that numeric string is attempted."""
        result = is_unattempted("42", "fill_blank")
        assert result is False


class TestIsUnattemptedUnknownType:
    """Tests for unknown question types (defaults to text behavior)."""
    
    def test_unknown_type_none_is_unattempted(self):
        """Test that None is unattempted for unknown types."""
        result = is_unattempted(None, "unknown")
        assert result is True
    
    def test_unknown_type_empty_string_is_unattempted(self):
        """Test that empty string is unattempted for unknown types."""
        result = is_unattempted("", "unknown")
        assert result is True
    
    def test_unknown_type_valid_answer_is_attempted(self):
        """Test that valid answer is attempted for unknown types."""
        result = is_unattempted("some answer", "unknown")
        assert result is False


class TestHelperFunctions:
    """Tests for the internal helper functions."""
    
    # _is_matching_unattempted tests
    def test_helper_matching_none_is_unattempted(self):
        """Test _is_matching_unattempted handles edge cases."""
        # Note: None is normally handled by parent, but test for robustness
        result = _is_matching_unattempted(None)
        assert result is True
    
    def test_helper_matching_empty_string_json_is_unattempted(self):
        """Test _is_matching_unattempted with empty JSON array string."""
        result = _is_matching_unattempted("[]")
        assert result is True
    
    # _is_true_false_unattempted tests
    def test_helper_true_false_none_is_unattempted(self):
        """Test _is_true_false_unattempted handles None."""
        result = _is_true_false_unattempted(None)
        assert result is True
    
    def test_helper_true_false_mixed_case_valid(self):
        """Test _is_true_false_unattempted with mixed case."""
        result = _is_true_false_unattempted("TrUe")
        assert result is False
    
    # _is_text_answer_unattempted tests
    def test_helper_text_none_is_unattempted(self):
        """Test _is_text_answer_unattempted handles None explicitly."""
        result = _is_text_answer_unattempted(None)
        assert result is True
    
    def test_helper_text_empty_string_is_unattempted(self):
        """Test _is_text_answer_unattempted with empty string."""
        result = _is_text_answer_unattempted("")
        assert result is True
    
    def test_helper_text_valid_string_is_attempted(self):
        """Test _is_text_answer_unattempted with valid string."""
        result = _is_text_answer_unattempted("valid answer")
        assert result is False


class TestScoreCalculationScenarios:
    """
    Tests documenting how unattempted detection affects score calculation.
    
    Score formula: correct / (correct + wrong + unattempted) * 100
    """
    
    def test_scenario_6_correct_2_wrong_2_unattempted(self):
        """
        Scenario: 10 questions, 6 correct, 2 wrong, 2 unattempted
        Expected score: 6 / (6 + 2 + 2) * 100 = 60%
        """
        answers = [
            ("Option A", "multiple_choice"),  # Attempted
            ("Option B", "multiple_choice"),  # Attempted
            ("true", "true_false"),           # Attempted
            ("false", "true_false"),          # Attempted
            ([0, 1, 2, 3], "matching"),       # Attempted
            ([1, 0, 3, 2], "matching"),       # Attempted
            ("answer", "fill_blank"),         # Attempted
            ("test", "fill_blank"),           # Attempted
            ("", "multiple_choice"),          # Unattempted
            (None, "fill_blank"),             # Unattempted
        ]
        
        unattempted_count = sum(1 for ans, qtype in answers if is_unattempted(ans, qtype))
        attempted_count = len(answers) - unattempted_count
        
        assert unattempted_count == 2
        assert attempted_count == 8
    
    def test_scenario_all_unattempted(self):
        """All questions unattempted should be detected."""
        answers = [
            (None, "multiple_choice"),
            ("", "fill_blank"),
            ("   ", "true_false"),
            ([], "matching"),
            ([-1, -1, -1], "matching"),
        ]
        
        unattempted_count = sum(1 for ans, qtype in answers if is_unattempted(ans, qtype))
        
        assert unattempted_count == 5
    
    def test_scenario_all_attempted(self):
        """All questions attempted should be detected."""
        answers = [
            ("Option A", "multiple_choice"),
            ("answer", "fill_blank"),
            ("true", "true_false"),
            (False, "true_false"),
            ([0, 1, 2, 3], "matching"),
        ]
        
        unattempted_count = sum(1 for ans, qtype in answers if is_unattempted(ans, qtype))
        
        assert unattempted_count == 0
