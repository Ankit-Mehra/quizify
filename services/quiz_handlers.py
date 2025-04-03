from fastapi import UploadFile, File, Query, HTTPException, Depends
from services.gemini import generate_quiz
from services.openai import generate_quiz as generate_quiz_openai
from services.doc_service import extract_text_from_pdf, extract_text_from_plain_text
from services.supabase import save_quiz_to_database
from dependencies.auth_helper import get_current_user_id


async def generate_quiz_from_file(
    file: UploadFile = File(...),
    num_questions: int = Query(1, gt=0, le=50),
    current_user_id: str = Depends(get_current_user_id),
):
    if file.content_type not in ["application/pdf", "text/plain"]:
        raise HTTPException(status_code=400, detail="Only PDF or TXT files are supported.")

    text = await file.read()
    parsed_text = (
        extract_text_from_pdf(text)
        if file.content_type == "application/pdf"
        else extract_text_from_plain_text(text)
    )

    quizzes = generate_quiz(parsed_text, num_questions)
    save_quiz_to_database(file.filename, quizzes, current_user_id)
    return quizzes


async def generate_quiz_from_file_openai(
    file: UploadFile = File(...),
    num_questions: int = Query(10, gt=0, le=50),
    current_user_id: str = Depends(get_current_user_id),
):
    if file.content_type not in ["application/pdf", "text/plain"]:
        raise HTTPException(status_code=400, detail="Only PDF or TXT files are supported.")

    text = await file.read()
    parsed_text = (
        extract_text_from_pdf(text)
        if file.content_type == "application/pdf"
        else extract_text_from_plain_text(text)
    )

    quizzes = list(generate_quiz_openai(parsed_text, num_questions))
    save_quiz_to_database(file.filename, quizzes, current_user_id)
    return quizzes

