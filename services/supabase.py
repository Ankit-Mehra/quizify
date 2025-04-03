from fastapi import HTTPException
from supabase import create_client, Client
from schemas.quiz import QuizQuestions
import os

supabase: Client = create_client(
    supabase_url=os.getenv("SUPABASE_URL"),
    supabase_key=os.getenv("SUPABASE_KEY")
)

def save_quiz_to_database(title: str, quizzes: QuizQuestions, created_by: str):
    try:
        # Convert QuizQuestions to dictionary
        quiz_dict = quizzes.model_dump()
        
        quiz_response = supabase.table("quizzes").insert({
            "title": title,
            "created_by": created_by
        }).execute()
        quiz_id = quiz_response.data[0]["id"]
        
        # Insert questions
        question_payload = [
            {
                "quiz_id": quiz_id,
                **q
            }
            for q in quiz_dict.get("quizzes", [])
        ]
        
        supabase.table("questions").insert(question_payload).execute()
        return {"message": "Quizzes saved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def get_quiz_from_database(quiz_id: int):
    return supabase.table("quizzes").select("*").eq("id", quiz_id).execute().data[0]

