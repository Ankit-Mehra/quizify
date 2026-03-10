"""
Export Schemas - Request/Response models for quiz export functionality.

This module defines the Pydantic models for the export API including:
- Export format enum
- Export request/response schemas
- Internal quiz data models for export processing
"""

from enum import Enum
from typing import List, Optional, Literal, Union, Dict
from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID
from datetime import datetime


class ExportFormat(str, Enum):
    """
    Supported export formats.
    
    Tier Access (UPDATED December 2025):
    - All tiers: All formats available (PDF, DOCX, CSV, QTI, Moodle XML, Google Forms, Share Link)
    
    Export is free for quiz owners. The only gating is on quiz generation (credits).
    If a user generated a quiz with their credits, they can export it in any format.
    """
    PDF = "pdf"
    DOCX = "docx"
    CSV_QUIZIFY = "csv_quizify"
    CSV_ANKI = "csv_anki"
    QTI = "qti"
    MOODLE_XML = "moodle_xml"
    SHARE_LINK = "share_link"
    GOOGLE_FORMS = "google_forms"


class FlashcardExportFormat(str, Enum):
    """
    Supported flashcard export formats.
    
    All formats available to all tiers who own the deck.
    """
    CSV_ANKI = "csv_anki"  # Anki-compatible TSV format
    PDF = "pdf"            # Printable flashcard sheets


# NOTE: Tier access constants (PRO_ONLY_FORMATS, PAID_TIER_FORMATS) are defined in
# services.exporters.tier_validator - that is the single source of truth for tier gating.
# Do not define duplicate constants here to avoid configuration drift.


class ExportRequest(BaseModel):
    """Request body for quiz export endpoint."""
    model_config = ConfigDict(use_enum_values=True)
    
    format: ExportFormat = Field(
        ..., 
        description="Export format to generate"
    )
    include_answer_key: bool = Field(
        default=True,
        description="Whether to include answer key in the export"
    )
    include_explanations: bool = Field(
        default=False,
        description="Whether to include explanations for each answer"
    )
    redirect_url: Optional[str] = Field(
        default=None,
        description=(
            "URL to redirect back to after Google OAuth completes. "
            "Only used for google_forms format when OAuth is required. "
            "Must be a relative path starting with '/' (e.g., '/quizzes/123')."
        )
    )


class ExportResponse(BaseModel):
    """Response for share_link export format."""
    share_url: str = Field(
        ...,
        description="Public URL to access the shared quiz"
    )


class TierInsufficientError(BaseModel):
    """Error response when user's tier doesn't allow the requested export format."""
    error: Literal["tier_insufficient"] = "tier_insufficient"
    message: str = Field(
        default="Pro features (QTI, Moodle XML, Google Forms) require a Pro subscription"
    )
    required_tier: Literal["pro"] = "pro"
    current_tier: str
    upgrade_url: str = Field(default="/billing/upgrade")


# ============================================================================
# Internal Models for Export Processing
# ============================================================================

class ExportQuestionMCQ(BaseModel):
    """MCQ question data for export."""
    id: UUID
    type: Literal["multiple_choice"]
    question: str
    options: List[str]
    correct_answer: str
    explanation: Optional[str] = None
    distractor_explanations: Optional[Dict[str, str]] = None
    source: Optional[str] = None


class ExportQuestionTrueFalse(BaseModel):
    """True/False question data for export."""
    id: UUID
    type: Literal["true_false"]
    question: str
    correct_answer: bool
    explanation: Optional[str] = None
    source: Optional[str] = None


class ExportQuestionFillBlank(BaseModel):
    """Fill-in-the-blank question data for export."""
    id: UUID
    type: Literal["fill_blank"]
    question: str
    options: List[str]  # Word bank
    correct_answer: str
    explanation: Optional[str] = None
    distractor_explanations: Optional[Dict[str, str]] = None
    source: Optional[str] = None


class ExportQuestionMatching(BaseModel):
    """Matching question data for export."""
    id: UUID
    type: Literal["matching"]
    question: str
    left: List[str]
    right: List[str]
    correct_answer: List[int]  # Indices mapping left to right
    explanation: Optional[str] = None
    source: Optional[str] = None


# Union type for all question types
ExportQuestion = Union[
    ExportQuestionMCQ,
    ExportQuestionTrueFalse,
    ExportQuestionFillBlank,
    ExportQuestionMatching
]


class QuizExportData(BaseModel):
    """
    Complete quiz data prepared for export.
    
    This is the internal model used by all exporters.
    It contains all quiz and question data needed for any export format.
    """
    model_config = ConfigDict(from_attributes=True)
    
    # Quiz metadata
    quiz_id: UUID
    title: str
    description: Optional[str] = None
    created_at: datetime
    
    # Content source info
    content_source_type: Optional[str] = None  # 'file', 'url', 'text'
    content_source_reference: Optional[str] = None
    
    # Questions
    questions: List[ExportQuestion]
    
    # Computed properties
    @property
    def question_count(self) -> int:
        return len(self.questions)
    
    @property
    def has_mcq(self) -> bool:
        return any(q.type == "multiple_choice" for q in self.questions)
    
    @property
    def has_true_false(self) -> bool:
        return any(q.type == "true_false" for q in self.questions)
    
    @property
    def has_fill_blank(self) -> bool:
        return any(q.type == "fill_blank" for q in self.questions)
    
    @property
    def has_matching(self) -> bool:
        return any(q.type == "matching" for q in self.questions)


class ExportOptions(BaseModel):
    """Options passed to exporters."""
    include_answer_key: bool = True
    include_explanations: bool = False


class ExportResult(BaseModel):
    """Result returned by an exporter."""
    content: bytes = Field(..., description="File content as bytes")
    content_type: str = Field(..., description="MIME type of the content")
    filename: Optional[str] = Field(None, description="Suggested filename for download (None for non-file exports)")
    share_url: Optional[str] = Field(None, description="Share URL for share_link exports")
    # Google Forms specific fields
    form_url: Optional[str] = Field(None, description="Google Forms responder URL")
    edit_url: Optional[str] = Field(None, description="Google Forms edit URL")
    form_id: Optional[str] = Field(None, description="Google Forms ID")
    questions_exported: Optional[int] = Field(None, description="Number of questions exported")
    questions_skipped: Optional[int] = Field(None, description="Number of questions skipped")
    warnings: Optional[List[str]] = Field(None, description="Warnings during export")
    
    model_config = ConfigDict(arbitrary_types_allowed=True)


# =============================================================================
# Flashcard Export Models
# =============================================================================

class FlashcardExportRequest(BaseModel):
    """Request body for flashcard deck export endpoint."""
    model_config = ConfigDict(use_enum_values=True)
    
    format: FlashcardExportFormat = Field(
        ..., 
        description="Export format to generate"
    )
    include_hints: bool = Field(
        default=True,
        description="Whether to include hints in the export"
    )


class ExportFlashcard(BaseModel):
    """Flashcard data for export."""
    id: UUID
    front: str
    back: str
    hint: Optional[str] = None


class FlashcardDeckExportData(BaseModel):
    """
    Complete flashcard deck data prepared for export.
    
    This is the internal model used by flashcard exporters.
    """
    model_config = ConfigDict(from_attributes=True)
    
    # Deck metadata
    deck_id: UUID
    title: str
    description: Optional[str] = None
    created_at: datetime
    
    # Content source info
    content_source_type: Optional[str] = None  # 'file', 'url', 'text'
    content_source_reference: Optional[str] = None
    
    # Flashcards
    cards: List[ExportFlashcard]
    
    @property
    def card_count(self) -> int:
        return len(self.cards)


class GoogleFormsExportResponse(BaseModel):
    """Response for google_forms export format."""
    form_url: str = Field(..., description="Google Forms URL for responders")
    edit_url: str = Field(..., description="Google Forms URL for editing")
    form_id: str = Field(..., description="Google Forms unique ID")
    questions_exported: int = Field(default=0, description="Number of questions exported")
    questions_skipped: int = Field(default=0, description="Number of questions skipped")
    warnings: Optional[List[str]] = Field(None, description="Warnings about skipped questions")


class GoogleAuthRequiredResponse(BaseModel):
    """Response when Google OAuth is required for export."""
    error: Literal["google_auth_required"] = "google_auth_required"
    message: str = Field(
        default="Please connect your Google account to export to Google Forms"
    )
    auth_url: str = Field(..., description="URL to initiate Google OAuth")
    current_tier: str = Field(..., description="User's current tier")
