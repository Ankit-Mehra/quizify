import os
from fastapi import HTTPException
from supabase import create_client, Client
from schemas.quiz import Question
from typing import List


STORAGE_NAME = os.getenv("SUPABASE_STORAGE_NAME")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(
    supabase_url=SUPABASE_URL,
    supabase_key=SUPABASE_KEY
)

def get_authed_supabase_client(user_token: str):
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    supabase.auth.session = {'access_token': user_token}
    return supabase

def save_quiz_to_database(title: str, quizzes: List[Question], created_by: str):
    try:
        # Validate user ID to prevent UUID errors
        if not created_by or created_by == "undefined":
            raise HTTPException(
                status_code=401, 
                detail="User authentication required to save quiz"
            )
        if not quizzes:
            raise HTTPException(status_code=500, detail="No questions were generated.")
        
        quiz_response = supabase.table("quizzes").insert({
            "title": title,
            "created_by": created_by
        }).execute()
        quiz_id = quiz_response.data[0]["id"]

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
                base["correct_answer"] = q.correct_answer

            elif q.type == "matching":
                base["left"] = q.left
                base["right"] = q.right
                base["correct_answer"] = q.correct_answer  # list[int]

            question_payload.append(base)

        print("📦 Payload to insert:", question_payload)
        # Insert into questions table
        supabase.table("questions").insert(question_payload).execute()

        return quiz_id

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def get_quiz_from_database(quiz_id: str):
    try:
        # Get the quiz metadata
        quiz = supabase.table("quizzes").select("*").eq("id", quiz_id).execute()
        if not quiz.data:
            raise HTTPException(status_code=404, detail="Quiz not found")
        
        # Get the questions for the quiz
        questions = supabase.table("questions").select("*").eq("quiz_id", quiz_id).execute()
        
        quiz_data = quiz.data[0]
        questions_data = questions.data
        
        # Format the response
        return {
            "id": quiz_data["id"],
            "title": quiz_data["title"],
            "created_by": quiz_data["created_by"],
            "created_at": quiz_data["created_at"],
            "questions": questions_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def get_user_quizzes(user_id: str):
    try:
        # Get all quizzes for a user
        quizzes_data = supabase.table("quizzes").select("*").eq("created_by", user_id).execute()
        
        if not quizzes_data.data:
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
        
        return quizzes
    except Exception as e:
        print(f"Error in get_user_quizzes: {str(e)}")  # Detailed logging
        raise HTTPException(status_code=500, detail=str(e))


def save_metadata(metadata: dict):
    try:
        supabase.table("quiz_metadata").insert(metadata).execute()

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def get_metadata(user_id: str):
    try:
        metadata = supabase.table("quiz_metadata").select("*").eq("created_by", user_id).execute()
        return metadata.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
