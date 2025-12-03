from typing import List, Literal, Union
from pydantic import BaseModel, field_validator
import logging

logger = logging.getLogger(__name__)


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
        """Handle LLM returning null for options field."""
        if v is None:
            logger.warning("MCQ question received null options, defaulting to empty list")
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
        """Handle LLM returning null for options field."""
        if v is None:
            logger.warning("FillBlank question received null options, defaulting to empty list")
            return []
        return v

class MatchingQuestionParsed(QuestionBaseParsed):
    type: Literal["matching"]
    question: str
    left: List[str]
    right: List[str]
    correct_answer: List[int]
    
    @field_validator('left', mode='before')
    @classmethod
    def ensure_left_list(cls, v):
        """Handle LLM returning null for left field."""
        if v is None:
            logger.warning("Matching question received null left, defaulting to empty list")
            return []
        return v
    
    @field_validator('right', mode='before')
    @classmethod
    def ensure_right_list(cls, v):
        """Handle LLM returning null for right field."""
        if v is None:
            logger.warning("Matching question received null right, defaulting to empty list")
            return []
        return v
    
    @field_validator('correct_answer', mode='before')
    @classmethod
    def ensure_correct_answer_list(cls, v):
        """Handle LLM returning null for correct_answer field."""
        if v is None:
            logger.warning("Matching question received null correct_answer, defaulting to empty list")
            return []
        return v

QuestionParsed = Union[
    MCQQuestionParsed,
    TrueFalseQuestionParsed,
    FillBlankQuestionParsed,
    MatchingQuestionParsed,
]

class QuizzesParsed(BaseModel):
    quizzes: List[QuestionParsed]
