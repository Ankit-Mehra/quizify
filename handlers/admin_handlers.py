"""
Admin Handlers
Business logic for administrative operations.
"""

from fastapi import HTTPException, status
from typing import List, Dict, Any, Optional
from services.logger import app_logger as logger
from config import config
from schemas.user import UserTierUpdate, UserWithTier

# Lazy load Supabase client to avoid initialization issues in tests
def get_supabase():
    """Get Supabase client (lazy loaded)"""
    return config.get_supabase_client()

def is_admin(user_id: str) -> bool:
    """
    Check if a user has admin role.
    
    Uses role-based access control (RBAC) by querying profiles.role column.
    Falls back to environment variable ADMIN_USER_IDS for backward compatibility.
    
    Args:
        user_id: UUID of the user to check
        
    Returns:
        True if user has 'admin' role, False otherwise
    """
    import os
    
    # For testing, allow any authenticated user to be admin
    if config.is_testing():
        logger.info(f"Testing mode: Granting admin access to user {user_id}")
        return True
    
    try:
        # Primary method: Check role in profiles table (RBAC)
        response = (
            get_supabase().table("profiles")
            .select("role")
            .eq("id", user_id)
            .execute()
        )
        
        if response.data and len(response.data) > 0:
            user_role = response.data[0].get("role", "user")
            is_admin_role = user_role == "admin"
            
            if is_admin_role:
                logger.info(f"Admin access granted to user {user_id} (role: {user_role})")
            else:
                logger.warning(f"Admin access denied for user {user_id} (role: {user_role})")
            
            return is_admin_role
        
        # Fallback: If no profile found, check environment variable (backward compatibility)
        logger.warning(f"No profile found for user {user_id}, checking ADMIN_USER_IDS fallback")
        admin_ids_env = os.getenv("ADMIN_USER_IDS", "")
        admin_ids = [id.strip() for id in admin_ids_env.split(",") if id.strip()]
        
        if user_id in admin_ids:
            logger.info(f"Admin access granted to user {user_id} (via ADMIN_USER_IDS fallback)")
            return True
        
        logger.warning(f"Admin access denied for user {user_id} (no admin role and not in ADMIN_USER_IDS)")
        return False
        
    except Exception as e:
        logger.error(f"Error checking admin status for user {user_id}: {str(e)}", exc_info=True)
        
        # Fallback to environment variable on database error
        admin_ids_env = os.getenv("ADMIN_USER_IDS", "")
        admin_ids = [id.strip() for id in admin_ids_env.split(",") if id.strip()]
        return user_id in admin_ids


async def list_all_users(
    current_user_id: str,
    limit: int = 100,
    offset: int = 0
) -> List[UserWithTier]:
    """
    List all users with their tier information.
    
    Args:
        current_user_id: UUID of the requesting user (must be admin)
        limit: Maximum number of users to return
        offset: Number of users to skip
        
    Returns:
        List of users with tier information
        
    Raises:
        HTTPException: If user is not admin or database error occurs
    """
    # Check admin authorization
    if not is_admin(current_user_id):
        logger.warning(f"Non-admin user {current_user_id} attempted to list users")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    try:
        # Validate limits
        if limit < 1 or limit > 1000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Limit must be between 1 and 1000"
            )
        
        logger.info(f"Admin {current_user_id} fetching users list (limit={limit}, offset={offset})")
        
        # Query user_tier_info view with pagination
        response = (
            get_supabase().table("user_tier_info")
            .select("*")
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        
        if not response.data:
            logger.info("No users found")
            return []
        
        users = [UserWithTier(**user) for user in response.data]
        logger.info(f"Retrieved {len(users)} users")
        
        return users
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing users: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching users: {str(e)}"
        )


async def get_user_details(
    current_user_id: str,
    user_id: str
) -> UserWithTier:
    """
    Get detailed information about a specific user.
    
    Args:
        current_user_id: UUID of the requesting user (must be admin)
        user_id: UUID of the user to retrieve
        
    Returns:
        User information with tier and quota details
        
    Raises:
        HTTPException: If user is not admin, user not found, or database error occurs
    """
    # Check admin authorization
    if not is_admin(current_user_id):
        logger.warning(f"Non-admin user {current_user_id} attempted to get user details")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    try:
        logger.info(f"Admin {current_user_id} fetching details for user {user_id}")
        
        # Query user_tier_info view
        response = (
            get_supabase().table("user_tier_info")
            .select("*")
            .eq("id", user_id)
            .execute()
        )
        
        if not response.data or len(response.data) == 0:
            logger.warning(f"User {user_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )
        
        user = UserWithTier(**response.data[0])
        logger.info(f"Retrieved details for user {user_id}: tier={user.account_tier}")
        
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching user details: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching user details: {str(e)}"
        )


async def update_user_tier(
    current_user_id: str,
    user_id: str,
    tier_update: UserTierUpdate
) -> Dict[str, Any]:
    """
    Update a user's account tier.
    
    Args:
        current_user_id: UUID of the requesting user (must be admin)
        user_id: UUID of the user to update
        tier_update: New tier and optional reason
        
    Returns:
        Success message with updated user info
        
    Raises:
        HTTPException: If user is not admin, user not found, or database error occurs
    """
    # Check admin authorization
    if not is_admin(current_user_id):
        logger.warning(f"Non-admin user {current_user_id} attempted to update user tier")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    try:
        # Validate tier value
        valid_tiers = ["free", "basic", "educator"]
        if tier_update.new_tier not in valid_tiers:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid tier. Must be one of: {', '.join(valid_tiers)}"
            )
        
        logger.info(f"Admin {current_user_id} updating user {user_id} to tier {tier_update.new_tier}")
        if tier_update.reason:
            logger.info(f"Reason: {tier_update.reason}")
        
        # First, check if user exists
        check_response = (
            get_supabase().table("profiles")
            .select("id, account_tier")
            .eq("id", user_id)
            .execute()
        )
        
        if not check_response.data or len(check_response.data) == 0:
            logger.warning(f"User {user_id} not found in profiles table")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )
        
        old_tier = check_response.data[0]["account_tier"]
        
        # Update the user's tier in profiles table
        update_response = (
            get_supabase().table("profiles")
            .update({"account_tier": tier_update.new_tier})
            .eq("id", user_id)
            .execute()
        )
        
        if not update_response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update user tier"
            )
        
        logger.info(f"Successfully updated user {user_id} from {old_tier} to {tier_update.new_tier}")
        
        # Get updated user info
        updated_user_response = (
            get_supabase().table("user_tier_info")
            .select("*")
            .eq("id", user_id)
            .execute()
        )
        
        updated_user = updated_user_response.data[0] if updated_user_response.data else None
        
        return {
            "success": True,
            "message": f"User tier updated from {old_tier} to {tier_update.new_tier}",
            "user_id": user_id,
            "old_tier": old_tier,
            "new_tier": tier_update.new_tier,
            "updated_user": updated_user,
            "updated_by": current_user_id,
            "reason": tier_update.reason
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user tier: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating user tier: {str(e)}"
        )


async def update_user_role(
    current_user_id: str,
    user_id: str,
    new_role: str,
    reason: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update a user's role (admin promotion/demotion).
    
    Args:
        current_user_id: UUID of the requesting user (must be admin)
        user_id: UUID of the user to update
        new_role: New role ('user', 'admin', 'moderator')
        reason: Optional reason for the role change
        
    Returns:
        Success message with updated user info and audit log
        
    Raises:
        HTTPException: If user is not admin, trying to modify own role, user not found, or database error
    """
    # Check admin authorization
    if not is_admin(current_user_id):
        logger.warning(f"Non-admin user {current_user_id} attempted to update user role")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    # Prevent users from modifying their own role (security best practice)
    if current_user_id == user_id:
        logger.warning(f"User {current_user_id} attempted to modify their own role")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot modify your own role"
        )
    
    try:
        # Validate role value
        valid_roles = ["user", "admin", "moderator"]
        if new_role not in valid_roles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}"
            )
        
        logger.info(f"Admin {current_user_id} updating user {user_id} to role {new_role}")
        if reason:
            logger.info(f"Reason: {reason}")
        
        # First, check if user exists and get current role
        check_response = (
            get_supabase().table("profiles")
            .select("id, role")
            .eq("id", user_id)
            .execute()
        )
        
        if not check_response.data or len(check_response.data) == 0:
            logger.warning(f"User {user_id} not found in profiles table")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )
        
        old_role = check_response.data[0].get("role", "user")
        
        # Don't update if role is already the same
        if old_role == new_role:
            return {
                "success": True,
                "message": f"User already has role '{new_role}'",
                "user_id": user_id,
                "role": new_role,
                "changed": False
            }
        
        # Update the user's role in profiles table
        update_response = (
            get_supabase().table("profiles")
            .update({"role": new_role})
            .eq("id", user_id)
            .execute()
        )
        
        if not update_response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update user role"
            )
        
        logger.info(f"Successfully updated user {user_id} from role '{old_role}' to '{new_role}'")
        
        # Log the role change in audit table
        try:
            audit_log = (
                get_supabase().table("role_audit_log")
                .insert({
                    "user_id": user_id,
                    "old_role": old_role,
                    "new_role": new_role,
                    "changed_by": current_user_id,
                    "reason": reason
                })
                .execute()
            )
            logger.info(f"Role change logged in audit table: {audit_log.data[0]['id']}")
        except Exception as audit_error:
            # Don't fail the role update if audit logging fails
            logger.error(f"Failed to log role change in audit table: {str(audit_error)}")
        
        # Get updated user info
        updated_user_response = (
            get_supabase().table("user_tier_info")
            .select("*")
            .eq("id", user_id)
            .execute()
        )
        
        updated_user = updated_user_response.data[0] if updated_user_response.data else None
        
        return {
            "success": True,
            "message": f"User role updated from '{old_role}' to '{new_role}'",
            "user_id": user_id,
            "old_role": old_role,
            "new_role": new_role,
            "updated_user": updated_user,
            "updated_by": current_user_id,
            "reason": reason,
            "changed": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user role: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating user role: {str(e)}"
        )
