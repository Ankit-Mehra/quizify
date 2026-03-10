"""
Answer evaluation utilities for quiz submissions.

This module provides shared logic for evaluating user answers,
including detection of unattempted questions and answer comparison.
"""
import json
from typing import Union, List


def is_unattempted(user_answer: Union[str, bool, List[int], None], question_type: str) -> bool:
    """
    Detect if an answer represents an unattempted question.
    
    Type-aware detection rules:
    - multiple_choice: Empty string, None, or whitespace-only = unattempted
    - fill_blank: Empty string, None, or whitespace-only = unattempted
    - true_false: Empty string, None, or non-boolean string = unattempted
                  (Note: False is a valid answer, not unattempted)
    - matching: Empty list [], None, or all values are -1 = unattempted
                (Note: [0,0,0,0] is attempted - user selected first option for all)
    
    Args:
        user_answer: User's submitted answer
        question_type: Type of question for type-aware detection
        
    Returns:
        bool: True if answer is unattempted, False if user provided an answer
    """
    # Handle None for all types
    if user_answer is None:
        return True
    
    if question_type == "matching":
        return _is_matching_unattempted(user_answer)
    elif question_type == "true_false":
        return _is_true_false_unattempted(user_answer)
    else:
        # multiple_choice, fill_blank: empty or whitespace-only = unattempted
        return _is_text_answer_unattempted(user_answer)


def _is_matching_unattempted(user_answer: Union[str, List[int], None]) -> bool:
    """
    Check if a matching question answer is unattempted.
    
    Matching answers are unattempted if:
    - Answer is None (handled by caller)
    - Answer is an empty list
    - All values are -1 (common frontend pattern for "not selected")
    """
    # Parse string representation if needed
    if isinstance(user_answer, str):
        try:
            user_list = json.loads(user_answer)
        except json.JSONDecodeError:
            # Try comma-separated format
            try:
                user_list = [int(x.strip()) for x in user_answer.split(",") if x.strip()]
            except (ValueError, AttributeError):
                return True  # Unparseable = unattempted
    elif isinstance(user_answer, list):
        user_list = user_answer
    else:
        return True  # Unknown type = unattempted
    
    # Empty list = unattempted
    if not user_list:
        return True
    
    # All -1 values = unattempted
    try:
        return all(int(x) == -1 for x in user_list)
    except (ValueError, TypeError):
        return True  # Invalid values = unattempted


def _is_true_false_unattempted(user_answer: Union[str, bool, None]) -> bool:
    """
    Check if a true/false question answer is unattempted.
    
    True/false answers are unattempted if:
    - Answer is None (handled by caller)
    - Answer is an empty or whitespace string
    - Answer is a string that's not "true" or "false"
    
    Note: Boolean False is a valid answer, not unattempted.
    """
    if isinstance(user_answer, bool):
        return False  # Valid answer (even False is an answer)
    
    if isinstance(user_answer, str):
        normalized = user_answer.strip().lower()
        # Only "true" or "false" are valid attempts
        return normalized not in ("true", "false")
    
    # Any other type = unattempted
    return True


def _is_text_answer_unattempted(user_answer: Union[str, None]) -> bool:
    """
    Check if a text-based answer (multiple_choice, fill_blank) is unattempted.
    
    Text answers are unattempted if None, empty, or whitespace-only.
    
    Note: This function handles None explicitly for defensive coding,
    even though the parent is_unattempted() checks for None first.
    """
    if user_answer is None:
        return True
    if isinstance(user_answer, str):
        return user_answer.strip() == ""
    # Non-string types: convert and check
    return str(user_answer).strip() == ""
