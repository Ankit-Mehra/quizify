"""
Flashcard Handlers.

This module contains the business logic for flashcard operations,
following the same patterns as quiz_handlers.py.

Supports two generation modes:
- Standard: Fast, direct LLM generation (1 credit)
- Enhanced: RAG-based with concept extraction and context retrieval (2 credits)
"""

import asyncio
import time
from typing import List, Dict, Any
from uuid import uuid4, UUID
from fastapi import HTTPException

from services.content.ingestion_service import get_content_ingestion_service
from services.content.models import ContentValidationError, ContentExtractionError
from services.ai_services.flashcard_service import (
    get_flashcard_generation_service,
    get_enhanced_flashcard_service,
    FlashcardGenerationError,
    FlashcardParseError,
)
from handlers.file_handlers import _validate_file_type
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
# Credit Units (1 unit = 0.5 credits)
# =============================================================================
CREDITS_PER_UNIT = 0.5  # Conversion factor: units to credits
STANDARD_FLASHCARD_UNITS = 1   # Standard mode
ENHANCED_FLASHCARD_UNITS = 2   # Enhanced mode


# =============================================================================
# Credit Validation Helper
# =============================================================================

async def validate_and_get_unit_cost(
    user_id: str,
    mode: str,
) -> int:
    """
    Validate user has sufficient credits for the requested generation mode.
    
    DRY: This function centralizes credit validation logic used across
    all flashcard generation handlers (text, file, URL).
    
    Args:
        user_id: ID of the user
        mode: Generation mode ("standard" or "enhanced")
        
    Returns:
        The unit cost for the requested mode (1 for standard, 2 for enhanced)
        
    Raises:
        HTTPException: 402 if insufficient credits
    """
    unit_cost = ENHANCED_FLASHCARD_UNITS if mode == "enhanced" else STANDARD_FLASHCARD_UNITS
    credit_cost = unit_cost * CREDITS_PER_UNIT
    
    billing_state = await get_billing_state(user_id)
    if billing_state.available_credits < credit_cost:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "insufficient_credits",
                "message": f"Not enough credits for {mode} flashcard generation.",
                "available_credits": billing_state.available_credits,
                "required_credits": credit_cost,
                "plan": billing_state.plan
            }
        )
    
    return unit_cost


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
    
    Supports two modes:
    - Standard: Fast, direct LLM generation (0.5 credits)
    - Enhanced: RAG-based with concept extraction (1 credit)
    
    Args:
        request: Text flashcard request with content and config
        user_id: ID of the requesting user
        user_token: JWT token for RLS enforcement
        
    Returns:
        FlashcardGenerationResponse with generated deck and cards
    """
    start_time = time.time()
    trace_id = str(uuid4())
    mode = request.config.mode
    
    logger.info(
        "Generating flashcards from text for user %s..., mode: %s, trace: %s",
        user_id[:8], mode, trace_id[:8]
    )
    
    # Validate credits (DRY - uses shared helper)
    unit_cost = await validate_and_get_unit_cost(user_id, mode)
    
    # Route to appropriate generation mode
    if mode == "enhanced":
        return await _generate_enhanced_flashcards(
            content=request.content,
            title=request.title,
            config=request.config,
            user_id=user_id,
            user_token=user_token,
            trace_id=trace_id,
            content_source_type="text",
            content_source_reference=None,
            start_time=start_time,
            unit_cost=unit_cost,
        )
    else:
        return await _generate_standard_flashcards(
            content=request.content,
            title=request.title,
            config=request.config,
            user_id=user_id,
            user_token=user_token,
            trace_id=trace_id,
            content_source_type="text",
            content_source_reference=None,
            start_time=start_time,
            unit_cost=unit_cost,
        )


# =============================================================================
# Internal Generation Functions
# =============================================================================

async def _generate_standard_flashcards(
    content: str,
    title: str | None,
    config,
    user_id: str,
    user_token: str,
    trace_id: str,
    content_source_type: str,
    content_source_reference: str | None,
    start_time: float,
    unit_cost: int,
) -> FlashcardGenerationResponse:
    """
    Generate flashcards using standard (fast) mode.
    
    Uses direct LLM generation without RAG pipeline.
    Costs 1 unit (0.5 credits).
    """
    credits_consumed = False
    
    # 1. Ingest content
    ingestion_service = get_content_ingestion_service()
    try:
        ingested_content = await ingestion_service.ingest_text(
            text=content,
            title=title,
        )
    except ContentValidationError as e:
        raise HTTPException(status_code=400, detail=e.message) from e
    
    try:
        # 2. Consume credits (with audit logging)
        logger.info(
            "CREDIT_AUDIT: Consuming standard credits for user %s..., trace: %s",
            user_id[:8], trace_id[:8]
        )
        success = await consume_units(user_id, "standard")
        if not success:
            raise HTTPException(
                status_code=402,
                detail="Failed to consume credits for flashcard generation"
            )
        credits_consumed = True
        
        # 3. Generate flashcards
        generation_service = get_flashcard_generation_service()
        generated_cards = await generation_service.generate(
            content=ingested_content,
            generation_config=config,
            user_id=user_id,
            trace_id=trace_id,
        )
        
        # 4. Create deck and save cards to database
        deck_title = title or f"Flashcards - {ingested_content.word_count} words"
        
        deck_data = create_deck(
            user_id=user_id,
            title=deck_title,
            user_token=user_token,
            content_source_type=content_source_type,
            content_source_reference=content_source_reference,
            generation_mode="standard",
        )
        
        saved_cards = create_flashcards_batch(
            deck_id=deck_data["id"],
            cards=generated_cards,
            user_token=user_token,
        )
        
        # 5. Build response BEFORE marking success (to ensure refund on build failure)
        elapsed_ms = int((time.time() - start_time) * 1000)
        estimated_study_time = len(saved_cards) // 3  # ~3 cards per minute
        
        response_cards = _build_flashcard_response_list(saved_cards)
        
        # Build response object - if this fails, credits should be refunded
        response = FlashcardGenerationResponse(
            deck_id=deck_data["id"],
            deck_title=deck_title,
            cards=response_cards,
            card_count=len(response_cards),
            content_source_type=content_source_type,
            generation_time_ms=elapsed_ms,
            estimated_study_time_minutes=max(1, estimated_study_time),
            generation_mode="standard",
            generation_stats={"mode": "standard", "cards_generated": len(response_cards)},
            credits_consumed=unit_cost * CREDITS_PER_UNIT,
        )
        
        # SUCCESS - only mark as not consumed AFTER response is built successfully
        credits_consumed = False
        
        logger.info(
            "CREDIT_AUDIT: Standard flashcard generation SUCCESS for user %s..., "
            "cards: %d, trace: %s",
            user_id[:8], len(response_cards), trace_id[:8]
        )
        
        return response
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except (FlashcardGenerationError, FlashcardParseError) as e:
        logger.error("Flashcard generation failed: %s", e.message)
        raise HTTPException(status_code=500, detail=e.message) from e
    except Exception as e:
        logger.error("Unexpected error in flashcard generation: %s", str(e))
        raise HTTPException(status_code=500, detail="Flashcard generation failed") from e
    finally:
        # Refund credits if consumed but generation failed
        if credits_consumed:
            logger.info(
                "CREDIT_AUDIT: Refunding standard credits for user %s..., trace: %s (generation failed)",
                user_id[:8], trace_id[:8]
            )
            success = await refund_units(user_id, "standard")
            if not success:
                logger.error(
                    "CRITICAL: Failed to refund credits for user %s..., trace: %s. "
                    "Manual intervention may be required.",
                    user_id[:8], trace_id[:8]
                )


async def _generate_enhanced_flashcards(
    content: str,
    title: str | None,
    config,
    user_id: str,
    user_token: str,
    trace_id: str,
    content_source_type: str,
    content_source_reference: str | None,
    start_time: float,
    unit_cost: int,
) -> FlashcardGenerationResponse:
    """
    Generate flashcards using enhanced (RAG-based) mode.
    
    Uses concept extraction, context retrieval, and Bloom's taxonomy.
    Costs 2 units (1 credit).
    """
    credits_consumed = False
    
    try:
        # 1. Consume credits (with audit logging)
        logger.info(
            "CREDIT_AUDIT: Consuming enhanced credits for user %s..., trace: %s",
            user_id[:8], trace_id[:8]
        )
        success = await consume_units(user_id, "enhanced")
        if not success:
            raise HTTPException(
                status_code=402,
                detail="Failed to consume credits for enhanced flashcard generation"
            )
        credits_consumed = True
        
        # 2. Generate enhanced flashcards
        enhanced_service = get_enhanced_flashcard_service()
        result = await enhanced_service.generate_enhanced(
            content=content,
            title=title or "Flashcards",
            config=config,
            user_id=user_id,
            user_token=user_token,
            trace_id=trace_id,
            content_source_type=content_source_type,
        )
        
        generated_cards = result["flashcards"]
        generation_stats = result["generation_stats"]
        
        # 3. Create deck and save cards to database
        deck_title = title or f"Flashcards (Enhanced) - {len(generated_cards)} cards"
        
        deck_data = create_deck(
            user_id=user_id,
            title=deck_title,
            user_token=user_token,
            content_source_type=content_source_type,
            content_source_reference=content_source_reference,
            generation_mode="enhanced",
        )
        
        saved_cards = create_flashcards_batch(
            deck_id=deck_data["id"],
            cards=generated_cards,
            user_token=user_token,
        )
        
        # 4. Build response with enhanced metadata BEFORE marking success
        elapsed_ms = int((time.time() - start_time) * 1000)
        estimated_study_time = len(saved_cards) // 3
        
        response_cards = _build_flashcard_response_list(saved_cards)
        
        # Build response object - if this fails, credits should be refunded
        response = FlashcardGenerationResponse(
            deck_id=deck_data["id"],
            deck_title=deck_title,
            cards=response_cards,
            card_count=len(response_cards),
            content_source_type=content_source_type,
            generation_time_ms=elapsed_ms,
            estimated_study_time_minutes=max(1, estimated_study_time),
            generation_mode="enhanced",
            generation_stats=generation_stats,
            credits_consumed=unit_cost * CREDITS_PER_UNIT,
        )
        
        # SUCCESS - only mark as not consumed AFTER response is built successfully
        credits_consumed = False
        
        logger.info(
            "CREDIT_AUDIT: Enhanced flashcard generation SUCCESS for user %s..., "
            "cards: %d, concepts: %d, trace: %s",
            user_id[:8], len(response_cards),
            generation_stats.get("concepts_extracted", 0), trace_id[:8]
        )
        
        return response
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except (FlashcardGenerationError, FlashcardParseError) as e:
        logger.error("Enhanced flashcard generation failed: %s", e.message)
        raise HTTPException(status_code=500, detail=e.message) from e
    except Exception as e:
        logger.error("Unexpected error in enhanced flashcard generation: %s", str(e))
        raise HTTPException(status_code=500, detail="Enhanced flashcard generation failed") from e
    finally:
        # Refund credits if consumed but generation failed
        if credits_consumed:
            logger.info(
                "CREDIT_AUDIT: Refunding enhanced credits for user %s..., trace: %s (generation failed)",
                user_id[:8], trace_id[:8]
            )
            success = await refund_units(user_id, "enhanced")
            if not success:
                logger.error(
                    "CRITICAL: Failed to refund enhanced credits for user %s..., trace: %s. "
                    "Manual intervention may be required.",
                    user_id[:8], trace_id[:8]
                )


def _build_flashcard_response_list(saved_cards: List[Dict]) -> List[Flashcard]:
    """Build list of Flashcard response objects from saved card data."""
    return [
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
            # Enhanced mode fields
            concept_name=c.get("concept_name"),
            bloom_level=c.get("bloom_level"),
            difficulty_score=c.get("difficulty_score"),
            source_chunk_id=c.get("source_chunk_id"),
            created_at=c.get("created_at"),
            updated_at=c.get("updated_at"),
        )
        for c in saved_cards
    ]


# =============================================================================
# Public Generation Handlers
# =============================================================================

async def generate_flashcards_from_file(
    file_id: UUID,
    request: FileFlashcardRequest,
    user_id: str,
    user_token: str,
) -> FlashcardGenerationResponse:
    """
    Generate flashcards from an uploaded file.
    
    Supports both standard and enhanced modes.
    
    Args:
        file_id: UUID of the previously uploaded file (from path parameter)
        request: File flashcard request with config options
        user_id: ID of the requesting user
        user_token: JWT token for RLS enforcement
        
    Returns:
        FlashcardGenerationResponse with generated deck and cards
    """
    start_time = time.time()
    trace_id = str(uuid4())
    mode = request.config.mode
    file_id_str = str(file_id)
    
    logger.info(
        "Generating flashcards from file %s for user %s..., mode: %s, trace: %s",
        file_id_str, user_id[:8], mode, trace_id[:8]
    )
    
    # Validate credits (DRY - uses shared helper)
    unit_cost = await validate_and_get_unit_cost(user_id, mode)
    
    # Get file record and parse content
    file_record = get_file_record(file_id_str, user_token)
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    
    file_content = await parse_file_from_supabase_async(
        file_record,
        user_token
    )
    
    if not file_content or len(file_content.strip()) < 50:
        raise HTTPException(
            status_code=400,
            detail="File contains insufficient text content"
        )
    
    # Route to appropriate generation mode
    title = request.title or file_record.get("filename", "Flashcards from File")
    
    if mode == "enhanced":
        return await _generate_enhanced_flashcards(
            content=file_content,
            title=title,
            config=request.config,
            user_id=user_id,
            user_token=user_token,
            trace_id=trace_id,
            content_source_type="file",
            content_source_reference=file_id_str,
            start_time=start_time,
            unit_cost=unit_cost,
        )
    else:
        return await _generate_standard_flashcards(
            content=file_content,
            title=title,
            config=request.config,
            user_id=user_id,
            user_token=user_token,
            trace_id=trace_id,
            content_source_type="file",
            content_source_reference=file_id_str,
            start_time=start_time,
            unit_cost=unit_cost,
        )

async def generate_flashcards_from_file_upload(
    file,
    title: str,
    card_count: int,
    card_style: str,
    difficulty: str,
    include_hints: bool,
    mode: str,
    user_id: str,
    user_token: str,
) -> FlashcardGenerationResponse:
    """
    Generate flashcards from direct file upload (single-step approach).
    
    This endpoint accepts a file upload directly and handles:
    1. File validation and extraction
    2. Saving file to storage
    3. Generating flashcards
    4. Cleanup on failure
    
    Args:
        file: Uploaded file (UploadFile)
        title: Title for the deck
        card_count: Number of cards to generate
        card_style: Card style (simple, detailed, mixed)
        difficulty: Difficulty level (beginner, intermediate, advanced)
        include_hints: Whether to include hints
        mode: Generation mode ("standard" or "enhanced")
        user_id: ID of the requesting user
        user_token: JWT token for RLS enforcement
        
    Returns:
        FlashcardGenerationResponse with generated deck and cards
    """
    from services.db_services.supabase_file import save_file_to_supabase_async, delete_file_from_supabase_async
    from services.content.parsers import extract_text_from_pdf, extract_text_from_docx, extract_text_from_plain_text
    from schemas.flashcard import FlashcardGenerationConfig
    
    async def cleanup_file_on_failure(fid: str, token: str, uid: str, fname: str) -> None:
        """Helper to cleanup uploaded file on failure."""
        try:
            await delete_file_from_supabase_async(fid, token, uid, fname)
            logger.info("Cleaned up orphaned file after flashcard generation failure (file_id: %s)", fid)
        except Exception as cleanup_err:
            logger.warning("Failed to cleanup orphaned file %s: %s", fid, cleanup_err)
    
    start_time = time.time()
    trace_id = str(uuid4())
    file_id = None
    original_filename = None
    
    logger.info(
        "Generating flashcards from file upload for user %s..., mode: %s, trace: %s",
        user_id[:8], mode, trace_id[:8]
    )
    
    # Validate credits (DRY - uses shared helper)
    unit_cost = await validate_and_get_unit_cost(user_id, mode)
    
    try:
        # Read and validate file
        file_bytes = await file.read()
        file_size = len(file_bytes)
        
        # Validate file size (10MB limit)
        MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum file size is 10MB. Your file is {file_size} bytes."
            )
        
        # Validate file type (consistent with file_handlers.py pattern)
        validated_content_type = _validate_file_type(file.filename, file.content_type)
        
        # Extract text based on file type
        try:
            if validated_content_type == "application/pdf":
                file_content = extract_text_from_pdf(file_bytes)
            elif validated_content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                file_content = extract_text_from_docx(file_bytes)
            else:  # text/plain or markdown
                file_content = extract_text_from_plain_text(file_bytes)
        except Exception as extraction_error:
            error_msg = str(extraction_error)
            if "Failed to extract text" in error_msg or "Failed to open" in error_msg:
                raise HTTPException(status_code=400, detail=error_msg) from extraction_error
            raise
        
        # Validate content length
        if not file_content or len(file_content.strip()) < 50:
            raise HTTPException(
                status_code=400,
                detail="File contains insufficient text content"
            )
        
        # Save file to storage (use validated content type)
        original_filename = file.filename or f"flashcard_upload_{int(time.time())}"
        file_result = await save_file_to_supabase_async(
            user_id, file_bytes, original_filename, user_token, validated_content_type
        )
        file_id = file_result.get('file_id')
        
        # Create flashcard config
        config = FlashcardGenerationConfig(
            num_cards=card_count,
            card_style=card_style,
            difficulty=difficulty,
            include_hints=include_hints,
            mode=mode
        )
        
        # Generate flashcards using appropriate mode
        if mode == "enhanced":
            result = await _generate_enhanced_flashcards(
                content=file_content,
                title=title,
                config=config,
                user_id=user_id,
                user_token=user_token,
                trace_id=trace_id,
                content_source_type="file",
                content_source_reference=file_id,
                start_time=start_time,
                unit_cost=unit_cost,
            )
        else:
            result = await _generate_standard_flashcards(
                content=file_content,
                title=title,
                config=config,
                user_id=user_id,
                user_token=user_token,
                trace_id=trace_id,
                content_source_type="file",
                content_source_reference=file_id,
                start_time=start_time,
                unit_cost=unit_cost,
            )
        
        return result
        
    except HTTPException:
        # Cleanup uploaded file on failure
        if file_id and original_filename:
            await cleanup_file_on_failure(file_id, user_token, user_id, original_filename)
        raise
    except Exception as e:
        # Cleanup uploaded file on failure
        if file_id and original_filename:
            await cleanup_file_on_failure(file_id, user_token, user_id, original_filename)
        raise HTTPException(
            status_code=500,
            detail=f"Error generating flashcards from file: {str(e)}"
        ) from e


async def generate_flashcards_from_url(
    request: UrlFlashcardRequest,
    user_id: str,
    user_token: str,
) -> FlashcardGenerationResponse:
    """
    Generate flashcards from a URL.
    
    Supports both standard and enhanced modes.
    
    Args:
        request: URL flashcard request with url and config
        user_id: ID of the requesting user
        user_token: JWT token for RLS enforcement
        
    Returns:
        FlashcardGenerationResponse with generated deck and cards
    """
    start_time = time.time()
    trace_id = str(uuid4())
    mode = request.config.mode
    
    logger.info(
        "Generating flashcards from URL for user %s..., mode: %s, trace: %s",
        user_id[:8], mode, trace_id[:8]
    )
    
    # Validate credits (DRY - uses shared helper)
    unit_cost = await validate_and_get_unit_cost(user_id, mode)
    
    # Ingest content from URL
    ingestion_service = get_content_ingestion_service()
    try:
        content = await ingestion_service.ingest_url(
            url=request.url,
            user_id=user_id,
            user_token=user_token,
        )
    except ContentValidationError as e:
        raise HTTPException(status_code=400, detail=e.message) from e
    except ContentExtractionError as e:
        raise HTTPException(status_code=400, detail=e.message) from e
    
    # Route to appropriate generation mode
    title = request.title or content.title or "Flashcards from URL"
    redacted_url = redact_url_for_storage(request.url)
    
    if mode == "enhanced":
        return await _generate_enhanced_flashcards(
            content=content.text,
            title=title,
            config=request.config,
            user_id=user_id,
            user_token=user_token,
            trace_id=trace_id,
            content_source_type="url",
            content_source_reference=redacted_url,
            start_time=start_time,
            unit_cost=unit_cost,
        )
    else:
        return await _generate_standard_flashcards(
            content=content.text,
            title=title,
            config=request.config,
            user_id=user_id,
            user_token=user_token,
            trace_id=trace_id,
            content_source_type="url",
            content_source_reference=redacted_url,
            start_time=start_time,
            unit_cost=unit_cost,
        )


# =============================================================================
# Deck CRUD Handlers
# =============================================================================

async def get_user_flashcard_decks(
    user_id: str,
    user_token: str,
    limit: int = 50,
    offset: int = 0,
) -> List[Deck]:
    """Get all flashcard decks for a user."""
    decks_data = await asyncio.to_thread(get_user_decks, user_id, user_token, limit, offset)
    return [
        Deck(
            id=d["id"],
            created_by=d["created_by"],
            title=d["title"],
            description=d.get("description"),
            card_count=d.get("card_count", 0),
            generation_mode=d.get("generation_mode", "standard"),
            content_source_type=d.get("content_source_type"),
            content_source_reference=d.get("content_source_reference"),
            created_at=d.get("created_at"),
            updated_at=d.get("updated_at"),
            last_studied=d.get("last_studied"),
        )
        for d in decks_data
    ]


async def get_flashcard_deck(
    deck_id: str,
    user_id: str,
    user_token: str,
    include_cards: bool = True,
    card_limit: int = 100,
    card_offset: int = 0,
) -> DeckWithCards:
    """Get a specific flashcard deck with its cards (paginated)."""
    deck_data = await asyncio.to_thread(
        get_deck,
        deck_id, user_id, user_token, include_cards,
        card_limit, card_offset
    )
    
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
                # Enhanced mode fields
                concept_name=c.get("concept_name"),
                bloom_level=c.get("bloom_level"),
                difficulty_score=float(c["difficulty_score"]) if c.get("difficulty_score") else None,
                source_chunk_id=c.get("source_chunk_id"),
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
        generation_mode=deck_data.get("generation_mode", "standard"),
        content_source_type=deck_data.get("content_source_type"),
        content_source_reference=deck_data.get("content_source_reference"),
        created_at=deck_data.get("created_at"),
        updated_at=deck_data.get("updated_at"),
        last_studied=deck_data.get("last_studied"),
        cards=cards,
    )


async def update_flashcard_deck(
    deck_id: str,
    user_id: str,
    user_token: str,
    update_data: DeckUpdate,
) -> Deck:
    """Update a flashcard deck."""
    updated = await asyncio.to_thread(
        update_deck,
        deck_id,
        user_id,
        user_token,
        update_data.title,
        update_data.description,
    )
    
    if not updated:
        raise HTTPException(status_code=404, detail="Deck not found")
    
    return Deck(
        id=updated["id"],
        created_by=updated["created_by"],
        title=updated["title"],
        description=updated.get("description"),
        card_count=updated.get("card_count", 0),
        generation_mode=updated.get("generation_mode", "standard"),
        content_source_type=updated.get("content_source_type"),
        content_source_reference=updated.get("content_source_reference"),
        created_at=updated.get("created_at"),
        updated_at=updated.get("updated_at"),
        last_studied=updated.get("last_studied"),
    )


async def delete_flashcard_deck(
    deck_id: str,
    user_id: str,
    user_token: str,
) -> Dict[str, Any]:
    """Delete a flashcard deck with ownership verification."""
    success = await asyncio.to_thread(delete_deck, deck_id, user_id, user_token)
    
    if not success:
        raise HTTPException(status_code=404, detail="Deck not found or access denied")
    
    return {"message": "Deck deleted successfully", "deck_id": deck_id}


# =============================================================================
# Flashcard CRUD Handlers
# =============================================================================

async def update_single_flashcard(
    card_id: str,
    user_id: str,
    user_token: str,
    update_data: FlashcardUpdate,
) -> Flashcard:
    """Update a single flashcard with ownership verification."""
    updated = await asyncio.to_thread(
        update_flashcard,
        card_id,
        user_id,
        user_token,
        update_data.front,
        update_data.back,
        update_data.hint,
    )
    
    if not updated:
        raise HTTPException(status_code=404, detail="Flashcard not found or access denied")
    
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
        # Enhanced mode fields
        concept_name=updated.get("concept_name"),
        bloom_level=updated.get("bloom_level"),
        difficulty_score=float(updated["difficulty_score"]) if updated.get("difficulty_score") else None,
        source_chunk_id=updated.get("source_chunk_id"),
        created_at=updated.get("created_at"),
        updated_at=updated.get("updated_at"),
    )


async def delete_single_flashcard(
    card_id: str,
    user_id: str,
    user_token: str,
) -> Dict[str, Any]:
    """Delete a single flashcard with ownership verification."""
    success = await asyncio.to_thread(delete_flashcard, card_id, user_id, user_token)
    
    if not success:
        raise HTTPException(status_code=404, detail="Flashcard not found or access denied")
    
    return {"message": "Flashcard deleted successfully", "card_id": card_id}


# =============================================================================
# Study Session Handlers
# =============================================================================

async def start_study_session(
    request: StudySessionStart,
    user_id: str,
    user_token: str,
) -> StudySessionResponse:
    """Start a new study session for a deck."""
    # Verify deck exists and belongs to user
    deck_data = await asyncio.to_thread(get_deck, str(request.deck_id), user_id, user_token)
    if not deck_data:
        raise HTTPException(status_code=404, detail="Deck not found")
    
    # Get cards for the session
    cards_data = await asyncio.to_thread(
        get_deck_cards,
        str(request.deck_id),
        user_token,
        request.filter_status,
        request.card_limit,
        request.shuffle,
    )
    
    if not cards_data:
        raise HTTPException(status_code=400, detail="No cards available for study")
    
    # Create session record
    session = await asyncio.to_thread(
        create_study_session,
        str(request.deck_id),
        user_id,
        user_token,
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
            # Enhanced mode fields
            concept_name=c.get("concept_name"),
            bloom_level=c.get("bloom_level"),
            difficulty_score=float(c["difficulty_score"]) if c.get("difficulty_score") else None,
            source_chunk_id=c.get("source_chunk_id"),
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


async def complete_flashcard_study_session(
    request: StudySessionComplete,
    _user_id: str,
    user_token: str,
) -> StudySessionSummary:
    """Complete a study session and update card progress."""
    # Update each card's spaced repetition data
    cards_correct = 0
    cards_incorrect = 0
    total_time = 0
    
    for result in request.results:
        await asyncio.to_thread(
            update_card_review,
            str(result.card_id),
            result.result,
            user_token,
        )
        
        if result.result in ("good", "easy"):
            cards_correct += 1
        elif result.result in ("again", "hard"):
            cards_incorrect += 1
        
        if result.time_spent_seconds:
            total_time += result.time_spent_seconds
    
    # Complete the session
    session = await asyncio.to_thread(
        complete_study_session,
        str(request.session_id),
        len(request.results),
        cards_correct,
        cards_incorrect,
        total_time,
        user_token,
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


# =============================================================================
# Flashcard Export Handlers
# =============================================================================

async def export_flashcard_deck(
    deck_id: str,
    format_type: str,
    include_hints: bool,
    _user_id: str,
    user_token: str,
):
    """
    Export a flashcard deck to the specified format.
    
    Args:
        deck_id: UUID of the deck to export
        format_type: Export format (csv_anki, pdf)
        include_hints: Whether to include hints in export
        _user_id: ID of the requesting user (unused, kept for API consistency)
        user_token: JWT token for RLS enforcement
        
    Returns:
        ExportResult with file bytes and metadata
    """
    from uuid import UUID
    from schemas.export import (
        FlashcardDeckExportData,
        ExportFlashcard,
        FlashcardExportFormat,
    )
    from services.exporters.csv_anki_exporter import CsvAnkiExporter
    
    logger.info("Exporting flashcard deck %s... format=%s", deck_id[:8], format_type)
    
    # 1. Validate format
    try:
        export_format = FlashcardExportFormat(format_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported export format: {format_type}. Supported: csv_anki, pdf"
        ) from exc
    
    # 2. Get deck with cards
    deck = get_deck(deck_id, user_token)
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    
    # 3. Get cards for the deck
    cards = get_deck_cards(deck_id, user_token)
    if not cards:
        raise HTTPException(status_code=422, detail="Deck has no cards to export")
    
    # 4. Build export data model
    deck_export_data = FlashcardDeckExportData(
        deck_id=UUID(deck["id"]),
        title=deck["title"],
        description=deck.get("description"),
        created_at=deck["created_at"],
        content_source_type=deck.get("content_source_type"),
        content_source_reference=deck.get("content_source_reference"),
        cards=[
            ExportFlashcard(
                id=UUID(card["id"]),
                front=card["front"],
                back=card["back"],
                hint=card.get("hint"),
            )
            for card in cards
        ]
    )
    
    # 5. Export based on format
    if export_format == FlashcardExportFormat.CSV_ANKI:
        exporter = CsvAnkiExporter()
        result = await exporter.export_flashcards(deck_export_data, include_hints)
    elif export_format == FlashcardExportFormat.PDF:
        # PDF export - to be implemented in Epic 5.2
        from services.exporters.pdf_flashcard_exporter import PdfFlashcardExporter
        exporter = PdfFlashcardExporter()
        result = await exporter.export_flashcards(deck_export_data, include_hints)
    else:
        raise HTTPException(
            status_code=422,
            detail=f"Export format {format} not yet implemented"
        )
    
    logger.info("Flashcard export complete: %s, %d bytes", result.filename, len(result.content))
    
    return result
