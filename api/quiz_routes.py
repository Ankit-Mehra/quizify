from fastapi import APIRouter, Depends, HTTPException, Response
from schemas.quiz import (
    TextQuizRequest, 
    QuizMetadata, 
    QuizGenerationResponse,
    QuizzesResponse,
    MyQuizzesResponse,
    FileQuizRequest
)
from dependencies.auth_dependencies import get_current_user_id
from handlers.quiz_handlers import (
    generate_quiz_from_file_openai,
    generate_quiz_from_text,
    generate_quiz_from_fileid,
    get_user_quizzes_handler,
    get_quiz_by_id_handler,
    get_metadata_handler,
    submit_quiz_answers,
    delete_quiz_by_id_handler
)
from typing import List
from services.logger import app_logger as logger

router = APIRouter()
logger.info("Quiz routes initialized")

# Test endpoint to check if API is working
@router.get("/test")
async def test_api():
    logger.debug("Test API endpoint called")
    return {"status": "ok", "message": "API is working correctly"}

# OPTIONS handler for quiz/generate
@router.options("/quiz/generate", tags=["Quiz Generation"])
async def quiz_generate_options():
    logger.debug("OPTIONS request for /quiz/generate")
    return Response(
        content="",
        status_code=200,
        headers={
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, Accept",
            "Access-Control-Max-Age": "3600",
        },
    )

# OPTIONS handler for quiz submissions
@router.options("/quiz/{quiz_id}/submit", tags=["Quiz Management"])
async def quiz_submit_options(quiz_id: str):
    logger.debug(f"OPTIONS request for /quiz/{quiz_id}/submit")
    return Response(
        content="",
        status_code=200,
        headers={
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, Accept",
            "Access-Control-Max-Age": "3600",
        },
    )

# Generate quiz from text
router.add_api_route(
    path="/quiz/generate/text",
    endpoint=generate_quiz_from_text,
    methods=["POST"],
    summary="Generate Quiz from Text",
    response_model=QuizGenerationResponse,
    tags=["Quiz Generation"],
    dependencies=[Depends(get_current_user_id)],
    openapi_extra={
        "security": [{"BearerAuth": []}],
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": TextQuizRequest.model_json_schema()
                }
            }
        }
    },
)

# Generate quiz from file
router.add_api_route(
    path="/quiz/generate/file",
    endpoint=generate_quiz_from_file_openai,
    methods=["POST"],
    summary="Generate Quiz from File (Gemini)",
    response_model=QuizGenerationResponse,
    tags=["Quiz Generation"],
    dependencies=[Depends(get_current_user_id)],
    openapi_extra={
        "security": [{"BearerAuth": []}],
        "requestBody": {
            "content": {
                "multipart/form-data": {"schema": FileQuizRequest.model_json_schema()}
            }
        }
    }
)
# Generate quiz from file ID
router.add_api_route(
    path="/quiz/generate/{file_id}",
    endpoint=generate_quiz_from_fileid,
    methods=["POST"],
    summary="Generate Quiz from File ID",
    response_model=QuizGenerationResponse,
    tags=["Quiz Generation"],
    dependencies=[Depends(get_current_user_id)],
    openapi_extra={
        "security": [{"BearerAuth": []}],
        "requestBody": {
            "content": {
                "multipart/form-data": {"schema": FileQuizRequest.model_json_schema()}
            }
        }
    }
)

# Get user quizzes
router.add_api_route(
    path="/quiz/my-quizzes",
    endpoint=get_user_quizzes_handler,
    methods=["GET"],
    response_model=List[MyQuizzesResponse],
    summary="Get User Quizzes",
    description="Returns a list of all quizzes created by the current user, with metadata such as title, creation date, and question count.",
    tags=["Quiz Management"],
    dependencies=[Depends(get_current_user_id)],
    openapi_extra={"security": [{"BearerAuth": []}]},
)

# Handle undefined quiz ID specifically
@router.get("/quiz/undefined", tags=["Quiz Management"])
async def handle_undefined_quiz_id():
    logger.warning("Invalid quiz ID 'undefined' was requested")
    raise HTTPException(
        status_code=400, 
        detail="Invalid quiz ID. This usually happens when quiz generation fails or no quiz ID is provided."
    )

# Get metadata of quizzes created by user
router.add_api_route(
    path="/quiz/metadata",
    endpoint=get_metadata_handler,
    methods=["GET"],
    response_model=List[QuizMetadata],
    summary="Get User Content Sources",
    description="Returns a list of all content sources (text and files) used to generate quizzes for the current user.",
    tags=["Content Management"],
    dependencies=[Depends(get_current_user_id)],
    openapi_extra={"security": [{"BearerAuth": []}]},
)

# Get specific quiz data (API endpoint for JSON data)
router.add_api_route(
    path="/quiz/{quiz_id}",
    endpoint=get_quiz_by_id_handler,
    methods=["GET"],
    response_model=QuizzesResponse,
    summary="Get Quiz by ID",
    tags=["Quiz Management"],
    dependencies=[Depends(get_current_user_id)],
    openapi_extra={"security": [{"BearerAuth": []}]},
)

# Delete quiz by ID
router.add_api_route(
    path="/quiz/{quiz_id}",
    endpoint=delete_quiz_by_id_handler,
    methods=["DELETE"],
    summary="Delete Quiz by ID",
    tags=["Quiz Management"],
    dependencies=[Depends(get_current_user_id)],
    openapi_extra={"security": [{"BearerAuth": []}]},
)

# Submit quiz answers
router.add_api_route(
    path="/quiz/{quiz_id}/submit",
    endpoint=submit_quiz_answers,
    methods=["POST"],
    summary="Submit Quiz Answers",
    tags=["Quiz Management"],
    dependencies=[Depends(get_current_user_id)],
    openapi_extra={"security": [{"BearerAuth": []}]},
)
