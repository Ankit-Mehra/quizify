"""
Admin API Routes
Endpoints for administrative tasks like user tier management and role-based access control.
"""

from fastapi import APIRouter, Depends
from typing import Dict, Any, List
from dependencies.auth_dependencies import get_current_user_id
from handlers.admin_handlers import (
    list_all_users,
    update_user_tier,
    get_user_details,
    update_user_role
)
from schemas.user import UserTierUpdate, UserWithTier, RoleUpdate
from services.logger import app_logger as logger

router = APIRouter(prefix="/admin", tags=["Admin"])
logger.info("Admin routes initialized")

# All admin routes require authentication
# Additional authorization checks happen in handlers


# ============================================================================
# Route Registration
# ============================================================================

# GET /admin/users - List all users
router.add_api_route(
    path="/users",
    endpoint=list_all_users,
    methods=["GET"],
    summary="List All Users",
    description="List all users with their tier information. Admin only endpoint.",
    response_model=List[UserWithTier],
    tags=["Admin"],
    dependencies=[Depends(get_current_user_id)],
    openapi_extra={"security": [{"BearerAuth": []}]}
)

# GET /admin/users/{user_id} - Get user details
router.add_api_route(
    path="/users/{user_id}",
    endpoint=get_user_details,
    methods=["GET"],
    summary="Get User Details",
    description="Get detailed information about a specific user. Admin only endpoint.",
    response_model=UserWithTier,
    tags=["Admin"],
    dependencies=[Depends(get_current_user_id)],
    openapi_extra={"security": [{"BearerAuth": []}]}
)

# PUT /admin/users/{user_id}/tier - Update user tier
router.add_api_route(
    path="/users/{user_id}/tier",
    endpoint=update_user_tier,
    methods=["PUT"],
    summary="Update User Tier",
    description="Update a user's account tier. Admin only endpoint.",
    response_model=Dict[str, Any],
    tags=["Admin"],
    dependencies=[Depends(get_current_user_id)],
    openapi_extra={
        "security": [{"BearerAuth": []}],
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": UserTierUpdate.model_json_schema()
                }
            }
        }
    }
)

# PUT /admin/users/{user_id}/role - Update user role (RBAC)
router.add_api_route(
    path="/users/{user_id}/role",
    endpoint=update_user_role,
    methods=["PUT"],
    summary="Update User Role",
    description="Update a user's role (promote/demote to admin). Admin only endpoint with audit logging.",
    response_model=Dict[str, Any],
    tags=["Admin"],
    dependencies=[Depends(get_current_user_id)],
    openapi_extra={
        "security": [{"BearerAuth": []}],
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": RoleUpdate.model_json_schema()
                }
            }
        }
    }
)

