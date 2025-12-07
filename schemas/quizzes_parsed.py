from typing import List, Literal, Union, Annotated
from pydantic import BaseModel, field_validator, Discriminator
import logging

logger = logging.getLogger(__name__)

# Default question text for matching questions when LLM omits the field
DEFAULT_MATCHING_QUESTION = "Match the items from the left column with the correct items on the right."


class QuestionBaseParsed(BaseModel):
    explanation: str
    source: str

class MCQQuestionParsed(QuestionBaseParsed):
    type: Literal["multiple_choice"]
    question: str
    options: List[str]
    correct_answer: str
    
    @field_validator('options', mode='before')
    @classmethod
    def ensure_options_list(cls, v):
        """Handle LLM returning null for options field.
        
        Note: Questions with empty options will be later rejected by
        _validate_question_structure() before verification.
        """
        if v is None:
            logger.warning("MCQ question received null options - LLM output quality issue")
            return []
        return v

class TrueFalseQuestionParsed(QuestionBaseParsed):
    type: Literal["true_false"]
    question: str
    correct_answer: bool

class FillBlankQuestionParsed(QuestionBaseParsed):
    type: Literal["fill_blank"]
    question: str
    options: List[str]
    correct_answer: str
    
    @field_validator('options', mode='before')
    @classmethod
    def ensure_options_list(cls, v):
        """Handle LLM returning null for options field.
        
        Note: Questions with empty options will be later rejected by
        _validate_question_structure() before verification.
        """
        if v is None:
            logger.warning("FillBlank question received null options - LLM output quality issue")
            return []
        return v

class MatchingQuestionParsed(QuestionBaseParsed):
    type: Literal["matching"]
    question: str = DEFAULT_MATCHING_QUESTION
    left: List[str]
    right: List[str]
    correct_answer: List[int]
    
    @field_validator('question', mode='before')
    @classmethod
    def ensure_question_exists(cls, v):
        """Handle LLM omitting question field for matching questions.
        
        Some LLM outputs skip the question field for matching type,
        providing only left/right columns. We provide a sensible default.
        """
        if v is None or (isinstance(v, str) and not v.strip()):
            logger.warning("Matching question received null/empty question - using default")
            return DEFAULT_MATCHING_QUESTION
        return v
    
    @field_validator('left', mode='before')
    @classmethod
    def ensure_left_list(cls, v):
        """Handle LLM returning null for left field.
        
        Note: Questions with empty left/right will be later rejected by
        _validate_question_structure() before verification.
        """
        if v is None:
            logger.warning("Matching question received null left - LLM output quality issue")
            return []
        return v
    
    @field_validator('right', mode='before')
    @classmethod
    def ensure_right_list(cls, v):
        """Handle LLM returning null for right field."""
        if v is None:
            logger.warning("Matching question received null right - LLM output quality issue")
            return []
        return v
    
    @field_validator('correct_answer', mode='before')
    @classmethod
    def ensure_correct_answer_list(cls, v):
        """Handle LLM returning null for correct_answer field."""
        if v is None:
            logger.warning("Matching question received null correct_answer - LLM output quality issue")
            return []
        return v

# Use discriminator to directly select the correct model based on 'type' field
# This prevents spurious warnings when parsing non-matching questions
QuestionParsed = Annotated[
    Union[
        MCQQuestionParsed,
        TrueFalseQuestionParsed,
        FillBlankQuestionParsed,
        MatchingQuestionParsed,
    ],
    Discriminator("type")
]

class QuizzesParsed(BaseModel):
    quizzes: List[QuestionParsed]
