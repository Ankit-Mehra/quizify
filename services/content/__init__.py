"""
Content services for unified content ingestion and processing.

This module provides a unified interface for extracting content from
various sources (text, files, URLs) that can be used by both Quiz
and Flashcard generation services.
"""

from services.content.ingestion_service import ContentIngestionService
from services.content.models import IngestedContent, ContentSourceType

__all__ = [
    "ContentIngestionService",
    "IngestedContent",
    "ContentSourceType",
]
