## Submission DB Services
import os
from supabase import create_client, Client
from services.logger import db_logger as logger
from typing import List
from schemas.submission import QuizSubmission, QuizAnswer
from schemas.quiz import Question
from fastapi import HTTPException
from uuid import UUID
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TESTING = os.getenv("TESTING", "false").lower() == "true"

if not TESTING:
    supabase: Client = create_client(
        supabase_url=SUPABASE_URL,
        supabase_key=SUPABASE_KEY
    )
else:
    supabase = None

def get_question(question_ids: List[UUID]) -> List[Question]:
    """
    Get questions by their IDs using Supabase `.in_` clause
    """
    logger.info(f"Getting questions with ids: {question_ids}")
    try:
        response = (
            supabase
            .table("questions")
            .select("*")
            .in_("id", question_ids)
            .execute()
        )
        return response.data
    except Exception as e:
        logger.error(f"Error retrieving questions: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving questions: {str(e)}")


def save_submission(submission: QuizSubmission):
    logger.info(f"Saving submission: {submission}")
    try:
        payload = submission.model_dump(mode="json")
        supabase.table("submissions").insert(payload).execute()
    except Exception as e:
        logger.error(f"Error saving submission: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error saving submission: {str(e)}")

def save_answer(answer: QuizAnswer):
    logger.info(f"Saving answer: {answer}")
    try:
        payload = answer.model_dump(mode="json")
        supabase.table("answers").insert(payload).execute()
    except Exception as e:
        logger.error(f"Error saving answer: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error saving answer: {str(e)}")

def get_submission_by_id(submission_id: UUID) -> QuizSubmission:
    logger.info(f"Getting submission with id: {submission_id}")
    try:
        response = (
            supabase
            .table("submissions")
            .select("*")
            .eq("id", submission_id)
            .execute()
        )
        return response.data[0]
    except Exception as e:
        logger.error(f"Error getting submission: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting submission: {str(e)}")
