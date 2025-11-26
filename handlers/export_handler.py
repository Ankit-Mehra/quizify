"""
Export Handler - Business logic for quiz export operations.

This module implements the strategy pattern for quiz exports:
1. Validates user access and tier permissions
2. Loads quiz data
3. Dispatches to appropriate exporter based on format
4. Returns file download response or JSON (for share_link)
"""

from typing import Optional, Dict, Type
from fastapi import HTTPException
from fastapi.responses import Response, JSONResponse

from schemas.export import (
    ExportFormat,
    ExportRequest,
    ExportOptions,
    ExportResult,
    QuizExportData
)
from services.exporters.base import BaseExporter, ExportError, ExportNotImplementedError
from services.exporters.tier_validator import validate_export_tier_access
from services.exporters.quiz_loader import load_quiz_for_export
from services.logger import app_logger as logger


# ============================================================================
# Exporter Registry - Strategy Pattern Factory
# ============================================================================

# Registry of format -> exporter class
# Exporters are lazily imported to avoid circular dependencies
_EXPORTER_REGISTRY: Dict[ExportFormat, Type[BaseExporter]] = {}


def register_exporter(format: ExportFormat, exporter_class: Type[BaseExporter]):
    """
    Register an exporter class for a specific format.
    
    Called by each exporter module when imported.
    """
    _EXPORTER_REGISTRY[format] = exporter_class
    logger.debug(f"Registered exporter for format: {format.value}")


def get_exporter(format: ExportFormat) -> BaseExporter:
    """
    Get an exporter instance for the specified format.
    
    Args:
        format: The export format
        
    Returns:
        Exporter instance
        
    Raises:
        ExportNotImplementedError: If format has no registered exporter
    """
    # Lazy import exporters to populate registry
    _ensure_exporters_loaded()
    
    exporter_class = _EXPORTER_REGISTRY.get(format)
    
    if exporter_class is None:
        raise ExportNotImplementedError(format.value)
    
    return exporter_class()


def _ensure_exporters_loaded():
    """
    Ensure all exporter modules are imported.
    
    This lazy loading prevents circular imports while ensuring
    the registry is populated before use.
    """
    # Only import if registry is empty (first call)
    if not _EXPORTER_REGISTRY:
        # Import placeholder exporter for now
        # Real exporters will be added in subsequent epics
        _register_placeholder_exporters()


def _register_placeholder_exporters():
    """
    Register placeholder exporters for formats not yet implemented.
    
    These will be replaced with real implementations in subsequent epics.
    """
    from services.exporters.placeholder import PlaceholderExporter
    
    for format in ExportFormat:
        if format not in _EXPORTER_REGISTRY:
            # Create a placeholder that raises NotImplemented
            _EXPORTER_REGISTRY[format] = PlaceholderExporter


# ============================================================================
# Main Export Handler
# ============================================================================

async def handle_export(
    quiz_id: str,
    user_id: str,
    user_tier: str,
    request: ExportRequest,
    user_token: Optional[str] = None
) -> Response:
    """
    Handle a quiz export request.
    
    This is the main entry point for all export operations.
    It orchestrates validation, data loading, and export generation.
    
    Args:
        quiz_id: UUID of the quiz to export
        user_id: UUID of the requesting user
        user_tier: User's subscription tier ('free', 'basic', 'pro')
        request: Export request with format and options
        user_token: Optional JWT token for authenticated queries
        
    Returns:
        Response: File download response or JSON for share_link
        
    Raises:
        HTTPException 401: Not authenticated
        HTTPException 403: Quiz not owned or tier insufficient
        HTTPException 404: Quiz not found
        HTTPException 422: Invalid format
        HTTPException 500: Export failed
    """
    export_format = request.format if isinstance(request.format, ExportFormat) else ExportFormat(request.format)
    
    logger.info(f"Export request: quiz={quiz_id[:8]}..., format={export_format.value}, user={user_id[:8]}...")
    
    # Step 1: Validate tier access for the requested format
    try:
        validate_export_tier_access(user_tier, export_format)
    except HTTPException:
        logger.warning(f"Tier access denied: user={user_id[:8]}..., tier={user_tier}, format={export_format.value}")
        raise
    
    # Step 2: Load quiz data (validates ownership)
    try:
        quiz_data = await load_quiz_for_export(quiz_id, user_id, user_token)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to load quiz data: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load quiz data")
    
    # Step 3: Get appropriate exporter
    try:
        exporter = get_exporter(export_format)
    except ExportNotImplementedError as e:
        logger.warning(f"Export format not implemented: {export_format.value}")
        raise HTTPException(
            status_code=422,
            detail=f"Export format '{export_format.value}' is not yet available"
        )
    
    # Step 4: Prepare export options
    options = ExportOptions(
        include_answer_key=request.include_answer_key,
        include_explanations=request.include_explanations
    )
    
    # Step 5: Execute export
    try:
        result = await exporter.export(quiz_data, options)
    except ExportError as e:
        logger.error(f"Export failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Export failed: {e.message}")
    except Exception as e:
        logger.error(f"Unexpected export error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Export failed due to an unexpected error")
    
    # Step 6: Return appropriate response
    if export_format == ExportFormat.SHARE_LINK:
        # Share link returns JSON
        return JSONResponse(
            content={"share_url": result.filename},  # filename contains URL for share_link
            status_code=200
        )
    else:
        # File export returns download
        return Response(
            content=result.content,
            media_type=result.content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{result.filename}"',
                "Content-Length": str(len(result.content))
            }
        )


async def get_export_formats_for_user(user_tier: str) -> dict:
    """
    Get available export formats for a user based on their tier.
    
    Useful for frontend to display available/locked formats.
    
    Args:
        user_tier: User's subscription tier
        
    Returns:
        Dict with format availability info
    """
    from services.exporters.tier_validator import (
        is_format_available_for_tier,
        PRO_ONLY_FORMATS
    )
    
    formats = {}
    for fmt in ExportFormat:
        formats[fmt.value] = {
            "available": is_format_available_for_tier(user_tier, fmt),
            "requires_pro": fmt in PRO_ONLY_FORMATS,
            "name": _get_format_display_name(fmt)
        }
    
    return formats


def _get_format_display_name(format: ExportFormat) -> str:
    """Get human-readable name for export format."""
    names = {
        ExportFormat.PDF: "PDF Document",
        ExportFormat.DOCX: "Word Document (DOCX)",
        ExportFormat.CSV_QUIZIFY: "CSV (Quizify Native)",
        ExportFormat.CSV_ANKI: "CSV (Anki Flashcards)",
        ExportFormat.QTI: "QTI 2.1 (LMS)",
        ExportFormat.MOODLE_XML: "Moodle XML (LMS)",
        ExportFormat.SHARE_LINK: "Shareable Link"
    }
    return names.get(format, format.value)
