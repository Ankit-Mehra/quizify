"""
Contact Form Schemas

Pydantic models for contact form submission from landing page.
"""

from pydantic import BaseModel, EmailStr, Field


class ContactRequest(BaseModel):
    """Request model for contact form submission."""
    
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Sender's name"
    )
    email: EmailStr = Field(
        ...,
        description="Sender's email address"
    )
    subject: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Message subject"
    )
    message: str = Field(
        ...,
        min_length=10,
        max_length=5000,
        description="Message content"
    )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "John Doe",
                "email": "john@example.com",
                "subject": "Question about Quizify",
                "message": "I'd like to learn more about your Pro tier features."
            }
        }
    }


class ContactResponse(BaseModel):
    """Response model for contact form submission."""
    
    success: bool = Field(..., description="Whether the message was sent successfully")
    message: str = Field(..., description="Response message")
