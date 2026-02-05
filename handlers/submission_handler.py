## Submission Handler
import json
from typing import List, Any
from schemas.quiz import MCQQuestion, TrueFalseQuestion, FillBlankQuestion, MatchingQuestion, Question
from schemas.submission import QuizSubmission, QuizAnswer, QuizSubmissionRequest
from pydantic import ValidationError
from fastapi import HTTPException, Depends
from uuid import UUID, uuid4
from datetime import datetime
from services.db_services.supabase_submission import (
    get_question, 
    save_submission, 
    save_answer, 
    get_submission_by_id, 
    get_user_submissions_cached,
    get_quiz_submissions_cached,
    invalidate_user_submissions_cache,
    invalidate_quiz_submissions_cache,
    get_submission_review as get_review_from_db
)
from services.db_services.supabase_quiz import get_quiz_from_database
from services.answer_utils import is_unattempted
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


# Note: is_unattempted() is imported from services.answer_utils


def compare_answers(user_answer, correct_answer, question_type: str) -> bool:
    """
    Compare user answer with correct answer based on question type.
    
    Handles different answer formats:
    - multiple_choice/fill_blank: string comparison (case-insensitive)
    - true_false: boolean comparison (handles string "true"/"false" and bool True/False)
    - matching: list of integers comparison (order matters)
    
    Note: This function assumes the answer is attempted. Call is_unattempted() first
    to check if the user skipped the question.
    
    Args:
        user_answer: User's submitted answer
        correct_answer: Correct answer from question
        question_type: Type of question for type-aware comparison
        
    Returns:
        bool: True if answer is correct, False otherwise
    """
    if question_type == "matching":
        # Matching questions: correct_answer is List[int]
        # User answer could be List[int] or string representation
        try:
            # Normalize user answer to list
            if isinstance(user_answer, str):
                # Parse string like "[1, 0, 3, 2]" or "1,0,3,2"
                try:
                    user_list = json.loads(user_answer)
                except json.JSONDecodeError:
                    # Try comma-separated format
                    user_list = [int(x.strip()) for x in user_answer.split(",")]
            elif isinstance(user_answer, list):
                user_list = [int(x) for x in user_answer]
            else:
                return False
            
            # Normalize correct answer to list
            if isinstance(correct_answer, str):
                correct_list = json.loads(correct_answer)
            elif isinstance(correct_answer, list):
                correct_list = [int(x) for x in correct_answer]
            else:
                return False
            
            return user_list == correct_list
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            logger.warning(f"Error comparing matching answers: {e}")
            return False
    
    elif question_type == "true_false":
        # True/False questions: normalize to boolean
        def to_bool(val):
            if isinstance(val, bool):
                return val
            if isinstance(val, str):
                return val.strip().lower() == "true"
            return bool(val)
        
        return to_bool(user_answer) == to_bool(correct_answer)
    
    else:
        # multiple_choice, fill_blank: case-insensitive string comparison
        return str(user_answer).strip().lower() == str(correct_answer).strip().lower()


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
    
    # Validate answer count matches total_questions
    if len(submission.answers) != submission.total_questions:
        raise HTTPException(
            status_code=400,
            detail=f"Answer count mismatch: expected {submission.total_questions} answers, received {len(submission.answers)}"
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
    unattempted = 0
    skipped = 0  # Backend data issues (question not found)
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
            # Question not found or failed to parse - track as skipped
            skipped += 1
            logger.warning(f"Question {ans.question_id} not found in question_map, skipping")
            continue

        # Check if question was unattempted first (cache result to avoid duplicate computation)
        answer_is_unattempted = is_unattempted(ans.user_answer, q.type)
        if answer_is_unattempted:
            unattempted += 1
            is_correct = False
        else:
            # Use type-aware answer comparison for attempted questions
            is_correct = compare_answers(ans.user_answer, q.correct_answer, q.type)
            if is_correct:
                correct += 1
            else:
                wrong += 1

        detailed_results.append({
            "question_id": str(q.id),
            "question": q.question,
            "question_type": q.type,  # Include question type for frontend rendering
            "your_answer": ans.user_answer,
            "correct_answer": q.correct_answer,
            "is_correct": is_correct,
            "is_unattempted": answer_is_unattempted,
        })

    # Log warning if any questions were skipped (data integrity issue)
    if skipped > 0:
        logger.warning(
            f"Submission for quiz {quiz_id} had {skipped} skipped questions "
            f"(invalid IDs or parsing errors). Scored {correct + wrong + unattempted}/{submission.total_questions} questions."
        )

    # Calculate score based on all evaluated questions (Option B: include unattempted as wrong)
    # This prevents gaming the system by skipping difficult questions
    # Formula: correct / (correct + wrong + unattempted) * 100
    evaluated_count = correct + wrong + unattempted
    if evaluated_count == 0:
        # No valid questions were evaluated - this is a serious error
        raise HTTPException(
            status_code=500,
            detail="Unable to evaluate any questions. Please contact support."
        )
    
    # Option B: Unattempted questions count against the score
    score = int(round((correct / evaluated_count) * 100))

    new_submission = QuizSubmission(
        id=uuid4(),
        user_id=UUID(user_id),  # Convert string user_id to UUID
        quiz_id=submission.quiz_id,
        correct_count=correct,
        wrong_count=wrong,
        unattempted_count=unattempted,
        score=score,
        total_questions=evaluated_count,  # Store actual evaluated count
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

    # Invalidate submission caches after successful submission
    # This ensures /my-attempts and quiz history show the new submission immediately
    try:
        await invalidate_user_submissions_cache(user_id)
        await invalidate_quiz_submissions_cache(str(quiz_id), user_id)
        logger.debug(f"Invalidated submission caches for user {user_id} and quiz {quiz_id}")
    except Exception as e:
        # Don't fail the submission if cache invalidation fails
        logger.warning(f"Failed to invalidate submission caches: {e}")

    return {
        "id": new_submission.id,
        "total_questions": evaluated_count,  # Return actual evaluated count
        "correct_count": correct,
        "wrong_count": wrong,
        "unattempted_count": unattempted,
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
    Get all quiz submissions for the current user with Redis caching.
    Returns list of submissions with basic info (no detailed answers).
    """
    try:
        logger.info(f"User {user_id} fetching all their submissions (with caching)")
        
        # Use cached version with authenticated client (RLS enforcement)
        submissions = await get_user_submissions_cached(user_id, user_token)
        
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
    Get all submissions for a specific quiz by the current user with Redis caching.
    Useful for seeing attempt history on a particular quiz.
    """
    try:
        logger.info(f"User {user_id} fetching submissions for quiz {quiz_id} (with caching)")
        
        # Use cached version with authenticated client (RLS enforcement)
        submissions = await get_quiz_submissions_cached(str(quiz_id), user_id, user_token)
        
        logger.info(f"User {user_id} has {len(submissions)} submissions for quiz {quiz_id}")
        return {
            "quiz_id": str(quiz_id),
            "user_id": user_id,
            "total_attempts": len(submissions),
            "submissions": submissions
        }
    except Exception as e:
        logger.error(f"Error listing submissions for quiz {quiz_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve quiz submissions. Please try again.")


async def get_submission_review(
    submission_id: UUID,
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token)
):
    """
    Retrieve detailed review of a submission including all questions, answers, and explanations.
    This allows users to review what they got right/wrong and learn from their mistakes.
    """
    try:
        logger.info(f"User {user_id} requesting review for submission {submission_id}")
        
        # Use authenticated client (RLS enforcement)
        review = get_review_from_db(submission_id, user_token)
        
        # Authorization check: user can only access their own submissions
        if str(review["user_id"]) != str(user_id):
            logger.warning(f"User {user_id} attempted to access submission review {submission_id} owned by {review['user_id']}")
            raise HTTPException(status_code=403, detail="You are not authorized to access this submission")
        
        logger.info(f"User {user_id} successfully accessed review for submission {submission_id}")
        return review
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions (404, 403, etc.)
    except Exception as e:
        logger.error(f"Unexpected error retrieving submission review {submission_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve submission review. Please try again.")
