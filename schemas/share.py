"""
Schemas for quiz sharing functionality.

These schemas handle share link creation, revocation, and public quiz viewing.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


# ============================================================================
# Share Link Request/Response Schemas
# ============================================================================


class ShareLinkCreate(BaseModel):
    """Request to create a share link for a quiz."""

    quiz_id: UUID = Field(..., description="The quiz ID to share")

    model_config = ConfigDict(
        json_schema_extra={"example": {"quiz_id": "550e8400-e29b-41d4-a716-446655440000"}}
    )


class ShareLinkResponse(BaseModel):
    """Response containing the generated share link."""

    quiz_id: UUID = Field(..., description="The quiz ID")
    public_slug: str = Field(..., description="Unique slug for the share URL")
    share_url: str = Field(..., description="Full shareable URL")
    is_public: bool = Field(..., description="Whether the quiz is currently public")
    shared_at: datetime = Field(..., description="When the quiz was shared")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "quiz_id": "550e8400-e29b-41d4-a716-446655440000",
                "public_slug": "abc12xyz",
                "share_url": "https://quizify.app/quiz/abc12xyz",
                "is_public": True,
                "shared_at": "2025-01-18T12:00:00Z",
            }
        }
    )


class ShareLinkRevoke(BaseModel):
    """Request to revoke (unpublish) a shared quiz."""

    quiz_id: UUID = Field(..., description="The quiz ID to unshare")

    model_config = ConfigDict(
        json_schema_extra={"example": {"quiz_id": "550e8400-e29b-41d4-a716-446655440000"}}
    )


class ShareLinkStatus(BaseModel):
    """Response with current share status of a quiz."""

    quiz_id: UUID = Field(..., description="The quiz ID")
    is_public: bool = Field(..., description="Whether the quiz is currently public")
    public_slug: Optional[str] = Field(
        None, description="The slug if public, None otherwise"
    )
    share_url: Optional[str] = Field(
        None, description="Full URL if public, None otherwise"
    )
    shared_at: Optional[datetime] = Field(
        None, description="When shared, None if never shared"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "quiz_id": "550e8400-e29b-41d4-a716-446655440000",
                "is_public": True,
                "public_slug": "abc12xyz",
                "share_url": "https://quizify.app/quiz/abc12xyz",
                "shared_at": "2025-01-18T12:00:00Z",
            }
        }
    )


# ============================================================================
# Public Quiz View Schemas (for anonymous/unauthenticated access)
# ============================================================================


class PublicQuestionOption(BaseModel):
    """A single option for a public multiple-choice question."""

    id: str = Field(..., description="Option identifier (a, b, c, d)")
    text: str = Field(..., description="Option text")


class PublicMatchingPair(BaseModel):
    """A matching pair for public matching questions."""

    left: str = Field(..., description="Left side item")
    right: str = Field(..., description="Right side item (shuffled in display)")


class PublicQuestion(BaseModel):
    """A question as shown in public quiz view."""

    id: UUID = Field(..., description="Question ID")
    question_number: int = Field(..., description="Order in quiz")
    question_type: str = Field(..., description="Type: mcq, true_false, fill_blank, matching")
    question_text: str = Field(..., description="The question text")
    options: Optional[List[PublicQuestionOption]] = Field(
        None, description="Options for MCQ/true_false"
    )
    matching_pairs: Optional[List[PublicMatchingPair]] = Field(
        None, description="Pairs for matching questions (left side only for display)"
    )
    difficulty: Optional[str] = Field(None, description="easy, medium, hard")


class QuizPublicView(BaseModel):
    """
    Public view of a shared quiz.
    
    This is what anonymous users see when accessing a shared quiz link.
    Does NOT include answers/correct options to prevent cheating.
    """

    id: UUID = Field(..., description="Quiz ID")
    title: str = Field(..., description="Quiz title")
    description: Optional[str] = Field(None, description="Quiz description")
    topic: Optional[str] = Field(None, description="Quiz topic/subject")
    total_questions: int = Field(..., description="Number of questions")
    questions: List[PublicQuestion] = Field(..., description="Quiz questions")
    shared_at: datetime = Field(..., description="When quiz was shared")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "title": "Python Basics Quiz",
                "description": "Test your Python knowledge",
                "topic": "Programming",
                "total_questions": 10,
                "questions": [
                    {
                        "id": "660e8400-e29b-41d4-a716-446655440001",
                        "question_number": 1,
                        "question_type": "mcq",
                        "question_text": "What is Python?",
                        "options": [
                            {"id": "a", "text": "A snake"},
                            {"id": "b", "text": "A programming language"},
                            {"id": "c", "text": "A car brand"},
                            {"id": "d", "text": "A food"},
                        ],
                        "difficulty": "easy",
                    }
                ],
                "shared_at": "2025-01-18T12:00:00Z",
            }
        }
    )


# ============================================================================
# Public Quiz Submission Schemas (optional - for taking shared quizzes)
# ============================================================================


class PublicQuizAnswer(BaseModel):
    """A single answer submission for a public quiz."""

    question_id: UUID = Field(..., description="The question being answered")
    answer: str = Field(..., description="The submitted answer (option id or text)")


class PublicQuizSubmission(BaseModel):
    """Submission of answers for a public quiz."""

    answers: List[PublicQuizAnswer] = Field(
        ..., description="List of answers", min_length=1
    )


class PublicQuizResult(BaseModel):
    """Result of a public quiz submission (no storage, immediate feedback)."""

    quiz_id: UUID = Field(..., description="Quiz ID")
    total_questions: int = Field(..., description="Total questions in quiz")
    correct_answers: int = Field(..., description="Number of correct answers")
    score_percentage: float = Field(..., description="Score as percentage (0-100)")
    passed: bool = Field(..., description="Whether score meets passing threshold")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "quiz_id": "550e8400-e29b-41d4-a716-446655440000",
                "total_questions": 10,
                "correct_answers": 8,
                "score_percentage": 80.0,
                "passed": True,
            }
        }
    )
