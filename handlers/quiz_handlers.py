from fastapi import HTTPException, Depends, Path, Body, UploadFile, File, Form
import re
from services.ai_services.doc_service import ( 
    extract_text_from_pdf,
    extract_text_from_plain_text,
    extract_text_from_docx
)
from services.db_services.supabase_quiz import ( 
    save_quiz_to_database, get_user_quizzes,
    get_quiz_from_database, save_metadata, 
    get_metadata, delete_quiz_from_database,
    get_user_tier_info)
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

def validate_user_quota(user_id: str, user_token: str = None):
    """
    Validate if user has available quota for quiz generation.
    
    Args:
        user_id: The UUID of the user
        user_token: User's authentication token for RLS enforcement (optional)
        
    Raises:
        HTTPException: 403 Forbidden if quota is exceeded with detailed error message
    """
    tier_info = get_user_tier_info(user_id, user_token)
    
    if tier_info["quota_exceeded"]:
        current_count = tier_info["current_quiz_count"]
        quota_limit = tier_info["quota_limit"]
        user_tier = tier_info["account_tier"]
        
        # Create upgrade suggestion based on current tier
        upgrade_suggestion = ""
        if user_tier == "free":
            upgrade_suggestion = "Upgrade to basic for 100 quizzes."
        elif user_tier == "basic":
            upgrade_suggestion = "Upgrade to educator for 500 quizzes."
        
        detail_message = f"Quiz quota exceeded for {user_tier} tier ({current_count}/{quota_limit}). {upgrade_suggestion}".strip()
        
        # Log with truncated user ID for security (server-side only)
        user_id_truncated = user_id[:8] + "..." if len(user_id) > 8 else user_id
        logger.warning(f"Quota exceeded for user {user_id_truncated}: {detail_message}")
        
        raise HTTPException(
            status_code=403,
            detail={
                "detail": detail_message,
                "current_count": current_count,
                "quota_limit": quota_limit,
                "user_tier": user_tier
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
    validate_user_quota(current_user_id, user_token)

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
        
        # Generate quiz questions
        quizzes = await generate_quizzes_single_async(
            parsed_text, 
            num_questions,
            question_types=question_type
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
    validate_user_quota(current_user_id, user_token)

    try:
        logger.info(f"Generating quiz questions from file content (length: {len(file_content)})")
        total_questions = data.num_questions if data.num_questions is not None else 10
        quizzes = await generate_quizzes_single_async(
            file_content, 
            total_questions,
            question_types=list(data.question_type)
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
        validate_user_quota(current_user_id, user_token)
        # Generate quiz questions
        total_questions = data.num_questions if data.num_questions is not None else 10
        quizzes = await generate_quizzes_single_async(
            data.content, 
            total_questions,
            question_types=list(data.question_type)
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
    """Get a specific quiz by ID."""
    try:
        # Check for invalid quiz IDs
        if not quiz_id or quiz_id.lower() == "undefined" or quiz_id.lower() == "null":
            raise HTTPException(
                status_code=400, 
                detail="Invalid quiz ID. Please provide a valid quiz ID."
            )
            
        # Get quiz data from database (this will raise 404 if not found)
        try:
            quiz_data = get_quiz_from_database(quiz_id, user_token)
        except HTTPException as e:
            if e.status_code == 404:
                # Quiz truly doesn't exist
                raise HTTPException(status_code=404, detail="Quiz not found")
            raise
        
        # Log quiz access attempt (without exposing user IDs)
        logger.info(f"Quiz access check for quiz ID: {quiz_id}")
        
        # Verify that the user has access to this quiz
        if quiz_data["created_by"] != current_user_id:
            logger.warning(f"Access denied - User {current_user_id} trying to access quiz {quiz_id} created by {quiz_data['created_by']}")
            raise HTTPException(
                status_code=403, 
                detail="Access denied. You don't have permission to view this quiz."
            )
        
        return quiz_data
    
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving quiz: {str(e)}")

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
    validate_user_quota(current_user_id, user_token)
    
    try:
        # Get user tier info for logging
        tier_info = get_user_tier_info(current_user_id, user_token)
        
        # Scrape content with user ID for resource tracking
        logger.info(f"User {current_user_id} ({tier_info['account_tier']} tier) generating quiz from URL: {data.url}")
        content = await scrape_content(str(data.url), current_user_id)
        
        # Generate quiz
        total_questions = data.num_questions if data.num_questions is not None else 10
        quizzes = await generate_quizzes_single_async(
            content,
            total_questions,
            question_types=list(data.question_type)
        )
        
        # Save to database
        quiz_id, saved_questions = save_quiz_to_database(
            data.title, 
            quizzes, 
            current_user_id,
            content_source_type="url",
            content_source_reference=str(data.url),
            user_token=user_token
        )
        logger.info(f"Saved quiz from URL with ID: {quiz_id}")
        
        # Save metadata
        metadata = {
            "quiz_id": quiz_id,
            "content_type": "url",
            "file_name": str(data.url),
            "file_type": "text/html",
            "word_count": len(content.split()),
            "created_by": current_user_id,
            "created_at": datetime.now().isoformat(),
            "question_count": len(quizzes)
        }
        save_metadata(metadata, user_token=user_token)
        logger.info(f"Saved metadata for URL quiz {quiz_id}")
        
        return {
            "quiz_id": quiz_id,
            "title": data.title,
            "message": "Quiz generated successfully from URL",
            "questions": saved_questions,  # Return saved questions with IDs
            "source_url": str(data.url)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating quiz from URL {data.url}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error generating quiz from URL: {str(e)}"
        )

