"""
Contact Routes - API endpoints for contact form.

Public endpoint for landing page contact form submission.
"""

from fastapi import APIRouter

from handlers.contact_handler import handle_contact_submission
from schemas.contact import ContactRequest, ContactResponse


router = APIRouter(prefix="/contact", tags=["Contact"])


@router.post(
    "",
    response_model=ContactResponse,
    summary="Submit Contact Form",
    description="Submit a message from the landing page contact form. No authentication required.",
    responses={
        200: {"description": "Message sent successfully"},
        422: {"description": "Validation error (invalid email, message too short, etc.)"},
        500: {"description": "Failed to send email"},
        503: {"description": "Email service not configured"}
    }
)
async def submit_contact_form(request: ContactRequest) -> ContactResponse:
    """
    Submit a contact form message.
    
    This endpoint is public (no authentication required) and is used by the
    landing page contact form. Messages are sent to admin@quizify.ca via Resend.
    """
    return await handle_contact_submission(request)
