# schemas/quiz.py
from pydantic import BaseModel, Field, model_validator, ConfigDict
from typing import List, Optional, Literal, Union
from fastapi import UploadFile

# === 1. Question type models ===

class MCQQuestion(BaseModel):
    type: Literal["multiple_choice"]
    question: str
    options: List[str]
    correct_answer: str
    explanation: str
    source: str

class TrueFalseQuestion(BaseModel):
    type: Literal["true_false"]
    question: str
    correct_answer: bool
    explanation: str
    source: str

class FillBlankQuestion(BaseModel):
    type: Literal["fill_blank"]
    question: str  # use ____ or {{blank}} in question
    options: List[str]
    correct_answer: str
    explanation: str
    source: str

class MatchingQuestion(BaseModel):
    type: Literal["matching"]
    question: str
    left: List[str]
    right: List[str]
    correct_answer: List[int]  # list of matching indices
    explanation: str
    source: str

# === 2. Discriminated union ===

Question = Union[MCQQuestion, TrueFalseQuestion, FillBlankQuestion, MatchingQuestion]

# === 3. Wrapper for lists of questions ===

class Quizzes(BaseModel):
    quizzes: List[Question]


class QuizzesResponse(BaseModel):
    model_config = ConfigDict(strict=True)
    id: Optional[str] = None
    title: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[str] = None
    questions: List[Question]

class QuizMetadata(BaseModel):
    model_config = ConfigDict(strict=False)
    id: Optional[str] = None
    quiz_id: Optional[str] = None
    content_type: str  # "text" or "file"
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
        "mcq", "true_false", "fill_in_the_blank","matching","mixed"]] = ["mixed"]
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
        "mcq", "true_false", "fill_in_the_blank","matching","mixed"]] = Field(default=["mixed"], description="Type of questions to generate")
    file: Optional[UploadFile] = None
    
    @model_validator(mode='after')
    def validate_fields(self) -> 'FileQuizRequest':
        if not self.title or not self.title.strip():
            raise ValueError('Quiz title cannot be empty')
        return self
    
class QuizGenerationResponse(BaseModel):
    model_config = ConfigDict(strict=True)
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
