# schemas/quiz.py
from pydantic import BaseModel, Field, model_validator, ConfigDict
from typing import List, Optional, Literal, Union
from uuid import UUID
# === 1. Question type models ===
class QuestionBase(BaseModel):
    id: Optional[UUID] = None
    quiz_id: Optional[UUID] = None
    explanation: str
    source: str
class MCQQuestion(QuestionBase):
    type: Literal["multiple_choice"]
    question: str
    options: List[str]
    correct_answer: str
    explanation: str
    source: str

class TrueFalseQuestion(QuestionBase):
    type: Literal["true_false"]
    question: str
    correct_answer: bool
    explanation: str
    source: str

class FillBlankQuestion(QuestionBase):
    type: Literal["fill_blank"]
    question: str  # use ____ or {{blank}} in question
    options: List[str]
    correct_answer: str
    explanation: str
    source: str

class MatchingQuestion(QuestionBase):
    type: Literal["matching"]
    question: str
    left: List[str]
    right: List[str]
    correct_answer: List[int]  # list of matching indices
    explanation: str
    source: str

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
    content_source_type: Optional[Literal["file", "url", "text"]] = None  # NEW
    content_source_reference: Optional[str] = None  # NEW
    questions: List[Question]

class QuizMetadata(BaseModel):
    model_config = ConfigDict(strict=False)
    id: Optional[str] = None
    quiz_id: Optional[str] = None
    content_type: str  # "text" or "file"
    content_source_type: Optional[Literal["file", "url", "text"]] = None  # NEW: source type
    content_source_reference: Optional[str] = None  # NEW: file_id or URL
    file_name: Optional[str] = None
    file_type: Optional[str] = None
    word_count: Optional[int] = None
    created_at: Optional[str] = None
    created_by: Optional[str] = None
    question_count: Optional[int] = None

class TextQuizRequest(BaseModel):
    model_config = ConfigDict(strict=True, validate_assignment=True)
    title: str = Field(..., description="Title of the quiz")
    content: str = Field(..., description="Content to generate questions from")
    question_type: List[Literal[
        "multiple_choice", "true_false", "fill_blank","matching","mixed"]] = ["mixed"]
    num_questions: Optional[int] = Field(10, gt=0, le=50, description="Number of questions to generate")

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

class WebQuizRequest(BaseModel):
    """Request to generate quiz from web URL (basic/educator tiers only)"""
    model_config = ConfigDict(strict=True, validate_assignment=True)
    title: str = Field(..., description="Title of the quiz")
    url: str = Field(..., description="Web URL to scrape content from")
    question_type: List[Literal[
        "multiple_choice", "true_false", "fill_blank","matching","mixed"]] = ["mixed"]
    num_questions: Optional[int] = Field(10, gt=0, le=50, description="Number of questions to generate")

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
    model_config = ConfigDict(strict=False, extra='allow')
    quiz_id: str
    title: str
    message: str

class MyQuizzesResponse(BaseModel):
    model_config = ConfigDict(strict=True)
    id: Optional[str] = None
    title: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[str] = None
    question_count: Optional[int] = None
