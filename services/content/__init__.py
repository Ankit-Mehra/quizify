"""
Content services for unified content ingestion and processing.

This module provides:
1. ContentIngestionService - Extracts content from various sources (text, files, URLs)
2. RAGIngestionService - Processes extracted content into chunks and embeddings for RAG

ContentIngestionService is the entry point for raw content, while RAGIngestionService
handles the downstream processing for retrieval-augmented generation.
"""

from services.content.ingestion_service import ContentIngestionService, get_content_ingestion_service
from services.content.rag_ingestion_service import RAGIngestionService, get_rag_ingestion_service
from services.content.models import (
    IngestedContent,
    ContentSourceType,
    ContentValidationError,
    ContentExtractionError,
)

__all__ = [
    # Content extraction
    "ContentIngestionService",
    "get_content_ingestion_service",
    # RAG pipeline (chunking + embeddings)
    "RAGIngestionService",
    "get_rag_ingestion_service",
    # Models
    "IngestedContent",
    "ContentSourceType",
    "ContentValidationError",
    "ContentExtractionError",
]
