"""
Tier Validator - Export format access control based on user subscription tier.

UPDATED (December 2025): Export is now available to ALL tiers.

The only gating for exports is quiz ownership - if a user generated a quiz 
(using their credits), they can export it in any format. This simplifies the 
business model:

- Quiz generation: Credit-gated (Free = 3 credits/mo, Pro = 43 credits/mo)
- Export: FREE for all users who own the quiz

This module is kept for backward compatibility and logging purposes.
All validation functions now allow all tiers to export all formats.
"""

import logging
from typing import Set
from fastapi import HTTPException

from schemas.export import ExportFormat

# Module logger for tier validation operations
logger = logging.getLogger(__name__)


# DEPRECATED: These constants are kept for backward compatibility but no longer enforced
# All formats are now available to all tiers
PRO_ONLY_FORMATS: Set[ExportFormat] = set()  # Empty - no tier restrictions

PAID_TIER_FORMATS: Set[ExportFormat] = {
    ExportFormat.PDF,
    ExportFormat.DOCX,
    ExportFormat.CSV_QUIZIFY,
    ExportFormat.CSV_ANKI,
    ExportFormat.SHARE_LINK,
    ExportFormat.QTI,
    ExportFormat.MOODLE_XML,
    ExportFormat.GOOGLE_FORMS,
}

# All tiers have export access (exports are free for quiz owners)
EXPORT_ALLOWED_TIERS = {"free", "premium", "pro"}

# Valid tier values
VALID_TIERS = {"free", "premium", "pro"}


class TierInsufficientError(HTTPException):
    """
    DEPRECATED: This exception is no longer raised for export operations.
    
    Kept for backward compatibility with any code that imports it.
    Export is now free for all tiers who own the quiz.
    """
    
    def __init__(self, current_tier: str, requested_format: ExportFormat, reason: str = "pro_required"):
        if reason == "free_tier":
            detail = {
                "error": "tier_insufficient",
                "message": "Export features require a Premium or Pro subscription",
                "required_tier": "premium",
                "current_tier": current_tier,
                "requested_format": requested_format.value,
                "upgrade_url": "/billing/upgrade"
            }
        else:  # pro_required
            detail = {
                "error": "tier_insufficient",
                "message": "Google Forms and LMS export formats (QTI, Moodle XML) require a Pro subscription",
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
    
    UPDATED: All tiers can now export all formats. Quiz generation is the only
    credit-gated operation. If a user owns a quiz (generated with their credits),
    they can export it in any format for free.
    
    Args:
        user_tier: User's current subscription tier ('free', 'premium', 'pro')
        export_format: The export format being requested
        
    Raises:
        ValueError: If user_tier is not a valid tier value (after normalization)
        
    Example:
        >>> validate_export_tier_access("free", ExportFormat.PDF)      # OK - no restrictions
        >>> validate_export_tier_access("free", ExportFormat.QTI)      # OK - no restrictions
        >>> validate_export_tier_access("pro", ExportFormat.QTI)       # OK
    """
    # Normalize tier to lowercase and map legacy "basic" to "premium"
    user_tier = user_tier.lower() if user_tier else "free"
    if user_tier == "basic":
        user_tier = "premium"  # Legacy mapping
    
    # Validate tier value
    if user_tier not in VALID_TIERS:
        logger.error(f"Invalid tier value: {user_tier}")
        raise ValueError(f"Invalid tier '{user_tier}'. Must be one of: {VALID_TIERS}")
    
    # Log the export access (all tiers allowed)
    logger.debug(f"Export access granted: tier={user_tier}, format={export_format.value}")
    
    # No tier restrictions - all formats available to all tiers
    # Quiz ownership is validated separately in the export handler
    return


def is_format_available_for_tier(user_tier: str, export_format: ExportFormat) -> bool:
    """
    Check if an export format is available for a given tier (non-throwing).
    
    UPDATED: Always returns True for all tiers and formats.
    Export is free for all quiz owners.
    
    Args:
        user_tier: User's current subscription tier
        export_format: The export format to check
        
    Returns:
        True - all formats available to all tiers
    """
    user_tier = user_tier.lower() if user_tier else "free"
    if user_tier == "basic":
        user_tier = "premium"  # Legacy mapping
    
    # Validate tier exists
    if user_tier not in VALID_TIERS:
        return False
    
    # All formats available to all valid tiers
    return True


def get_available_formats_for_tier(user_tier: str) -> list[ExportFormat]:
    """
    Get list of all export formats available for a given tier.
    
    UPDATED: Returns all formats for all valid tiers.
    Export is free for all quiz owners.
    
    Args:
        user_tier: User's current subscription tier
        
    Returns:
        List of all ExportFormat values for valid tiers, empty list for invalid tiers
    """
    user_tier = user_tier.lower() if user_tier else "free"
    if user_tier == "basic":
        user_tier = "premium"  # Legacy mapping
    
    # Invalid tier gets nothing
    if user_tier not in VALID_TIERS:
        return []
    
    # All tiers get all formats
    return list(ExportFormat)
