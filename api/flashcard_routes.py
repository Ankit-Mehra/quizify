"""
Flashcard API Routes.

This module defines the FastAPI routes for flashcard operations,
including generation, deck management, card CRUD, and study sessions.
"""

from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Path, Body, UploadFile, File, Form
from fastapi.responses import Response

from dependencies.auth_dependencies import get_current_user_id, get_current_user_token
from handlers.flashcard_handlers import (
    generate_flashcards_from_text,
    generate_flashcards_from_file,
    generate_flashcards_from_file_upload,
    generate_flashcards_from_url,
    get_user_flashcard_decks,
    get_flashcard_deck,
    update_flashcard_deck,
    delete_flashcard_deck,
    update_single_flashcard,
    delete_single_flashcard,
    start_study_session,
    complete_flashcard_study_session,
    export_flashcard_deck,
)
from schemas.flashcard import (
    TextFlashcardRequest,
    FileFlashcardRequest,
    UrlFlashcardRequest,
    FlashcardGenerationResponse,
    Deck,
    DeckWithCards,
    DeckUpdate,
    Flashcard,
    FlashcardUpdate,
    StudySessionStart,
    StudySessionResponse,
    StudySessionComplete,
    StudySessionSummary,
)
from schemas.export import FlashcardExportRequest


router = APIRouter(prefix="/api/flashcards", tags=["flashcards"])


# =============================================================================
# Generation Endpoints
# =============================================================================

@router.post(
    "/generate/text",
    response_model=FlashcardGenerationResponse,
    summary="Generate flashcards from text",
    description="Generate AI-powered flashcards from text content. "
                "Supports configurable card count, style, and difficulty."
)
async def generate_from_text(
    request: TextFlashcardRequest,
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token),
):
    """Generate flashcards from direct text input."""
    return await generate_flashcards_from_text(request, user_id, user_token)


@router.post(
    "/generate/upload",
    response_model=FlashcardGenerationResponse,
    summary="Generate flashcards from direct file upload",
    description="Generate AI-powered flashcards from a file upload in a single step (PDF, DOCX, TXT)."
)
async def generate_from_upload(
    file: UploadFile = File(...),
    title: str = Form(...),
    card_count: int = Form(10),
    card_style: str = Form("mixed"),
    difficulty: str = Form("intermediate"),
    include_hints: bool = Form(True),
    mode: str = Form("standard"),
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token),
):
    """Generate flashcards from direct file upload (single-step)."""
    return await generate_flashcards_from_file_upload(
        file=file,
        title=title,
        card_count=card_count,
        card_style=card_style,
        difficulty=difficulty,
        include_hints=include_hints,
        mode=mode,
        user_id=user_id,
        user_token=user_token,
    )


@router.post(
    "/generate/file/{file_id}",
    response_model=FlashcardGenerationResponse,
    summary="Generate flashcards from file ID",
    description="Generate AI-powered flashcards from a previously uploaded file using its UUID."
)
async def generate_from_file(
    file_id: UUID = Path(..., description="UUID of the previously uploaded file"),
    request: FileFlashcardRequest = Body(...),
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token),
):
    """Generate flashcards from a previously uploaded file."""
    return await generate_flashcards_from_file(file_id, request, user_id, user_token)


@router.post(
    "/generate/url",
    response_model=FlashcardGenerationResponse,
    summary="Generate flashcards from URL",
    description="Generate AI-powered flashcards from web page content."
)
async def generate_from_url(
    request: UrlFlashcardRequest,
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token),
):
    """Generate flashcards from a URL."""
    return await generate_flashcards_from_url(request, user_id, user_token)


# =============================================================================
# Deck CRUD Endpoints
# =============================================================================

@router.get(
    "/decks",
    response_model=List[Deck],
    summary="List user's flashcard decks",
    description="Get all flashcard decks for the authenticated user."
)
async def list_decks(
    limit: int = Query(50, ge=1, le=100, description="Maximum decks to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token),
):
    """Get all flashcard decks for the current user."""
    return await get_user_flashcard_decks(user_id, user_token, limit, offset)


@router.get(
    "/decks/{deck_id}",
    response_model=DeckWithCards,
    summary="Get flashcard deck",
    description="Get a specific flashcard deck with its cards (paginated)."
)
async def get_deck_endpoint(
    deck_id: UUID = Path(..., description="ID of the deck"),
    include_cards: bool = Query(True, description="Include cards in response"),
    card_limit: int = Query(100, ge=1, le=500, description="Maximum cards to return"),
    card_offset: int = Query(0, ge=0, description="Offset for card pagination"),
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token),
):
    """Get a specific flashcard deck."""
    return await get_flashcard_deck(str(deck_id), user_id, user_token, include_cards, card_limit, card_offset)


@router.patch(
    "/decks/{deck_id}",
    response_model=Deck,
    summary="Update flashcard deck",
    description="Update deck title or description."
)
async def update_deck_endpoint(
    deck_id: UUID = Path(..., description="ID of the deck"),
    update_data: DeckUpdate = Body(...),
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token),
):
    """Update a flashcard deck."""
    return await update_flashcard_deck(str(deck_id), user_id, user_token, update_data)


@router.delete(
    "/decks/{deck_id}",
    summary="Delete flashcard deck",
    description="Delete a deck and all its cards."
)
async def delete_deck_endpoint(
    deck_id: UUID = Path(..., description="ID of the deck"),
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token),
):
    """Delete a flashcard deck."""
    return await delete_flashcard_deck(str(deck_id), user_id, user_token)


# =============================================================================
# Flashcard CRUD Endpoints
# =============================================================================

@router.patch(
    "/cards/{card_id}",
    response_model=Flashcard,
    summary="Update flashcard",
    description="Update a flashcard's front, back, or hint text."
)
async def update_card_endpoint(
    card_id: UUID = Path(..., description="ID of the flashcard"),
    update_data: FlashcardUpdate = Body(...),
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token),
):
    """Update a flashcard."""
    return await update_single_flashcard(str(card_id), user_id, user_token, update_data)


@router.delete(
    "/cards/{card_id}",
    summary="Delete flashcard",
    description="Delete a single flashcard from a deck."
)
async def delete_card_endpoint(
    card_id: UUID = Path(..., description="ID of the flashcard"),
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token),
):
    """Delete a flashcard."""
    return await delete_single_flashcard(str(card_id), user_id, user_token)


# =============================================================================
# Study Session Endpoints
# =============================================================================

@router.post(
    "/study/start",
    response_model=StudySessionResponse,
    summary="Start study session",
    description="Start a new study session for a deck. "
                "Returns cards to study based on filters."
)
async def start_session_endpoint(
    request: StudySessionStart,
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token),
):
    """Start a new study session."""
    return await start_study_session(request, user_id, user_token)


@router.post(
    "/study/complete",
    response_model=StudySessionSummary,
    summary="Complete study session",
    description="Complete a study session and update card progress "
                "based on review results."
)
async def complete_session_endpoint(
    request: StudySessionComplete,
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token),
):
    """Complete a study session with results."""
    return await complete_flashcard_study_session(request, user_id, user_token)


# =============================================================================
# Export Endpoints
# =============================================================================

@router.post(
    "/decks/{deck_id}/export",
    summary="Export flashcard deck",
    description="""
Export a flashcard deck to the specified format.

**Supported Formats:**
- `csv_anki` - Anki-compatible TSV format for importing to Anki
- `pdf` - Printable PDF flashcard sheets

**Options:**
- `include_hints` - Include hints in export (default: true)

**Returns:**
- Binary file download with appropriate Content-Type
    """,
    responses={
        200: {
            "description": "Export successful",
            "content": {
                "text/tab-separated-values": {},
                "application/pdf": {},
            }
        },
        401: {"description": "Authentication required"},
        403: {"description": "Access denied (not owner)"},
        404: {"description": "Deck not found"},
        422: {"description": "Invalid format or empty deck"},
    }
)
async def export_deck_endpoint(
    request: FlashcardExportRequest,
    deck_id: UUID = Path(..., description="UUID of the deck to export"),
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token),
) -> Response:
    """Export a flashcard deck to the specified format."""
    result = await export_flashcard_deck(
        deck_id=str(deck_id),
        format_type=request.format,
        include_hints=request.include_hints,
        _user_id=user_id,
        user_token=user_token,
    )
    
    return Response(
        content=result.content,
        media_type=result.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{result.filename}"'
        }
    )
