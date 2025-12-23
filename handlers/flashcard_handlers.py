"""
Flashcard Handlers.

This module contains the business logic for flashcard operations,
following the same patterns as quiz_handlers.py.
"""

import time
from typing import List, Dict, Any
from uuid import uuid4
from fastapi import HTTPException

from services.content.ingestion_service import get_content_ingestion_service
from services.content.models import ContentSourceType, ContentValidationError, ContentExtractionError
from services.ai_services.flashcard_service import get_flashcard_generation_service, FlashcardGenerationError, FlashcardParseError
from services.db_services.supabase_flashcard import (
    create_deck,
    get_deck,
    get_user_decks,
    update_deck,
    delete_deck,
    create_flashcards_batch,
    get_deck_cards,
    update_flashcard,
    delete_flashcard,
    update_card_review,
    create_study_session,
    complete_study_session,
)
from services.db_services.supabase_file import get_file_record, parse_file_from_supabase_async
from services.billing_service import consume_units, get_billing_state, refund_units
from services.url_utils import redact_url_for_storage
from services.logger import app_logger as logger
from schemas.flashcard import (
    TextFlashcardRequest,
    FileFlashcardRequest,
    UrlFlashcardRequest,
    FlashcardGenerationResponse,
    Flashcard,
    Deck,
    DeckWithCards,
    FlashcardUpdate,
    DeckUpdate,
    StudySessionStart,
    StudySessionResponse,
    StudySessionComplete,
    StudySessionSummary,
)


# =============================================================================
# Flashcard Generation Handlers
# =============================================================================

async def generate_flashcards_from_text(
    request: TextFlashcardRequest,
    user_id: str,
    user_token: str,
) -> FlashcardGenerationResponse:
    """
    Generate flashcards from text content.
    
    Args:
        request: Text flashcard request with content and config
        user_id: ID of the requesting user
        user_token: JWT token for RLS enforcement
        
    Returns:
        FlashcardGenerationResponse with generated deck and cards
    """
    start_time = time.time()
    trace_id = str(uuid4())
    
    logger.info(
        "Generating flashcards from text for user %s..., trace: %s",
        user_id[:8], trace_id[:8]
    )
    
    # 1. Validate credits/quota (use "standard" type - 1 unit like standard quiz)
    billing_state = await get_billing_state(user_id)
    if billing_state.available_credits < 1:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "insufficient_credits",
                "message": "Not enough credits for flashcard generation.",
                "available_credits": billing_state.available_credits,
                "required_credits": 1,
                "plan": billing_state.plan
            }
        )
    
    # 2. Ingest content
    ingestion_service = get_content_ingestion_service()
    try:
        content = await ingestion_service.ingest_text(
            text=request.content,
            title=request.title,
        )
    except ContentValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)
    
    # 3. Consume credits (use "standard" - 1 unit for flashcard generation)
    success = await consume_units(user_id, "standard")
    if not success:
        raise HTTPException(
            status_code=402,
            detail="Failed to consume credits for flashcard generation"
        )
    
    # 4. Generate flashcards
    try:
        generation_service = get_flashcard_generation_service()
        generated_cards = await generation_service.generate(
            content=content,
            generation_config=request.config,
            user_id=user_id,
            trace_id=trace_id,
        )
    except (FlashcardGenerationError, FlashcardParseError) as e:
        # Refund credit on generation failure
        await refund_units(user_id, "standard")
        logger.error("Flashcard generation failed: %s", e.message)
        raise HTTPException(status_code=500, detail=e.message)
    
    # 5. Create deck and save cards to database
    title = request.title or f"Flashcards - {content.word_count} words"
    
    deck_data = create_deck(
        user_id=user_id,
        title=title,
        user_token=user_token,
        content_source_type="text",
        content_source_reference=None,
    )
    
    saved_cards = create_flashcards_batch(
        deck_id=deck_data["id"],
        cards=generated_cards,
        user_token=user_token,
    )
    
    # 6. Build response
    elapsed_ms = int((time.time() - start_time) * 1000)
    estimated_study_time = len(saved_cards) // 3  # ~3 cards per minute
    
    response_cards = [
        Flashcard(
            id=c["id"],
            deck_id=c["deck_id"],
            front=c["front"],
            back=c["back"],
            hint=c.get("hint"),
            position=c.get("position", 0),
            status=c.get("status", "new"),
            ease_factor=float(c.get("ease_factor", 2.5)),
            interval_days=c.get("interval_days", 0),
            repetitions=c.get("repetitions", 0),
            next_review=c.get("next_review"),
            created_at=c.get("created_at"),
            updated_at=c.get("updated_at"),
        )
        for c in saved_cards
    ]
    
    logger.info(
        "Generated %d flashcards in %dms for user %s...",
        len(response_cards), elapsed_ms, user_id[:8]
    )
    
    return FlashcardGenerationResponse(
        deck_id=deck_data["id"],
        deck_title=title,
        cards=response_cards,
        card_count=len(response_cards),
        content_source_type="text",
        generation_time_ms=elapsed_ms,
        estimated_study_time_minutes=max(1, estimated_study_time),
    )


async def generate_flashcards_from_file(
    request: FileFlashcardRequest,
    user_id: str,
    user_token: str,
) -> FlashcardGenerationResponse:
    """
    Generate flashcards from an uploaded file.
    
    Args:
        request: File flashcard request with file_id and config
        user_id: ID of the requesting user
        user_token: JWT token for RLS enforcement
        
    Returns:
        FlashcardGenerationResponse with generated deck and cards
    """
    start_time = time.time()
    trace_id = str(uuid4())
    
    logger.info(
        "Generating flashcards from file %s for user %s..., trace: %s",
        str(request.file_id), user_id[:8], trace_id[:8]
    )
    
    # 1. Validate credits
    billing_state = await get_billing_state(user_id)
    if billing_state.available_credits < 1:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "insufficient_credits",
                "message": "Not enough credits for flashcard generation.",
                "available_credits": billing_state.available_credits,
                "required_credits": 1,
                "plan": billing_state.plan
            }
        )
    
    # 2. Get file record and parse content
    file_record = get_file_record(str(request.file_id), user_id, user_token)
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    
    file_content = await parse_file_from_supabase_async(
        str(request.file_id),
        user_id,
        user_token
    )
    
    if not file_content or len(file_content.strip()) < 50:
        raise HTTPException(
            status_code=400,
            detail="File contains insufficient text content"
        )
    
    # 3. Ingest content
    ingestion_service = get_content_ingestion_service()
    try:
        content = await ingestion_service.ingest_text(
            text=file_content,
            title=request.title or file_record.get("file_name", "Untitled"),
        )
        content.source_type = ContentSourceType.FILE
        content.source_reference = str(request.file_id)
    except ContentValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)
    
    # 4. Consume credits
    success = await consume_units(user_id, "standard")
    if not success:
        raise HTTPException(
            status_code=402,
            detail="Failed to consume credits for flashcard generation"
        )
    
    # 5. Generate flashcards
    try:
        generation_service = get_flashcard_generation_service()
        generated_cards = await generation_service.generate(
            content=content,
            generation_config=request.config,
            user_id=user_id,
            trace_id=trace_id,
        )
    except (FlashcardGenerationError, FlashcardParseError) as e:
        await refund_units(user_id, "standard")
        logger.error("Flashcard generation failed: %s", e.message)
        raise HTTPException(status_code=500, detail=e.message)
    
    # 6. Create deck and save cards
    title = request.title or file_record.get("file_name", "Flashcards")
    if title.endswith(('.pdf', '.docx', '.txt', '.md')):
        title = title.rsplit('.', 1)[0]
    
    deck_data = create_deck(
        user_id=user_id,
        title=title,
        user_token=user_token,
        content_source_type="file",
        content_source_reference=str(request.file_id),
    )
    
    saved_cards = create_flashcards_batch(
        deck_id=deck_data["id"],
        cards=generated_cards,
        user_token=user_token,
    )
    
    # 7. Build response
    elapsed_ms = int((time.time() - start_time) * 1000)
    estimated_study_time = len(saved_cards) // 3
    
    response_cards = [
        Flashcard(
            id=c["id"],
            deck_id=c["deck_id"],
            front=c["front"],
            back=c["back"],
            hint=c.get("hint"),
            position=c.get("position", 0),
            status=c.get("status", "new"),
            ease_factor=float(c.get("ease_factor", 2.5)),
            interval_days=c.get("interval_days", 0),
            repetitions=c.get("repetitions", 0),
            next_review=c.get("next_review"),
            created_at=c.get("created_at"),
            updated_at=c.get("updated_at"),
        )
        for c in saved_cards
    ]
    
    logger.info(
        "Generated %d flashcards from file in %dms for user %s...",
        len(response_cards), elapsed_ms, user_id[:8]
    )
    
    return FlashcardGenerationResponse(
        deck_id=deck_data["id"],
        deck_title=title,
        cards=response_cards,
        card_count=len(response_cards),
        content_source_type="file",
        generation_time_ms=elapsed_ms,
        estimated_study_time_minutes=max(1, estimated_study_time),
    )


async def generate_flashcards_from_url(
    request: UrlFlashcardRequest,
    user_id: str,
    user_token: str,
) -> FlashcardGenerationResponse:
    """
    Generate flashcards from a URL.
    
    Args:
        request: URL flashcard request with url and config
        user_id: ID of the requesting user
        user_token: JWT token for RLS enforcement
        
    Returns:
        FlashcardGenerationResponse with generated deck and cards
    """
    start_time = time.time()
    trace_id = str(uuid4())
    
    logger.info(
        "Generating flashcards from URL for user %s..., trace: %s",
        user_id[:8], trace_id[:8]
    )
    
    # 1. Validate credits
    billing_state = await get_billing_state(user_id)
    if billing_state.available_credits < 1:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "insufficient_credits",
                "message": "Not enough credits for flashcard generation.",
                "available_credits": billing_state.available_credits,
                "required_credits": 1,
                "plan": billing_state.plan
            }
        )
    
    # 2. Ingest content from URL
    ingestion_service = get_content_ingestion_service()
    try:
        content = await ingestion_service.ingest_url(
            url=request.url,
            user_id=user_id,
            user_token=user_token,
        )
    except ContentValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except ContentExtractionError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except HTTPException:
        raise  # Re-raise HTTP exceptions from scraping
    
    # 3. Consume credits
    success = await consume_units(user_id, "standard")
    if not success:
        raise HTTPException(
            status_code=402,
            detail="Failed to consume credits for flashcard generation"
        )
    
    # 4. Generate flashcards
    try:
        generation_service = get_flashcard_generation_service()
        generated_cards = await generation_service.generate(
            content=content,
            generation_config=request.config,
            user_id=user_id,
            trace_id=trace_id,
        )
    except (FlashcardGenerationError, FlashcardParseError) as e:
        await refund_units(user_id, "standard")
        logger.error("Flashcard generation failed: %s", e.message)
        raise HTTPException(status_code=500, detail=e.message)
    
    # 5. Create deck and save cards
    title = request.title or content.title or "Flashcards from URL"
    redacted_url = redact_url_for_storage(request.url)
    
    deck_data = create_deck(
        user_id=user_id,
        title=title,
        user_token=user_token,
        content_source_type="url",
        content_source_reference=redacted_url,
    )
    
    saved_cards = create_flashcards_batch(
        deck_id=deck_data["id"],
        cards=generated_cards,
        user_token=user_token,
    )
    
    # 6. Build response
    elapsed_ms = int((time.time() - start_time) * 1000)
    estimated_study_time = len(saved_cards) // 3
    
    response_cards = [
        Flashcard(
            id=c["id"],
            deck_id=c["deck_id"],
            front=c["front"],
            back=c["back"],
            hint=c.get("hint"),
            position=c.get("position", 0),
            status=c.get("status", "new"),
            ease_factor=float(c.get("ease_factor", 2.5)),
            interval_days=c.get("interval_days", 0),
            repetitions=c.get("repetitions", 0),
            next_review=c.get("next_review"),
            created_at=c.get("created_at"),
            updated_at=c.get("updated_at"),
        )
        for c in saved_cards
    ]
    
    logger.info(
        "Generated %d flashcards from URL in %dms for user %s...",
        len(response_cards), elapsed_ms, user_id[:8]
    )
    
    return FlashcardGenerationResponse(
        deck_id=deck_data["id"],
        deck_title=title,
        cards=response_cards,
        card_count=len(response_cards),
        content_source_type="url",
        generation_time_ms=elapsed_ms,
        estimated_study_time_minutes=max(1, estimated_study_time),
    )


# =============================================================================
# Deck CRUD Handlers
# =============================================================================

def get_user_flashcard_decks(
    user_id: str,
    user_token: str,
    limit: int = 50,
    offset: int = 0,
) -> List[Deck]:
    """Get all flashcard decks for a user."""
    decks_data = get_user_decks(user_id, user_token, limit, offset)
    return [
        Deck(
            id=d["id"],
            created_by=d["created_by"],
            title=d["title"],
            description=d.get("description"),
            card_count=d.get("card_count", 0),
            content_source_type=d.get("content_source_type"),
            content_source_reference=d.get("content_source_reference"),
            created_at=d.get("created_at"),
            updated_at=d.get("updated_at"),
            last_studied=d.get("last_studied"),
        )
        for d in decks_data
    ]


def get_flashcard_deck(
    deck_id: str,
    user_id: str,
    user_token: str,
    include_cards: bool = True,
) -> DeckWithCards:
    """Get a specific flashcard deck with its cards."""
    deck_data = get_deck(deck_id, user_id, user_token, include_cards)
    
    if not deck_data:
        raise HTTPException(status_code=404, detail="Deck not found")
    
    cards = []
    if include_cards and "cards" in deck_data:
        cards = [
            Flashcard(
                id=c["id"],
                deck_id=c["deck_id"],
                front=c["front"],
                back=c["back"],
                hint=c.get("hint"),
                position=c.get("position", 0),
                status=c.get("status", "new"),
                ease_factor=float(c.get("ease_factor", 2.5)),
                interval_days=c.get("interval_days", 0),
                repetitions=c.get("repetitions", 0),
                next_review=c.get("next_review"),
                created_at=c.get("created_at"),
                updated_at=c.get("updated_at"),
            )
            for c in deck_data["cards"]
        ]
    
    return DeckWithCards(
        id=deck_data["id"],
        created_by=deck_data["created_by"],
        title=deck_data["title"],
        description=deck_data.get("description"),
        card_count=deck_data.get("card_count", 0),
        content_source_type=deck_data.get("content_source_type"),
        content_source_reference=deck_data.get("content_source_reference"),
        created_at=deck_data.get("created_at"),
        updated_at=deck_data.get("updated_at"),
        last_studied=deck_data.get("last_studied"),
        cards=cards,
    )


def update_flashcard_deck(
    deck_id: str,
    user_id: str,
    user_token: str,
    update_data: DeckUpdate,
) -> Deck:
    """Update a flashcard deck."""
    updated = update_deck(
        deck_id=deck_id,
        user_id=user_id,
        user_token=user_token,
        title=update_data.title,
        description=update_data.description,
    )
    
    if not updated:
        raise HTTPException(status_code=404, detail="Deck not found")
    
    return Deck(
        id=updated["id"],
        created_by=updated["created_by"],
        title=updated["title"],
        description=updated.get("description"),
        card_count=updated.get("card_count", 0),
        content_source_type=updated.get("content_source_type"),
        content_source_reference=updated.get("content_source_reference"),
        created_at=updated.get("created_at"),
        updated_at=updated.get("updated_at"),
        last_studied=updated.get("last_studied"),
    )


def delete_flashcard_deck(
    deck_id: str,
    user_id: str,
    user_token: str,
) -> Dict[str, Any]:
    """Delete a flashcard deck."""
    success = delete_deck(deck_id, user_id, user_token)
    
    if not success:
        raise HTTPException(status_code=404, detail="Deck not found")
    
    return {"message": "Deck deleted successfully", "deck_id": deck_id}


# =============================================================================
# Flashcard CRUD Handlers
# =============================================================================

def update_single_flashcard(
    card_id: str,
    user_id: str,
    user_token: str,
    update_data: FlashcardUpdate,
) -> Flashcard:
    """Update a single flashcard."""
    updated = update_flashcard(
        card_id=card_id,
        user_token=user_token,
        front=update_data.front,
        back=update_data.back,
        hint=update_data.hint,
    )
    
    if not updated:
        raise HTTPException(status_code=404, detail="Flashcard not found")
    
    return Flashcard(
        id=updated["id"],
        deck_id=updated["deck_id"],
        front=updated["front"],
        back=updated["back"],
        hint=updated.get("hint"),
        position=updated.get("position", 0),
        status=updated.get("status", "new"),
        ease_factor=float(updated.get("ease_factor", 2.5)),
        interval_days=updated.get("interval_days", 0),
        repetitions=updated.get("repetitions", 0),
        next_review=updated.get("next_review"),
        created_at=updated.get("created_at"),
        updated_at=updated.get("updated_at"),
    )


def delete_single_flashcard(
    card_id: str,
    user_id: str,
    user_token: str,
) -> Dict[str, Any]:
    """Delete a single flashcard."""
    success = delete_flashcard(card_id, user_token)
    
    if not success:
        raise HTTPException(status_code=404, detail="Flashcard not found")
    
    return {"message": "Flashcard deleted successfully", "card_id": card_id}


# =============================================================================
# Study Session Handlers
# =============================================================================

def start_study_session(
    request: StudySessionStart,
    user_id: str,
    user_token: str,
) -> StudySessionResponse:
    """Start a new study session for a deck."""
    # Verify deck exists and belongs to user
    deck_data = get_deck(str(request.deck_id), user_id, user_token)
    if not deck_data:
        raise HTTPException(status_code=404, detail="Deck not found")
    
    # Get cards for the session
    cards_data = get_deck_cards(
        deck_id=str(request.deck_id),
        user_token=user_token,
        status_filter=request.filter_status,
        limit=request.card_limit,
        shuffle=request.shuffle,
    )
    
    if not cards_data:
        raise HTTPException(status_code=400, detail="No cards available for study")
    
    # Create session record
    session = create_study_session(
        deck_id=str(request.deck_id),
        user_id=user_id,
        user_token=user_token,
    )
    
    # Count cards by status
    new_count = sum(1 for c in cards_data if c.get("status") == "new")
    learning_count = sum(1 for c in cards_data if c.get("status") == "learning")
    review_count = sum(1 for c in cards_data if c.get("status") == "review")
    
    cards = [
        Flashcard(
            id=c["id"],
            deck_id=c["deck_id"],
            front=c["front"],
            back=c["back"],
            hint=c.get("hint"),
            position=c.get("position", 0),
            status=c.get("status", "new"),
            ease_factor=float(c.get("ease_factor", 2.5)),
            interval_days=c.get("interval_days", 0),
            repetitions=c.get("repetitions", 0),
            next_review=c.get("next_review"),
            created_at=c.get("created_at"),
            updated_at=c.get("updated_at"),
        )
        for c in cards_data
    ]
    
    return StudySessionResponse(
        session_id=session["id"],
        deck_id=deck_data["id"],
        deck_title=deck_data["title"],
        cards=cards,
        total_cards=len(cards),
        new_count=new_count,
        learning_count=learning_count,
        review_count=review_count,
    )


def complete_flashcard_study_session(
    request: StudySessionComplete,
    user_id: str,
    user_token: str,
) -> StudySessionSummary:
    """Complete a study session and update card progress."""
    # Update each card's spaced repetition data
    cards_correct = 0
    cards_incorrect = 0
    total_time = 0
    
    for result in request.results:
        update_card_review(
            card_id=str(result.card_id),
            result=result.result,
            user_token=user_token,
        )
        
        if result.result in ("good", "easy"):
            cards_correct += 1
        elif result.result in ("again", "hard"):
            cards_incorrect += 1
        
        if result.time_spent_seconds:
            total_time += result.time_spent_seconds
    
    # Complete the session
    session = complete_study_session(
        session_id=str(request.session_id),
        cards_studied=len(request.results),
        cards_correct=cards_correct,
        cards_incorrect=cards_incorrect,
        time_spent_seconds=total_time,
        user_token=user_token,
    )
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    accuracy = (cards_correct / len(request.results) * 100) if request.results else 0
    
    return StudySessionSummary(
        session_id=session["id"],
        deck_id=session["deck_id"],
        cards_studied=len(request.results),
        time_spent_seconds=total_time,
        accuracy_percent=round(accuracy, 1),
        cards_mastered=sum(1 for r in request.results if r.result == "easy"),
        cards_learning=sum(1 for r in request.results if r.result in ("again", "hard")),
        streak_days=0,  # TODO: Calculate streak
    )
