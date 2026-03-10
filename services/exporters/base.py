"""
Base Exporter Interface - Abstract base class for all export formats.

This module defines the strategy pattern interface for quiz exporters.
Each export format (PDF, DOCX, CSV, etc.) implements this interface.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from schemas.export import QuizExportData, ExportOptions, ExportResult


class BaseExporter(ABC):
    """
    Abstract base class for quiz exporters.
    
    All export format implementations must inherit from this class
    and implement the export() method.
    
    Example usage:
        exporter = PdfExporter()
        result = await exporter.export(quiz_data, options)
        # result.content contains the file bytes
        # result.content_type is the MIME type
        # result.filename is the suggested filename
    """
    
    # Override in subclasses
    FORMAT_NAME: str = "base"
    CONTENT_TYPE: str = "application/octet-stream"
    FILE_EXTENSION: str = ""
    
    @abstractmethod
    async def export(
        self, 
        quiz_data: "QuizExportData", 
        options: "ExportOptions"
    ) -> "ExportResult":
        """
        Export quiz data to the specific format.
        
        Args:
            quiz_data: Complete quiz data including all questions
            options: Export options (include_answer_key, include_explanations)
            
        Returns:
            ExportResult containing file bytes, content type, and filename
            
        Raises:
            ExportError: If export fails for any reason
        """
        pass
    
    def generate_filename(self, quiz_title: str) -> str:
        """
        Generate a safe filename for the export.
        
        Args:
            quiz_title: The quiz title to use in the filename
            
        Returns:
            Safe filename with appropriate extension
        """
        # Sanitize title for filename
        safe_title = self._sanitize_filename(quiz_title)
        return f"{safe_title}.{self.FILE_EXTENSION}"
    
    @staticmethod
    def _sanitize_filename(title: str, max_length: int = 50) -> str:
        """
        Sanitize a string for use as a filename.
        
        Args:
            title: Original title
            max_length: Maximum length of the sanitized string
            
        Returns:
            Sanitized filename-safe string
        """
        # Replace spaces with hyphens
        safe = title.replace(" ", "-")
        
        # Remove or replace unsafe characters
        unsafe_chars = '<>:"/\\|?*'
        for char in unsafe_chars:
            safe = safe.replace(char, "")
        
        # Remove multiple consecutive hyphens
        while "--" in safe:
            safe = safe.replace("--", "-")
        
        # Strip leading/trailing hyphens
        safe = safe.strip("-")
        
        # Truncate if too long
        if len(safe) > max_length:
            safe = safe[:max_length].rstrip("-")
        
        # Fallback if empty
        if not safe:
            safe = "quiz-export"
        
        return safe.lower()


class ExportError(Exception):
    """Exception raised when export fails."""
    
    def __init__(self, message: str, format_name: str = "unknown"):
        self.message = message
        self.format_name = format_name
        super().__init__(f"Export failed ({format_name}): {message}")


class GoogleConnectionRequiredError(ExportError):
    """Exception raised when Google Forms export requires OAuth connection."""
    
    def __init__(self):
        super().__init__(
            message="Google account connection required",
            format_name="google_forms"
        )


class ExportNotImplementedError(ExportError):
    """Exception raised when an export format is not yet implemented."""
    
    def __init__(self, format_name: str):
        super().__init__(
            message=f"Export format '{format_name}' is not yet implemented",
            format_name=format_name
        )
