# API Contract: Admin Endpoints (ACTUAL IMPLEMENTATION)

**Module**: Admin User Management  
**Base Path**: `/admin`  
**Status**: ✅ FULLY IMPLEMENTED  
**Last Updated**: 2025-10-28

---

## Overview

Admin-only endpoints for user management with Role-Based Access Control (RBAC). All endpoints require admin authentication and enforce strict permission checks.

---

## Endpoint Summary

| Endpoint | Method | Response Model | Required Role | Description |
|----------|--------|----------------|---------------|-------------|
| `/admin/users` | GET | `List[UserWithTier]` | admin | List all users |
| `/admin/users/{user_id}` | GET | `UserWithTier` | admin | Get specific user |
| `/admin/users/{user_id}/tier` | PUT | `AdminUpdateResponse` | admin | Update user tier |
| `/admin/users/{user_id}/role` | PUT | `AdminUpdateResponse` | admin | Update user role |

---

## Authentication & Authorization

**Required Headers**:
```
Authorization: Bearer {admin_access_token}
```

**Permission Checks**:
1. User must be authenticated (valid JWT token)
2. User must have `role = 'admin'` in their profile
3. Automatic 403 Forbidden if not admin

**RBAC Implementation**:
- Uses `get_admin_user()` dependency from `dependencies/auth_dependencies.py`
- Checks `public.profiles.role = 'admin'`
- Admins cannot downgrade themselves (self-protection)

---

## 1. GET /admin/users

**Purpose**: List all users with tier and quota information

**Authentication**: Admin only

**Response Model**: `List[UserWithTier]`

**Query Parameters**:
- `skip` (int, default=0): Number of records to skip
- `limit` (int, default=100): Maximum records to return

**Success Response (200)**:
```json
[
  {
    "user_id": "760602fe-b19f-472a-b65e-060f9e195529",
    "email": "user1@example.com",
    "account_tier": "free",
    "current_quiz_count": 3,
    "quota_limit": 5,
    "quota_exceeded": false,
    "role": "user",
    "created_at": "2025-10-15T10:30:00Z"
  },
  {
    "user_id": "860703fe-c29f-573b-c76f-170g0f295630",
    "email": "user2@example.com",
    "account_tier": "basic",
    "current_quiz_count": 15,
    "quota_limit": 20,
    "quota_exceeded": false,
    "role": "user",
    "created_at": "2025-10-16T14:20:00Z"
  }
]
```

**Response Fields**:
- `user_id` (string): User's UUID
- `email` (string): User's email address
- `account_tier` (enum): `"free"`, `"basic"`, or `"educator"`
- `current_quiz_count` (int): Number of quizzes created
- `quota_limit` (int): Maximum quizzes allowed
- `quota_exceeded` (boolean): Whether user has hit quota
- `role` (enum): `"user"`, `"admin"`, or `"moderator"`
- `created_at` (string): Account creation timestamp

**Error Responses**:
- `401 Unauthorized`: No valid token
- `403 Forbidden`: User is not admin
- `500 Internal Server Error`: Database error

**Implementation Details**:
- Queries `user_tier_info` view which joins `auth.users` and `public.profiles`
- Includes pagination via `skip` and `limit`
- Returns users sorted by `created_at` DESC (newest first)

---

## 2. GET /admin/users/{user_id}

**Purpose**: Get detailed information for a specific user

**Authentication**: Admin only

**Response Model**: `UserWithTier`

**Path Parameters**:
- `user_id` (UUID, required): User's unique identifier

**Success Response (200)**:
```json
{
  "user_id": "760602fe-b19f-472a-b65e-060f9e195529",
  "email": "user@example.com",
  "account_tier": "free",
  "current_quiz_count": 3,
  "quota_limit": 5,
  "quota_exceeded": false,
  "role": "user",
  "created_at": "2025-10-15T10:30:00Z"
}
```

**Error Responses**:
- `401 Unauthorized`: No valid token
- `403 Forbidden`: User is not admin
- `404 Not Found`: User ID does not exist
- `500 Internal Server Error`: Database error

---

## 3. PUT /admin/users/{user_id}/tier

**Purpose**: Update a user's account tier (affects quiz quota)

**Authentication**: Admin only

**Response Model**: `AdminUpdateResponse`

**Path Parameters**:
- `user_id` (UUID, required): User's unique identifier

**Request Body**:
```json
{
  "account_tier": "basic"
}
```

**Request Schema**: Uses `UserTierUpdate` from `schemas/user.py`

**Valid Tier Values**:
- `"free"`: 5 quizzes max
- `"basic"`: 20 quizzes max
- `"educator"`: Unlimited quizzes

**Success Response (200)**:
```json
{
  "message": "User tier updated successfully",
  "user_id": "760602fe-b19f-472a-b65e-060f9e195529",
  "updated_field": "account_tier",
  "new_value": "basic"
}
```

**Error Responses**:
- `401 Unauthorized`: No valid token
- `403 Forbidden`: User is not admin
- `404 Not Found`: User ID does not exist
- `422 Unprocessable Entity`: Invalid tier value

**Implementation Details**:
- Updates `public.profiles.account_tier`
- Quota is recalculated automatically via view
- Does NOT reset `current_quiz_count`

**Use Cases**:
- Reward active users with tier upgrades
- Trial period for premium features
- Manual tier corrections

---

## 4. PUT /admin/users/{user_id}/role

**Purpose**: Update a user's role (changes permissions)

**Authentication**: Admin only

**Response Model**: `AdminUpdateResponse`

**Path Parameters**:
- `user_id` (UUID, required): User's unique identifier

**Request Body**:
```json
{
  "role": "moderator"
}
```

**Request Schema**: Uses `RoleUpdate` from `schemas/user.py`

**Valid Role Values**:
- `"user"`: Standard user (no special permissions)
- `"moderator"`: Can moderate content (future feature)
- `"admin"`: Full admin access (user management, etc.)

**Success Response (200)**:
```json
{
  "message": "User role updated successfully",
  "user_id": "760602fe-b19f-472a-b65e-060f9e195529",
  "updated_field": "role",
  "new_value": "moderator"
}
```

**Error Responses**:
- `401 Unauthorized`: No valid token
- `403 Forbidden`: User is not admin OR admin trying to change own role
- `404 Not Found`: User ID does not exist
- `422 Unprocessable Entity`: Invalid role value

**Security Features**:
- **Self-Protection**: Admins cannot change their own role (prevents accidental lockout)
- **Validation**: Only allows roles defined in `USER_ROLES` enum

**Implementation Details**:
- Updates `public.profiles.role`
- Enforced via `get_admin_user()` dependency on subsequent requests
- Changes take effect immediately (next API call)

---

## Response Schemas Reference

### UserWithTier
```python
class UserWithTier(BaseModel):
    user_id: str
    email: str
    account_tier: Literal["free", "basic", "educator"]
    current_quiz_count: int
    quota_limit: int
    quota_exceeded: bool
    role: Literal["user", "admin", "moderator"]
    created_at: str
```

### AdminUpdateResponse
```python
class AdminUpdateResponse(BaseModel):
    message: str
    user_id: str
    updated_field: str
    new_value: str
```

### UserTierUpdate
```python
class UserTierUpdate(BaseModel):
    account_tier: Literal["free", "basic", "educator"]
```

### RoleUpdate
```python
class RoleUpdate(BaseModel):
    role: Literal["user", "admin", "moderator"]
```

---

## Security Features

### Role-Based Access Control (RBAC)
```python
# From dependencies/auth_dependencies.py
async def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """Dependency to ensure user is an admin"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user
```

### Self-Protection Rules
- Admins cannot change their own role
- Prevents accidental privilege escalation/removal
- Checked in handler before database update

### Audit Considerations
- All admin actions should be logged (not yet implemented)
- User changes visible in database timestamps

---

## Common Error Patterns

### 403 Forbidden (Not Admin)
```json
{
  "detail": "Admin access required"
}
```
**Cause**: User's `role` is not `"admin"`

### 403 Forbidden (Self-Modification)
```json
{
  "detail": "Admins cannot change their own role"
}
```
**Cause**: Admin tried to change their own role

### 404 Not Found
```json
{
  "detail": "User not found"
}
```
**Cause**: User ID does not exist in database

### 422 Unprocessable Entity
```json
{
  "detail": [
    {
      "loc": ["body", "account_tier"],
      "msg": "unexpected value; permitted: 'free', 'basic', 'educator'",
      "type": "value_error.const"
    }
  ]
}
```
**Cause**: Invalid enum value for tier or role

---

## Usage Examples

### 1. List All Users
```bash
curl -X GET "/admin/users?skip=0&limit=10" \
  -H "Authorization: Bearer {admin_token}"
```

### 2. Get Specific User
```bash
curl -X GET "/admin/users/760602fe-b19f-472a-b65e-060f9e195529" \
  -H "Authorization: Bearer {admin_token}"
```

### 3. Upgrade User to Basic Tier
```bash
curl -X PUT "/admin/users/760602fe-b19f-472a-b65e-060f9e195529/tier" \
  -H "Authorization: Bearer {admin_token}" \
  -H "Content-Type: application/json" \
  -d '{"account_tier": "basic"}'
```

### 4. Promote User to Moderator
```bash
curl -X PUT "/admin/users/760602fe-b19f-472a-b65e-060f9e195529/role" \
  -H "Authorization: Bearer {admin_token}" \
  -H "Content-Type: application/json" \
  -d '{"role": "moderator"}'
```

---

## Implementation Flow

### Tier Update Flow
1. Admin sends PUT request with new tier
2. `get_admin_user()` validates admin permissions
3. Handler validates user_id exists
4. Handler updates `public.profiles.account_tier`
5. View `user_tier_info` automatically reflects new quota
6. Response returned with confirmation

### Role Update Flow
1. Admin sends PUT request with new role
2. `get_admin_user()` validates admin permissions
3. Handler checks if admin is modifying own role (forbidden)
4. Handler validates user_id exists
5. Handler updates `public.profiles.role`
6. Response returned with confirmation

---

## Database Schema Dependencies

### Tables Used
- `auth.users`: Core user authentication (Supabase managed)
- `public.profiles`: Extended user data (tier, role, display_name)

### Views Used
- `user_tier_info`: Joins auth.users + profiles, calculates quotas

### Key Fields
- `public.profiles.account_tier`: Enum ('free', 'basic', 'educator')
- `public.profiles.role`: Enum ('user', 'admin', 'moderator')
- `user_tier_info.current_quiz_count`: Calculated from quizzes table
- `user_tier_info.quota_limit`: Based on tier (5, 20, unlimited)

---

## Testing Considerations

### Test Cases
- ✅ Non-admin cannot access any endpoint
- ✅ Admin can list all users
- ✅ Admin can view specific user
- ✅ Admin can update user tier
- ✅ Admin can update user role
- ✅ Admin cannot change own role
- ✅ Invalid tier/role values rejected
- ✅ Non-existent user_id returns 404

### Test Data Requirements
- At least 2 users (one admin, one regular)
- Users with different tiers
- Users at different quota levels

---

## Future Enhancements

- [ ] Bulk user operations (batch tier updates)
- [ ] Admin audit log (track who changed what)
- [ ] User search/filtering (by email, tier, role)
- [ ] User statistics dashboard
- [ ] Quota reset functionality
- [ ] User suspension/ban feature
- [ ] Email notification on tier/role change

---

**Contract Status**: ✅ Complete  
**Security Audit**: ✅ Passed  
**Production Ready**: ✅ Yes  
**RBAC Enforcement**: ✅ Active
