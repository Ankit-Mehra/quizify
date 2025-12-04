# schemas/quiz.py
from pydantic import BaseModel, Field, model_validator, field_validator, ConfigDict
from typing import List, Optional, Literal, Union, Dict, Any
from uuid import UUID
from enum import Enum
import logging

logger = logging.getLogger(__name__)

# Content source type options
# IMPORTANT: These values MUST match migrations/001_add_missing_features.sql CHECK constraint
# Database constraint: CHECK (content_source_type IN ('file', 'url', 'text'))
CONTENT_SOURCE_TYPES = Literal["file", "url", "text"]

# Question type constants - used for validation and random selection
# IMPORTANT: Keep in sync with QUESTION_TYPE_PROMPTS in openai_service.py
QUESTION_TYPE = Literal["multiple_choice", "true_false", "fill_blank", "matching"]
ALL_QUESTION_TYPES: List[str] = ["multiple_choice", "true_false", "fill_blank", "matching"]

# === 1. Question type models ===
class QuestionBase(BaseModel):
    """Base class for questions with database IDs (used in retrieval/submission)"""
    id: Optional[UUID] = None
    quiz_id: Optional[UUID] = None
    explanation: str = ""
    source: str = ""
    # Enhanced metadata (optional for backward compatibility)
    bloom_level: Optional[str] = None
    difficulty: Optional[str] = None
    concept_id: Optional[UUID] = None
    concept_name: Optional[str] = None  # Human-readable concept name
    chunk_id: Optional[UUID] = None
    confidence_score: Optional[float] = None

class MCQQuestion(QuestionBase):
    type: Literal["multiple_choice"]
    question: str
    options: List[str]
    correct_answer: str
    
    @field_validator('options', mode='before')
    @classmethod
    def ensure_options_list(cls, v):
        """Handle LLM returning null for options field.
        
        Converts null to empty list to prevent validation crash.
        Note: Questions with empty options will be later rejected by
        _validate_question_structure() before verification.
        """
        if v is None:
            logger.warning("MCQ question received null options - LLM output quality issue")
            return []
        return v

class TrueFalseQuestion(QuestionBase):
    type: Literal["true_false"]
    question: str
    correct_answer: bool

class FillBlankQuestion(QuestionBase):
    type: Literal["fill_blank"]
    question: str  # use ____ or {{blank}} in question
    options: List[str]
    correct_answer: str
    
    @field_validator('options', mode='before')
    @classmethod
    def ensure_options_list(cls, v):
        """Handle LLM returning null for options field.
        
        The LLM sometimes returns {"options": null} despite prompts
        requiring a list. Converts null to empty list to prevent crash.
        Note: Questions with empty options will be later rejected by
        _validate_question_structure() before verification.
        """
        if v is None:
            logger.warning("FillBlank question received null options - LLM output quality issue")
            return []
        return v

class MatchingQuestion(QuestionBase):
    type: Literal["matching"]
    question: str
    left: List[str]
    right: List[str]
    correct_answer: List[int]  # list of matching indices
    
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
        """Handle LLM returning null for right field.
        
        Converts null to empty list to prevent validation errors.
        Questions with empty right list are later rejected by structure validation.
        """
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

# === 2. Discriminated union ===

Question = Union[
    MCQQuestion,
    TrueFalseQuestion,
    FillBlankQuestion,
    MatchingQuestion
]

# === 3. Wrapper for lists of questions ===

class Quizzes(BaseModel):
    quizzes: List[Question]


class QuizzesResponse(BaseModel):
    model_config = ConfigDict(strict=True)
    id: Optional[str] = None
    title: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[str] = None
    content_source_type: Optional[CONTENT_SOURCE_TYPES] = None  # NEW
    content_source_reference: Optional[str] = None  # NEW
    questions: List[Question]

class QuizMetadata(BaseModel):
    """
    Metadata for quiz generation.
    Strict validation enabled to catch data inconsistencies early.
    """
    model_config = ConfigDict(strict=True, validate_assignment=True)
    
    id: Optional[str] = None
    quiz_id: Optional[str] = None
    quiz_title: Optional[str] = None  # Title of the quiz (from quizzes table)
    content_type: str  # "text" or "file"
    content_source_type: Optional[CONTENT_SOURCE_TYPES] = None  # NEW: source type
    content_source_reference: Optional[str] = None  # NEW: file_id or URL
    file_name: Optional[str] = None
    file_type: Optional[str] = None
    word_count: Optional[int] = None
    created_at: Optional[str] = None
    created_by: Optional[str] = None
    question_count: Optional[int] = None

# Generation mode options
GENERATION_MODE = Literal["standard", "enhanced"]

class TextQuizRequest(BaseModel):
    model_config = ConfigDict(strict=True, validate_assignment=True)
    title: str = Field(..., description="Title of the quiz")
    content: str = Field(..., description="Content to generate questions from")
    question_type: List[Literal[
        "multiple_choice", "true_false", "fill_blank","matching","mixed"]] = ["mixed"]
    num_questions: Optional[int] = Field(10, gt=0, le=50, description="Number of questions to generate")
    mode: GENERATION_MODE = Field("standard", description="Generation mode: 'standard' for fast generation, 'enhanced' for RAG-based quality with Bloom's taxonomy")

    @model_validator(mode='after')
    def validate_fields(self) -> 'TextQuizRequest':
        if not self.title or not self.title.strip():
            raise ValueError('Quiz title cannot be empty')
        
        if not self.content or len(self.content.strip()) < 10:
            raise ValueError('Quiz content must be at least 10 characters long')
        
        return self

class FileQuizRequest(BaseModel):
    model_config = ConfigDict(strict=True, validate_assignment=True)
    title: str = Field(..., description="Title of the quiz")
    num_questions: Optional[int] = Field(10, gt=0, le=50, description="Number of questions to generate")
    question_type: List[Literal[
        "multiple_choice", "true_false", "fill_blank","matching","mixed"]] = ["mixed"]
    mode: GENERATION_MODE = Field("standard", description="Generation mode: 'standard' for fast generation, 'enhanced' for RAG-based quality")

class WebQuizRequest(BaseModel):
    """Request to generate quiz from web URL (basic/pro tiers only)"""
    model_config = ConfigDict(strict=True, validate_assignment=True)
    title: str = Field(..., description="Title of the quiz")
    url: str = Field(..., description="Web URL to scrape content from")
    question_type: List[Literal[
        "multiple_choice", "true_false", "fill_blank","matching","mixed"]] = ["mixed"]
    num_questions: Optional[int] = Field(10, gt=0, le=50, description="Number of questions to generate")
    mode: GENERATION_MODE = Field("standard", description="Generation mode: 'standard' for fast generation, 'enhanced' for RAG-based quality")

    @model_validator(mode='after')
    def validate_web_fields(self) -> 'WebQuizRequest':
        if not self.title or not self.title.strip():
            raise ValueError('Quiz title cannot be empty')
        
        if not self.url or not self.url.strip():
            raise ValueError('URL cannot be empty')
        
        # Basic URL validation
        if not self.url.startswith(('http://', 'https://')):
            raise ValueError('URL must start with http:// or https://')
        
        return self
    
class QuizGenerationResponse(BaseModel):
    """
    Response model for quiz generation endpoints.
    Returns saved questions with database IDs for immediate use.
    """
    model_config = ConfigDict(strict=True, validate_assignment=True, extra='forbid')
    quiz_id: str
    title: str
    message: str
    questions: Optional[List[Question]] = None  # Saved questions from database with IDs
    source_url: Optional[str] = None  # URL source for web-based quizzes
    file_id: Optional[str] = None  # File ID if PDF was saved from URL

class MyQuizzesResponse(BaseModel):
    model_config = ConfigDict(strict=True)
    id: Optional[str] = None
    title: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[str] = None
    question_count: Optional[int] = None

class DeleteQuizResponse(BaseModel):
    """Response for quiz deletion"""
    message: str

# === 5. Enhanced RAG Pipeline Models ===

class BloomLevel(str, Enum):
    REMEMBER = "remember"
    UNDERSTAND = "understand"
    APPLY = "apply"
    ANALYZE = "analyze"
    EVALUATE = "evaluate"
    CREATE = "create"

class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"

class EnhancedQuestion(BaseModel):
    """Enhanced question with quality metadata"""
    id: Optional[UUID] = None
    quiz_id: Optional[UUID] = None
    type: Literal["multiple_choice", "true_false", "fill_blank", "matching"]
    question: str
    options: Optional[List[str]] = None
    # For matching questions
    left: Optional[List[str]] = None
    right: Optional[List[str]] = None
    correct_answer: Union[str, bool, List[int]]
    explanation: str
    source: str
    # Enhanced mode fields (optional for standard mode)
    bloom_level: Optional[BloomLevel] = None
    difficulty: Optional[Difficulty] = None
    concept_id: Optional[UUID] = None
    concept_name: Optional[str] = None  # Human-readable concept name (e.g., "Photosynthesis")
    chunk_id: Optional[UUID] = None
    confidence_score: Optional[float] = None

class QuizGenerationOptions(BaseModel):
    """Options for quiz generation
    
    Note: Dict keys use string values for JSON serialization compatibility.
    BloomLevel/Difficulty enum values should be used as keys (e.g., "remember", "easy").
    """
    bloom_distribution: Optional[Dict[str, float]] = None  # {"remember": 0.3, "understand": 0.4, ...}
    difficulty_distribution: Optional[Dict[str, float]] = None  # {"easy": 0.3, "medium": 0.5, "hard": 0.2}
    enable_rag: bool = True
    enable_fact_check: bool = True

class EnhancedTextQuizRequest(BaseModel):
    title: str
    content: str
    # Allow mixed, single type, or list of types
    question_type: Union[Literal["mixed"], Literal["multiple_choice", "true_false", "fill_blank", "matching"], List[Literal["multiple_choice", "true_false", "fill_blank", "matching"]]] = "mixed"
    num_questions: int = Field(10, gt=0, le=50)
    mode: GENERATION_MODE = Field("enhanced", description="Generation mode: 'standard' for fast generation, 'enhanced' for RAG-based quality")
    options: Optional[QuizGenerationOptions] = None

class EnhancedQuizGenerationResponse(BaseModel):
    quiz_id: str
    title: str
    message: str
    questions: List[EnhancedQuestion]
    generation_stats: Dict[str, Any] = Field(default_factory=dict)  # Chunks, concepts, tokens used, etc.
    source_url: Optional[str] = None
    file_id: Optional[str] = None
