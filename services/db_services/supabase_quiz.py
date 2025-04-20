import os
from fastapi import HTTPException
from supabase import create_client, Client
from schemas.quiz import Question
from typing import List
from services.logger import db_logger as logger


STORAGE_NAME = os.getenv("SUPABASE_STORAGE_NAME")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(
    supabase_url=SUPABASE_URL,
    supabase_key=SUPABASE_KEY
)
logger.info("Supabase client initialized")

def get_authed_supabase_client(user_token: str):
    logger.debug(f"Creating authenticated Supabase client with token: {user_token[:10]}...")
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    supabase.auth.session = {'access_token': user_token}
    return supabase

def save_quiz_to_database(title: str, quizzes: List[Question], created_by: str):
    try:
        logger.info(f"Saving quiz '{title}' with {len(quizzes)} questions")
        # Validate user ID to prevent UUID errors
        if not created_by or created_by == "undefined":
            logger.error("User authentication required to save quiz")
            raise HTTPException(
                status_code=401, 
                detail="User authentication required to save quiz"
            )
        if not quizzes:
            logger.error("No questions were generated")
            raise HTTPException(status_code=500, detail="No questions were generated.")
        
        quiz_response = supabase.table("quizzes").insert({
            "title": title,
            "created_by": created_by
        }).execute()
        quiz_id = quiz_response.data[0]["id"]
        logger.info(f"Created quiz with ID: {quiz_id}")

        # Build question payload based on type
        question_payload = []

        for q in quizzes:
            base = {
                "quiz_id": quiz_id,
                "type": q.type,
                "question": q.question,
                "explanation": q.explanation,
                "source": q.source
            }

            if q.type == "multiple_choice":
                base["options"] = q.options
                base["correct_answer"] = q.correct_answer

            elif q.type == "true_false":
                base["correct_answer"] = q.correct_answer  # boolean, JSONB-compatible

            elif q.type == "fill_blank":
                base["options"] = q.options
                base["correct_answer"] = q.correct_answer

            elif q.type == "matching":
                base["left"] = q.left
                base["right"] = q.right
                base["correct_answer"] = q.correct_answer  # list[int]

            question_payload.append(base)

        # Insert into questions table
        supabase.table("questions").insert(question_payload).execute()
        logger.info(f"Added {len(question_payload)} questions to quiz {quiz_id}")

        return quiz_id

    except Exception as e:
        logger.error(f"Error saving quiz to database: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def get_quiz_from_database(quiz_id: str):
    try:
        logger.info(f"Fetching quiz with ID: {quiz_id}")
        # Get the quiz metadata
        quiz = supabase.table("quizzes").select("*").eq("id", quiz_id).execute()
        if not quiz.data:
            logger.warning(f"Quiz not found: {quiz_id}")
            raise HTTPException(status_code=404, detail="Quiz not found")
        
        # Get the questions for the quiz
        questions = supabase.table("questions").select("*").eq("quiz_id", quiz_id).execute()
        
        quiz_data = quiz.data[0]
        questions_data = questions.data
        logger.info(f"Found quiz '{quiz_data['title']}' with {len(questions_data)} questions")
        
        # Format the response
        return {
            "id": quiz_data["id"],
            "title": quiz_data["title"],
            "created_by": quiz_data["created_by"],
            "created_at": quiz_data["created_at"],
            "questions": questions_data
        }
    except Exception as e:
        logger.error(f"Error retrieving quiz from database: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def get_user_quizzes(user_id: str):
    try:
        logger.info(f"Fetching quizzes for user: {user_id}")
        # Get all quizzes for a user
        quizzes_data = supabase.table("quizzes").select("*").eq("created_by", user_id).execute()
        
        if not quizzes_data.data:
            logger.info(f"No quizzes found for user: {user_id}")
            return []
        
        # Process the results and add question_count
        quizzes = []
        for quiz in quizzes_data.data:
            # Count questions for this quiz
            questions = supabase.table("questions").select("id", count="exact").eq("quiz_id", quiz["id"]).execute()
            
            quizzes.append({
                "id": quiz["id"],
                "title": quiz["title"],
                "created_at": quiz["created_at"],
                "created_by": quiz["created_by"],
                "question_count": questions.count or 0  # Add question count
            })
        
        logger.info(f"Found {len(quizzes)} quizzes for user: {user_id}")
        return quizzes
    except Exception as e:
        logger.error(f"Error retrieving user quizzes: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def save_metadata(metadata: dict):
    try:
        logger.info(f"Saving metadata for quiz: {metadata.get('quiz_id', 'unknown')}")
        supabase.table("quiz_metadata").insert(metadata).execute()
        logger.info("Metadata saved successfully")
    except Exception as e:
        logger.error(f"Error saving metadata: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

def get_metadata(user_id: str):
    try:
        logger.info(f"Fetching metadata for user: {user_id}")
        metadata = supabase.table("quiz_metadata").select("*").eq("created_by", user_id).execute()
        logger.info(f"Found {len(metadata.data)} metadata records for user: {user_id}")
        return metadata.data
    except Exception as e:
        logger.error(f"Error retrieving metadata: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
