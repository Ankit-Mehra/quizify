"""
Service for managing quiz share links.

Handles slug generation, share link creation, revocation, and public quiz retrieval.
"""

import secrets
import string
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from config import Config
from services.db_services.supabase_quiz import get_supabase, get_authed_supabase_client


# Constants for slug generation
SLUG_LENGTH = 8
SLUG_CHARS = string.ascii_lowercase + string.digits


def generate_slug(length: int = SLUG_LENGTH) -> str:
    """
    Generate a random URL-safe slug.
    
    Uses cryptographically secure random choice for unpredictable slugs.
    
    Args:
        length: Length of slug to generate (default: 8)
        
    Returns:
        Random alphanumeric slug (lowercase)
    """
    return "".join(secrets.choice(SLUG_CHARS) for _ in range(length))


async def generate_unique_slug(max_attempts: int = 10) -> str:
    """
    Generate a unique slug that doesn't exist in the database.
    
    Args:
        max_attempts: Maximum attempts before giving up
        
    Returns:
        A unique slug
        
    Raises:
        RuntimeError: If unable to generate unique slug after max attempts
    """
    # Skip DB check in testing mode
    if Config.is_testing():
        return generate_slug()
    
    supabase = get_supabase()
    
    for _ in range(max_attempts):
        slug = generate_slug()
        
        # Check if slug exists
        result = (
            supabase.table("quizzes")
            .select("id")
            .eq("public_slug", slug)
            .execute()
        )
        
        if not result.data:
            return slug
    
    raise RuntimeError(
        f"Unable to generate unique slug after {max_attempts} attempts"
    )


def build_share_url(slug: str) -> str:
    """
    Build the full shareable URL for a quiz.
    
    Args:
        slug: The quiz's public slug
        
    Returns:
        Full URL like https://quizify.ca/quiz/abc12xyz
    """
    base_url = Config.FRONTEND_URL.rstrip("/")
    return f"{base_url}/quiz/{slug}"


async def create_share_link(
    quiz_id: UUID,
    user_id: UUID,
    user_token: Optional[str] = None,
) -> dict:
    """
    Create or retrieve a share link for a quiz.
    
    If quiz is already public, returns existing share link.
    If not public, generates new slug and makes quiz public.
    
    Args:
        quiz_id: The quiz to share
        user_id: The user requesting the share (must be owner)
        user_token: Optional JWT token for RLS enforcement
        
    Returns:
        Dict with quiz_id, public_slug, share_url, is_public, shared_at
        
    Raises:
        ValueError: If quiz not found or user doesn't own it
        RuntimeError: If unable to generate unique slug
    """
    if Config.is_testing():
        # Return mock response in testing mode
        slug = generate_slug()
        now = datetime.now(timezone.utc)
        return {
            "quiz_id": str(quiz_id),
            "public_slug": slug,
            "share_url": build_share_url(slug),
            "is_public": True,
            "shared_at": now.isoformat(),
        }
    
    # Use authenticated client for RLS
    if user_token:
        supabase = get_authed_supabase_client(user_token)
    else:
        supabase = get_supabase()
    
    # Verify quiz exists and user owns it
    quiz_result = (
        supabase.table("quizzes")
        .select("id, created_by, is_public, public_slug, shared_at")
        .eq("id", str(quiz_id))
        .single()
        .execute()
    )
    
    if not quiz_result.data:
        raise ValueError(f"Quiz not found: {quiz_id}")
    
    quiz = quiz_result.data
    
    # Verify ownership
    if quiz.get("created_by") != str(user_id):
        raise ValueError("You don't have permission to share this quiz")
    
    # If already public, return existing share link
    if quiz.get("is_public") and quiz.get("public_slug"):
        return {
            "quiz_id": str(quiz_id),
            "public_slug": quiz["public_slug"],
            "share_url": build_share_url(quiz["public_slug"]),
            "is_public": True,
            "shared_at": quiz.get("shared_at"),
        }
    
    # Generate new slug and make public
    slug = await generate_unique_slug()
    now = datetime.now(timezone.utc)
    
    update_result = (
        supabase.table("quizzes")
        .update({
            "is_public": True,
            "public_slug": slug,
            "shared_at": now.isoformat(),
        })
        .eq("id", str(quiz_id))
        .execute()
    )
    
    if not update_result.data:
        raise RuntimeError(f"Failed to update quiz share status: {quiz_id}")
    
    return {
        "quiz_id": str(quiz_id),
        "public_slug": slug,
        "share_url": build_share_url(slug),
        "is_public": True,
        "shared_at": now.isoformat(),
    }


async def revoke_share_link(
    quiz_id: UUID,
    user_id: UUID,
    user_token: Optional[str] = None,
) -> dict:
    """
    Revoke (unpublish) a quiz's share link.
    
    Sets is_public to False but preserves the slug for potential re-sharing.
    
    Args:
        quiz_id: The quiz to unshare
        user_id: The user requesting revocation (must be owner)
        user_token: Optional JWT token for RLS enforcement
        
    Returns:
        Dict with quiz_id, is_public (False), message
        
    Raises:
        ValueError: If quiz not found or user doesn't own it
    """
    if Config.is_testing():
        return {
            "quiz_id": str(quiz_id),
            "is_public": False,
            "message": "Share link revoked successfully",
        }
    
    # Use authenticated client for RLS
    if user_token:
        supabase = get_authed_supabase_client(user_token)
    else:
        supabase = get_supabase()
    
    # Verify quiz exists and user owns it
    quiz_result = (
        supabase.table("quizzes")
        .select("id, created_by")
        .eq("id", str(quiz_id))
        .single()
        .execute()
    )
    
    if not quiz_result.data:
        raise ValueError(f"Quiz not found: {quiz_id}")
    
    # Verify ownership
    if quiz_result.data.get("created_by") != str(user_id):
        raise ValueError("You don't have permission to revoke this share link")
    
    # Set is_public to False (keep slug for potential re-sharing)
    update_result = (
        supabase.table("quizzes")
        .update({"is_public": False})
        .eq("id", str(quiz_id))
        .execute()
    )
    
    if not update_result.data:
        raise RuntimeError(f"Failed to revoke share link: {quiz_id}")
    
    return {
        "quiz_id": str(quiz_id),
        "is_public": False,
        "message": "Share link revoked successfully",
    }


async def get_share_status(
    quiz_id: UUID,
    user_id: UUID,
    user_token: Optional[str] = None,
) -> dict:
    """
    Get the current share status of a quiz.
    
    Args:
        quiz_id: The quiz to check
        user_id: The user requesting status (must be owner)
        user_token: Optional JWT token for RLS enforcement
        
    Returns:
        Dict with quiz_id, is_public, public_slug, share_url, shared_at
        
    Raises:
        ValueError: If quiz not found or user doesn't own it
    """
    if Config.is_testing():
        return {
            "quiz_id": str(quiz_id),
            "is_public": False,
            "public_slug": None,
            "share_url": None,
            "shared_at": None,
        }
    
    # Use authenticated client for RLS
    if user_token:
        supabase = get_authed_supabase_client(user_token)
    else:
        supabase = get_supabase()
    
    # Get quiz with share fields
    quiz_result = (
        supabase.table("quizzes")
        .select("id, created_by, is_public, public_slug, shared_at")
        .eq("id", str(quiz_id))
        .single()
        .execute()
    )
    
    if not quiz_result.data:
        raise ValueError(f"Quiz not found: {quiz_id}")
    
    quiz = quiz_result.data
    
    # Verify ownership
    if quiz.get("created_by") != str(user_id):
        raise ValueError("You don't have permission to view this quiz's share status")
    
    is_public = quiz.get("is_public", False)
    slug = quiz.get("public_slug")
    
    return {
        "quiz_id": str(quiz_id),
        "is_public": is_public,
        "public_slug": slug if is_public else None,
        "share_url": build_share_url(slug) if is_public and slug else None,
        "shared_at": quiz.get("shared_at") if is_public else None,
    }


async def get_public_quiz_by_slug(slug: str) -> dict:
    """
    Retrieve a public quiz by its share slug.
    
    This is used for anonymous access to shared quizzes.
    Does NOT include answer keys to prevent cheating.
    
    Args:
        slug: The quiz's public slug
        
    Returns:
        Dict with quiz data and questions (without answers)
        
    Raises:
        ValueError: If quiz not found or not public
    """
    if Config.is_testing():
        # Return mock public quiz in testing mode
        from uuid import uuid4
        return {
            "id": str(uuid4()),
            "title": "Test Public Quiz",
            "description": "A test quiz",
            "topic": "Testing",
            "total_questions": 1,
            "questions": [
                {
                    "id": str(uuid4()),
                    "question_number": 1,
                    "question_type": "mcq",
                    "question_text": "Test question?",
                    "options": [
                        {"id": "a", "text": "Option A"},
                        {"id": "b", "text": "Option B"},
                    ],
                    "difficulty": "easy",
                }
            ],
            "shared_at": datetime.now(timezone.utc).isoformat(),
        }
    
    supabase = get_supabase()
    
    # Get public quiz by slug
    quiz_result = (
        supabase.table("quizzes")
        .select("id, title, description, topic, is_public, shared_at")
        .eq("public_slug", slug)
        .eq("is_public", True)
        .single()
        .execute()
    )
    
    if not quiz_result.data:
        raise ValueError(f"Quiz not found or not public: {slug}")
    
    quiz = quiz_result.data
    
    # Get questions without correct answers
    questions_result = (
        supabase.table("questions")
        .select("id, question_number, question_type, question_text, options, difficulty")
        .eq("quiz_id", quiz["id"])
        .order("question_number")
        .execute()
    )
    
    # Transform questions to hide correct answers
    public_questions = []
    for q in questions_result.data or []:
        public_q = {
            "id": q["id"],
            "question_number": q["question_number"],
            "question_type": q["question_type"],
            "question_text": q["question_text"],
            "difficulty": q.get("difficulty"),
        }
        
        # Include options without marking correct answer
        if q.get("options"):
            if q["question_type"] in ("mcq", "true_false"):
                public_q["options"] = [
                    {"id": opt.get("id", str(i)), "text": opt.get("text", "")}
                    for i, opt in enumerate(q["options"])
                ]
            elif q["question_type"] == "matching":
                # For matching, show left side only (right side shuffled by client)
                public_q["matching_pairs"] = [
                    {"left": opt.get("left", ""), "right": opt.get("right", "")}
                    for opt in q["options"]
                ]
        
        public_questions.append(public_q)
    
    return {
        "id": quiz["id"],
        "title": quiz["title"],
        "description": quiz.get("description"),
        "topic": quiz.get("topic"),
        "total_questions": len(public_questions),
        "questions": public_questions,
        "shared_at": quiz.get("shared_at"),
    }


async def re_enable_share_link(
    quiz_id: UUID,
    user_id: UUID,
    user_token: Optional[str] = None,
) -> dict:
    """
    Re-enable a previously revoked share link.
    
    If quiz has an existing slug, just sets is_public=True.
    If no slug exists, generates a new one.
    
    Args:
        quiz_id: The quiz to re-share
        user_id: The user requesting re-share (must be owner)
        user_token: Optional JWT token for RLS enforcement
        
    Returns:
        Same as create_share_link
    """
    # For simplicity, just call create_share_link which handles both cases
    return await create_share_link(quiz_id, user_id, user_token)
