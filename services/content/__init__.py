"""
Content services for unified content ingestion and processing.

This module provides a unified interface for extracting content from
various sources (text, files, URLs) that can be used by both Quiz
and Flashcard generation services.
"""

from services.content.ingestion_service import ContentIngestionService, get_content_ingestion_service
from services.content.models import (
    IngestedContent,
    ContentSourceType,
    ContentValidationError,
    ContentExtractionError,
)

__all__ = [
    "ContentIngestionService",
    "get_content_ingestion_service",
    "IngestedContent",
    "ContentSourceType",
    "ContentValidationError",
    "ContentExtractionError",
]
