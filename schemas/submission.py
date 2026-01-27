## Submission Schemas
from pydantic import BaseModel, Field
from uuid import UUID
from typing import Union, List
from datetime import datetime

class AnswerSubmission(BaseModel):
    """Represents a single answer submission for a question"""
    question_id: UUID = Field(..., description="ID of the question being answered")
    user_answer: Union[str, bool, List[int]] = Field(..., description="User's answer (format depends on question type)")

class QuizSubmissionRequest(BaseModel):
    """Request payload for submitting quiz answers"""
    quiz_id: UUID = Field(..., description="ID of the quiz being submitted")
    total_questions: int = Field(..., description="Total number of questions in the quiz", gt=0)
    answers: List[AnswerSubmission] = Field(..., description="List of all answers submitted")

class QuizSubmission(BaseModel):
    """Complete submission record stored in database"""
    id: UUID = Field(..., description="Unique submission ID")
    quiz_id: UUID = Field(..., description="ID of the quiz that was submitted")
    user_id: UUID = Field(..., description="ID of the user who submitted")
    score: int = Field(..., description="Calculated score percentage (0-100, rounded to nearest integer)", ge=0, le=100)
    correct_count: int = Field(..., description="Number of correct answers", ge=0)
    wrong_count: int = Field(..., description="Number of wrong answers", ge=0)
    total_questions: int = Field(..., description="Total questions answered", gt=0)
    submitted_at: datetime = Field(..., description="Timestamp of submission")
    quiz_title: str | None = Field(None, description="Title of the quiz (for display purposes)")

class QuizAnswer(BaseModel):
    """Individual answer record with correctness evaluation"""
    id: UUID = Field(..., description="Unique answer record ID")
    submission_id: UUID = Field(..., description="ID of the parent submission")
    question_id: UUID = Field(..., description="ID of the question answered")
    user_answer: Union[str, bool, List[int]] = Field(..., description="User's submitted answer")
    correct_answer: Union[str, bool, List[int]] = Field(..., description="Correct answer for comparison")
    is_correct: bool = Field(..., description="Whether the answer was correct")

class DetailedResult(BaseModel):
    """Detailed result for a single question in the submission response.
    
    This is the base schema for question results, used in immediate submission responses.
    """
    question_id: UUID = Field(..., description="ID of the question")
    question_type: str = Field(
        ...,
        description=(
            "Type of question: multiple_choice, true_false, fill_blank, matching, "
            "or unknown (used when the original question has been deleted and full "
            "question data is no longer available)"
        ),
    )
    question: str = Field(..., description="The question text")
    your_answer: Union[str, bool, List[int]] = Field(..., description="User's submitted answer")
    correct_answer: Union[str, bool, List[int]] = Field(..., description="The correct answer")
    is_correct: bool = Field(..., description="Whether the answer was correct")

class SubmissionResponse(BaseModel):
    """Response returned after submitting a quiz with detailed results"""
    id: UUID = Field(..., description="Unique submission ID for future reference")
    total_questions: int = Field(..., description="Total number of questions", gt=0)
    correct_count: int = Field(..., description="Number of correct answers", ge=0)
    wrong_count: int = Field(..., description="Number of wrong answers", ge=0)
    score: int = Field(..., description="Calculated percentage score (0-100, rounded to nearest integer)", ge=0, le=100)
    detailed_results: List[DetailedResult] = Field(..., description="Detailed results for each question")

class UserSubmissionsResponse(BaseModel):
    """Response for listing all user's quiz submissions"""
    user_id: str = Field(..., description="User's UUID")
    total_submissions: int = Field(..., description="Total number of submissions", ge=0)
    submissions: List[QuizSubmission] = Field(..., description="List of submissions ordered by most recent first")

class QuizSubmissionsResponse(BaseModel):
    """Response for listing all attempts for a specific quiz"""
    quiz_id: str = Field(..., description="Quiz UUID")
    user_id: str = Field(..., description="User's UUID")
    total_attempts: int = Field(..., description="Number of attempts on this quiz", ge=0)
    submissions: List[QuizSubmission] = Field(..., description="List of attempts ordered by most recent first")

class QuestionReviewDetail(DetailedResult):
    """Extended question result with explanations for post-submission review.
    
    Inherits from DetailedResult and adds explanation and metadata fields
    for comprehensive quiz review experience.
    """
    explanation: str = Field(default="", description="Explanation of the correct answer")
    # Optional fields for enhanced quiz mode
    options: List[str] | None = Field(None, description="Answer options (for multiple_choice questions)")
    distractor_explanations: dict[str, str] | None = Field(None, description="Explanations for incorrect options (MCQ/fill_blank)")
    bloom_level: str | None = Field(None, description="Bloom's taxonomy level")
    difficulty: str | None = Field(None, description="Question difficulty: easy, medium, hard")
    concept_name: str | None = Field(None, description="Concept being tested")

class SubmissionReviewResponse(BaseModel):
    """Full review of a quiz submission with detailed answers and explanations"""
    submission_id: UUID = Field(..., description="Unique submission ID")
    quiz_id: UUID = Field(..., description="ID of the quiz")
    quiz_title: str | None = Field(None, description="Title of the quiz")
    user_id: UUID = Field(..., description="User who submitted")
    score: int = Field(..., description="Percentage score (0-100)", ge=0, le=100)
    correct_count: int = Field(..., description="Number of correct answers", ge=0)
    wrong_count: int = Field(..., description="Number of wrong answers", ge=0)
    total_questions: int = Field(..., description="Total questions answered", gt=0)
    submitted_at: datetime = Field(..., description="Timestamp of submission")
    questions: List[QuestionReviewDetail] = Field(..., description="Detailed review for each question with explanations")


