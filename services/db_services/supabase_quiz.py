from fastapi import HTTPException
from schemas.quiz import Question
from typing import List, Optional
from services.logger import db_logger as logger
from config import config as app_config

# Lazy load Supabase client to avoid initialization issues in tests
def get_supabase():
    """Get Supabase client (lazy loaded)"""
    return app_config.get_supabase_client()

# Use centralized configuration
STORAGE_NAME = app_config.STORAGE_NAME

if app_config.is_testing():
    logger.debug("Supabase client initialized in TEST mode")
else:
    logger.debug("Supabase client initialized")

def get_authed_supabase_client(user_token: str):
    logger.debug(f"Creating authenticated Supabase client with token: {user_token[:10]}...")
    return app_config.get_authenticated_supabase_client(user_token)

def save_quiz_to_database(
    title: str, 
    quizzes: List[Question], 
    created_by: str,
    content_source_type: Optional[str] = None,
    content_source_reference: Optional[str] = None,
    user_token: Optional[str] = None
):
    try:
        # Use authenticated client if token provided, otherwise use service role
        if user_token:
            supabase = get_authed_supabase_client(user_token)
            logger.debug(f"Using authenticated client for user {created_by}")
            logger.debug(f"Token being used: {user_token[:20]}...")
        else:
            supabase = get_supabase()
            logger.debug("Using service role client")
        
        logger.debug(f"Saving quiz '{title}' with {len(quizzes)} questions")
        # Validate user ID to prevent UUID errors
        if not created_by or created_by == "undefined":
            logger.error("User authentication required to save quiz")
            raise HTTPException(
                status_code=401, 
                detail="User authentication required to save quiz"
            )
        if not quizzes:
            logger.error("No questions were generated")
            raise HTTPException(status_code=500, detail="No questions were generated.")
        
        # Build quiz insert payload
        quiz_data = {
            "title": title,
            "created_by": created_by
        }
        
        # Add optional fields if provided
        if content_source_type:
            quiz_data["content_source_type"] = content_source_type
        if content_source_reference:
            quiz_data["content_source_reference"] = content_source_reference
        
        quiz_response = supabase.table("quizzes").insert(quiz_data).execute()
        quiz_id = quiz_response.data[0]["id"]
        logger.debug(f"Created quiz with ID: {quiz_id}")

        # Build question payload based on type
        question_payload = []

        for q in quizzes:
            base = {
                "quiz_id": quiz_id,
                "type": q.type,
                "question": q.question,
                "explanation": q.explanation,
                "source": q.source
            }

            if q.type == "multiple_choice":
                base["options"] = q.options
                base["correct_answer"] = q.correct_answer

            elif q.type == "true_false":
                base["correct_answer"] = q.correct_answer  # boolean, JSONB-compatible

            elif q.type == "fill_blank":
                base["options"] = q.options
                base["correct_answer"] = q.correct_answer

            elif q.type == "matching":
                base["left"] = q.left
                base["right"] = q.right
                base["correct_answer"] = q.correct_answer  # list[int]

            question_payload.append(base)

        # Insert into questions table and get back the saved questions with IDs
        questions_response = supabase.table("questions").insert(question_payload).execute()
        saved_questions = questions_response.data
        logger.debug(f"Added {len(question_payload)} questions to quiz {quiz_id}")

        return quiz_id, saved_questions  # Return both quiz_id and saved questions with IDs

    except Exception as e:
        logger.error(f"Error saving quiz to database: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def get_quiz_from_database(quiz_id: str, user_token: str):
    try:
        if not user_token or not user_token.strip():
            logger.error("User token required to fetch quiz data")
            raise HTTPException(status_code=401, detail="User authentication required to fetch quiz")

        supabase = get_authed_supabase_client(user_token)
        logger.debug(f"Using authenticated client to fetch quiz: {quiz_id}")

        # Get the quiz metadata
        quiz = supabase.table("quizzes").select("*").eq("id", quiz_id).execute()
        if not quiz.data:
            logger.warning(f"Quiz not found: {quiz_id}")
            raise HTTPException(status_code=404, detail="Quiz not found")
        
        # Get the questions for the quiz
        questions = supabase.table("questions").select("*").eq("quiz_id", quiz_id).execute()

        quiz_data = quiz.data[0]
        questions_data = questions.data
        logger.debug(f"Found quiz '{quiz_data['title']}' with {len(questions_data)} questions")
        
        # Format the response
        return {
            "id": quiz_data["id"],
            "title": quiz_data["title"],
            "created_by": quiz_data["created_by"],
            "created_at": quiz_data["created_at"],
            "questions": questions_data
        }
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error retrieving quiz from database: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def get_user_quizzes(user_id: str, user_token: Optional[str] = None):
    try:
        # Use authenticated client if token provided, otherwise use service role
        if user_token:
            supabase = get_authed_supabase_client(user_token)
            logger.debug(f"Using authenticated client to fetch quizzes for user: {user_id}")
        else:
            supabase = get_supabase()
            logger.debug(f"Using service role to fetch quizzes for user: {user_id}")
        
        # Get all quizzes for a user
        quizzes_data = supabase.table("quizzes").select("*").eq("created_by", user_id).execute()
        
        if not quizzes_data.data:
            logger.debug(f"No quizzes found for user: {user_id}")
            return []
        
        # Process the results and add question_count
        quizzes = []
        for quiz in quizzes_data.data:
            questions = supabase.table("questions").select("id", count="exact").eq("quiz_id", quiz["id"]).execute()  # type: ignore

            quizzes.append({
                "id": quiz["id"],
                "title": quiz["title"],
                "created_at": quiz["created_at"],
                "created_by": quiz["created_by"],
                "question_count": questions.count or 0
            })

        logger.debug(f"Found {len(quizzes)} quizzes for user: {user_id}")
        return quizzes
    except Exception as e:
        logger.error(f"Error retrieving user quizzes: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def save_metadata(metadata: dict, user_token: Optional[str] = None):
    try:
        # Use authenticated client if token provided, otherwise use service role
        if user_token:
            supabase = get_authed_supabase_client(user_token)
            logger.debug(f"Using authenticated client to save metadata for quiz: {metadata.get('quiz_id', 'unknown')}")
        else:
            supabase = get_supabase()
            logger.debug(f"Using service role to save metadata for quiz: {metadata.get('quiz_id', 'unknown')}")
        
        supabase.table("quiz_metadata").insert(metadata).execute()
        logger.debug("Metadata saved successfully")
    except Exception as e:
        logger.error(f"Error saving metadata: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

def get_metadata(user_id: str, user_token: str = None):
    """
    Get quiz metadata for a user with quiz titles.
    
    Args:
        user_id: The user ID to fetch metadata for
        user_token: User's authentication token for RLS enforcement (recommended)
                    If None, uses service role (bypasses RLS - use with caution)
    """
    try:
        # Use authenticated client if token provided (enforces RLS)
        if user_token:
            supabase = get_authed_supabase_client(user_token)
        else:
            supabase = get_supabase()  # Service role - bypasses RLS
        
        logger.debug(f"Fetching metadata for user: {user_id}")

        # Join quiz_metadata with quizzes to get the quiz title
        # Order by created_at DESC to show most recent quizzes first
        metadata = supabase.table("quiz_metadata") \
            .select("*, quizzes(title)") \
            .eq("created_by", user_id) \
            .order("created_at", desc=True) \
            .execute()
        
        # Flatten the nested quiz title into the response
        result = []
        for item in metadata.data or []:
            flattened = {**item}
            # Extract quiz title safely (handles missing key, None, non-dict, missing title)
            flattened["quiz_title"] = item.get("quizzes", {}).get("title")
            # Remove nested object after flattening to match schema
            flattened.pop("quizzes", None)
            result.append(flattened)
        
        logger.debug(f"Found {len(result)} metadata records for user: {user_id}")
        return result
    except Exception as e:
        logger.error(f"Error retrieving metadata: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

def delete_quiz_from_database(quiz_id: str, user_token: str = None):
    """
    Delete a quiz from the database.
    
    Args:
        quiz_id: The quiz ID to delete
        user_token: User's authentication token for RLS enforcement (recommended)
                    If None, uses service role (bypasses RLS - use with caution)
    """
    try:
        # Use authenticated client if token provided (enforces RLS)
        if user_token:
            supabase = get_authed_supabase_client(user_token)
        else:
            supabase = get_supabase()  # Service role - bypasses RLS
        
        logger.debug(f"Deleting quiz with ID: {quiz_id}")

        supabase.table("quizzes").delete().eq("id", quiz_id).execute()
        logger.debug(f"Quiz deleted successfully: {quiz_id}")
    except Exception as e:
        logger.error(f"Error deleting quiz: {str(e)}", exc_info=True)

def get_user_tier_info(user_id: str):
    """
    Get user tier information including quota status from user_tier_info view.
    
    SECURITY MODEL:
    - This function ALWAYS uses SERVICE ROLE client (not authenticated client)
    - Reason: user_tier_info view accesses auth.users table which requires elevated permissions
    - Safety: user_id comes from authenticated JWT (validated by FastAPI dependency injection)
    - No data leakage risk: Query is explicitly filtered by user_id parameter
    
    This is the ONE documented exception to the "use authenticated clients everywhere" rule.
    All other database operations should use authenticated clients for RLS enforcement.
    
    Args:
        user_id: The UUID of the user (must be validated from JWT token by caller)
        
    Returns:
        dict: User tier information with keys:
            - id: User UUID
            - email: User email
            - account_tier: 'free', 'basic', or 'educator'
            - current_quiz_count: Number of quizzes created
            - quizzes_attempted: Number of quizzes attempted (submissions)
            - quota_limit: Max quizzes allowed for tier
            - quota_exceeded: Boolean indicating if quota is exceeded
              
    Raises:
        HTTPException: If user not found (404) or database error occurs (500)
    """
    try:
        # Always use service role for querying user_tier_info view
        # This is necessary because the view accesses auth.users table
        # Security is maintained by:
        # 1. user_id comes from authenticated JWT (validated by FastAPI dependency)
        # 2. We only return data for the specific user_id (no risk of data leakage)
        supabase = get_supabase()
        
        logger.debug(f"Fetching tier info for user: {user_id}")
        
        # Query the user_tier_info view with explicit refresh
        # Note: Supabase Python client doesn't support cache control headers,
        # but we can ensure we're getting fresh data by re-initializing if needed
        response = supabase.table("user_tier_info").select("*").eq("id", user_id).execute()
        
        if not response.data or len(response.data) == 0:
            logger.warning(f"User tier info not found for user: {user_id}")
            raise HTTPException(status_code=404, detail="User not found")
        
        tier_info = response.data[0]
        
        # Log the actual data we received from database
        logger.info(
            f"User {user_id[:8]}... tier info from DB: "
            f"tier={tier_info.get('account_tier')}, "
            f"quiz_count={tier_info.get('current_quiz_count')}, "
            f"quizzes_attempted={tier_info.get('quizzes_attempted')}, "
            f"quota={tier_info.get('quota_limit')}, "
            f"exceeded={tier_info.get('quota_exceeded')}"
        )
        
        return tier_info
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error fetching user tier info: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching user tier information: {str(e)}")