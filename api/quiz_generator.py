from fastapi import APIRouter, File, UploadFile, HTTPException, Query
from schemas.quiz import QuizQuestions
from services.gemini import generate_quiz
from services.openai import generate_quiz as generate_quiz_openai
from services.doc_service import extract_text_from_pdf, extract_text_from_plain_text

router = APIRouter()

@router.post("/ai/generate-quiz", response_model=QuizQuestions)
async def generate_quiz_from_file(file: UploadFile = File(...), num_questions: int = Query(10, gt=0, le=50)):
    if file.content_type not in ["application/pdf", "text/plain"]:
        raise HTTPException(status_code=400, detail="Only PDF or TXT files are supported.")

    if file.content_type == "application/pdf":
        text = extract_text_from_pdf(await file.read())
    else:
        text = extract_text_from_plain_text(await file.read())

    # TODO: Send text to Gemini and parse response
    print("\n=== Parsed Text ===\n", text[:1000], "\n===================")

    quizzes = generate_quiz(text, num_questions)
    return quizzes


@router.post("/ai/generate-quiz-openai", response_model=QuizQuestions)
async def generate_quiz_from_file_openai(file: UploadFile = File(...), num_questions: int = Query(10, gt=0, le=50)):
    if file.content_type not in ["application/pdf", "text/plain"]:
        raise HTTPException(status_code=400, detail="Only PDF or TXT files are supported.")
    
    text = await file.read()

    if file.content_type == "application/pdf":
        text = extract_text_from_pdf(text)
    else:
        text = extract_text_from_plain_text(text)
    
    quizzes = generate_quiz_openai(text, num_questions)
    return quizzes
