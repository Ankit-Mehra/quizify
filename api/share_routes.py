"""
Share Routes - API endpoints for quiz sharing functionality.

These endpoints handle:
- Creating share links (making quiz public)
- Revoking share links (making quiz private)
- Getting share status
- Accessing public quizzes (anonymous access)
"""

from fastapi import APIRouter, HTTPException, Depends
from uuid import UUID

from schemas.share import (
    ShareLinkCreate,
    ShareLinkResponse,
    ShareLinkStatus,
    QuizPublicView,
)
from services.share_service import (
    create_share_link,
    revoke_share_link,
    get_share_status,
    get_public_quiz_by_slug,
)
from dependencies.auth_dependencies import get_current_user_id, get_current_user_token
from services.logger import app_logger as logger


router = APIRouter(prefix="/share", tags=["Share"])


# ============================================================================
# Authenticated Endpoints (Require Login)
# ============================================================================


@router.post("", response_model=ShareLinkResponse)
async def create_quiz_share_link(
    request: ShareLinkCreate,
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token),
):
    """
    Create a share link for a quiz.
    
    Makes the quiz public and generates a unique shareable URL.
    If the quiz is already public, returns the existing share link.
    
    Args:
        request: ShareLinkCreate with quiz_id
        user_id: Authenticated user ID from dependency
        user_token: Authenticated user token from dependency
        
    Returns:
        ShareLinkResponse with share URL and metadata
        
    Raises:
        401: Not authenticated
        403: User doesn't own the quiz
        404: Quiz not found
        500: Failed to create share link
    """
    logger.info(f"Creating share link: quiz={str(request.quiz_id)[:8]}..., user={user_id[:8]}...")
    
    try:
        result = await create_share_link(
            quiz_id=request.quiz_id,
            user_id=UUID(user_id),
            user_token=user_token,
        )
        
        return ShareLinkResponse(
            quiz_id=result["quiz_id"],
            public_slug=result["public_slug"],
            share_url=result["share_url"],
            is_public=result["is_public"],
            shared_at=result["shared_at"],
        )
        
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(status_code=404, detail=error_msg)
        elif "permission" in error_msg.lower():
            raise HTTPException(status_code=403, detail=error_msg)
        else:
            raise HTTPException(status_code=400, detail=error_msg)
    except RuntimeError as e:
        logger.error(f"Failed to create share link: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create share link")


@router.delete("/{quiz_id}")
async def revoke_quiz_share_link(
    quiz_id: str,
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token),
):
    """
    Revoke (unpublish) a quiz's share link.
    
    Makes the quiz private again. The slug is preserved so if you
    re-share the quiz later, it will have the same URL.
    
    Args:
        quiz_id: UUID of the quiz to unshare
        user_id: Authenticated user ID from dependency
        user_token: Authenticated user token from dependency
        
    Returns:
        Success message
        
    Raises:
        401: Not authenticated
        403: User doesn't own the quiz
        404: Quiz not found
    """
    logger.info(f"Revoking share link: quiz={quiz_id[:8]}..., user={user_id[:8]}...")
    
    try:
        result = await revoke_share_link(
            quiz_id=UUID(quiz_id),
            user_id=UUID(user_id),
            user_token=user_token,
        )
        
        return {"message": result["message"], "is_public": result["is_public"]}
        
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(status_code=404, detail=error_msg)
        elif "permission" in error_msg.lower():
            raise HTTPException(status_code=403, detail=error_msg)
        else:
            raise HTTPException(status_code=400, detail=error_msg)
    except RuntimeError as e:
        logger.error(f"Failed to revoke share link: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to revoke share link")


@router.get("/status/{quiz_id}", response_model=ShareLinkStatus)
async def get_quiz_share_status(
    quiz_id: str,
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token),
):
    """
    Get the current share status of a quiz.
    
    Returns whether the quiz is public and its share URL if applicable.
    
    Args:
        quiz_id: UUID of the quiz to check
        user_id: Authenticated user ID from dependency
        user_token: Authenticated user token from dependency
        
    Returns:
        ShareLinkStatus with current state
        
    Raises:
        401: Not authenticated
        403: User doesn't own the quiz
        404: Quiz not found
    """
    try:
        result = await get_share_status(
            quiz_id=UUID(quiz_id),
            user_id=UUID(user_id),
            user_token=user_token,
        )
        
        return ShareLinkStatus(
            quiz_id=result["quiz_id"],
            is_public=result["is_public"],
            public_slug=result["public_slug"],
            share_url=result["share_url"],
            shared_at=result["shared_at"],
        )
        
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(status_code=404, detail=error_msg)
        elif "permission" in error_msg.lower():
            raise HTTPException(status_code=403, detail=error_msg)
        else:
            raise HTTPException(status_code=400, detail=error_msg)


# ============================================================================
# Public Endpoints (No Authentication Required)
# ============================================================================


@router.get("/public/{slug}", response_model=QuizPublicView)
async def get_public_quiz(slug: str):
    """
    Get a public quiz by its share slug.
    
    This endpoint is accessible without authentication.
    Returns quiz with questions but WITHOUT correct answers to prevent cheating.
    
    Args:
        slug: The quiz's public slug (e.g., 'abc12xyz')
        
    Returns:
        QuizPublicView with quiz and questions (no answers)
        
    Raises:
        404: Quiz not found or not public
    """
    logger.info(f"Fetching public quiz: slug={slug}")
    
    try:
        quiz_data = await get_public_quiz_by_slug(slug)
        
        return QuizPublicView(
            id=quiz_data["id"],
            title=quiz_data["title"],
            description=quiz_data.get("description"),
            topic=quiz_data.get("topic"),
            total_questions=quiz_data["total_questions"],
            questions=quiz_data["questions"],
            shared_at=quiz_data["shared_at"],
        )
        
    except ValueError:
        raise HTTPException(status_code=404, detail="Quiz not found or not public")
