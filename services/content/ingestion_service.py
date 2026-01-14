"""
Unified Content Ingestion Service.

This service provides a single entry point for extracting content from
various sources (text, files, URLs). It consolidates logic previously
scattered across quiz_handlers.py and other modules.

The service returns standardized IngestedContent objects that can be
used by any downstream generation service (Quiz, Flashcard, etc.).
"""

from typing import Optional
from fastapi import UploadFile, HTTPException
from datetime import datetime

from services.content.models import (
    IngestedContent,
    ContentSourceType,
    ContentValidationError,
    ContentExtractionError,
)
from services.ai_services.doc_service import (
    extract_text_from_pdf,
    extract_text_from_docx,
    extract_text_from_plain_text,
    is_pdf,
)
from services.web_scraping_service import scrape_content
from services.logger import app_logger as logger


# Content validation constants
MIN_CONTENT_LENGTH = 50  # Minimum characters for generation
MAX_CONTENT_LENGTH = 500_000  # Maximum characters (~125k words)
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# Supported file extensions
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md", ".text"}


class ContentIngestionService:
    """
    Unified service for content ingestion from multiple sources.
    
    This service abstracts the complexity of extracting content from
    different sources (text, files, URLs) and provides a consistent
    interface for downstream services.
    
    Example usage:
        service = ContentIngestionService()
        
        # From text
        content = await service.ingest_text("Some educational content...")
        
        # From file
        content = await service.ingest_file(upload_file)
        
        # From URL
        content = await service.ingest_url("https://example.com/article", user_id, user_token)
        
        # Use content for generation
        flashcards = await flashcard_service.generate(content)
    """
    
    def __init__(
        self,
        min_content_length: int = MIN_CONTENT_LENGTH,
        max_content_length: int = MAX_CONTENT_LENGTH,
        max_file_size: int = MAX_FILE_SIZE,
    ):
        """
        Initialize the content ingestion service.
        
        Args:
            min_content_length: Minimum characters required for content
            max_content_length: Maximum characters allowed
            max_file_size: Maximum file size in bytes
        """
        self.min_content_length = min_content_length
        self.max_content_length = max_content_length
        self.max_file_size = max_file_size
    
    async def ingest_text(
        self,
        text: str,
        title: Optional[str] = None,
        validate: bool = True,
    ) -> IngestedContent:
        """
        Ingest content from direct text input.
        
        Args:
            text: The text content to ingest
            title: Optional title for the content
            validate: Whether to validate content length
            
        Returns:
            IngestedContent object with extracted text and metadata
            
        Raises:
            ContentValidationError: If content validation fails
        """
        logger.debug("Ingesting text content (length: %d chars)", len(text))
        
        # Clean and normalize text
        cleaned_text = self._normalize_text(text)
        
        if validate:
            self._validate_content_length(cleaned_text)
        
        word_count = len(cleaned_text.split())
        
        return IngestedContent(
            text=cleaned_text,
            source_type=ContentSourceType.TEXT,
            source_reference=None,
            title=title,
            word_count=word_count,
            char_count=len(cleaned_text),
            metadata={"input_type": "direct_text"},
            extracted_at=datetime.utcnow(),
        )
    
    async def ingest_file(
        self,
        file: UploadFile,
        validate: bool = True,
    ) -> IngestedContent:
        """
        Ingest content from an uploaded file.
        
        Supports PDF, DOCX, DOC, TXT, and MD files.
        
        Args:
            file: The uploaded file
            validate: Whether to validate content length
            
        Returns:
            IngestedContent object with extracted text and metadata
            
        Raises:
            ContentExtractionError: If file extraction fails
            ContentValidationError: If content validation fails
            HTTPException: If file type is not supported or file is too large
        """
        filename = file.filename or "unknown"
        logger.info("Ingesting file: %s", filename)
        
        # Validate file extension
        file_ext = self._get_file_extension(filename)
        if file_ext not in SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file_ext}. Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
            )
        
        # Read file contents
        try:
            contents = await file.read()
        except Exception as e:
            logger.error("Failed to read file %s: %s", filename, str(e))
            raise ContentExtractionError(
                message=f"Failed to read file: {str(e)}",
                source_type=ContentSourceType.FILE,
                original_error=e,
            )
        
        # Validate file size
        file_size = len(contents)
        if file_size > self.max_file_size:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size: {self.max_file_size // (1024 * 1024)}MB"
            )
        
        # Extract text based on file type
        try:
            extracted_text = self._extract_text_from_bytes(contents, file_ext)
        except Exception as e:
            logger.error("Failed to extract text from %s: %s", filename, str(e))
            raise ContentExtractionError(
                message=f"Failed to extract text from file: {str(e)}",
                source_type=ContentSourceType.FILE,
                original_error=e,
            )
        
        # Clean and normalize
        cleaned_text = self._normalize_text(extracted_text)
        
        if validate:
            self._validate_content_length(cleaned_text)
        
        word_count = len(cleaned_text.split())
        
        # Extract title from filename (remove extension)
        title = filename.rsplit(".", 1)[0] if "." in filename else filename
        
        return IngestedContent(
            text=cleaned_text,
            source_type=ContentSourceType.FILE,
            source_reference=None,  # Will be set after file is saved to storage
            title=title,
            word_count=word_count,
            char_count=len(cleaned_text),
            metadata={
                "filename": filename,
                "file_extension": file_ext,
                "file_size_bytes": file_size,
            },
            extracted_at=datetime.utcnow(),
        )
    
    async def ingest_file_bytes(
        self,
        contents: bytes,
        filename: str,
        validate: bool = True,
    ) -> IngestedContent:
        """
        Ingest content from file bytes directly.
        
        Useful when file is already loaded (e.g., from storage).
        
        Args:
            contents: The file contents as bytes
            filename: The filename (for extension detection)
            validate: Whether to validate content length
            
        Returns:
            IngestedContent object with extracted text and metadata
        """
        logger.info("Ingesting file bytes: %s", filename)
        
        file_ext = self._get_file_extension(filename)
        if file_ext not in SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file_ext}. Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
            )
        
        # Validate file size
        file_size = len(contents)
        if file_size > self.max_file_size:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size: {self.max_file_size // (1024 * 1024)}MB"
            )
        
        # Extract text
        try:
            extracted_text = self._extract_text_from_bytes(contents, file_ext)
        except Exception as e:
            logger.error("Failed to extract text from bytes: %s", str(e))
            raise ContentExtractionError(
                message=f"Failed to extract text: {str(e)}",
                source_type=ContentSourceType.FILE,
                original_error=e,
            )
        
        cleaned_text = self._normalize_text(extracted_text)
        
        if validate:
            self._validate_content_length(cleaned_text)
        
        word_count = len(cleaned_text.split())
        title = filename.rsplit(".", 1)[0] if "." in filename else filename
        
        return IngestedContent(
            text=cleaned_text,
            source_type=ContentSourceType.FILE,
            source_reference=None,
            title=title,
            word_count=word_count,
            char_count=len(cleaned_text),
            metadata={
                "filename": filename,
                "file_extension": file_ext,
                "file_size_bytes": file_size,
            },
            extracted_at=datetime.utcnow(),
        )
    
    async def ingest_url(
        self,
        url: str,
        user_id: str,
        user_token: str,
        validate: bool = True,
    ) -> IngestedContent:
        """
        Ingest content from a URL.
        
        Uses Playwright + Trafilatura for robust content extraction.
        Includes SSRF protection.
        
        Args:
            url: The URL to scrape
            user_id: User ID for browser slot management
            user_token: User token for authentication
            validate: Whether to validate content length
            
        Returns:
            IngestedContent object with extracted text and metadata
            
        Raises:
            ContentExtractionError: If URL scraping fails
            ContentValidationError: If content validation fails
            HTTPException: If URL is invalid or blocked
        """
        logger.info("Ingesting URL content for user %s...", user_id[:8])
        
        try:
            # Use existing web scraping service (includes SSRF protection)
            # scrape_content returns tuple: (extracted_text, file_info_dict or None)
            extracted_text, file_info = await scrape_content(url, user_id, user_token)
        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        except Exception as e:
            logger.error("Failed to scrape URL: %s", str(e))
            raise ContentExtractionError(
                message=f"Failed to extract content from URL: {str(e)}",
                source_type=ContentSourceType.URL,
                original_error=e,
            )
        
        # Extract file_id if PDF was saved
        file_id = file_info.get("file_id") if file_info else None
        # Current scraping pipeline does not provide a page title for HTML or PDF;
        # we keep this placeholder and fall back to URL-based title extraction.
        page_title = ""
        
        cleaned_text = self._normalize_text(extracted_text)
        
        if validate:
            self._validate_content_length(cleaned_text)
        
        word_count = len(cleaned_text.split())
        
        return IngestedContent(
            text=cleaned_text,
            source_type=ContentSourceType.URL,
            source_reference=url,  # Store the URL (consider redacting for storage)
            title=page_title or self._extract_title_from_url(url),
            word_count=word_count,
            char_count=len(cleaned_text),
            metadata={
                "original_url": url,
                "scraped_title": page_title,
                "file_id": file_id,  # If PDF was downloaded
            },
            extracted_at=datetime.utcnow(),
        )
    
    def _normalize_text(self, text: str) -> str:
        """
        Normalize and clean extracted text.
        
        - Strip leading/trailing whitespace
        - Normalize multiple spaces and newlines
        - Remove control characters
        """
        if not text:
            return ""
        
        # Strip and normalize whitespace
        text = text.strip()
        
        # Replace multiple whitespace with single space (except newlines)
        import re
        text = re.sub(r'[^\S\n]+', ' ', text)
        
        # Replace more than 2 consecutive newlines with 2
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Remove control characters (except newline, tab)
        text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', text)
        
        return text.strip()
    
    def _validate_content_length(self, text: str) -> None:
        """
        Validate that content meets length requirements.
        
        Raises:
            ContentValidationError: If content is too short or too long
        """
        if len(text) < self.min_content_length:
            raise ContentValidationError(
                message=f"Content too short. Minimum {self.min_content_length} characters required, got {len(text)}.",
                min_required=self.min_content_length,
            )
        
        if len(text) > self.max_content_length:
            raise ContentValidationError(
                message=f"Content too long. Maximum {self.max_content_length} characters allowed.",
            )
    
    def _get_file_extension(self, filename: str) -> str:
        """Extract and normalize file extension."""
        if "." not in filename:
            return ""
        return "." + filename.rsplit(".", 1)[-1].lower()
    
    def _extract_text_from_bytes(self, contents: bytes, file_ext: str) -> str:
        """
        Extract text from file bytes based on file extension.
        
        Args:
            contents: File contents as bytes
            file_ext: File extension (e.g., '.pdf', '.docx')
            
        Returns:
            Extracted text content
        """
        # Check if it's actually a PDF regardless of extension
        if is_pdf(contents):
            return extract_text_from_pdf(contents)
        
        if file_ext == ".pdf":
            return extract_text_from_pdf(contents)
        elif file_ext in {".docx", ".doc"}:
            return extract_text_from_docx(contents)
        elif file_ext in {".txt", ".md", ".text"}:
            return extract_text_from_plain_text(contents)
        else:
            # Fallback: try to decode as text
            return extract_text_from_plain_text(contents)
    
    def _extract_title_from_url(self, url: str) -> str:
        """Extract a human-readable title from URL."""
        from urllib.parse import urlparse, unquote
        
        parsed = urlparse(url)
        path = unquote(parsed.path)
        
        # Get the last path segment
        segments = [s for s in path.split("/") if s]
        if segments:
            title = segments[-1]
            # Remove file extension if present
            if "." in title:
                title = title.rsplit(".", 1)[0]
            # Replace hyphens and underscores with spaces
            title = title.replace("-", " ").replace("_", " ")
            return title.title()
        
        # Fallback to domain name
        return parsed.netloc


# Singleton instance for convenience
_content_ingestion_service: Optional[ContentIngestionService] = None


def get_content_ingestion_service() -> ContentIngestionService:
    """Get or create the singleton ContentIngestionService instance."""
    global _content_ingestion_service
    if _content_ingestion_service is None:
        _content_ingestion_service = ContentIngestionService()
    return _content_ingestion_service
