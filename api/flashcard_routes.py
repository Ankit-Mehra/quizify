"""
Flashcard API Routes.

This module defines the FastAPI routes for flashcard operations,
including generation, deck management, card CRUD, and study sessions.
"""

from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Path, Body

from dependencies.auth_dependencies import get_current_user_id, get_current_user_token
from handlers.flashcard_handlers import (
    generate_flashcards_from_text,
    generate_flashcards_from_file,
    generate_flashcards_from_url,
    get_user_flashcard_decks,
    get_flashcard_deck,
    update_flashcard_deck,
    delete_flashcard_deck,
    update_single_flashcard,
    delete_single_flashcard,
    start_study_session,
    complete_flashcard_study_session,
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
    "/generate/file",
    response_model=FlashcardGenerationResponse,
    summary="Generate flashcards from file",
    description="Generate AI-powered flashcards from an uploaded file (PDF, DOCX, TXT)."
)
async def generate_from_file(
    request: FileFlashcardRequest,
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token),
):
    """Generate flashcards from an uploaded file."""
    return await generate_flashcards_from_file(request, user_id, user_token)


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
def list_decks(
    limit: int = Query(50, ge=1, le=100, description="Maximum decks to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token),
):
    """Get all flashcard decks for the current user."""
    return get_user_flashcard_decks(user_id, user_token, limit, offset)


@router.get(
    "/decks/{deck_id}",
    response_model=DeckWithCards,
    summary="Get flashcard deck",
    description="Get a specific flashcard deck with all its cards."
)
def get_deck_endpoint(
    deck_id: UUID = Path(..., description="ID of the deck"),
    include_cards: bool = Query(True, description="Include cards in response"),
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token),
):
    """Get a specific flashcard deck."""
    return get_flashcard_deck(str(deck_id), user_id, user_token, include_cards)


@router.patch(
    "/decks/{deck_id}",
    response_model=Deck,
    summary="Update flashcard deck",
    description="Update deck title or description."
)
def update_deck_endpoint(
    deck_id: UUID = Path(..., description="ID of the deck"),
    update_data: DeckUpdate = Body(...),
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token),
):
    """Update a flashcard deck."""
    return update_flashcard_deck(str(deck_id), user_id, user_token, update_data)


@router.delete(
    "/decks/{deck_id}",
    summary="Delete flashcard deck",
    description="Delete a deck and all its cards."
)
def delete_deck_endpoint(
    deck_id: UUID = Path(..., description="ID of the deck"),
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token),
):
    """Delete a flashcard deck."""
    return delete_flashcard_deck(str(deck_id), user_id, user_token)


# =============================================================================
# Flashcard CRUD Endpoints
# =============================================================================

@router.patch(
    "/cards/{card_id}",
    response_model=Flashcard,
    summary="Update flashcard",
    description="Update a flashcard's front, back, or hint text."
)
def update_card_endpoint(
    card_id: UUID = Path(..., description="ID of the flashcard"),
    update_data: FlashcardUpdate = Body(...),
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token),
):
    """Update a flashcard."""
    return update_single_flashcard(str(card_id), user_id, user_token, update_data)


@router.delete(
    "/cards/{card_id}",
    summary="Delete flashcard",
    description="Delete a single flashcard from a deck."
)
def delete_card_endpoint(
    card_id: UUID = Path(..., description="ID of the flashcard"),
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token),
):
    """Delete a flashcard."""
    return delete_single_flashcard(str(card_id), user_id, user_token)


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
def start_session_endpoint(
    request: StudySessionStart,
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token),
):
    """Start a new study session."""
    return start_study_session(request, user_id, user_token)


@router.post(
    "/study/complete",
    response_model=StudySessionSummary,
    summary="Complete study session",
    description="Complete a study session and update card progress "
                "based on review results."
)
def complete_session_endpoint(
    request: StudySessionComplete,
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token),
):
    """Complete a study session with results."""
    return complete_flashcard_study_session(request, user_id, user_token)
