## Submission Routes
from fastapi import APIRouter, Response
from services.logger import app_logger as logger
from schemas.submission import SubmissionResponse, QuizSubmission
from handlers.submission_handler import submit_quiz, get_submission

router = APIRouter(tags=["Quiz Submissions"])
logger.info("Submission routes initialized")

# OPTIONS handler for quiz submissions
@router.options("/quiz/{quiz_id}/submit")
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

# Submit quiz answers - RESTful endpoint
router.add_api_route(
    path="/quiz/{quiz_id}/submit",
    endpoint=submit_quiz,
    methods=["POST"],
    summary="Submit Quiz Answers",
    description=(
        "Submit answers for a quiz and receive detailed scoring results.\n\n"
        "**Important:** The `quiz_id` in the request body must match the `quiz_id` in the URL path. "
        "This is validated by the API and will return HTTP 400 if they don't match.\n\n"
        "**Request Body:**\n"
        "- `quiz_id`: Must match the URL parameter\n"
        "- `total_questions`: Total number of questions (must be > 0)\n"
        "- `answers`: List of answer submissions\n\n"
        "**Response:**\n"
        "- Submission ID for future reference\n"
        "- Score (0-100 percentage)\n"
        "- Correct/wrong counts\n"
        "- Detailed results for each question"
    ),
    response_model=SubmissionResponse
)

# Get submission by ID
router.add_api_route(
    path="/submission/{submission_id}",
    endpoint=get_submission,
    methods=["GET"],
    summary="Get Submission Details",
    description="Retrieve details of a previously submitted quiz",
    response_model=QuizSubmission
)
