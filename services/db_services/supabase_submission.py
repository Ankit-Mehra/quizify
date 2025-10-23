## Submission DB Services
from services.logger import db_logger as logger
from typing import List
from schemas.submission import QuizSubmission, QuizAnswer
from schemas.quiz import Question
from fastapi import HTTPException
from uuid import UUID
from config import config as app_config

# Lazy load Supabase client to avoid initialization issues in tests
def get_supabase():
    """Get Supabase client (lazy loaded)"""
    return app_config.get_supabase_client()

def get_question(question_ids: List[UUID]) -> List[Question]:
    """
    Get questions by their IDs using Supabase `.in_` clause
    """
    supabase = get_supabase()
    logger.debug(f"Fetching {len(question_ids)} questions")
    try:
        response = (
            supabase
            .table("questions")
            .select("*")
            .in_("id", question_ids)
            .execute()
        )
        
        if not response.data:
            logger.warning("No questions found for provided IDs")
            raise HTTPException(status_code=404, detail="Questions not found. The quiz may have been deleted.")

        logger.debug(f"Successfully retrieved {len(response.data)} questions")
        return response.data
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        # Log full error details for debugging
        logger.error(f"Database error retrieving questions: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve quiz questions. Please try again.")


def save_submission(submission: QuizSubmission):
    supabase = get_supabase()
    logger.debug(f"Saving submission for quiz_id: {submission.quiz_id}, user_id: {submission.user_id}")
    try:
        payload = submission.model_dump(mode="json")
        supabase.table("submissions").insert(payload).execute()
        logger.debug(f"Successfully saved submission: {submission.id}")
    except Exception as e:
        # Log full error details for debugging
        logger.error(f"Database error saving submission: {str(e)}")
        
        # Parse error and return user-friendly message
        error_str = str(e)
        if "23503" in error_str and "quiz_id" in error_str:
            raise HTTPException(status_code=404, detail="Quiz not found. Please verify the quiz ID.")
        elif "23503" in error_str:
            raise HTTPException(status_code=400, detail="Invalid reference in submission data.")
        elif "23505" in error_str:
            raise HTTPException(status_code=409, detail="This submission already exists.")
        else:
            raise HTTPException(status_code=500, detail="Failed to save submission. Please try again.")

def save_answer(answer: QuizAnswer):
    supabase = get_supabase()
    logger.debug(f"Saving answer for question_id: {answer.question_id}")
    try:
        payload = answer.model_dump(mode="json")
        supabase.table("answers").insert(payload).execute()
    except Exception as e:
        # Log full error details for debugging
        logger.error(f"Database error saving answer: {str(e)}")
        
        # Parse error and return user-friendly message
        error_str = str(e)
        if "23503" in error_str:
            raise HTTPException(status_code=400, detail="Invalid question or submission reference.")
        elif "23505" in error_str:
            raise HTTPException(status_code=409, detail="This answer has already been recorded.")
        else:
            raise HTTPException(status_code=500, detail="Failed to save answer. Please try again.")

def get_submission_by_id(submission_id: UUID) -> QuizSubmission:
    supabase = get_supabase()
    logger.debug(f"Fetching submission with id: {submission_id}")
    try:
        response = (
            supabase
            .table("submissions")
            .select("*")
            .eq("id", submission_id)
            .execute()
        )
        if not response.data:
            logger.warning(f"Submission not found: {submission_id}")
            raise HTTPException(status_code=404, detail="Submission not found.")

        logger.debug(f"Successfully retrieved submission: {submission_id}")
        return QuizSubmission(**response.data[0])
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        # Log full error details for debugging
        logger.error(f"Database error fetching submission: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve submission. Please try again.")
