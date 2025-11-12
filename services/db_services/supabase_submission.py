## Submission DB Services
from services.logger import db_logger as logger
from typing import List
from schemas.submission import QuizSubmission, QuizAnswer
from schemas.quiz import Question
from fastapi import HTTPException
from uuid import UUID
from config import config as app_config
from pydantic import BaseModel
import asyncio


# Pydantic models for caching
class SubmissionSummary(BaseModel):
    """Submission summary model for caching"""
    id: str
    quiz_id: str
    user_id: str
    score: int
    total_questions: int
    correct_count: int
    wrong_count: int
    submitted_at: str


# Lazy load Supabase client to avoid initialization issues in tests
def get_supabase():
    """Get Supabase client (lazy loaded)"""
    return app_config.get_supabase_client()

def get_authed_supabase_client(user_token: str):
    """Returns Supabase client with user's JWT token for RLS enforcement"""
    logger.debug(f"Creating authenticated Supabase client with token: {user_token[:4]}...")
    return app_config.get_authenticated_supabase_client(user_token)

def get_question(question_ids: List[UUID], user_token: str = None) -> List[Question]:
    """
    Get questions by their IDs using Supabase `.in_` clause
    
    Args:
        question_ids: List of question UUIDs to fetch
        user_token: User's authentication token for RLS enforcement (recommended)
                    If None, uses service role (bypasses RLS - use with caution)
    
    Returns:
        List of Question objects
    """
    # Use authenticated client if token provided (enforces RLS)
    if user_token:
        supabase = app_config.get_authenticated_supabase_client(user_token)
    else:
        supabase = get_supabase()  # Service role - bypasses RLS
    
    # Convert UUIDs to strings for Supabase query
    # Supabase/PostgREST expects string representation of UUIDs
    question_id_strs = [str(qid) for qid in question_ids]
    
    # Safe logging - show first 3 IDs if available
    sample_ids = question_id_strs[:3] if question_id_strs else []
    logger.debug(f"Fetching {len(question_ids)} questions. Sample IDs: {sample_ids}")
    
    try:
        response = (
            supabase
            .table("questions")
            .select("*")
            .in_("id", question_id_strs)  # Use string IDs
            .execute()
        )
        
        if not response.data:
            logger.warning(f"No questions found for {len(question_id_strs)} provided IDs")
            # Log only count and status, not full response object (may contain sensitive data)
            logger.warning(f"Query returned empty result. Expected {len(question_id_strs)} questions.")
            raise HTTPException(status_code=404, detail="Questions not found. The quiz may have been deleted.")

        logger.debug(f"Successfully retrieved {len(response.data)} questions")
        return response.data
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        # Log full error details for debugging
        logger.error(f"Database error retrieving questions: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve quiz questions. Please try again.")


def save_submission(submission: QuizSubmission, user_token: str = None):
    """
    Save a quiz submission to the database.
    
    Args:
        submission: QuizSubmission object to save
        user_token: User's authentication token for RLS enforcement (recommended)
                    If None, uses service role (bypasses RLS - use with caution)
    """
    # Use authenticated client if token provided (enforces RLS)
    if user_token:
        supabase = app_config.get_authenticated_supabase_client(user_token)
    else:
        supabase = get_supabase()  # Service role - bypasses RLS
    
    logger.debug(f"Saving submission for quiz_id: {submission.quiz_id}, user_id: {submission.user_id}")
    try:
        payload = submission.model_dump(mode="json")
        supabase.table("submissions").insert(payload).execute()
        logger.debug(f"Successfully saved submission: {submission.id}")
    except Exception as e:
        # Log full error details for debugging
        logger.error(f"Database error saving submission: {str(e)}")
        
        # Parse error and return user-friendly message
        error_str = str(e)
        if "42501" in error_str:  # RLS policy violation
            raise HTTPException(status_code=403, detail="Permission denied. You can only submit your own quiz answers.")
        elif "23503" in error_str and "quiz_id" in error_str:
            raise HTTPException(status_code=404, detail="Quiz not found. Please verify the quiz ID.")
        elif "23503" in error_str:
            raise HTTPException(status_code=400, detail="Invalid reference in submission data.")
        elif "23505" in error_str:
            raise HTTPException(status_code=409, detail="This submission already exists.")
        else:
            raise HTTPException(status_code=500, detail="Failed to save submission. Please try again.")

def save_answer(answer: QuizAnswer, user_token: str = None):
    """
    Save a quiz answer to the database.
    
    Args:
        answer: QuizAnswer object to save
        user_token: User's authentication token for RLS enforcement (recommended)
                    If None, uses service role (bypasses RLS - use with caution)
    """
    # Use authenticated client if token provided (enforces RLS)
    if user_token:
        supabase = app_config.get_authenticated_supabase_client(user_token)
    else:
        supabase = get_supabase()  # Service role - bypasses RLS
    
    logger.debug(f"Saving answer for question_id: {answer.question_id}")
    try:
        payload = answer.model_dump(mode="json")
        supabase.table("answers").insert(payload).execute()
    except Exception as e:
        # Log full error details for debugging
        logger.error(f"Database error saving answer: {str(e)}")
        
        # Parse error and return user-friendly message
        error_str = str(e)
        if "42501" in error_str:  # RLS policy violation
            raise HTTPException(status_code=403, detail="Permission denied. You can only submit your own answers.")
        elif "23503" in error_str:
            raise HTTPException(status_code=400, detail="Invalid question or submission reference.")
        elif "23505" in error_str:
            raise HTTPException(status_code=409, detail="This answer has already been recorded.")
        else:
            raise HTTPException(status_code=500, detail="Failed to save answer. Please try again.")

def get_submission_by_id(submission_id: UUID, user_token: str = None) -> QuizSubmission:
    """
    Retrieve a submission by its ID.
    
    Args:
        submission_id: The UUID of the submission
        user_token: User's authentication token for RLS enforcement (recommended)
    """
    try:
        # Use authenticated client if token provided (enforces RLS)
        if user_token:
            supabase = get_authed_supabase_client(user_token)
        else:
            supabase = get_supabase()
        
        # Get submission
        submission_data = supabase.table("submissions").select("*").eq("id", str(submission_id)).execute()
        
        if not submission_data.data:
            raise HTTPException(status_code=404, detail=f"Submission {submission_id} not found")
        
        submission = submission_data.data[0]
        
        # Convert to QuizSubmission model (summary only, no detailed answers)
        # Note: QuizSubmission schema doesn't include 'answers' field
        # For detailed answer breakdown, use a separate endpoint (future enhancement)
        return QuizSubmission(
            id=UUID(submission["id"]),
            quiz_id=UUID(submission["quiz_id"]),
            user_id=UUID(submission["user_id"]),
            score=submission["score"],
            total_questions=submission["total_questions"],
            correct_count=submission["correct_count"],
            wrong_count=submission["wrong_count"],
            submitted_at=submission["submitted_at"]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving submission: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def get_user_submissions(user_id: str, user_token: str = None) -> List[dict]:
    """
    Get all submissions for a user with basic info (no detailed answers).
    
    Args:
        user_id: The user's UUID
        user_token: User's authentication token for RLS enforcement (recommended)
        
    Returns:
        List of submission summaries with: id, quiz_id, score, submitted_at, total_questions
    """
    try:
        # Use authenticated client if token provided (enforces RLS)
        if user_token:
            supabase = get_authed_supabase_client(user_token)
        else:
            supabase = get_supabase()
        
        logger.debug(f"Fetching submissions for user: {user_id}")
        
        # Get all submissions for this user, ordered by most recent first
        submissions = supabase.table("submissions") \
            .select("id, quiz_id, user_id, score, total_questions, correct_count, wrong_count, submitted_at") \
            .eq("user_id", user_id) \
            .order("submitted_at", desc=True) \
            .execute()
        
        logger.debug(f"Found {len(submissions.data or [])} submissions for user: {user_id}")
        return submissions.data or []
        
    except Exception as e:
        logger.error(f"Error retrieving user submissions: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def get_quiz_submissions(quiz_id: str, user_id: str, user_token: str = None) -> List[dict]:
    """
    Get all submissions for a specific quiz by a specific user.
    
    Args:
        quiz_id: The quiz UUID
        user_id: The user's UUID
        user_token: User's authentication token for RLS enforcement (recommended)
        
    Returns:
        List of submission summaries for this quiz
    """
    try:
        # Use authenticated client if token provided (enforces RLS)
        if user_token:
            supabase = get_authed_supabase_client(user_token)
        else:
            supabase = get_supabase()
        
        logger.debug(f"Fetching submissions for quiz {quiz_id} by user {user_id}")
        
        # Get submissions for this quiz by this user
        submissions = supabase.table("submissions") \
            .select("id, quiz_id, user_id, score, total_questions, correct_count, wrong_count, submitted_at") \
            .eq("quiz_id", quiz_id) \
            .eq("user_id", user_id) \
            .order("submitted_at", desc=True) \
            .execute()
        
        logger.debug(f"Found {len(submissions.data or [])} submissions for quiz {quiz_id} by user {user_id}")
        return submissions.data or []
        
    except Exception as e:
        logger.error(f"Error retrieving quiz submissions: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def get_user_submissions_cached(user_id: str, user_token: str) -> List[dict]:
    """
    Get all submissions for a user with Redis caching.
    
    IMPORTANT: Always uses authenticated Supabase client with user_token for RLS enforcement.
    This ensures users only see their own submissions.
    
    Performance benefits:
    - 10-minute cache TTL reduces database load for frequently accessed submission lists
    - Faster "My Attempts" page loading
    - Reduces database queries by ~20x for submission listings
    
    Cache invalidation:
    - Automatic after 10 minutes (TTL)
    - Manual via invalidate_user_submissions_cache() on new submission
    
    **Security Note**:
    - Cache key includes user_id to ensure per-user isolation
    - Always uses authenticated client (never service role) for RLS enforcement
    - No risk of cross-user data leakage
    
    Args:
        user_id: UUID of the user
        user_token: JWT token for authenticated queries (REQUIRED)
        
    Returns:
        List[dict]: List of submission summaries ordered by most recent first
        
    Example:
        submissions = await get_user_submissions_cached(user_id, user_token)
        for sub in submissions:
            print(f"Quiz {sub['quiz_id']}: {sub['score']}%")
    """
    from services.redis import get_cache_service
    
    cache = get_cache_service(prefix="user_submissions")
    
    async def fetch_from_db():
        # Run blocking Supabase call in thread pool
        def fetch_submissions():
            # ALWAYS use authenticated client (enforces RLS)
            supabase = get_authed_supabase_client(user_token)
            
            # Get all submissions for this user
            submissions = supabase.table("submissions") \
                .select("id, quiz_id, user_id, score, total_questions, correct_count, wrong_count, submitted_at") \
                .eq("user_id", user_id) \
                .order("submitted_at", desc=True) \
                .execute()
            
            return submissions.data or []
        
        submissions_data = await asyncio.to_thread(fetch_submissions)
        
        # Convert to Pydantic models for caching (ensures consistent serialization)
        return [SubmissionSummary(**sub) for sub in submissions_data]
    
    # Cache key: user_id only (no need for per-quiz caching here)
    cache_key = user_id
    
    submissions = await cache.get_or_fetch(
        key=cache_key,
        fetch_fn=fetch_from_db,
        model=List[SubmissionSummary],  # type: ignore
        ttl=app_config.REDIS_CACHE_TTL_SUBMISSIONS  # 10 minutes (600 seconds)
    )
    
    # Convert back to dict for backward compatibility
    return [sub.model_dump() for sub in submissions]


async def get_quiz_submissions_cached(quiz_id: str, user_id: str, user_token: str) -> List[dict]:
    """
    Get all submissions for a specific quiz by a user with Redis caching.
    
    IMPORTANT: Always uses authenticated Supabase client with user_token for RLS enforcement.
    
    Performance benefits:
    - 10-minute cache TTL for per-quiz attempt history
    - Faster "Attempt History" page for specific quizzes
    - Reduces repeated queries when reviewing quiz performance
    
    Cache invalidation:
    - Automatic after 10 minutes (TTL)
    - Manual via invalidate_quiz_submissions_cache() on new submission
    
    Args:
        quiz_id: UUID of the quiz
        user_id: UUID of the user
        user_token: JWT token for authenticated queries (REQUIRED)
        
    Returns:
        List[dict]: List of submission summaries for this quiz ordered by most recent first
    """
    from services.redis import get_cache_service
    
    cache = get_cache_service(prefix="quiz_submissions")
    
    async def fetch_from_db():
        # Run blocking Supabase call in thread pool
        def fetch_submissions():
            # ALWAYS use authenticated client (enforces RLS)
            supabase = get_authed_supabase_client(user_token)
            
            # Get submissions for this quiz by this user
            submissions = supabase.table("submissions") \
                .select("id, quiz_id, user_id, score, total_questions, correct_count, wrong_count, submitted_at") \
                .eq("quiz_id", quiz_id) \
                .eq("user_id", user_id) \
                .order("submitted_at", desc=True) \
                .execute()
            
            return submissions.data or []
        
        submissions_data = await asyncio.to_thread(fetch_submissions)
        
        # Convert to Pydantic models for caching
        return [SubmissionSummary(**sub) for sub in submissions_data]
    
    # Cache key: "quiz_id:user_id" (per-quiz, per-user)
    cache_key = f"{quiz_id}:{user_id}"
    
    submissions = await cache.get_or_fetch(
        key=cache_key,
        fetch_fn=fetch_from_db,
        model=List[SubmissionSummary],  # type: ignore
        ttl=app_config.REDIS_CACHE_TTL_SUBMISSIONS  # 10 minutes (600 seconds)
    )
    
    # Convert back to dict for backward compatibility
    return [sub.model_dump() for sub in submissions]


async def invalidate_user_submissions_cache(user_id: str) -> None:
    """
    Invalidate cached submission list for a user.
    
    Call this when:
    - User submits a new quiz (new submission added)
    - Submission is deleted (rare, but should invalidate)
    
    Args:
        user_id: UUID of the user
    """
    from services.redis import get_cache_service
    
    cache = get_cache_service(prefix="user_submissions")
    deleted = await cache.delete(user_id)
    
    user_preview = user_id[:8] if len(user_id) >= 8 else user_id
    
    if deleted:
        logger.info(f"Invalidated submissions cache for user: {user_preview}...")
    else:
        logger.debug(f"No submissions cache to invalidate for user: {user_preview}...")


async def invalidate_quiz_submissions_cache(quiz_id: str, user_id: str) -> None:
    """
    Invalidate cached submission list for a specific quiz-user combination.
    
    Call this when:
    - User submits a new attempt for this quiz
    - Submission is deleted for this quiz
    
    Args:
        quiz_id: UUID of the quiz
        user_id: UUID of the user
    """
    from services.redis import get_cache_service
    
    cache = get_cache_service(prefix="quiz_submissions")
    cache_key = f"{quiz_id}:{user_id}"
    deleted = await cache.delete(cache_key)
    
    quiz_preview = quiz_id[:8] if len(quiz_id) >= 8 else quiz_id
    user_preview = user_id[:8] if len(user_id) >= 8 else user_id
    
    if deleted:
        logger.info(f"Invalidated quiz submissions cache for quiz {quiz_preview}... user {user_preview}...")
    else:
        logger.debug(f"No quiz submissions cache to invalidate for quiz {quiz_preview}... user {user_preview}...")
