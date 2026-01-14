"""
Data models for content ingestion.

These models provide a standardized interface for content that has been
extracted from various sources (text input, file upload, URL scraping).
"""

from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class ContentSourceType(str, Enum):
    """Enumeration of supported content source types."""
    TEXT = "text"
    FILE = "file"
    URL = "url"


class IngestedContent(BaseModel):
    """
    Standardized representation of ingested content.
    
    This model is the output of the ContentIngestionService and serves
    as the input for generation services (Quiz, Flashcard, etc.).
    
    Attributes:
        text: The extracted text content
        source_type: The type of source (text, file, url)
        source_reference: Reference to the original source (file_id, URL, or None for text)
        title: Optional title for the content (from filename, page title, or user input)
        word_count: Number of words in the content
        char_count: Number of characters in the content
        metadata: Additional metadata about the content
        extracted_at: Timestamp when the content was extracted
    """
    text: str = Field(..., description="The extracted text content")
    source_type: ContentSourceType = Field(..., description="Type of content source")
    source_reference: Optional[str] = Field(None, description="Reference to original source")
    title: Optional[str] = Field(None, description="Content title")
    word_count: int = Field(0, description="Number of words")
    char_count: int = Field(0, description="Number of characters")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    extracted_at: datetime = Field(default_factory=datetime.utcnow, description="Extraction timestamp")
    
    @property
    def is_empty(self) -> bool:
        """Check if the content is empty or whitespace-only."""
        return not self.text or not self.text.strip()
    
    @property
    def estimated_flashcard_count(self) -> int:
        """Estimate number of flashcards based on content length (~1 card per 100 words)."""
        return max(1, self.word_count // 100)
    
    @property
    def estimated_quiz_questions(self) -> int:
        """Estimate number of quiz questions based on content length (~1 question per 150 words)."""
        return max(1, self.word_count // 150)
    
    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ContentValidationError(Exception):
    """Raised when content validation fails."""
    
    def __init__(self, message: str, min_required: Optional[int] = None):
        self.message = message
        self.min_required = min_required
        super().__init__(self.message)


class ContentExtractionError(Exception):
    """Raised when content extraction fails."""
    
    def __init__(self, message: str, source_type: ContentSourceType, original_error: Optional[Exception] = None):
        self.message = message
        self.source_type = source_type
        self.original_error = original_error
        super().__init__(self.message)
