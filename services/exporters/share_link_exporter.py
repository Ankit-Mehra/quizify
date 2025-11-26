"""
Share Link Exporter - Creates shareable links for quizzes.

This exporter doesn't generate a file but rather creates/retrieves
a share link for the quiz and returns the URL.
"""

from typing import TYPE_CHECKING
from uuid import UUID

from services.exporters.base import BaseExporter, ExportError
from services.share_service import create_share_link
from schemas.export import ExportResult

if TYPE_CHECKING:
    from schemas.export import QuizExportData, ExportOptions


class ShareLinkExporter(BaseExporter):
    """
    Exporter that creates a shareable link for a quiz.
    
    Unlike file-based exporters, this:
    1. Sets quiz.is_public = True in database
    2. Generates a unique public_slug
    3. Returns the share URL as content (not file bytes)
    
    The returned ExportResult:
    - content: The share URL as bytes (UTF-8 encoded)
    - content_type: "text/plain"
    - filename: None (not a downloadable file)
    - share_url: The full shareable URL
    """
    
    FORMAT_NAME = "share_link"
    CONTENT_TYPE = "text/plain"
    FILE_EXTENSION = ""  # Not a file-based export
    
    def __init__(self, user_id: UUID = None, user_token: str = None):
        """
        Initialize ShareLinkExporter.
        
        Args:
            user_id: The ID of the user creating the share link
            user_token: JWT token for authenticated database operations
        """
        self.user_id = user_id
        self.user_token = user_token
    
    async def export(
        self, 
        quiz_data: "QuizExportData", 
        options: "ExportOptions"
    ) -> ExportResult:
        """
        Create or retrieve a share link for the quiz.
        
        Args:
            quiz_data: Quiz data (quiz_id is required)
            options: Export options (mostly ignored for share links)
            
        Returns:
            ExportResult with share URL as content
            
        Raises:
            ExportError: If share link creation fails
        """
        if not self.user_id:
            raise ExportError(
                "User ID is required for share link creation",
                self.FORMAT_NAME
            )
        
        try:
            # Create/retrieve share link
            share_result = await create_share_link(
                quiz_id=quiz_data.quiz_id,
                user_id=self.user_id,
                user_token=self.user_token,
            )
            
            share_url = share_result["share_url"]
            
            return ExportResult(
                content=share_url.encode("utf-8"),
                content_type=self.CONTENT_TYPE,
                filename=None,  # Not a file download
                share_url=share_url,
            )
            
        except ValueError as e:
            raise ExportError(str(e), self.FORMAT_NAME)
        except RuntimeError as e:
            raise ExportError(str(e), self.FORMAT_NAME)
        except Exception as e:
            raise ExportError(
                f"Failed to create share link: {str(e)}",
                self.FORMAT_NAME
            )
    
    def generate_filename(self, quiz_title: str) -> str:
        """Share links don't have filenames."""
        return None
