from fastapi import APIRouter, Depends
from schemas.quiz import QuizQuestions
from dependencies.auth_helper import get_current_user_id
from services.quiz_handlers import (
    generate_quiz_from_file,
    generate_quiz_from_file_openai
)

router = APIRouter()

# Gemini quiz
router.add_api_route(
    path="/ai/generate-quiz",
    endpoint=generate_quiz_from_file,
    methods=["POST"],
    response_model=QuizQuestions,
    summary="Generate Quiz from File (Gemini)",
    tags=["Quiz Generation"],
    dependencies=[Depends(get_current_user_id)],
    openapi_extra={"security": [{"BearerAuth": []}]},
)

# OpenAI quiz
router.add_api_route(
    path="/ai/generate-quiz-openai",
    endpoint=generate_quiz_from_file_openai,
    methods=["POST"],
    response_model=QuizQuestions,
    summary="Generate Quiz from File (OpenAI)",
    tags=["Quiz Generation"],
    dependencies=[Depends(get_current_user_id)],
    openapi_extra={"security": [{"BearerAuth": []}]},
)
