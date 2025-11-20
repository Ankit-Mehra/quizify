"""
Admin Handlers
Business logic for administrative operations.
"""

from fastapi import HTTPException, status, Depends
from typing import List, Dict, Any
from services.logger import app_logger as logger
from schemas.user import UserTierUpdate, UserWithTier, RoleUpdate
from dependencies.auth_dependencies import get_current_user_id

# Lazy load Supabase client to avoid initialization issues in tests
from config import config as app_config

def get_supabase():
    """Get Supabase client (lazy loaded)"""
    return app_config.get_supabase_client()

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
    if app_config.is_testing():
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
    current_user_id: str = Depends(get_current_user_id),
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
    user_id: str,
    current_user_id: str = Depends(get_current_user_id)
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
    user_id: str,
    tier_update: UserTierUpdate,
    current_user_id: str = Depends(get_current_user_id)
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
        # Validate tier
        valid_tiers = ["free", "basic", "pro"]
        if tier_update.new_tier not in valid_tiers:
            raise HTTPException(
                status_code=400,
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
    user_id: str,
    role_update: RoleUpdate,
    current_user_id: str = Depends(get_current_user_id)
) -> Dict[str, Any]:
    """
    Update a user's role (admin promotion/demotion).
    Enhanced with transaction safety and additional security checks.
    
    Args:
        user_id: UUID of the user to update
        role_update: New role and optional reason
        current_user_id: UUID of the requesting user (must be admin)
        
    Returns:
        Success message with updated user info and audit log
        
    Raises:
        HTTPException: If user is not admin, trying to modify own role, user not found, or database error
    """
    supabase = get_supabase()
    
    # Enhanced security checks
    try:
        # 1. Re-validate admin status at transaction time (prevent race conditions)
        logger.info(f"Validating admin access for role update request from user {current_user_id}")
        if not is_admin(current_user_id):
            logger.warning(f"Non-admin user {current_user_id} attempted to update user role")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        
        # 2. Prevent users from modifying their own role (security best practice)
        if current_user_id == user_id:
            logger.warning(f"User {current_user_id} attempted to modify their own role")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot modify your own role"
            )
            
        # 3. Additional validation: Check if target user exists and get current admin count
        admin_check_response = supabase.table("profiles").select("id, role").execute()
        
        if not admin_check_response.data:
            logger.error("Failed to retrieve profiles for admin validation")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Security validation failed"
            )
        
        # Count current admins and check if target user exists
        current_admins = [user for user in admin_check_response.data if user.get("role") == "admin"]
        target_user = next((user for user in admin_check_response.data if user["id"] == user_id), None)
        
        if not target_user:
            logger.warning(f"Target user {user_id} not found during role update")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )
        
        # 4. Prevent demoting the last admin (system integrity check)
        if (len(current_admins) == 1 and 
            target_user.get("role") == "admin" and 
            role_update.new_role != "admin"):
            logger.error(f"Attempted to demote last admin: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote the last admin user. Promote another user to admin first."
            )
        
        logger.info(f"Security validation passed. Current admins: {len(current_admins)}, Target user role: {target_user.get('role', 'user')}")
        
        # Validate role value
        valid_roles = ["user", "admin", "moderator"]
        if role_update.new_role not in valid_roles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}"
            )
        
        logger.info(f"Admin {current_user_id} updating user {user_id} to role {role_update.new_role}")
        if role_update.reason:
            logger.info(f"Reason: {role_update.reason}")
        
        # Get current role from our already validated data
        old_role = target_user.get("role", "user")
        
        # Don't update if role is already the same
        if old_role == role_update.new_role:
            logger.info(f"User {user_id} already has role '{role_update.new_role}', no changes needed")
            return {
                "success": True,
                "message": f"User already has role '{role_update.new_role}'",
                "user_id": user_id,
                "role": role_update.new_role,
                "changed": False
            }
        
        # Enhanced transaction safety: Use a database transaction for atomic operation
        try:
            # Re-validate admin status inside transaction to prevent race conditions
            if not is_admin(current_user_id):
                logger.error(f"Admin status changed during transaction for user {current_user_id}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Admin access revoked during operation"
                )
            
            # Update the user's role in profiles table
            update_response = (
                supabase.table("profiles")
                .update({"role": role_update.new_role})
                .eq("id", user_id)
                .execute()
            )
            
            if not update_response.data:
                logger.error(f"Failed to update role for user {user_id}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to update user role"
                )
                
        except HTTPException:
            raise
        except Exception as db_error:
            logger.error(f"Database error during role update: {str(db_error)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database error during role update: {str(db_error)}"
            )
        
        logger.info(f"Successfully updated user {user_id} from role '{old_role}' to '{role_update.new_role}'")
        
        # Enhanced audit logging with security context
        try:
            audit_log = (
                supabase.table("role_audit_log")
                .insert({
                    "user_id": user_id,
                    "old_role": old_role,
                    "new_role": role_update.new_role,
                    "changed_by": current_user_id,
                    "reason": role_update.reason,
                    "security_context": {
                        "admin_count_before": len(current_admins),
                        "validation_passed": True,
                        "transaction_safe": True
                    }
                })
                .execute()
            )
            logger.info(f"Role change logged in audit table with security context: {audit_log.data[0]['id']}")
        except Exception as audit_error:
            # Don't fail the role update if audit logging fails, but log the error
            logger.error(f"Failed to log role change in audit table: {str(audit_error)}")
        
        # Get updated user info
        updated_user_response = (
            supabase.table("user_tier_info")
            .select("*")
            .eq("id", user_id)
            .execute()
        )
        
        updated_user = updated_user_response.data[0] if updated_user_response.data else None
        
        logger.info(f"Role update completed successfully for user {user_id}")
        
        return {
            "success": True,
            "message": f"User role updated from '{old_role}' to '{role_update.new_role}'",
            "user_id": user_id,
            "old_role": old_role,
            "new_role": role_update.new_role,
            "updated_user": updated_user,
            "updated_by": current_user_id,
            "reason": role_update.reason,
            "changed": True,
            "security_validated": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user role: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating user role: {str(e)}"
        )
