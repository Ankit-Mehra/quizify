## Submission Schemas
from pydantic import BaseModel
from uuid import UUID
from typing import Union, List
from datetime import datetime

class AnswerSubmission(BaseModel):
    question_id: UUID
    user_answer: Union[str,bool,List[int]]

class QuizSubmissionRequest(BaseModel):
    quiz_id: UUID
    total_questions: int
    answers: List[AnswerSubmission]

class QuizSubmission(BaseModel):
    id: UUID
    quiz_id: UUID
    user_id: UUID
    score: int
    correct_count: int
    wrong_count: int
    total_questions: int
    submitted_at: datetime

class QuizAnswer(BaseModel):
    id: UUID
    submission_id: UUID
    question_id: UUID
    user_answer: Union[str,bool,List[int]]
    correct_answer: Union[str,bool,List[int]]
    is_correct: bool

class DetailedResult(BaseModel):
    question_id: UUID
    question: str
    your_answer: Union[str,bool,List[int]]
    correct_answer: Union[str,bool,List[int]]
    is_correct: bool

class SubmissionResponse(BaseModel):
    id: UUID
    total_questions: int
    correct_count: int
    wrong_count: int
    score: int
    detailed_results: List[DetailedResult]

