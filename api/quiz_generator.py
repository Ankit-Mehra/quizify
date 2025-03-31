from fastapi import APIRouter, File, UploadFile, HTTPException
from schemas.quiz import QuizQuestion
from services.gemini import generate_quiz
from services.openai import generate_quiz as generate_quiz_openai
from services.doc_service import extract_text_from_pdf, extract_text_from_plain_text

router = APIRouter()

@router.post("/ai/generate-quiz", response_model=QuizQuestion)
async def generate_quiz_from_file(file: UploadFile = File(...)):
    if file.content_type not in ["application/pdf", "text/plain"]:
        raise HTTPException(status_code=400, detail="Only PDF or TXT files are supported.")

    if file.content_type == "application/pdf":
        text = extract_text_from_pdf(await file.read())
    else:
        text = extract_text_from_plain_text(await file.read())

    # TODO: Send text to Gemini and parse response
    print("\n=== Parsed Text ===\n", text[:1000], "\n===================")

    quiz = generate_quiz(text)
    return quiz


@router.post("/ai/generate-quiz-openai", response_model=QuizQuestion)
async def generate_quiz_from_file_openai(file: UploadFile = File(...)):
    if file.content_type not in ["application/pdf", "text/plain"]:
        raise HTTPException(status_code=400, detail="Only PDF or TXT files are supported.")
    
    text = await file.read()

    if file.content_type == "application/pdf":
        text = extract_text_from_pdf(text)
    else:
        text = extract_text_from_plain_text(text)
    
    quiz = generate_quiz_openai(text)
    return quiz
