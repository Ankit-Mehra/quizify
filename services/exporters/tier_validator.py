"""
Tier Validator - Export format access control based on user subscription tier.

This module enforces tier-based access to export formats:
- Free tier: No export access
- Basic tier: PDF, DOCX, CSV (Quizify), CSV (Anki), Share Link
- Pro tier: All formats including QTI 2.1, Moodle XML

Access is validated at the API layer before any export processing begins.
"""

from typing import Set
from fastapi import HTTPException

from schemas.export import ExportFormat


# Export formats restricted to Pro tier only
PRO_ONLY_FORMATS: Set[ExportFormat] = {
    ExportFormat.QTI,
    ExportFormat.MOODLE_XML
}

# Tiers that have export access (free tier excluded)
EXPORT_ALLOWED_TIERS = {"basic", "pro"}

# Valid tier values
VALID_TIERS = {"free", "basic", "pro"}


class TierInsufficientError(HTTPException):
    """
    Exception raised when user's tier doesn't allow the requested export format.
    
    This is an HTTPException subclass for easy integration with FastAPI.
    """
    
    def __init__(self, current_tier: str, requested_format: ExportFormat, reason: str = "pro_required"):
        if reason == "free_tier":
            detail = {
                "error": "tier_insufficient",
                "message": "Export features require a Basic or Pro subscription",
                "required_tier": "basic",
                "current_tier": current_tier,
                "requested_format": requested_format.value,
                "upgrade_url": "/billing/upgrade"
            }
        else:  # pro_required
            detail = {
                "error": "tier_insufficient",
                "message": "LMS export formats (QTI, Moodle XML) require a Pro subscription",
                "required_tier": "pro",
                "current_tier": current_tier,
                "requested_format": requested_format.value,
                "upgrade_url": "/billing/upgrade"
            }
        super().__init__(status_code=403, detail=detail)


def validate_export_tier_access(
    user_tier: str, 
    export_format: ExportFormat
) -> None:
    """
    Validate that user's subscription tier allows the requested export format.
    
    Args:
        user_tier: User's current subscription tier ('free', 'basic', 'pro')
        export_format: The export format being requested
        
    Raises:
        TierInsufficientError: If user's tier doesn't allow the format (403)
        ValueError: If user_tier is not a valid tier value
        
    Example:
        >>> validate_export_tier_access("free", ExportFormat.PDF)   # Raises 403
        >>> validate_export_tier_access("basic", ExportFormat.PDF)  # OK
        >>> validate_export_tier_access("basic", ExportFormat.QTI)  # Raises 403
        >>> validate_export_tier_access("pro", ExportFormat.QTI)    # OK
    """
    # Normalize tier to lowercase
    user_tier = user_tier.lower() if user_tier else "free"
    
    # Validate tier value
    if user_tier not in VALID_TIERS:
        raise ValueError(f"Invalid tier '{user_tier}'. Must be one of: {VALID_TIERS}")
    
    # Free tier has no export access at all
    if user_tier == "free":
        raise TierInsufficientError(
            current_tier=user_tier,
            requested_format=export_format,
            reason="free_tier"
        )
    
    # Check if format requires Pro tier
    if export_format in PRO_ONLY_FORMATS:
        if user_tier != "pro":
            raise TierInsufficientError(
                current_tier=user_tier,
                requested_format=export_format,
                reason="pro_required"
            )


def is_format_available_for_tier(user_tier: str, export_format: ExportFormat) -> bool:
    """
    Check if an export format is available for a given tier (non-throwing).
    
    This is useful for frontend feature flags and UI rendering.
    
    Args:
        user_tier: User's current subscription tier
        export_format: The export format to check
        
    Returns:
        True if format is available, False otherwise
    """
    user_tier = user_tier.lower() if user_tier else "free"
    
    # Free tier has no export access
    if user_tier == "free":
        return False
    
    # Pro-only formats check
    if export_format in PRO_ONLY_FORMATS:
        return user_tier == "pro"
    
    # Basic and Pro have access to non-Pro formats
    return True


def get_available_formats_for_tier(user_tier: str) -> list[ExportFormat]:
    """
    Get list of all export formats available for a given tier.
    
    Args:
        user_tier: User's current subscription tier
        
    Returns:
        List of available ExportFormat values
    """
    user_tier = user_tier.lower() if user_tier else "free"
    
    # Free tier gets nothing
    if user_tier == "free":
        return []
    
    available = []
    for fmt in list(ExportFormat):
        if is_format_available_for_tier(user_tier, fmt):
            available.append(fmt)
    
    return available
