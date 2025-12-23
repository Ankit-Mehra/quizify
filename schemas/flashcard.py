"""
Flashcard schemas for request/response models.

These schemas define the data structures for flashcard generation,
storage, and API responses.
"""

from typing import Optional, List, Literal
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field


# =============================================================================
# Flashcard Core Models
# =============================================================================

class FlashcardBase(BaseModel):
    """Base model for flashcard data."""
    front: str = Field(..., description="The question or prompt (front of card)")
    back: str = Field(..., description="The answer or response (back of card)")
    hint: Optional[str] = Field(None, description="Optional hint for difficult cards")


class FlashcardCreate(FlashcardBase):
    """Schema for creating a new flashcard."""
    deck_id: Optional[UUID] = Field(None, description="ID of the deck this card belongs to")


class Flashcard(FlashcardBase):
    """Full flashcard model with all fields."""
    id: UUID = Field(..., description="Unique identifier for the flashcard")
    deck_id: UUID = Field(..., description="ID of the deck this card belongs to")
    position: int = Field(0, description="Position in the deck for ordering")
    
    # Spaced Repetition fields (for future use)
    status: Literal["new", "learning", "review", "mastered"] = Field(
        "new", description="Current learning status"
    )
    ease_factor: float = Field(2.5, description="Ease factor for spaced repetition")
    interval_days: int = Field(0, description="Days until next review")
    repetitions: int = Field(0, description="Number of successful repetitions")
    next_review: Optional[datetime] = Field(None, description="Next scheduled review date")
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


# =============================================================================
# Deck Models
# =============================================================================

class DeckBase(BaseModel):
    """Base model for flashcard deck."""
    title: str = Field(..., description="Title of the deck")
    description: Optional[str] = Field(None, description="Description of the deck")


class DeckCreate(DeckBase):
    """Schema for creating a new deck."""
    pass


class Deck(DeckBase):
    """Full deck model with all fields."""
    id: UUID = Field(..., description="Unique identifier for the deck")
    created_by: UUID = Field(..., description="User who created the deck")
    card_count: int = Field(0, description="Number of cards in the deck")
    
    # Content source tracking (like quizzes)
    content_source_type: Optional[Literal["text", "file", "url"]] = Field(
        None, description="Source type of the content"
    )
    content_source_reference: Optional[str] = Field(
        None, description="Reference to the source (file_id, URL, etc.)"
    )
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    last_studied: Optional[datetime] = Field(None, description="Last time deck was studied")
    
    class Config:
        from_attributes = True


class DeckWithCards(Deck):
    """Deck model including all cards."""
    cards: List[Flashcard] = Field(default_factory=list, description="Cards in the deck")


# =============================================================================
# Generation Request Models
# =============================================================================

class FlashcardGenerationConfig(BaseModel):
    """Configuration options for flashcard generation."""
    num_cards: Optional[int] = Field(
        None, 
        ge=1, 
        le=100,
        description="Number of cards to generate. If None, auto-calculated from content length."
    )
    include_hints: bool = Field(False, description="Whether to include hints on cards")
    card_style: Literal["question_answer", "term_definition", "cloze", "mixed"] = Field(
        "mixed", description="Style of flashcards to generate"
    )
    difficulty: Literal["easy", "medium", "hard", "mixed"] = Field(
        "mixed", description="Difficulty level of cards"
    )


class TextFlashcardRequest(BaseModel):
    """Request for generating flashcards from text."""
    content: str = Field(..., min_length=50, description="Text content to generate flashcards from")
    title: Optional[str] = Field(None, description="Title for the deck")
    config: FlashcardGenerationConfig = Field(
        default_factory=FlashcardGenerationConfig,
        description="Generation configuration"
    )


class FileFlashcardRequest(BaseModel):
    """Request for generating flashcards from a file."""
    file_id: UUID = Field(..., description="ID of the uploaded file")
    title: Optional[str] = Field(None, description="Title for the deck")
    config: FlashcardGenerationConfig = Field(
        default_factory=FlashcardGenerationConfig,
        description="Generation configuration"
    )


class UrlFlashcardRequest(BaseModel):
    """Request for generating flashcards from a URL."""
    url: str = Field(..., description="URL to generate flashcards from")
    title: Optional[str] = Field(None, description="Title for the deck")
    config: FlashcardGenerationConfig = Field(
        default_factory=FlashcardGenerationConfig,
        description="Generation configuration"
    )


# =============================================================================
# Generation Response Models
# =============================================================================

class FlashcardGenerationResponse(BaseModel):
    """Response from flashcard generation."""
    deck_id: UUID = Field(..., description="ID of the created deck")
    deck_title: str = Field(..., description="Title of the created deck")
    cards: List[Flashcard] = Field(..., description="Generated flashcards")
    card_count: int = Field(..., description="Number of cards generated")
    
    # Generation metadata
    content_source_type: Literal["text", "file", "url"] = Field(..., description="Source type")
    generation_time_ms: int = Field(..., description="Time taken to generate in milliseconds")
    estimated_study_time_minutes: int = Field(
        ..., description="Estimated time to study all cards"
    )
    
    class Config:
        from_attributes = True


# =============================================================================
# Study Session Models
# =============================================================================

class CardReviewResult(BaseModel):
    """Result of reviewing a single card."""
    card_id: UUID = Field(..., description="ID of the card reviewed")
    result: Literal["again", "hard", "good", "easy"] = Field(
        ..., description="How well the user remembered the card"
    )
    time_spent_seconds: Optional[int] = Field(
        None, description="Time spent on this card"
    )


class StudySessionStart(BaseModel):
    """Request to start a study session."""
    deck_id: UUID = Field(..., description="ID of the deck to study")
    card_limit: Optional[int] = Field(
        None, ge=1, le=100, description="Maximum cards to study"
    )
    shuffle: bool = Field(True, description="Whether to shuffle the cards")
    filter_status: Optional[List[Literal["new", "learning", "review", "mastered"]]] = Field(
        None, description="Filter cards by status"
    )


class StudySessionResponse(BaseModel):
    """Response with cards for a study session."""
    session_id: UUID = Field(..., description="Unique session identifier")
    deck_id: UUID = Field(..., description="ID of the deck being studied")
    deck_title: str = Field(..., description="Title of the deck")
    cards: List[Flashcard] = Field(..., description="Cards to study in this session")
    total_cards: int = Field(..., description="Total cards in session")
    
    # Progress tracking
    new_count: int = Field(0, description="Number of new cards")
    learning_count: int = Field(0, description="Number of cards in learning")
    review_count: int = Field(0, description="Number of cards due for review")


class StudySessionComplete(BaseModel):
    """Request to complete a study session with results."""
    session_id: UUID = Field(..., description="Session identifier")
    results: List[CardReviewResult] = Field(..., description="Results for each card")


class StudySessionSummary(BaseModel):
    """Summary after completing a study session."""
    session_id: UUID
    deck_id: UUID
    cards_studied: int
    time_spent_seconds: int
    accuracy_percent: float
    cards_mastered: int
    cards_learning: int
    streak_days: int = Field(0, description="Current study streak")


# =============================================================================
# Update Models
# =============================================================================

class FlashcardUpdate(BaseModel):
    """Schema for updating a flashcard."""
    front: Optional[str] = Field(None, description="Updated front text")
    back: Optional[str] = Field(None, description="Updated back text")
    hint: Optional[str] = Field(None, description="Updated hint")


class DeckUpdate(BaseModel):
    """Schema for updating a deck."""
    title: Optional[str] = Field(None, description="Updated title")
    description: Optional[str] = Field(None, description="Updated description")


# =============================================================================
# AI Generation Schema (for LLM output parsing)
# =============================================================================

class GeneratedFlashcard(BaseModel):
    """Single flashcard generated by AI."""
    front: str = Field(..., description="Question or prompt")
    back: str = Field(..., description="Answer or response")
    hint: Optional[str] = Field(None, description="Optional hint")


class GeneratedFlashcards(BaseModel):
    """Collection of flashcards generated by AI."""
    cards: List[GeneratedFlashcard] = Field(..., description="Generated flashcards")
