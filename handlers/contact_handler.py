"""
Contact Handler - Business logic for contact form submissions.

Sends contact form emails to admin using Resend API.
"""

import html
import resend
from fastapi import HTTPException

from config import Config
from schemas.contact import ContactRequest, ContactResponse
from services.logger import app_logger as logger


async def handle_contact_submission(request: ContactRequest) -> ContactResponse:
    """
    Handle contact form submission from landing page.
    
    Sends an email to admin@quizify.ca with the contact form details.
    
    Args:
        request: Contact form data (name, email, subject, message)
        
    Returns:
        ContactResponse indicating success/failure
        
    Raises:
        HTTPException: If email sending fails
    """
    # Check if Resend is configured
    if not Config.RESEND_API_KEY:
        logger.error("Contact form submission failed: RESEND_API_KEY not configured")
        raise HTTPException(
            status_code=503,
            detail="Contact form is temporarily unavailable. Please email us directly at admin@quizify.ca"
        )
    
    # Configure Resend
    resend.api_key = Config.RESEND_API_KEY
    
    # SECURITY: Escape user inputs to prevent HTML/XSS injection in emails
    safe_name = html.escape(request.name)
    safe_email = html.escape(request.email)
    safe_subject = html.escape(request.subject)
    safe_message = html.escape(request.message)
    
    # Build email content with escaped inputs
    html_content = f"""
    <h2>New Contact Form Submission</h2>
    <p><strong>From:</strong> {safe_name} ({safe_email})</p>
    <p><strong>Subject:</strong> {safe_subject}</p>
    <hr>
    <h3>Message:</h3>
    <p style="white-space: pre-wrap;">{safe_message}</p>
    <hr>
    <p style="color: #666; font-size: 12px;">
        This message was sent from the Quizify contact form.
        Reply directly to this email to respond to the sender.
    </p>
    """
    
    # Plain text doesn't need escaping (no HTML rendering)
    text_content = f"""
New Contact Form Submission

From: {request.name} ({request.email})
Subject: {request.subject}

Message:
{request.message}

---
This message was sent from the Quizify contact form.
Reply directly to this email to respond to the sender.
    """
    
    try:
        # Send email via Resend
        # Using reply_to so admin can reply directly to the sender
        params = {
            "from": "Quizify Contact <contact@quizify.ca>",
            "to": [Config.CONTACT_EMAIL],
            "reply_to": request.email,
            "subject": f"[Contact Form] {request.subject}",
            "html": html_content,
            "text": text_content,
        }
        
        email_response = resend.Emails.send(params)
        
        logger.info(
            f"Contact form email sent successfully: "
            f"from={request.email[:3]}***@***, "
            f"subject={request.subject[:20]}..., "
            f"resend_id={email_response.get('id', 'unknown')}"
        )
        
        return ContactResponse(
            success=True,
            message="Your message has been sent successfully. We'll get back to you soon!"
        )
        
    except resend.exceptions.ResendError as e:
        logger.error(f"Resend API error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to send message. Please try again later or email us directly at admin@quizify.ca"
        )
    except Exception as e:
        logger.error(f"Unexpected error sending contact email: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred. Please try again later."
        )
