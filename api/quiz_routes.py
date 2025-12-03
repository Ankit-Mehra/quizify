from fastapi import APIRouter, HTTPException, Response, Depends
from schemas.quiz import (
    QuizMetadata, 
    QuizGenerationResponse,
    QuizzesResponse,
    MyQuizzesResponse,
    DeleteQuizResponse,
    EnhancedTextQuizRequest,
    EnhancedQuizGenerationResponse
)
from handlers.quiz_handlers import (
    generate_quiz_from_file_openai,
    generate_quiz_from_text,
    generate_quiz_from_fileid,
    generate_quiz_from_url,
    get_user_quizzes_handler,
    get_quiz_by_id_handler,
    get_metadata_handler,
    delete_quiz_by_id_handler,
    generate_quiz_rag_async
)
from dependencies.auth_dependencies import get_current_user_id, get_current_user_token
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

# Generate quiz from text
router.add_api_route(
    path="/quiz/generate/text",
    endpoint=generate_quiz_from_text,
    methods=["POST"],
    summary="Generate Quiz from Text",
    response_model=QuizGenerationResponse,
    tags=["Quiz Generation"]
)

# Generate quiz from file
router.add_api_route(
    path="/quiz/generate/file",
    endpoint=generate_quiz_from_file_openai,
    methods=["POST"],
    summary="Generate Quiz from File (Gemini)",
    response_model=QuizGenerationResponse,
    status_code=201,
    tags=["Quiz Generation"]
)

# Generate quiz from URL (must come BEFORE /quiz/generate/{file_id} to avoid route conflict)
router.add_api_route(
    path="/quiz/generate/url",
    endpoint=generate_quiz_from_url,
    methods=["POST"],
    summary="Generate Quiz from Web URL",
    description="Generate a quiz from a web page URL. Available for all tiers with quota limits (Free: 5, Basic: 100, Pro: Unlimited).",
    response_model=QuizGenerationResponse,
    status_code=201,
    tags=["Quiz Generation"]
)

# Generate quiz from file ID (must come AFTER specific routes like /url to avoid capturing them)
router.add_api_route(
    path="/quiz/generate/{file_id}",
    endpoint=generate_quiz_from_fileid,
    methods=["POST"],
    summary="Generate Quiz from File ID",
    response_model=QuizGenerationResponse,
    tags=["Quiz Generation"]
)

# Get user quizzes
router.add_api_route(
    path="/quiz/my-quizzes",
    endpoint=get_user_quizzes_handler,
    methods=["GET"],
    response_model=List[MyQuizzesResponse],
    summary="Get User Quizzes",
    description="Returns a list of all quizzes created by the current user, with metadata such as title, creation date, and question count.",
    tags=["Quiz Management"]
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
    tags=["Content Management"]
)

# Get specific quiz data (API endpoint for JSON data)
router.add_api_route(
    path="/quiz/{quiz_id}",
    endpoint=get_quiz_by_id_handler,
    methods=["GET"],
    response_model=QuizzesResponse,
    summary="Get Quiz by ID",
    tags=["Quiz Management"]
)

# Delete quiz by ID
router.add_api_route(
    path="/quiz/{quiz_id}",
    endpoint=delete_quiz_by_id_handler,
    methods=["DELETE"],
    summary="Delete Quiz by ID",
    response_model=DeleteQuizResponse,
    tags=["Quiz Management"]
)

# === V2 RAG Pipeline Endpoints ===

@router.post(
    "/v2/quiz/text",
    response_model=EnhancedQuizGenerationResponse,
    summary="Generate Enhanced Quiz from Text (RAG)",
    tags=["Quiz Generation V2"]
)
async def generate_quiz_from_text_v2(
    request: EnhancedTextQuizRequest,
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token)
):
    """
    Generate a high-quality quiz from text using the RAG pipeline.
    Includes concept extraction, Bloom's taxonomy classification, and difficulty leveling.
    """
    return await generate_quiz_rag_async(request, user_id, user_token)
