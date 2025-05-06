from typing import List, Literal, Union
from pydantic import BaseModel

class QuestionBaseParsed(BaseModel):
    explanation: str
    source: str

class MCQQuestionParsed(QuestionBaseParsed):
    type: Literal["multiple_choice"]
    question: str
    options: List[str]
    correct_answer: str

class TrueFalseQuestionParsed(QuestionBaseParsed):
    type: Literal["true_false"]
    question: str
    correct_answer: bool

class FillBlankQuestionParsed(QuestionBaseParsed):
    type: Literal["fill_blank"]
    question: str
    options: List[str]
    correct_answer: str

class MatchingQuestionParsed(QuestionBaseParsed):
    type: Literal["matching"]
    question: str
    left: List[str]
    right: List[str]
    correct_answer: List[int]

QuestionParsed = Union[
    MCQQuestionParsed,
    TrueFalseQuestionParsed,
    FillBlankQuestionParsed,
    MatchingQuestionParsed,
]

class QuizzesParsed(BaseModel):
    quizzes: List[QuestionParsed]
