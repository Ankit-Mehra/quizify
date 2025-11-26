"""
Export Routes - API endpoints for quiz export functionality.

This module provides the REST API for exporting quizzes to various formats:
- PDF, DOCX, CSV (Quizify Native), CSV (Anki), Share Link - Basic & Pro tiers
- QTI 2.1, Moodle XML - Pro tier only
- Free tier has no export access

Authentication is required for all endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.responses import Response

from schemas.export import ExportRequest
from handlers.export_handler import handle_export, get_export_formats_for_user
from dependencies.auth_dependencies import (
    get_current_user_id,
    get_current_user_token
)
from services.db_services.supabase_quiz import get_user_tier_info
from services.logger import app_logger as logger


router = APIRouter(prefix="/quizzes", tags=["Quiz Export"])


@router.post(
    "/{quiz_id}/export",
    summary="Export Quiz",
    description="""
Export a quiz to the specified format.

**Supported Formats:**
- `pdf` - PDF document (printable quiz)
- `docx` - Word document (editable)
- `csv_quizify` - CSV (Quizify native format)
- `csv_anki` - CSV (Anki flashcard format)
- `qti` - QTI 2.1 XML (LMS import) - **Pro only**
- `moodle_xml` - Moodle XML (LMS import) - **Pro only**
- `share_link` - Generate shareable public link

**Options:**
- `include_answer_key` - Include answers in export (default: true)
- `include_explanations` - Include explanations (default: false)

**Responses:**
- File formats return binary download
- `share_link` returns JSON with `share_url`

**Error Codes:**
- 401: Not authenticated
- 403: Quiz not owned by user OR tier insufficient for LMS formats
- 404: Quiz not found
- 422: Invalid format or quiz has no questions
- 500: Export failed
    """,
    responses={
        200: {
            "description": "Export successful",
            "content": {
                "application/pdf": {},
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {},
                "text/csv": {},
                "application/xml": {},
                "application/json": {
                    "example": {"share_url": "https://app.quizify.ca/share/abc123"}
                }
            }
        },
        401: {"description": "Authentication required"},
        403: {"description": "Access denied (not owner or tier insufficient)"},
        404: {"description": "Quiz not found"},
        422: {"description": "Invalid format or empty quiz"},
        500: {"description": "Export failed"}
    }
)
async def export_quiz(
    request: ExportRequest,
    quiz_id: str = Path(..., description="UUID of the quiz to export"),
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token)
) -> Response:
    """
    Export a quiz to the specified format.
    
    Validates user ownership and tier access before generating export.
    """
    logger.info(f"Export request received: quiz={quiz_id[:8]}..., format={request.format}")
    
    # Get user's tier for access control
    try:
        tier_info = get_user_tier_info(user_id)
        user_tier = tier_info.get("account_tier", "free")
    except HTTPException:
        # If tier lookup fails, default to free (most restrictive)
        logger.warning(f"Could not fetch tier info for user {user_id[:8]}..., defaulting to free")
        user_tier = "free"
    
    # Delegate to handler
    return await handle_export(
        quiz_id=quiz_id,
        user_id=user_id,
        user_tier=user_tier,
        request=request,
        user_token=user_token
    )


@router.get(
    "/export/formats",
    summary="Get Available Export Formats",
    description="""
Get list of available export formats for the current user based on their subscription tier.

Returns all export formats with availability status and whether they require Pro tier.
Useful for frontend to display format options with proper tier indicators.
    """,
    response_model=dict,
    responses={
        200: {
            "description": "List of export formats with availability",
            "content": {
                "application/json": {
                    "example": {
                        "pdf": {"available": True, "requires_pro": False, "name": "PDF Document"},
                        "qti": {"available": False, "requires_pro": True, "name": "QTI 2.1 (LMS)"}
                    }
                }
            }
        }
    }
)
async def get_available_formats(
    user_id: str = Depends(get_current_user_id)
) -> dict:
    """
    Get available export formats for the current user.
    
    Returns format availability based on user's subscription tier.
    """
    # Get user's tier
    try:
        tier_info = get_user_tier_info(user_id)
        user_tier = tier_info.get("account_tier", "free")
    except HTTPException:
        user_tier = "free"
    
    return await get_export_formats_for_user(user_tier)
