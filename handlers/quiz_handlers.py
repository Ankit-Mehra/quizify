from fastapi import HTTPException, Depends, Path, Body, UploadFile, File, Form
import re
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
from schemas.quiz import TextQuizRequest, FileQuizRequest, WebQuizRequest
from typing import Dict, Any, List
from datetime import datetime
from services.ai_services.chunking_service import generate_quizzes_single_async
from services.logger import app_logger as logger
from services.web_scraping_service import scrape_content

# Content validation constants
MIN_CONTENT_LENGTH = 50  # Minimum characters required for quiz generation from uploaded files
MIN_STORED_CONTENT_LENGTH = 10  # Minimum characters required for stored file content validation

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
    current_user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token)
):
    if file.content_type not in ["application/pdf", "text/plain", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]:
        raise HTTPException(status_code=400, detail="Only PDF, DOCX, or TXT files are supported.")

    # Validate quota BEFORE file processing and generation (don't waste AI API calls)
    await validate_user_quota(current_user_id, user_token)

    try:
        text = await file.read()
        
        # Choose the appropriate extractor based on file type
        try:
            if file.content_type == "application/pdf":
                parsed_text = extract_text_from_pdf(text)
            elif file.content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                parsed_text = extract_text_from_docx(text)
            else:  # text/plain
                parsed_text = extract_text_from_plain_text(text)
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

        # Save file to supabase storage FIRST to get file_id
        await file.seek(0)  # Reset file pointer after reading
        file_bytes = await file.read()
        original_filename = file.filename or f"uploaded_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        file_result = save_file_to_supabase(current_user_id, file_bytes, original_filename, user_token, file.content_type)
        file_id = file_result.get('file_id')
        
        # Generate quiz questions with PostHog LLM analytics
        trace_id = str(uuid4())  # Unique trace for this quiz generation
        quizzes = await generate_quizzes_single_async(
            parsed_text, 
            num_questions,
            question_types=question_type,
            user_id=current_user_id,
            trace_id=trace_id
        )
        
        # Save quiz to database with file reference
        quiz_id, saved_questions = save_quiz_to_database(
            title, 
            quizzes, 
            current_user_id,
            content_source_type="file",
            content_source_reference=file_id,
            user_token=user_token
        )

        metadata = {
            "quiz_id": quiz_id,
            "content_type": "file",
            "file_name": file.filename,
            "file_type": file.content_type,
            "word_count": len(parsed_text.split()),
            "created_by": current_user_id,
            "created_at": datetime.now().isoformat(),
            "question_count": num_questions
        }

        #save metadata to database
        save_metadata(metadata, user_token=user_token)

        return {
            "quiz_id": quiz_id, 
            "title": title,
            "message": "Quiz generated successfully from file",
            "questions": saved_questions  # Return saved questions with IDs
        }
    
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
        # Generate quiz questions with PostHog LLM analytics
        trace_id = str(uuid4())  # Unique trace for this quiz generation
        quizzes = await generate_quizzes_single_async(
            file_content, 
            total_questions,
            question_types=list(data.question_type),
            user_id=current_user_id,
            trace_id=trace_id
        )
        
        if not quizzes or len(quizzes) == 0:
            logger.error(f"No questions were generated for file {file_id}")
            raise HTTPException(status_code=500, detail="No questions were generated. The AI service may have failed.")
        
        logger.info(f"Generated {len(quizzes)} questions")
        for i, q in enumerate(quizzes):
            logger.info(f"Question {i+1}: type={q.type}, correct_answer={q.correct_answer}")
        
        quiz_id, saved_questions = save_quiz_to_database(
            data.title, 
            quizzes, 
            current_user_id,
            content_source_type="file",
            content_source_reference=file_id,
            user_token=user_token
        )
        logger.info(f"Saved quiz with ID: {quiz_id}")

        metadata = {
            "quiz_id": quiz_id,
            "content_type": file_record["file_type"],
            "file_name": file_record["original_filename"],
            "file_type": file_record["file_type"],
            "word_count": len(file_content.split()),
            "created_by": current_user_id,
            "created_at": datetime.now().isoformat(),
            "question_count": len(quizzes)
        }
        save_metadata(metadata, user_token=user_token)
        logger.info(f"Saved metadata for quiz {quiz_id}")

        return {
            "quiz_id": quiz_id, 
            "title": data.title,
            "message": "Quiz generated successfully from file",
            "questions": saved_questions  # Return saved questions with IDs
        }
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
        
        # Validate quota BEFORE generation (don't waste AI API calls)
        await validate_user_quota(current_user_id, user_token)
        # Generate quiz questions with PostHog LLM analytics
        total_questions = data.num_questions if data.num_questions is not None else 10
        trace_id = str(uuid4())  # Unique trace for this quiz generation
        quizzes = await generate_quizzes_single_async(
            data.content, 
            total_questions,
            question_types=list(data.question_type),
            user_id=current_user_id,
            trace_id=trace_id
        )
        
        # Save text as a file in Supabase Storage FIRST (for consistent user experience)
        # This allows users to access their text content later, same as uploaded files
        text_bytes = data.content.encode('utf-8')
        file_size = len(text_bytes)
        
        # Validate text size (same 10MB limit as file uploads)
        MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"Text content too large. Maximum size is 10MB ({MAX_FILE_SIZE} bytes). Your text is {file_size} bytes."
            )
        
        # Create safe filename (remove spaces and special characters)
        safe_title = sanitize_filename(data.title)
        filename = f"{safe_title}.txt"
        
        file_result = save_file_to_supabase(
            current_user_id, 
            text_bytes, 
            filename, 
            user_token, 
            "text/plain"
        )
        file_id = file_result.get('file_id')
            
        # Save quiz to database with file reference
        quiz_id, saved_questions = save_quiz_to_database(
            title=data.title,
            quizzes=quizzes,
            created_by=current_user_id,
            content_source_type="text",
            content_source_reference=file_id,  # Link to the saved text file
            user_token=user_token
        )

        # Save metadata for analytics/tracking
        metedata = {
            "quiz_id": quiz_id,
            "content_type": "text",
            "file_name": filename,
            "file_type": "text/plain",
            "word_count": len(data.content.split()),
            "created_by": current_user_id,
            "created_at": datetime.now().isoformat(),
            "question_count": total_questions
        }
        save_metadata(metedata, user_token=user_token)
        
        # Return response with questions for immediate display
        return {
            "quiz_id": quiz_id, 
            "title": data.title,
            "message": "Quiz generated successfully from text",
            "questions": saved_questions  # Return saved questions with IDs
        }
    
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
    user_token: str = Depends(get_current_user_token)
):
    """Get all quizzes created by the current user."""
    try:
        quizzes = get_user_quizzes(current_user_id, user_token)
        return quizzes
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
        
        # Generate quiz with PostHog LLM analytics
        total_questions = data.num_questions if data.num_questions is not None else 10
        trace_id = str(uuid4())  # Unique trace for this quiz generation
        quizzes = await generate_quizzes_single_async(
            content,
            total_questions,
            question_types=list(data.question_type),
            user_id=current_user_id,
            trace_id=trace_id
        )
        
        # Save to database
        quiz_id, saved_questions = save_quiz_to_database(
            data.title, 
            quizzes, 
            current_user_id,
            content_source_type="url",
            content_source_reference=content_source_reference,  # file_id if PDF, URL otherwise
            user_token=user_token
        )
        logger.info(f"Saved quiz from URL with ID: {quiz_id}")
        
        # Save metadata
        metadata = {
            "quiz_id": quiz_id,
            "content_type": "url",
            "file_name": str(data.url),
            "file_type": "application/pdf" if file_info else "text/html",
            "word_count": len(content.split()),
            "created_by": current_user_id,
            "created_at": datetime.now().isoformat(),
            "question_count": len(quizzes)
        }
        save_metadata(metadata, user_token=user_token)
        logger.info(f"Saved metadata for URL quiz {quiz_id}")
        
        # Build response
        response = {
            "quiz_id": quiz_id,
            "title": data.title,
            "message": "Quiz generated successfully from URL",
            "questions": saved_questions,  # Return saved questions with IDs
            "source_url": str(data.url)
        }
        
        # If PDF was saved, include file info
        if file_info:
            response["file_id"] = file_info.get('file_id')
            response["message"] = "Quiz generated successfully from PDF URL (PDF saved to your files)"
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating quiz from URL {data.url}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error generating quiz from URL: {str(e)}"
        )

