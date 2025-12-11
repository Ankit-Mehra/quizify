"""
Storage Service - User file storage quota management.

This module handles storage quota enforcement:
- Free plan: 250 MB
- Pay-as-you-go (purchased credits, no Pro subscription): 2 GB
- Pro subscription: 5 GB

Storage quota is checked before file uploads and storage usage is tracked
per user via the user_files table.
"""

from typing import Optional, TypedDict
from fastapi import HTTPException
from services.logger import app_logger as logger
from services.db_services.supabase_quiz import get_supabase


# Storage quota constants in bytes
STORAGE_QUOTA_FREE = 262_144_000          # 250 MB
STORAGE_QUOTA_PAYG = 2_147_483_648        # 2 GB (pay-as-you-go)
STORAGE_QUOTA_PRO = 5_368_709_120         # 5 GB

# Human-readable labels for error messages
STORAGE_QUOTA_LABELS = {
    "free": "250 MB",
    "payg": "2 GB",
    "pro": "5 GB",
}


class StorageQuotaInfo(TypedDict):
    """Storage quota information for a user."""
    user_id: str
    plan_type: str                   # "free", "payg", or "pro"
    storage_used_bytes: int          # Current storage usage
    storage_quota_bytes: int         # Maximum allowed storage
    storage_remaining_bytes: int     # Remaining storage available
    storage_used_formatted: str      # e.g., "125.5 MB"
    storage_quota_formatted: str     # e.g., "250 MB"
    storage_remaining_formatted: str # e.g., "124.5 MB"
    usage_percentage: float          # 0.0 to 100.0


def format_bytes(size_bytes: int) -> str:
    """
    Format bytes to human-readable string.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Human-readable string (e.g., "125.5 MB", "1.2 GB")
    """
    if size_bytes < 0:
        return "0 B"
    
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(size_bytes) < 1024.0:
            if unit == 'B':
                return f"{size_bytes} {unit}"
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    
    return f"{size_bytes:.1f} PB"


def get_plan_type(billing_plan: Optional[str], subscription_status: Optional[str], purchased_units: int) -> str:
    """
    Determine the plan type for storage quota purposes.
    
    Args:
        billing_plan: User's billing plan ("free" or "pro")
        subscription_status: Stripe subscription status
        purchased_units: Number of purchased credit units
        
    Returns:
        Plan type: "free", "payg", or "pro"
    """
    # Pro users with active subscription
    if billing_plan == "pro" and subscription_status in ("active", "trialing"):
        return "pro"
    
    # Pay-as-you-go: has purchased credits but no active Pro subscription
    if purchased_units > 0:
        return "payg"
    
    # Default to free
    return "free"


def get_storage_quota_for_plan(plan_type: str) -> int:
    """
    Get storage quota in bytes for a plan type.
    
    Args:
        plan_type: "free", "payg", or "pro"
        
    Returns:
        Storage quota in bytes
    """
    if plan_type == "pro":
        return STORAGE_QUOTA_PRO
    elif plan_type == "payg":
        return STORAGE_QUOTA_PAYG
    else:
        return STORAGE_QUOTA_FREE


async def get_storage_usage(user_id: str) -> int:
    """
    Get total storage used by a user in bytes.
    
    Args:
        user_id: User ID
        
    Returns:
        Total bytes used
    """
    supabase = get_supabase()
    
    # Try RPC function first (more efficient)
    try:
        result = supabase.rpc("get_storage_usage", {"p_user_id": user_id}).execute()
        if result.data is not None:
            return int(result.data)
    except Exception as e:
        logger.warning(f"RPC get_storage_usage failed for user {user_id[:8]}: {e}. Falling back to direct query.")
    
    # Fallback: calculate from user_files table
    try:
        response = supabase.table("user_files").select("file_size_bytes").eq("user_id", user_id).execute()
        
        total = 0
        for row in (response.data or []):
            if row.get("file_size_bytes"):
                total += row["file_size_bytes"]
        
        return total
        
    except Exception as e:
        logger.error(f"Fallback user_files query failed for user {user_id[:8]}: {e}")
        # Return 0 on error to avoid blocking uploads
        return 0


async def get_storage_quota_info(user_id: str) -> StorageQuotaInfo:
    """
    Get complete storage quota information for a user.
    
    Args:
        user_id: User ID
        
    Returns:
        StorageQuotaInfo with usage and quota details
    """
    supabase = get_supabase()
    
    # Fetch user's billing info
    response = supabase.table("profiles").select(
        "billing_plan, subscription_status, credit_units_purchased"
    ).eq("id", user_id).single().execute()
    
    if not response.data:
        # User not found, use free tier defaults
        plan_type = "free"
        quota = STORAGE_QUOTA_FREE
    else:
        data = response.data
        plan_type = get_plan_type(
            data.get("billing_plan"),
            data.get("subscription_status"),
            data.get("credit_units_purchased", 0)
        )
        quota = get_storage_quota_for_plan(plan_type)
    
    # Get current usage
    used = await get_storage_usage(user_id)
    remaining = max(0, quota - used)
    
    # Calculate usage percentage
    usage_pct = (used / quota * 100) if quota > 0 else 0.0
    
    return StorageQuotaInfo(
        user_id=user_id,
        plan_type=plan_type,
        storage_used_bytes=used,
        storage_quota_bytes=quota,
        storage_remaining_bytes=remaining,
        storage_used_formatted=format_bytes(used),
        storage_quota_formatted=format_bytes(quota),
        storage_remaining_formatted=format_bytes(remaining),
        usage_percentage=round(usage_pct, 1)
    )


async def check_storage_quota(user_id: str, file_size_bytes: int) -> tuple[bool, StorageQuotaInfo]:
    """
    Check if uploading a file would exceed the user's storage quota.
    
    Args:
        user_id: User ID
        file_size_bytes: Size of file to upload in bytes
        
    Returns:
        Tuple of (allowed: bool, quota_info: StorageQuotaInfo)
    """
    quota_info = await get_storage_quota_info(user_id)
    
    would_use = quota_info["storage_used_bytes"] + file_size_bytes
    allowed = would_use <= quota_info["storage_quota_bytes"]
    
    return allowed, quota_info


async def validate_storage_quota_or_raise(user_id: str, file_size_bytes: int) -> StorageQuotaInfo:
    """
    Validate that uploading a file won't exceed quota.
    Raises HTTP 402 if quota would be exceeded.
    
    Args:
        user_id: User ID
        file_size_bytes: Size of file to upload in bytes
        
    Returns:
        StorageQuotaInfo if allowed
        
    Raises:
        HTTPException: 402 if quota would be exceeded
    """
    allowed, quota_info = await check_storage_quota(user_id, file_size_bytes)
    
    if not allowed:
        plan_label = STORAGE_QUOTA_LABELS.get(quota_info["plan_type"], "250 MB")
        
        # Construct helpful error message based on plan
        if quota_info["plan_type"] == "free":
            message = (
                f"Storage quota exceeded. You have used {quota_info['storage_used_formatted']} "
                f"of your {plan_label} limit. Purchase credits to unlock 2 GB storage, "
                f"or upgrade to Pro for 5 GB storage."
            )
        elif quota_info["plan_type"] == "payg":
            message = (
                f"Storage quota exceeded. You have used {quota_info['storage_used_formatted']} "
                f"of your {plan_label} limit. Upgrade to Pro for 5 GB storage."
            )
        else:
            message = (
                f"Storage quota exceeded. You have used {quota_info['storage_used_formatted']} "
                f"of your {plan_label} limit. Please delete some files to continue."
            )
        
        logger.warning(
            f"Storage quota exceeded for user {user_id[:8]}: "
            f"used={quota_info['storage_used_formatted']}, "
            f"quota={quota_info['storage_quota_formatted']}, "
            f"file_size={format_bytes(file_size_bytes)}"
        )
        
        raise HTTPException(
            status_code=402,
            detail={
                "error": "storage_quota_exceeded",
                "message": message,
                "storage_used_bytes": quota_info["storage_used_bytes"],
                "storage_quota_bytes": quota_info["storage_quota_bytes"],
                "storage_remaining_bytes": quota_info["storage_remaining_bytes"],
                "file_size_bytes": file_size_bytes,
                "plan": quota_info["plan_type"],
                "storage_used_formatted": quota_info["storage_used_formatted"],
                "storage_quota_formatted": quota_info["storage_quota_formatted"],
            }
        )
    
    return quota_info


async def update_storage_quota_for_plan_change(user_id: str, new_plan: str) -> None:
    """
    Update user's storage quota when their plan changes.
    
    Called by billing webhook handlers when subscription status changes.
    
    Args:
        user_id: User ID
        new_plan: New plan type ("free", "payg", or "pro")
    """
    quota = get_storage_quota_for_plan(new_plan)
    
    supabase = get_supabase()
    
    try:
        supabase.table("profiles").update({
            "storage_quota_bytes": quota
        }).eq("id", user_id).execute()
        
        logger.info(
            f"Updated storage quota for user {user_id[:8]} to {format_bytes(quota)} "
            f"(plan: {new_plan})"
        )
    except Exception as e:
        logger.error(f"Failed to update storage quota for user {user_id[:8]}: {e}")
        raise
