"""
DEPRECATED: This module has been moved to services/content/rag_ingestion_service.py

This file is kept for backwards compatibility only.
Please update your imports to use:

    from services.content.rag_ingestion_service import RAGIngestionService
    
Or via the content module:

    from services.content import RAGIngestionService, get_rag_ingestion_service

The class has been renamed from IngestionService to RAGIngestionService to better
distinguish it from ContentIngestionService (which handles content extraction).

Migration:
- IngestionService -> RAGIngestionService
- services.ai_services.ingestion_service -> services.content.rag_ingestion_service
"""

import warnings

# Re-export from new location for backwards compatibility
from services.content.rag_ingestion_service import (
    RAGIngestionService,
    get_rag_ingestion_service,  # noqa: F401
)

# Backwards compatibility alias
IngestionService = RAGIngestionService

# Issue deprecation warning on import
warnings.warn(
    "services.ai_services.ingestion_service is deprecated. "
    "Use services.content.rag_ingestion_service instead.",
    DeprecationWarning,
    stacklevel=2
)
