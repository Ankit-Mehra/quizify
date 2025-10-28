## Submission Handler
from typing import List, Any
from schemas.quiz import MCQQuestion, TrueFalseQuestion, FillBlankQuestion, MatchingQuestion, Question
from schemas.submission import QuizSubmission, QuizAnswer, QuizSubmissionRequest
from pydantic import ValidationError
from fastapi import HTTPException, Depends
from uuid import UUID, uuid4
from datetime import datetime
from services.db_services.supabase_submission import get_question, save_submission, save_answer, get_submission_by_id, get_user_submissions, get_quiz_submissions
from services.db_services.supabase_quiz import get_quiz_from_database
from dependencies.auth_dependencies import get_current_user_id, get_current_user_token
from services.logger import app_logger as logger


TYPE_TO_MODEL = {
    "multiple_choice": MCQQuestion,
    "true_false": TrueFalseQuestion,
    "fill_blank": FillBlankQuestion,
    "matching": MatchingQuestion,
}

def parse_question_models(raw_questions: List[Any]) -> List[Question]:
    """
    Converts list of raw dicts (from Supabase) into strongly-typed Pydantic question models.
    """
    parsed_questions = []

    for q in raw_questions:
        question_type = q.get("type", "")
        model_cls = TYPE_TO_MODEL.get(question_type) if question_type else None
        if not model_cls:
            logger.warning(f"Unknown question type: {q.get('type')}")
            continue
        try:
            parsed_questions.append(model_cls(**q))
        except ValidationError as e:
            logger.warning(f"Failed to parse question {q.get('id')}: {e}")
            continue

    return parsed_questions


async def submit_quiz(
    quiz_id: UUID,
    submission: QuizSubmissionRequest,
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token)
):
    """Submit answers for a quiz and get detailed results with score"""
    # Validate that quiz_id in path matches quiz_id in body
    if submission.quiz_id != quiz_id:
        raise HTTPException(
            status_code=400, 
            detail="Quiz ID in URL does not match quiz ID in request body"
        )
    
    # Validate that the quiz exists before processing submission
    # Note: total_questions > 0 is already validated by Pydantic schema (gt=0)
    try:
        get_quiz_from_database(str(quiz_id), user_token)
    except HTTPException as e:
        if e.status_code == 404:
            raise HTTPException(status_code=404, detail="Quiz not found. Please verify the quiz ID.")
        raise
    
    correct = 0
    wrong = 0
    detailed_results = []

    # Fetch raw questions using authenticated client (RLS enforcement)
    question_ids = [a.question_id for a in submission.answers]
    try:
        raw_questions = get_question(question_ids, user_token)
        questions = parse_question_models(raw_questions)
        question_map = {q.id: q for q in questions}
    except Exception as e:
        logger.error(f"Error fetching or parsing questions: {e}")
        raise HTTPException(status_code=500, detail="Error processing questions")

    # Evaluate answers
    for ans in submission.answers:
        q = question_map.get(ans.question_id)
        if not q:
            continue

        is_correct = str(ans.user_answer).strip().lower() == str(q.correct_answer).strip().lower()
        if is_correct:
            correct += 1
        else:
            wrong += 1

        detailed_results.append({
            "question_id": str(q.id),
            "question": q.question,
            "your_answer": ans.user_answer,
            "correct_answer": q.correct_answer,
            "is_correct": is_correct,
        })

    # Calculate score as integer (database expects INTEGER type)
    score = int(round((correct / submission.total_questions) * 100))

    new_submission = QuizSubmission(
        id=uuid4(),
        user_id=UUID(user_id),  # Convert string user_id to UUID
        quiz_id=submission.quiz_id,
        correct_count=correct,
        wrong_count=wrong,
        score=score,
        total_questions=submission.total_questions,
        submitted_at=datetime.now()
    )

    # Save submission with authenticated client (RLS enforcement)
    save_submission(new_submission, user_token)

    for result in detailed_results:
        # Save each answer with authenticated client (RLS enforcement)
        save_answer(QuizAnswer(
            id=uuid4(),
            submission_id=new_submission.id,
            question_id=result["question_id"],
            user_answer=result["your_answer"],
            correct_answer=result["correct_answer"],
            is_correct=result["is_correct"]
        ), user_token)

    return {
        "id": new_submission.id,
        "total_questions": submission.total_questions,
        "correct_count": correct,
        "wrong_count": wrong,
        "score": score,
        "detailed_results": detailed_results
    }


async def get_submission(
    submission_id: UUID, 
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token)
):
    """Retrieve a submission by ID with authorization check"""
    try:
        # Use authenticated client (RLS enforcement)
        submission = get_submission_by_id(submission_id, user_token)
        
        # Authorization check: user can only access their own submissions
        # Convert both to strings for comparison (user_id is string from auth, submission.user_id is UUID)
        if str(submission.user_id) != str(user_id):
            logger.warning(f"User {user_id} attempted to access submission {submission_id} owned by {submission.user_id}")
            raise HTTPException(status_code=403, detail="You are not authorized to access this submission")
        
        logger.info(f"User {user_id} successfully accessed their submission {submission_id}")
        return submission
    except HTTPException:
        raise  # Re-raise HTTP exceptions (404, 403, etc.)
    except Exception as e:
        logger.error(f"Unexpected error retrieving submission {submission_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve submission. Please try again.")


async def list_user_submissions(
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token)
):
    """
    Get all quiz submissions for the current user.
    Returns list of submissions with basic info (no detailed answers).
    """
    try:
        logger.info(f"User {user_id} fetching all their submissions")
        
        # Use authenticated client (RLS enforcement)
        submissions = get_user_submissions(user_id, user_token)
        
        logger.info(f"User {user_id} has {len(submissions)} submissions")
        return {
            "user_id": user_id,
            "total_submissions": len(submissions),
            "submissions": submissions
        }
    except Exception as e:
        logger.error(f"Error listing submissions for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve submissions. Please try again.")


async def list_quiz_submissions(
    quiz_id: UUID,
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token)
):
    """
    Get all submissions for a specific quiz by the current user.
    Useful for seeing attempt history on a particular quiz.
    """
    try:
        logger.info(f"User {user_id} fetching submissions for quiz {quiz_id}")
        
        # Use authenticated client (RLS enforcement)
        submissions = get_quiz_submissions(str(quiz_id), user_id, user_token)
        
        logger.info(f"User {user_id} has {len(submissions)} attempts on quiz {quiz_id}")
        return {
            "quiz_id": str(quiz_id),
            "user_id": user_id,
            "total_attempts": len(submissions),
            "submissions": submissions
        }
    except Exception as e:
        logger.error(f"Error listing submissions for quiz {quiz_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve quiz submissions. Please try again.")
