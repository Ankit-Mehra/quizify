from fastapi import HTTPException, Depends, Path, Body, UploadFile, File, Form, Query
import asyncio
import random
import re
import time
from uuid import uuid4
from services.ai_services.doc_service import ( 
    extract_text_from_pdf,
    extract_text_from_plain_text,
    extract_text_from_docx
)
from services.db_services.supabase_quiz import (  # noqa: F401
    save_quiz_to_database, get_user_quizzes,
    get_quiz_from_database, save_metadata, 
    get_metadata, delete_quiz_from_database,
    get_user_tier_info_cached, get_quiz_metadata_cached,
    get_authed_supabase_client)
from services.db_services.supabase_file import ( 
    get_file_record, save_file_to_supabase,
    parse_file_from_supabase)
from dependencies.auth_dependencies import get_current_user_id, get_current_user_token
from schemas.quiz import (
    TextQuizRequest, FileQuizRequest, WebQuizRequest,
    EnhancedTextQuizRequest, EnhancedQuizGenerationResponse, EnhancedQuestion,
    BloomLevel, Difficulty, ALL_QUESTION_TYPES
)
from typing import Dict, Any, List, Optional
from services.ai_services.ingestion_service import IngestionService
from services.ai_services.concept_extraction_service import ConceptExtractionService
from services.ai_services.orchestration_service import QuizOrchestrationService
from datetime import datetime, date
from services.ai_services.chunking_service import generate_quizzes_single_async
from services.logger import app_logger as logger
from services.web_scraping_service import scrape_content

# Content validation constants
MIN_CONTENT_LENGTH = 50  # Minimum characters required for quiz generation from uploaded files
MIN_STORED_CONTENT_LENGTH = 10  # Minimum characters required for stored file content validation
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB = 10,485,760 bytes


# =============================================================================
# Helper Functions for generate_quiz_rag_async (Refactored for SRP)
# =============================================================================

async def _validate_quiz_request(
    request: EnhancedTextQuizRequest,
    user_id: str,
    user_token: str
) -> None:
    """
    Validate user quota and content length before quiz generation.
    
    Raises:
        HTTPException: 403 if quota exceeded, 400 if content too short
    """
    await validate_user_quota(user_id, user_token)
    
    if len(request.content) < MIN_CONTENT_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Content too short. Minimum {MIN_CONTENT_LENGTH} characters required, got {len(request.content)}."
        )


async def _generate_standard_mode(
    request: EnhancedTextQuizRequest,
    user_id: str,
    user_token: str,
    trace_id: str,
    content_source_type: str,
    content_source_reference: str
) -> EnhancedQuizGenerationResponse:
    """
    Generate quiz using standard (fast) mode with direct LLM calls.
    
    Returns:
        EnhancedQuizGenerationResponse with generated questions
    """
    total_questions = request.num_questions
    
    # Normalize question_type to list
    if request.question_type == "mixed":
        question_types = ["mixed"]
    elif isinstance(request.question_type, list):
        question_types = list(request.question_type)
    else:
        question_types = [request.question_type]
    
    quizzes = await generate_quizzes_single_async(
        request.content,
        total_questions,
        question_types=question_types,
        user_id=user_id,
        trace_id=trace_id
    )
    
    # Save to database with proper content source tracking
    quiz_id, saved_questions = save_quiz_to_database(
        title=request.title,
        quizzes=quizzes,
        created_by=user_id,
        content_source_type=content_source_type,
        content_source_reference=content_source_reference,
        user_token=user_token,
        generation_mode="standard"
    )
    
    # Convert to EnhancedQuestion format (with defaults for enhanced fields)
    final_questions = []
    for q in saved_questions:
        # Handle both dict and Pydantic model
        q_dict = q if isinstance(q, dict) else q.model_dump() if hasattr(q, 'model_dump') else vars(q)
        eq = EnhancedQuestion(
            id=q_dict.get("id"),
            quiz_id=q_dict.get("quiz_id"),
            type=q_dict.get("type"),
            question=q_dict.get("question"),
            options=q_dict.get("options"),
            left=q_dict.get("left"),
            right=q_dict.get("right"),
            correct_answer=q_dict.get("correct_answer"),
            explanation=q_dict.get("explanation", ""),
            source=q_dict.get("source", ""),
            # Standard mode doesn't have these - leave as None
            bloom_level=None,
            difficulty=None,
            concept_id=None,
            concept_name=None,
            chunk_id=None,
            confidence_score=None
        )
        final_questions.append(eq)
    
    return EnhancedQuizGenerationResponse(
        quiz_id=quiz_id,
        title=request.title,
        message="Quiz generated successfully (standard mode)",
        questions=final_questions,
        generation_stats={
            "mode": "standard",
            "questions_generated": len(final_questions)
        }
    )


async def _ingest_and_extract_concepts(
    request: EnhancedTextQuizRequest,
    user_id: str,
    user_token: str,
    trace_id: str,
    ingestion_service: IngestionService,
    concept_service: ConceptExtractionService
) -> tuple[str, List[Dict], List[Dict]]:
    """
    Ingest content and extract concepts for enhanced mode.
    
    Returns:
        Tuple of (document_id, chunks, concepts)
        
    Raises:
        ValueError: If no concepts could be extracted
    """
    # Ingest Content (with user_token for RLS)
    t0 = time.time()
    ingestion_result = await ingestion_service.ingest_content(
        user_id=user_id,
        user_token=user_token,
        content=request.content,
        title=request.title,
        source_type="text",
        trace_id=trace_id
    )
    t1 = time.time()
    logger.info(f"[TIMING] Ingestion took {t1-t0:.2f}s")
    
    document_id = ingestion_result["document_id"]
    chunks = ingestion_result.get("chunks", [])
    
    # Extract Concepts (with user_token for RLS)
    t2 = time.time()
    concepts = await concept_service.extract_concepts(
        chunks=chunks,
        user_id=user_id,
        user_token=user_token,
        document_id=document_id,
        trace_id=trace_id
    )
    t3 = time.time()
    logger.info(f"[TIMING] Concept extraction took {t3-t2:.2f}s for {len(chunks)} chunks -> {len(concepts)} concepts")
    
    if not concepts:
        raise ValueError(
            f"No concepts could be extracted from the content. "
            f"Please ensure your content is at least {MIN_CONTENT_LENGTH} characters long and contains "
            f"sufficient educational detail. Try providing more specific terminology, definitions, or examples."
        )
    
    return document_id, chunks, concepts


def _select_and_assign_concepts(
    concepts: List[Dict],
    num_questions: int,
    question_type: Any,
    orchestration_service: QuizOrchestrationService
) -> tuple[List[tuple], List[tuple]]:
    """
    Select top concepts and assign question types, Bloom levels, and difficulties.
    
    Returns:
        Tuple of (concept_type_pairs, bloom_difficulty_pairs)
    """
    # Sort by relevance and select top N
    concepts.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    selected_concepts = concepts[:num_questions]
    
    # If not enough concepts, pad with cycling through existing ones
    if len(selected_concepts) < num_questions:
        original_count = len(selected_concepts)
        while len(selected_concepts) < num_questions:
            idx = len(selected_concepts) % original_count
            selected_concepts.append(selected_concepts[idx])
    
    # Assign Question Types
    concept_type_pairs = []
    
    if question_type == "mixed":
        # Balanced distribution of all types with randomized order
        # This ensures each type gets roughly equal representation
        # while still providing variety through shuffled order
        shuffled_types = ALL_QUESTION_TYPES.copy()
        random.shuffle(shuffled_types)
        for i, c in enumerate(selected_concepts):
            t = shuffled_types[i % len(shuffled_types)]
            concept_type_pairs.append((c, t))
    elif isinstance(question_type, list):
        # Round robin through specified types
        for i, c in enumerate(selected_concepts):
            t = question_type[i % len(question_type)]
            concept_type_pairs.append((c, t))
    else:
        # Single type for all
        for c in selected_concepts:
            concept_type_pairs.append((c, question_type))
    
    # Assign Bloom Levels and Difficulty (balanced distribution)
    bloom_difficulty_pairs = orchestration_service.assign_bloom_and_difficulty(
        num_questions=len(concept_type_pairs)
    )
    
    return concept_type_pairs, bloom_difficulty_pairs


async def _generate_questions_parallel(
    concept_type_pairs: List[tuple],
    bloom_difficulty_pairs: List[tuple],
    user_id: str,
    user_token: str,
    trace_id: str,
    orchestration_service: QuizOrchestrationService,
    all_concepts: List[Dict] = None
) -> List[Dict]:
    """
    Generate questions in parallel with retry logic for failures.
    
    Matching questions are handled specially - they aggregate 4 concepts
    to provide enough context for creating 4 matching pairs.
    
    Args:
        concept_type_pairs: List of (concept, question_type) tuples.
        bloom_difficulty_pairs: List of (bloom_level, difficulty) tuples.
        user_id: ID of the user generating the quiz.
        user_token: Authentication token for the user.
        trace_id: Request trace ID for logging.
        orchestration_service: Service for orchestrating question generation.
        all_concepts: Optional full list of extracted concepts for matching question diversity.
            If None, falls back to concepts assigned to matching slots only.
    
    Returns:
        List of valid generated question dictionaries.
        
    Raises:
        ValueError: If no valid questions could be generated.
    """
    # Separate matching from non-matching questions
    matching_indices = []
    non_matching_pairs = []
    non_matching_bloom_diff = []
    
    for i, (concept, q_type) in enumerate(concept_type_pairs):
        if q_type == "matching":
            matching_indices.append(i)
        else:
            non_matching_pairs.append((concept, q_type, i))
            non_matching_bloom_diff.append(bloom_difficulty_pairs[i])
    
    valid_questions = []
    
    # Generate non-matching questions in parallel
    if non_matching_pairs:
        async def generate_one(concept: Dict, q_type: str, orig_idx: int):
            bloom_level, difficulty = bloom_difficulty_pairs[orig_idx]
            return await orchestration_service.generate_question_for_concept(
                concept=concept,
                question_type=q_type,
                user_id=user_id,
                user_token=user_token,
                trace_id=trace_id,
                bloom_level=bloom_level,
                difficulty=difficulty
            )
        
        tasks = [generate_one(c, t, idx) for c, t, idx in non_matching_pairs]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        failed_items = []
        for (concept, q_type, orig_idx), res in zip(non_matching_pairs, results):
            if isinstance(res, dict):
                valid_questions.append(res)
            else:
                logger.error(f"Question generation failed for index {orig_idx}: {res}")
                failed_items.append((concept, q_type, orig_idx))
        
        # Retry failed non-matching questions with fallback to MCQ
        if failed_items:
            logger.info(f"Retrying {len(failed_items)} failed non-matching questions...")
            retry_tasks = []
            for concept, q_type, orig_idx in failed_items:
                # First retry with same type
                retry_tasks.append(generate_one(concept, q_type, orig_idx))
            
            retry_results = await asyncio.gather(*retry_tasks, return_exceptions=True)
            
            fallback_items = []
            for (concept, q_type, orig_idx), res in zip(failed_items, retry_results):
                if isinstance(res, dict):
                    valid_questions.append(res)
                else:
                    logger.error(f"Retry failed for index {orig_idx}, will try MCQ fallback")
                    fallback_items.append((concept, orig_idx))
            
            # Fallback to MCQ
            if fallback_items:
                logger.info(f"Fallback: {len(fallback_items)} questions switching to multiple_choice")
                fallback_tasks = [generate_one(c, "multiple_choice", idx) for c, idx in fallback_items]
                fallback_results = await asyncio.gather(*fallback_tasks, return_exceptions=True)
                
                for res in fallback_results:
                    if isinstance(res, dict):
                        valid_questions.append(res)
                    else:
                        logger.error(f"Fallback also failed: {res}")
    
    # Generate matching questions - aggregate 4 concepts per matching question
    if matching_indices:
        logger.info(f"Generating {len(matching_indices)} matching question(s) using aggregated concepts")
        
        # Use ALL available concepts for matching (not just those assigned to matching slots)
        # This ensures diverse matching questions with unique concept sets
        if all_concepts:
            # Deduplicate concepts by name (or content for unnamed) to avoid similar matching questions
            seen_names = set()
            seen_unnamed = set()
            unique_concepts = []
            included_empty_source = False  # Only include one concept with empty source_text
            for c in all_concepts:
                name = c.get("name", "").lower().strip()
                if name:
                    if name not in seen_names:
                        seen_names.add(name)
                        unique_concepts.append(c)
                else:
                    # Deduplicate unnamed concepts by their content
                    concept_key = c.get("source_text", "")[:100]  # Use first 100 chars of source
                    if concept_key and concept_key not in seen_unnamed:
                        seen_unnamed.add(concept_key)
                        unique_concepts.append(c)
                    elif not concept_key and not included_empty_source:
                        # No source_text - include at most one such concept
                        unique_concepts.append(c)
                        included_empty_source = True
            
            # Sort by relevance to prioritize important concepts
            unique_concepts.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
            available_concepts = unique_concepts
            logger.info(f"Using {len(available_concepts)} unique concepts for {len(matching_indices)} matching questions")
        else:
            # Fallback to concepts assigned to matching slots
            available_concepts = [concept_type_pairs[i][0] for i in matching_indices]
        
        # Early check: if no concepts available, fall back to MCQ for all matching questions
        if not available_concepts:
            logger.warning("No concepts available for matching questions, falling back to MCQ")
            for idx in matching_indices:
                concept = concept_type_pairs[idx][0]
                bloom_level, difficulty = bloom_difficulty_pairs[idx]
                try:
                    fallback_result = await orchestration_service.generate_question_for_concept(
                        concept=concept,
                        question_type="multiple_choice",
                        user_id=user_id,
                        user_token=user_token,
                        trace_id=trace_id,
                        bloom_level=bloom_level,
                        difficulty=difficulty
                    )
                    valid_questions.append(fallback_result)
                except Exception as e:
                    logger.error(f"MCQ fallback for empty matching concepts failed: {e}")
        else:
            # For each matching question, we need 4 UNIQUE concepts
            # Ensure each matching question uses different concepts
            matching_tasks = []
            used_concept_indices = set()
            concept_pool_idx = 0  # Track position across all matching questions
            
            for i, idx in enumerate(matching_indices):
                bloom_level, difficulty = bloom_difficulty_pairs[idx]
                
                # Get 4 unique concepts for this matching question
                concepts_for_matching = []
                checked_indices = set()  # Track which indices we've checked this iteration
                max_checks = len(available_concepts)  # Stop after checking all concepts once
                
                while len(concepts_for_matching) < 4 and len(checked_indices) < max_checks:
                    concept_idx = concept_pool_idx % len(available_concepts)
                    
                    # Track that we've checked this index
                    if concept_idx not in checked_indices:
                        checked_indices.add(concept_idx)
                    
                    # Only use concepts not already used in previous matching questions
                    # (if we have enough concepts for full uniqueness)
                    if len(available_concepts) > len(matching_indices) * 4:
                        if concept_idx not in used_concept_indices:
                            concepts_for_matching.append(available_concepts[concept_idx])
                            used_concept_indices.add(concept_idx)
                    else:
                        # Not enough concepts for full uniqueness, allow reuse
                        concepts_for_matching.append(available_concepts[concept_idx])
                    
                    concept_pool_idx += 1
                
                # Safety check: if we still don't have enough concepts, skip this question
                if len(concepts_for_matching) < 4:
                    if available_concepts:
                        # Fill with remaining concepts
                        while len(concepts_for_matching) < 4:
                            fill_idx = len(concepts_for_matching) % len(available_concepts)
                            concepts_for_matching.append(available_concepts[fill_idx])
                    else:
                        logger.error(f"No available concepts for matching question {i}, skipping")
                        continue
            
                matching_tasks.append(
                    orchestration_service.generate_matching_question(
                        concepts=concepts_for_matching,
                        user_id=user_id,
                        user_token=user_token,
                        trace_id=trace_id,
                        bloom_level=bloom_level,
                        difficulty=difficulty
                    )
                )
            
            matching_results = await asyncio.gather(*matching_tasks, return_exceptions=True)
            
            for i, res in enumerate(matching_results):
                if isinstance(res, dict):
                    valid_questions.append(res)
                else:
                    logger.error(f"Matching question {i} failed: {res}")
                    # Fallback to MCQ for failed matching
                    logger.info(f"Falling back to MCQ for failed matching question {i}")
                    try:
                        idx = matching_indices[i]
                        concept = concept_type_pairs[idx][0]
                        bloom_level, difficulty = bloom_difficulty_pairs[idx]
                        fallback_result = await orchestration_service.generate_question_for_concept(
                            concept=concept,
                            question_type="multiple_choice",
                            user_id=user_id,
                            user_token=user_token,
                            trace_id=trace_id,
                            bloom_level=bloom_level,
                            difficulty=difficulty
                        )
                        valid_questions.append(fallback_result)
                    except Exception as e:
                        logger.error(f"Matching fallback to MCQ also failed: {e}")
    
    if not valid_questions:
        raise ValueError(
            "Failed to generate any valid questions after multiple attempts. "
            "This may happen when content is too vague, lacks educational structure, or contains mostly lists/tables. "
            "Try providing narrative text with clear concepts, definitions, and explanations."
        )
    
    return valid_questions


def _build_enhanced_questions(valid_questions: List[Dict]) -> List[EnhancedQuestion]:
    """
    Convert raw question dictionaries to EnhancedQuestion Pydantic models.
    
    Returns:
        List of EnhancedQuestion objects
    """
    final_questions = []
    for q in valid_questions:
        eq = EnhancedQuestion(
            # Required fields - use direct indexing
            type=q["type"],
            question=q["question"],
            correct_answer=q["correct_answer"],
            explanation=q["explanation"],
            source=q["source"],
            bloom_level=BloomLevel(q["bloom_level"]),
            difficulty=Difficulty(q["difficulty"]),
            # Optional fields - use .get() for safe access
            options=q.get("options"),
            left=q.get("left"),
            right=q.get("right"),
            concept_id=q.get("concept_id"),
            concept_name=q.get("concept_name"),
            chunk_id=q.get("chunk_id"),
            confidence_score=q.get("confidence_score")
        )
        final_questions.append(eq)
    return final_questions

def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to make it safe for storage URLs.
    Removes special characters, replaces spaces with underscores, and limits length.
    """
    # Remove file extension if present
    name_without_ext = filename.rsplit('.', 1)[0] if '.' in filename else filename
    
    # Replace spaces and special characters with underscores
    # Keep only alphanumeric, underscores, and hyphens
    sanitized = re.sub(r'[^\w\s-]', '', name_without_ext)
    sanitized = re.sub(r'[-\s]+', '_', sanitized)
    
    # Limit length to 50 characters
    sanitized = sanitized[:50]
    
    # Remove leading/trailing underscores
    sanitized = sanitized.strip('_')
    
    # If empty after sanitization, use a default name
    if not sanitized:
        sanitized = "quiz_content"
    
    return sanitized

async def validate_user_quota(user_id: str, user_token: str = None):
    """
    Validate if user has available quota for quiz generation.
    
    Uses Redis caching for 50x performance improvement.
    
    Args:
        user_id: The UUID of the user
        user_token: User's authentication token for RLS enforcement (optional)
        
    Raises:
        HTTPException: 403 Forbidden if quota is exceeded with detailed error message
    """
    tier_info = await get_user_tier_info_cached(user_id)
    
    if tier_info["quota_exceeded"]:
        current_count = tier_info["current_quiz_count"]
        quota_limit = tier_info["quota_limit"]
        user_tier = tier_info["account_tier"]
        
        # Normalize legacy tier naming for user-facing messages
        # Database may still have "basic" but we display "premium" to users
        display_tier = "premium" if user_tier == "basic" else user_tier
        
        # Create upgrade suggestion based on current tier
        upgrade_suggestion = ""
        if user_tier == "free":
            upgrade_suggestion = "Upgrade to Premium for 100 quizzes."
        elif user_tier in ("basic", "premium"):  # Support both legacy and new naming
            upgrade_suggestion = "Upgrade to Pro for unlimited quizzes."
        
        detail_message = f"Quiz quota exceeded for {display_tier} tier ({current_count}/{quota_limit}). {upgrade_suggestion}".strip()
        
        # Log with truncated user ID for security (server-side only)
        user_id_truncated = user_id[:8] + "..." if len(user_id) > 8 else user_id
        logger.warning(f"Quota exceeded for user {user_id_truncated}: {detail_message}")
        
        raise HTTPException(
            status_code=403,
            detail={
                "detail": detail_message,
                "current_count": current_count,
                "quota_limit": quota_limit,
                "user_tier": display_tier  # Return normalized tier name
            }
        )
    
    # Log successful quota check with truncated user ID (server-side only)
    user_id_truncated = user_id[:8] + "..." if len(user_id) > 8 else user_id
    logger.info(f"Quota check passed for user {user_id_truncated}: "
               f"{tier_info['current_quiz_count']}/{tier_info['quota_limit']}")


# === Generate quiz from file ===
async def generate_quiz_from_file_openai(
    file: UploadFile = File(...),
    title: str = Form(...),
    num_questions: int = Form(10),
    question_type: List[str] = Form(["mixed"]),
    mode: str = Form("standard"),  # "standard" or "enhanced"
    current_user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token)
):
    if file.content_type not in ["application/pdf", "text/plain", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]:
        raise HTTPException(status_code=400, detail="Only PDF, DOCX, or TXT files are supported.")

    # Validate quota BEFORE file processing and generation (don't waste AI API calls)
    await validate_user_quota(current_user_id, user_token)

    try:
        file_bytes = await file.read()
        file_size = len(file_bytes)
        
        # Validate file size (10MB limit, inclusive - files up to 10MB accepted)
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum file size is 10MB ({MAX_FILE_SIZE} bytes). Your file is {file_size} bytes."
            )
        
        # Choose the appropriate extractor based on file type
        try:
            if file.content_type == "application/pdf":
                parsed_text = extract_text_from_pdf(file_bytes)
            elif file.content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                parsed_text = extract_text_from_docx(file_bytes)
            else:  # text/plain
                parsed_text = extract_text_from_plain_text(file_bytes)
        except Exception as extraction_error:
            # Extraction errors (corrupted files, invalid format, etc.)
            error_msg = str(extraction_error)
            if "Failed to extract text" in error_msg or "Failed to open" in error_msg:
                raise HTTPException(status_code=400, detail=error_msg)
            raise  # Re-raise unexpected errors

        # Validate extraction succeeded (for extractors that return error strings instead of raising)
        if "Failed to extract text" in parsed_text:
            raise HTTPException(status_code=400, detail=parsed_text)
        
        # Validate minimum content length
        if not parsed_text or len(parsed_text.strip()) < MIN_CONTENT_LENGTH:
            raise HTTPException(
                status_code=400, 
                detail=f"Insufficient content in file. Please provide a document with at least {MIN_CONTENT_LENGTH} characters of text."
            )

        # Save file to supabase storage FIRST to get file_id (reuse already-read bytes)
        original_filename = file.filename or f"uploaded_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        file_result = save_file_to_supabase(current_user_id, file_bytes, original_filename, user_token, file.content_type)
        file_id = file_result.get('file_id')
        
        # Use unified generation function that handles both modes
        enhanced_request = EnhancedTextQuizRequest(
            title=title,
            content=parsed_text,
            question_type="mixed" if "mixed" in question_type else question_type,
            num_questions=num_questions,
            mode=mode  # Pass mode from request (standard or enhanced)
        )
        result = await generate_quiz_rag_async(
            enhanced_request, 
            current_user_id, 
            user_token,
            content_source_type="file",
            content_source_reference=file_id
        )
        
        # Save metadata for file-based quiz
        metadata = {
            "quiz_id": result.quiz_id,
            "content_type": "file",
            "content_source_type": "file",
            "content_source_reference": file_id,
            "file_name": file.filename,
            "file_type": file.content_type,
            "file_size_bytes": file_size,
            "word_count": len(parsed_text.split()),
            "created_by": current_user_id,
            "created_at": datetime.now().isoformat(),
            "question_count": len(result.questions)
        }
        save_metadata(metadata, user_token=user_token)
        
        # Update message and return EnhancedQuizGenerationResponse directly
        result.message = f"Quiz generated successfully from file ({mode} mode)"
        result.file_id = file_id
        return result
    
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

# === Generate quiz from file ID ===
async def generate_quiz_from_fileid(
    file_id: str = Path(...),
    data: FileQuizRequest = Body(...),
    current_user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token)
):
    logger.info(f"Generating quiz from file ID: {file_id}")
    logger.info(f"Quiz parameters: title={data.title}, num_questions={data.num_questions}, question_types={data.question_type}")
    
    file_content = None
    
    try:
        # Check file record exists (use authenticated client)
        file_record = get_file_record(file_id, user_token)
        
        if not file_record:
            logger.error(f"File not found with ID: {file_id}")
            raise HTTPException(status_code=404, detail="File not found in the database")
        
        # Check user authorization
        if file_record["user_id"] != current_user_id:
            logger.warning(f"Unauthorized file access attempt for file {file_id}")
            raise HTTPException(status_code=403, detail="You don't have permission to access this file")
            
        storage_path = file_record.get("storage_path")
        logger.info(f"File storage path: {storage_path}")
        
        # Try to get content from storage
        try:
            logger.info("Attempting to get file content...")
            file_content = parse_file_from_supabase(file_record, user_token)
            logger.info(f"Successfully retrieved file content: {len(file_content)} characters")
        except HTTPException as he:
            if he.status_code == 404:
                logger.error("File missing from storage but exists in database")
                raise HTTPException(
                    status_code=404,
                    detail="The file was found in the database but is missing from storage. It may have been deleted."
                )
            # Re-raise other HTTP exceptions
            raise he
        
        # Validate content
        if not file_content or not isinstance(file_content, str) or len(file_content.strip()) < MIN_STORED_CONTENT_LENGTH:
            logger.error(f"Invalid or insufficient content extracted from file {file_id}")
            raise HTTPException(status_code=400, detail="The file content couldn't be properly extracted or is too short")

    except HTTPException as he:
        # Re-raise HTTP exceptions
        raise he
    except Exception as e:
        logger.error(f"Error reading file {file_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")

    # Validate quota BEFORE generation (don't waste AI API calls)
    await validate_user_quota(current_user_id, user_token)

    try:
        logger.info(f"Generating quiz questions from file content (length: {len(file_content)})")
        total_questions = data.num_questions if data.num_questions is not None else 10
        
        # Use unified generation function that handles both modes
        enhanced_request = EnhancedTextQuizRequest(
            title=data.title,
            content=file_content,
            question_type="mixed" if "mixed" in data.question_type else data.question_type,
            num_questions=total_questions,
            mode=data.mode  # Pass mode from request (standard or enhanced)
        )
        result = await generate_quiz_rag_async(
            enhanced_request, 
            current_user_id, 
            user_token,
            content_source_type="file",
            content_source_reference=file_id
        )
        
        # Save metadata for file-based quiz
        metadata = {
            "quiz_id": result.quiz_id,
            "content_type": file_record["file_type"],
            "content_source_type": "file",
            "content_source_reference": file_id,
            "file_name": file_record["original_filename"],
            "file_type": file_record["file_type"],
            "word_count": len(file_content.split()),
            "created_by": current_user_id,
            "created_at": datetime.now().isoformat(),
            "question_count": len(result.questions)
        }
        save_metadata(metadata, user_token=user_token)
        logger.info(f"Saved quiz with ID: {result.quiz_id}")

        # Update message and return EnhancedQuizGenerationResponse
        result.message = f"Quiz generated successfully from file ({data.mode} mode)"
        result.file_id = file_id
        return result
    except HTTPException as he:
        # Re-raise HTTP exceptions
        raise he
    except Exception as e:
        logger.error(f"Error generating quiz from file {file_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error generating quiz: {str(e)}")

# === Generate quiz from text ===
async def generate_quiz_from_text(
    data: TextQuizRequest,
    current_user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token)
):
    """Generate a quiz from text content provided directly by the user."""
    try:
        # Validate the user ID
        if not current_user_id or current_user_id == "undefined":
            raise HTTPException(
                status_code=401, 
                detail="Authentication required to generate quiz"
            )
        
        # Use unified generation function that handles both modes
        enhanced_request = EnhancedTextQuizRequest(
            title=data.title,
            content=data.content,
            question_type="mixed" if "mixed" in data.question_type else data.question_type,
            num_questions=data.num_questions or 10,
            mode=data.mode  # Pass mode from request (standard or enhanced)
        )
        result = await generate_quiz_rag_async(
            enhanced_request, 
            current_user_id, 
            user_token,
            content_source_type="text",
            content_source_reference=None  # Text input has no reference
        )
        
        # Save metadata for text-based quiz
        metadata = {
            "quiz_id": result.quiz_id,
            "content_type": "text",
            "content_source_type": "text",
            "content_source_reference": None,
            "file_name": None,
            "file_type": "text/plain",
            "word_count": len(data.content.split()),
            "created_by": current_user_id,
            "created_at": datetime.now().isoformat(),
            "question_count": len(result.questions)
        }
        save_metadata(metadata, user_token=user_token)
        
        # Update message and return EnhancedQuizGenerationResponse directly
        result.message = f"Quiz generated successfully from text ({data.mode} mode)"
        return result
    
    except HTTPException as he:
        # Re-raise HTTP exceptions as-is
        raise he
    except ValueError as ve:
        # Handle validation errors
        raise HTTPException(status_code=422, detail=str(ve))
    except Exception as e:
        # Handle all other errors
        raise HTTPException(status_code=500, detail=f"Error generating quiz: {str(e)}")

# === Get user quizzes ===
async def get_user_quizzes_handler(
    current_user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token),
    title: Optional[str] = Query(None, description="Search quizzes by title (case-insensitive, partial match)"),
    start_date: Optional[date] = Query(None, description="Filter quizzes created on or after this date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="Filter quizzes created on or before this date (YYYY-MM-DD)"),
    source_type: Optional[str] = Query(None, description="Filter by content source type: file, url, or text"),
    mode: Optional[str] = Query(None, description="Filter by generation mode: standard or enhanced"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(20, ge=1, le=100, description="Number of quizzes per page (max 100)")
):
    """
    Get all quizzes created by the current user with optional filtering and pagination.
    
    Supports filtering by:
    - title: Case-insensitive partial match
    - start_date/end_date: Date range filter (inclusive)
    - source_type: Content source (file, url, text)
    - mode: Generation mode (standard, enhanced)
    
    Returns paginated results with metadata for building pagination UI.
    """
    try:
        # Validate date range
        if start_date and end_date and start_date > end_date:
            raise HTTPException(
                status_code=400,
                detail="start_date must be less than or equal to end_date"
            )
        
        # Validate source_type if provided
        if source_type and source_type not in ("file", "url", "text"):
            raise HTTPException(
                status_code=400,
                detail="source_type must be one of: file, url, text"
            )
        
        # Validate mode if provided
        if mode and mode not in ("standard", "enhanced"):
            raise HTTPException(
                status_code=400,
                detail="mode must be one of: standard, enhanced"
            )
        
        result = get_user_quizzes(
            current_user_id,
            user_token=user_token,
            title=title,
            start_date=start_date,
            end_date=end_date,
            source_type=source_type,
            mode=mode,
            page=page,
            limit=limit
        )
        return result
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# === Get quiz by ID ===
async def get_quiz_by_id_handler(
    quiz_id: str = Path(...),
    current_user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token)
):
    """
    Retrieve a specific quiz by ID, combining cached metadata and fresh questions.

    Uses hybrid caching: metadata cached in Redis (30min TTL), questions fetched fresh.
    Metadata uses service role with explicit filter; questions use RLS for access control.

    Args:
        quiz_id: The ID of the quiz to retrieve.
        current_user_id: The ID of the requesting user (injected by auth dependency).
        user_token: The user's authentication token (injected by auth dependency).

    Returns:
        dict: Quiz metadata (id, title, created_by, created_at, content_source fields,
              question_count) and full questions array.

    Raises:
        HTTPException: 400 if quiz_id invalid, 404 if not found/no access,
                      500 if data integrity issues or internal errors.

    Note:
        Mixed authorization approach (explicit filter + RLS) creates maintenance burden.
        TODO(authorization): Consolidate to single approach when quiz sharing implemented.
    """
    try:
        # Truncate quiz_id for logging (security: prevent information leakage)
        quiz_preview = quiz_id[:8] if len(quiz_id) >= 8 else quiz_id
        
        # Check for invalid quiz IDs
        if not quiz_id or quiz_id.lower() == "undefined" or quiz_id.lower() == "null":
            raise HTTPException(
                status_code=400, 
                detail="Invalid quiz ID. Please provide a valid quiz ID."
            )
        
        # Get quiz metadata from cache.
        # Ownership is enforced by RLS when using authenticated client (user_token provided).
        # If the quiz does not exist or does not belong to the user, a 404 is raised.
        try:
            metadata = await get_quiz_metadata_cached(quiz_id, current_user_id, user_token)
        except HTTPException as e:
            if e.status_code == 404:
                # Quiz doesn't exist or user doesn't have access
                raise HTTPException(status_code=404, detail="Quiz not found")
            raise
        
        # Defense-in-depth: Explicitly verify ownership after fetching metadata
        # Protects against cache poisoning attacks
        if metadata["created_by"] != current_user_id:
            logger.warning("Access denied - User attempting to access quiz they don't own")
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Log quiz access (without exposing full quiz IDs)
        logger.info(f"Quiz access for quiz ID: {quiz_preview}...")
        
        # Check question_count from cached metadata to detect data integrity issues early
        # This avoids an unnecessary database query if we know there are no questions
        question_count = metadata.get("question_count", 0)
        if question_count == 0:
            logger.error(f"Data integrity issue: Quiz {quiz_preview}... has no questions")
            raise HTTPException(status_code=500, detail="Quiz data incomplete. Please contact support.")
        
        # Fetch questions from database (not cached due to size)
        # Uses authenticated client with RLS enforcement for consistent access control
        supabase = get_authed_supabase_client(user_token)
        questions_response = supabase.table("questions").select("*").eq("quiz_id", quiz_id).execute()
        
        # Verify questions were actually returned (RLS could filter them out)
        if not questions_response.data:
            logger.error(f"Data integrity issue: Quiz {quiz_preview}... has question_count={question_count} but RLS returned no questions")
            raise HTTPException(status_code=500, detail="Quiz data incomplete. Please contact support.")
        
        # Combine metadata and questions
        return {
            "id": metadata["id"],
            "title": metadata["title"],
            "created_by": metadata["created_by"],
            "created_at": metadata["created_at"],
            "content_source_type": metadata.get("content_source_type"),
            "content_source_reference": metadata.get("content_source_reference"),
            "generation_mode": metadata.get("generation_mode", "standard"),
            "question_count": question_count,
            "questions": questions_response.data
        }
    
    except HTTPException as e:
        raise e
    except Exception as e:
        # Log detailed error for debugging (with truncated quiz_id)
        logger.error(f"Error retrieving quiz {quiz_preview}...: {str(e)}", exc_info=True)
        # Return generic error message (security: don't expose internal details)
        raise HTTPException(status_code=500, detail="An error occurred while retrieving the quiz. Please try again later.")

# === Delete quiz by ID ===
async def delete_quiz_by_id_handler(
    quiz_id: str = Path(...),
    current_user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token)
):
    """Delete a quiz by ID."""
    try:
        delete_quiz_from_database(quiz_id, user_token)
        return {"message": "Quiz deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting quiz: {str(e)}")

# === Get metadata ===
async def get_metadata_handler(
    current_user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token)
):
    """Get all content sources created by the current user."""
    try:
        sources = get_metadata(current_user_id, user_token)
        
        return sources
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# === Submit quiz answers ===
async def submit_quiz_answers(
    quiz_id: str,
    answers: Dict[str, Any],
    current_user_id: str = Depends(get_current_user_id)
):
    """Submit answers for a quiz and get score"""
    try:
        # For now, just return the submitted data and a mock score
        # In a real implementation, you would validate answers against correct ones
        correct_count = len(answers.get("answers", [])) // 2  # Mock calculation
        total_count = len(answers.get("answers", []))
        
        return {
            "quiz_id": quiz_id,
            "user_id": current_user_id,
            "score": {
                "correct": correct_count,
                "total": total_count,
                "percentage": int((correct_count / total_count) * 100) if total_count > 0 else 0
            },
            "submitted_at": datetime.now().isoformat(),
            "status": "completed"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === Generate quiz from URL ===
async def generate_quiz_from_url(
    data: WebQuizRequest,
    current_user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token)
):
    """Generate quiz from web URL (available for all tiers with quota limits)."""
    
    # Validate quota BEFORE scraping and generation (don't waste resources)
    await validate_user_quota(current_user_id, user_token)
    
    try:
        # Get user tier info for logging (cached for performance)
        tier_info = await get_user_tier_info_cached(current_user_id)
        
        # Scrape content with user ID for resource tracking
        # Enable PDF saving to user_files if URL is a PDF
        logger.info(f"User {current_user_id} ({tier_info['account_tier']} tier) generating quiz from URL: {data.url}")
        content, file_info = await scrape_content(
            url=str(data.url), 
            user_id=current_user_id,
            user_token=user_token,
            save_pdf=True  # Save PDFs to user_files
        )
        
        # Determine content source reference
        # If PDF was saved, use file_id; otherwise use URL
        if file_info and file_info.get('file_id'):
            content_source_reference = file_info['file_id']
            logger.info(f"PDF from URL saved as file_id: {content_source_reference}")
        else:
            content_source_reference = str(data.url)
        
        # Generate quiz using unified function that handles both modes
        total_questions = data.num_questions if data.num_questions is not None else 10
        
        enhanced_request = EnhancedTextQuizRequest(
            title=data.title,
            content=content,
            question_type="mixed" if "mixed" in data.question_type else data.question_type,
            num_questions=total_questions,
            mode=data.mode  # Pass mode from request (standard or enhanced)
        )
        result = await generate_quiz_rag_async(
            enhanced_request, 
            current_user_id, 
            user_token,
            content_source_type="url",
            content_source_reference=content_source_reference  # file_id if PDF, URL otherwise
        )
        
        # Save metadata for URL-based quiz
        metadata = {
            "quiz_id": result.quiz_id,
            "content_type": "url",
            "content_source_type": "url",
            "content_source_reference": content_source_reference,
            "file_name": str(data.url),
            "file_type": "application/pdf" if file_info else "text/html",
            "word_count": len(content.split()),
            "created_by": current_user_id,
            "created_at": datetime.now().isoformat(),
            "question_count": len(result.questions)
        }
        save_metadata(metadata, user_token=user_token)
        logger.info(f"Saved quiz from URL with ID: {result.quiz_id}")
        
        # Update result with URL-specific info and return directly
        result.source_url = str(data.url)
        if file_info:
            result.file_id = file_info.get('file_id')
            result.message = f"Quiz generated successfully from PDF URL ({data.mode} mode, PDF saved to your files)"
        else:
            result.message = f"Quiz generated successfully from URL ({data.mode} mode)"
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating quiz from URL {data.url}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error generating quiz from URL: {str(e)}"
        )

async def generate_quiz_rag_async(
    request: EnhancedTextQuizRequest,
    user_id: str,
    user_token: str,
    content_source_type: str = "text",
    content_source_reference: str = None
) -> EnhancedQuizGenerationResponse:
    """
    Generate a quiz with support for both standard and enhanced (RAG) modes.
    
    Modes:
    - standard: Fast generation using direct LLM calls (generate_quizzes_single_async)
    - enhanced: Full RAG pipeline with concept extraction, Bloom's taxonomy, etc.
    
    Pipeline (enhanced mode):
    1. Validate quota and content length
    2. Ingest content (chunk & embed)
    3. Extract concepts from chunks
    4. Assign question types and Bloom/difficulty levels
    5. Generate questions with context
    6. Save to database
    
    Args:
        request: Enhanced quiz request with content, title, options, and mode
        user_id: UUID of the user
        user_token: JWT token for RLS enforcement
        content_source_type: "text", "file", or "url"
        content_source_reference: file_id or URL for tracking the source
        
    Returns:
        EnhancedQuizGenerationResponse with generated questions
        
    Raises:
        HTTPException: 403 if quota exceeded, 400 if content too short, 500 on error
    """
    trace_id = str(uuid4())
    
    # Step 1: Validate request (quota and content length)
    await _validate_quiz_request(request, user_id, user_token)
    
    # Step 2: Route to appropriate generation mode
    if request.mode == "standard":
        try:
            return await _generate_standard_mode(
                request=request,
                user_id=user_id,
                user_token=user_token,
                trace_id=trace_id,
                content_source_type=content_source_type,
                content_source_reference=content_source_reference
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Standard Quiz Generation failed: {str(e)}")
            raise HTTPException(status_code=500, detail="Quiz generation failed. Please try again.")
    
    # Step 3: Enhanced mode - Full RAG pipeline
    return await _generate_enhanced_mode(
        request=request,
        user_id=user_id,
        user_token=user_token,
        trace_id=trace_id,
        content_source_type=content_source_type,
        content_source_reference=content_source_reference
    )


async def _generate_enhanced_mode(
    request: EnhancedTextQuizRequest,
    user_id: str,
    user_token: str,
    trace_id: str,
    content_source_type: str,
    content_source_reference: str
) -> EnhancedQuizGenerationResponse:
    """
    Generate quiz using enhanced (RAG) mode with full pipeline.
    
    Pipeline:
    1. Ingest content and extract concepts
    2. Select concepts and assign question types
    3. Generate questions in parallel
    4. Build and save response
    
    Returns:
        EnhancedQuizGenerationResponse with generated questions
    """
    pipeline_start = time.time()
    
    # Initialize services
    ingestion_service = IngestionService()
    concept_service = ConceptExtractionService()
    orchestration_service = QuizOrchestrationService()
    
    try:
        # Step 1: Ingest content and extract concepts
        t1 = time.time()
        document_id, chunks, concepts = await _ingest_and_extract_concepts(
            request=request,
            user_id=user_id,
            user_token=user_token,
            trace_id=trace_id,
            ingestion_service=ingestion_service,
            concept_service=concept_service
        )
        logger.info(f"[TIMING] Step 1 (ingest+extract) took {time.time()-t1:.2f}s")
        
        # Step 2: Select concepts and assign types/bloom/difficulty
        t2 = time.time()
        concept_type_pairs, bloom_difficulty_pairs = _select_and_assign_concepts(
            concepts=concepts,
            num_questions=request.num_questions,
            question_type=request.question_type,
            orchestration_service=orchestration_service
        )
        logger.info(f"[TIMING] Step 2 (select concepts) took {time.time()-t2:.2f}s")
        
        # Step 3: Generate questions in parallel
        t3 = time.time()
        valid_questions = await _generate_questions_parallel(
            concept_type_pairs=concept_type_pairs,
            bloom_difficulty_pairs=bloom_difficulty_pairs,
            user_id=user_id,
            user_token=user_token,
            trace_id=trace_id,
            orchestration_service=orchestration_service,
            all_concepts=concepts  # Pass all concepts for matching question diversity
        )
        logger.info(f"[TIMING] Step 3 (generate questions) took {time.time()-t3:.2f}s")
        
        # Step 4: Convert to Pydantic models
        t4 = time.time()
        final_questions = _build_enhanced_questions(valid_questions)
        logger.info(f"[TIMING] Step 4 (build models) took {time.time()-t4:.2f}s")
        
        # Step 5: Save to Database
        t5 = time.time()
        quiz_id, _ = save_quiz_to_database(
            title=request.title,
            quizzes=final_questions,
            created_by=user_id,
            content_source_type=content_source_type,
            content_source_reference=content_source_reference or document_id,
            user_token=user_token,
            generation_mode="enhanced"
        )
        logger.info(f"[TIMING] Step 5 (save quiz) took {time.time()-t5:.2f}s")
        
        logger.info(f"[TIMING] TOTAL PIPELINE took {time.time()-pipeline_start:.2f}s")
        
        # Step 6: Build response
        return EnhancedQuizGenerationResponse(
            quiz_id=quiz_id,
            title=request.title,
            message="Quiz generated successfully using RAG pipeline (enhanced mode)",
            questions=final_questions,
            generation_stats={
                "mode": "enhanced",
                "document_id": document_id,
                "chunks_count": len(chunks),
                "concepts_extracted": len(concepts),
                "concepts_used": len(concept_type_pairs),
                "questions_generated": len(final_questions),
                "total_time_seconds": round(time.time()-pipeline_start, 2)
            }
        )
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"RAG Quiz Generation validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"RAG Quiz Generation failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Quiz generation failed. Please try again.")
