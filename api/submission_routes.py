## Submission Routes
from fastapi import APIRouter
from services.logger import app_logger as logger
from schemas.submission import SubmissionResponse, QuizSubmission
from handlers.submission_handler import submit_quiz, get_submission

router = APIRouter(prefix="/submission", tags=["Submission"])
logger.info("Submission routes initialized")


router.add_api_route(
    path="/submit",
    endpoint=submit_quiz,
    methods=["POST"],
    summary="Submit a submission",
    response_model=SubmissionResponse
)

router.add_api_route(
    path="/{submission_id}",
    endpoint=get_submission,
    methods=["GET"],
    summary="Get a submission",
    response_model=QuizSubmission
)
