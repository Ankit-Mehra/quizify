# schemas/quiz.py
from pydantic import BaseModel
from typing import List

class QuizQuestion(BaseModel):
    question: str
    options: List[str]
    correct_answer: str
    source: str
    explanation: str