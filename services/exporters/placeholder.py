"""
Placeholder Exporter - Temporary implementation for formats not yet built.

This exporter raises ExportNotImplementedError for all exports.
It serves as a placeholder until real exporters are implemented in subsequent epics.
"""

from schemas.export import QuizExportData, ExportOptions, ExportResult
from services.exporters.base import BaseExporter, ExportNotImplementedError


class PlaceholderExporter(BaseExporter):
    """
    Placeholder exporter for formats not yet implemented.
    
    This is used by the exporter registry for formats that don't
    have a real implementation yet. It always raises an error
    indicating the format is not available.
    """
    
    FORMAT_NAME = "placeholder"
    CONTENT_TYPE = "application/octet-stream"
    FILE_EXTENSION = ""
    
    async def export(
        self, 
        quiz_data: QuizExportData, 
        options: ExportOptions
    ) -> ExportResult:
        """
        Raises ExportNotImplementedError.
        
        This method is never expected to succeed - it exists only
        to satisfy the abstract interface requirement.
        """
        raise ExportNotImplementedError(self.FORMAT_NAME)
