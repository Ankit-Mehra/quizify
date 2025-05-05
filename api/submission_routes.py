## Submission Routes
from fastapi import APIRouter, Depends
from services.logger import app_logger as logger
from schemas.submission import SubmissionResponse, QuizSubmission
from handlers.submission_handler import submit_quiz, get_submission
from dependencies.auth_dependencies import get_current_user_id

router = APIRouter(prefix="/submission", tags=["Submission"])
logger.info("Submission routes initialized")


router.add_api_route(
    path="/submit",
    endpoint=submit_quiz,
    methods=["POST"],
    summary="Submit a submission",
    response_model=SubmissionResponse,
    dependencies=[Depends(get_current_user_id)],
    openapi_extra={
        "security": [{"BearerAuth": []}]
    }
)

router.add_api_route(
    path="/{submission_id}",
    endpoint=get_submission,
    methods=["GET"],
    summary="Get a submission",
    response_model=QuizSubmission,
    dependencies=[Depends(get_current_user_id)],
    openapi_extra={
        "security": [{"BearerAuth": []}]
    }
)
