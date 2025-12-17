"""
Quiz Data Loader - Load quiz data for export processing.

This module handles loading quiz data from the database and transforming
it into the QuizExportData format used by all exporters.
"""

from typing import Optional
from uuid import UUID
from datetime import datetime
from fastapi import HTTPException

from schemas.export import (
    QuizExportData,
    ExportQuestion,
    ExportQuestionMCQ,
    ExportQuestionTrueFalse,
    ExportQuestionFillBlank,
    ExportQuestionMatching
)
from services.logger import app_logger as logger
from config import config as app_config


def get_service_role_client():
    """Get service role client for admin operations."""
    return app_config.get_service_role_client()


def get_authed_supabase_client(user_token: str):
    """Get authenticated client for user operations with RLS."""
    return app_config.get_authenticated_supabase_client(user_token)


async def load_quiz_for_export(
    quiz_id: str,
    user_id: str,
    user_token: str
) -> QuizExportData:
    """
    Load complete quiz data for export processing.
    
    This function:
    1. Verifies the quiz exists
    2. Verifies the user has access (owns the quiz) via RLS
    3. Loads all questions with proper type handling
    4. Transforms data into QuizExportData format
    
    Args:
        quiz_id: UUID of the quiz to load
        user_id: UUID of the requesting user
        user_token: JWT token for authenticated queries (required for RLS enforcement)
        
    Returns:
        QuizExportData containing all quiz and question data
        
    Raises:
        HTTPException 401: Missing authentication token
        HTTPException 404: Quiz not found
        HTTPException 403: User doesn't own the quiz
        HTTPException 500: Database error
    """
    import asyncio
    
    try:
        # Require authenticated client for RLS enforcement on user export operations
        if not user_token:
            raise HTTPException(
                status_code=401,
                detail="Authentication token required for quiz export"
            )
        supabase = get_authed_supabase_client(user_token)
        
        # Fetch quiz metadata
        def fetch_quiz():
            response = supabase.table("quizzes").select("*").eq("id", quiz_id).execute()
            return response.data[0] if response.data else None
        
        # Fetch questions
        def fetch_questions():
            response = supabase.table("questions").select("*").eq("quiz_id", quiz_id).execute()
            return response.data or []
        
        # Run both queries concurrently
        quiz_data, questions_data = await asyncio.gather(
            asyncio.to_thread(fetch_quiz),
            asyncio.to_thread(fetch_questions)
        )
        
        # Check if quiz exists
        if not quiz_data:
            logger.warning(f"Quiz not found for export: {quiz_id}")
            raise HTTPException(status_code=404, detail="Quiz not found")
        
        # Verify ownership (only if not using RLS via token)
        if not user_token and quiz_data.get("created_by") != user_id:
            logger.warning(f"User {user_id[:8]} attempted to export quiz {quiz_id[:8]} owned by {quiz_data.get('created_by', 'unknown')[:8]}")
            raise HTTPException(status_code=403, detail="You don't have access to this quiz")
        
        # Check if quiz has questions
        if not questions_data:
            logger.warning(f"Quiz {quiz_id[:8]} has no questions")
            raise HTTPException(
                status_code=400, 
                detail="Cannot export quiz with no questions"
            )
        
        # Transform questions into typed export format
        export_questions = _transform_questions(questions_data)
        
        # Parse created_at
        created_at = quiz_data.get("created_at")
        if isinstance(created_at, str):
            # Handle ISO format with or without timezone
            try:
                created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except ValueError:
                created_at = datetime.now()
        
        # Build export data
        export_data = QuizExportData(
            quiz_id=UUID(quiz_id),
            title=quiz_data.get("title", "Untitled Quiz"),
            description=quiz_data.get("description"),
            created_at=created_at,
            content_source_type=quiz_data.get("content_source_type"),
            content_source_reference=quiz_data.get("content_source_reference"),
            questions=export_questions
        )
        
        logger.info(f"Loaded quiz {quiz_id[:8]} for export: {len(export_questions)} questions")
        return export_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading quiz for export: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail="Failed to load quiz data for export"
        )


def _transform_questions(questions_data: list) -> list[ExportQuestion]:
    """
    Transform raw database questions into typed ExportQuestion models.
    
    Args:
        questions_data: List of question dicts from database
        
    Returns:
        List of typed ExportQuestion objects
    """
    export_questions: list[ExportQuestion] = []
    
    for q in questions_data:
        question_type = q.get("type", "").lower()
        question_id = UUID(q["id"])
        
        try:
            if question_type == "multiple_choice":
                export_questions.append(ExportQuestionMCQ(
                    id=question_id,
                    type="multiple_choice",
                    question=q.get("question", ""),
                    options=_ensure_list(q.get("options", [])),
                    correct_answer=str(q.get("correct_answer", "")),
                    explanation=q.get("explanation"),
                    distractor_explanations=q.get("distractor_explanations"),
                    source=q.get("source")
                ))
                
            elif question_type == "true_false":
                export_questions.append(ExportQuestionTrueFalse(
                    id=question_id,
                    type="true_false",
                    question=q.get("question", ""),
                    correct_answer=_parse_bool(q.get("correct_answer", True)),
                    explanation=q.get("explanation"),
                    source=q.get("source")
                ))
                
            elif question_type == "fill_blank":
                export_questions.append(ExportQuestionFillBlank(
                    id=question_id,
                    type="fill_blank",
                    question=q.get("question", ""),
                    options=_ensure_list(q.get("options", [])),
                    correct_answer=str(q.get("correct_answer", "")),
                    explanation=q.get("explanation"),
                    distractor_explanations=q.get("distractor_explanations"),
                    source=q.get("source")
                ))
                
            elif question_type == "matching":
                export_questions.append(ExportQuestionMatching(
                    id=question_id,
                    type="matching",
                    question=q.get("question", ""),
                    left=_ensure_list(q.get("left", [])),
                    right=_ensure_list(q.get("right", [])),
                    correct_answer=_ensure_int_list(q.get("correct_answer", [])),
                    explanation=q.get("explanation"),
                    source=q.get("source")
                ))
            else:
                logger.warning(f"Unknown question type '{question_type}' for question {question_id}")
                
        except Exception as e:
            logger.error(f"Error transforming question {question_id}: {str(e)}")
            # Skip malformed questions rather than failing entire export
            continue
    
    return export_questions


def _ensure_list(value) -> list:
    """Ensure value is a list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        # Try to parse JSON
        import json
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else [value]
        except json.JSONDecodeError:
            return [value]
    return [value]


def _ensure_int_list(value) -> list[int]:
    """Ensure value is a list of integers."""
    items = _ensure_list(value)
    result = []
    for item in items:
        try:
            result.append(int(item))
        except (ValueError, TypeError):
            continue
    return result


def _parse_bool(value) -> bool:
    """Parse a boolean value from various formats."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "t")
    if isinstance(value, (int, float)):
        return bool(value)
    return False


async def verify_quiz_ownership(
    quiz_id: str,
    user_id: str,
    user_token: str
) -> bool:
    """
    Verify that a user owns a specific quiz.
    
    Args:
        quiz_id: UUID of the quiz
        user_id: UUID of the user
        user_token: JWT token for RLS enforcement (required)
        
    Returns:
        True if user owns the quiz
        
    Raises:
        HTTPException 401: Missing authentication token
        HTTPException 404: Quiz not found
        HTTPException 403: User doesn't own the quiz
    """
    import asyncio
    
    # Require authenticated client for RLS enforcement on ownership verification
    if not user_token:
        raise HTTPException(
            status_code=401,
            detail="Authentication token required for ownership verification"
        )
    supabase = get_authed_supabase_client(user_token)
    
    def check_ownership():
        response = supabase.table("quizzes").select("id, created_by").eq("id", quiz_id).execute()
        return response.data[0] if response.data else None
    
    quiz = await asyncio.to_thread(check_ownership)
    
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    
    # With RLS enabled and user token, if we got a result, they have access
    if user_token:
        return True
    
    # Without RLS, check ownership manually
    if quiz.get("created_by") != user_id:
        raise HTTPException(status_code=403, detail="You don't have access to this quiz")
    
    return True
