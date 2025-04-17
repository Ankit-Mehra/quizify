from fastapi import HTTPException, Depends, Path, Body
from services.ai_services.doc_service import extract_text_from_pdf,extract_text_from_plain_text, extract_text_from_docx
from services.db_services.supabase_quiz import save_quiz_to_database, get_user_quizzes, get_quiz_from_database,save_metadata, get_metadata
from services.db_services.supabase_file import get_file_record, save_file_to_supabase, parse_file_from_supabase
from dependencies.auth_helper import get_current_user_id, get_current_user_token
from schemas.quiz import TextQuizRequest, FileQuizRequest
from typing import Dict, Any
from datetime import datetime
from services.ai_services.chunking_service import generate_questions_async

# === Generate quiz from file ===
async def generate_quiz_from_file_openai(
    data: FileQuizRequest = Body(...),
    current_user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token)
):
    if data.file.content_type not in ["application/pdf", "text/plain", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]:
        raise HTTPException(status_code=400, detail="Only PDF, DOCX, or TXT files are supported.")

    try:
        text = await data.file.read()
        
        # Choose the appropriate extractor based on file type
        if data.file.content_type == "application/pdf":
            parsed_text = extract_text_from_pdf(text)
        elif data.file.content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            parsed_text = extract_text_from_docx(text)
        else:  # text/plain
            parsed_text = extract_text_from_plain_text(text)

        quizzes = await generate_questions_async(
            parsed_text, 
            data.num_questions,
            question_types=data.question_type
        )
        quiz_id = save_quiz_to_database(data.title, quizzes, current_user_id)

        metadata = {
            "quiz_id": quiz_id,
            "content_type": "file",
            "file_name": data.file.filename,
            "file_type": data.file.content_type,
            "word_count": len(parsed_text.split()),
            "created_by": current_user_id,
            "created_at": datetime.now().isoformat(),
            "question_count": data.num_questions
        }

        #save metadata to database
        save_metadata(metadata)

        #save file to supabase storage
        file_bytes = await data.file.read()
        save_file_to_supabase(current_user_id, file_bytes, data.file.filename, user_token)

        return {
            "quiz_id": quiz_id, 
            "title": data.title,
            "message": "Quiz generated successfully from file"
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

# === Generate quiz from file ID ===
async def generate_quiz_from_fileid(
    file_id: str = Path(...),
    data: FileQuizRequest = Body(...),
    current_user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token)
):
    try:
        file_record = get_file_record(file_id)
        if not file_record:
            raise HTTPException(status_code=404, detail="File not found")
        
        file_content = parse_file_from_supabase(file_record, user_token)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")

    try:   
        quizzes = await generate_questions_async(
            file_content, 
            data.num_questions,
            question_types=data.question_type
        )

        quiz_id = save_quiz_to_database(data.title, quizzes, current_user_id)
        
        return {
            "quiz_id": quiz_id, 
            "title": data.title,
            "message": "Quiz generated successfully from file"
        }
    except Exception as e:
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
            
        # Generate quiz questions
        quizzes = await generate_questions_async(
            data.content, 
            data.num_questions,
            question_types=data.question_type
        )
            
        # Save to database
        quiz_id = save_quiz_to_database(data.title, quizzes, current_user_id)

        # Convert text content to bytes
        text_bytes = data.content.encode('utf-8')
        
        # Save to Supabase storage
        save_file_to_supabase(current_user_id, text_bytes, f"{data.title}.txt", user_token, "text/plain")
        
        #save metadata to database
        metedata = {
            "quiz_id": quiz_id,
            "content_type": "text",
            "file_name": f"{data.title}.txt",
            "file_type": "text/plain",
            "word_count": len(data.content.split()),
            "created_by": current_user_id,
            "created_at": datetime.now().isoformat(),
            "question_count": data.num_questions
        }
        save_metadata(metedata)
        
        # Return response
        return {
            "quiz_id": quiz_id, 
            "title": data.title,
            "message": "Quiz generated successfully from text"
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
    current_user_id: str = Depends(get_current_user_id)
):
    """Get all quizzes created by the current user."""
    try:
        quizzes = get_user_quizzes(current_user_id)
        return quizzes
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# === Get quiz by ID ===
async def get_quiz_by_id_handler(
    quiz_id: str = Path(...),
    current_user_id: str = Depends(get_current_user_id)
):
    """Get a specific quiz by ID."""
    try:
        # Check for invalid quiz IDs
        if not quiz_id or quiz_id.lower() == "undefined" or quiz_id.lower() == "null":
            raise HTTPException(
                status_code=400, 
                detail="Invalid quiz ID. Please provide a valid quiz ID."
            )
            
        # Get quiz data from database
        quiz_data = get_quiz_from_database(quiz_id)
        
        # Verify that the user has access to this quiz
        if quiz_data["created_by"] != current_user_id:
            raise HTTPException(status_code=403, detail="You do not have permission to access this quiz.")
        
        return quiz_data
    
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving quiz: {str(e)}")

# === Get metadata ===
async def get_metadata_handler(
    current_user_id: str = Depends(get_current_user_id),
):
    """Get all content sources created by the current user."""
    try:
        sources = get_metadata(current_user_id)
        
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
