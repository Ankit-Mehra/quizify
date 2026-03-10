# API Contract: Authentication Endpoints (ACTUAL IMPLEMENTATION)

**Module**: Authentication & User Management  
**Base Path**: `/auth`  
**Status**: ✅ FULLY IMPLEMENTED  
**Last Updated**: 2025-10-28

---

## Overview

Complete authentication system with signup, login, email management, password management, and user profile access. All endpoints use Supabase Auth for backend authentication.

---

## Endpoint Summary

| Endpoint | Method | Response Model | Description |
|----------|--------|----------------|-------------|
| `/auth/signup` | POST | `Dict[str, Any]` | Register new user |
| `/auth/login` | POST | `Dict[str, Any]` | Authenticate user |
| `/auth/logout` | POST | `AuthMessageResponse` | End user session |
| `/auth/me` | GET | `UserInfoResponse` | Get current user info |
| `/auth/change-password` | PATCH | `AuthMessageResponse` | Update password |
| `/auth/update-email` | PATCH | `AuthMessageResponse` | Update email address |
| `/auth/delete-account` | DELETE | `AuthMessageResponse` | Permanently delete account |
| `/auth/forgot-password` | POST | `AuthMessageResponse` | Request password reset |
| `/auth/reset-password` | POST | `Dict[str, Any]` | Reset password with token |
| `/auth/confirm` | GET | HTML Redirect | Confirm email address |
| `/auth/resend-verification` | POST | `Dict[str, Any]` | Resend verification email |

---

## 1. POST /auth/signup

**Purpose**: Register a new user account

**Authentication**: None required

**Request Body**:
```json
{
  "email": "user@example.com",
  "password": "SecurePass123!",
  "name": "John Doe"
}
```

**Request Schema**: Uses `SignupRequest` from `schemas/auth.py`

**Field Validation**:
- `email`: Valid email format (EmailStr)
- `password`: Minimum 8 characters
- `name`: Non-empty string

**Success Response (200)**:
```json
{
  "message": "Signup successful. Please check your email to verify your account.",
  "user_id": "760602fe-b19f-472a-b65e-060f9e195529",
  "email": "user@example.com"
}
```

**Error Responses**:
- `400 Bad Request`: Email already registered
- `422 Unprocessable Entity`: Validation errors

---

## 2. POST /auth/login

**Purpose**: Authenticate user and receive access tokens

**Authentication**: None required

**Request Body**:
```json
{
  "email": "user@example.com",
  "password": "SecurePass123!"
}
```

**Request Schema**: Uses `LoginRequest` from `schemas/auth.py`

**Success Response (200)**:
```json
{
  "message": "Login successful",
  "user_id": "760602fe-b19f-472a-b65e-060f9e195529",
  "email": "user@example.com",
  "access_token": "eyJhbGc...",
  "refresh_token": "eyJhbGc..."
}
```

**Error Responses**:
- `401 Unauthorized`: Invalid credentials
- `403 Forbidden`: Email not verified
- `422 Unprocessable Entity`: Validation errors

---

## 3. POST /auth/logout

**Purpose**: End user session and invalidate tokens

**Authentication**: Required (Bearer token)

**Response Model**: `AuthMessageResponse`

**Request Body**: None (or optional token in body)

**Success Response (200)**:
```json
{
  "message": "Logout successful"
}
```

**Error Responses**:
- `401 Unauthorized`: No valid token provided

---

## 4. GET /auth/me

**Purpose**: Get current authenticated user's profile and quota information

**Authentication**: Required (Bearer token)

**Response Model**: `UserInfoResponse`

**Success Response (200)**:
```json
{
  "user_id": "760602fe-b19f-472a-b65e-060f9e195529",
  "email": "user@example.com",
  "display_name": "John Doe",
  "account_tier": "free",
  "role": "user",
  "current_quiz_count": 3,
  "quizzes_attempted": 5,
  "quota_limit": 5,
  "quota_exceeded": false,
  "created_at": "2025-10-15T10:30:00Z"
}
```

**Response Fields**:
- `user_id` (string): User's UUID
- `email` (string): User's email address
- `display_name` (string, optional): User's display name
- `account_tier` (enum): `"free"`, `"basic"`, or `"educator"`
- `role` (enum): `"user"`, `"admin"`, or `"moderator"`
- `current_quiz_count` (int): Number of quizzes created
- `quizzes_attempted` (int): Number of quizzes attempted (submission count)
- `quota_limit` (int): Maximum quizzes allowed for tier
- `quota_exceeded` (boolean): Whether user has hit quota
- `created_at` (string, optional): Account creation timestamp

**Error Responses**:
- `401 Unauthorized`: Invalid or expired token
- `500 Internal Server Error`: Database error

---

## 5. PATCH /auth/change-password

**Purpose**: Change user's password (user must be authenticated)

**Authentication**: Required (Bearer token)

**Response Model**: `AuthMessageResponse`

**Request Body**:
```json
{
  "new_password": "NewSecurePass456!"
}
```

**Request Schema**: Uses `ChangePasswordRequest` from `schemas/auth.py`

**Field Validation**:
- `new_password`: Minimum 8 characters

**Success Response (200)**:
```json
{
  "message": "Password changed successfully"
}
```

**Error Responses**:
- `401 Unauthorized`: Invalid token
- `422 Unprocessable Entity`: Password validation failed

---

## 6. PATCH /auth/update-email

**Purpose**: Update user's email address (requires re-verification)

**Authentication**: Required (Bearer token)

**Response Model**: `AuthMessageResponse`

**Request Body**:
```json
{
  "new_email": "newemail@example.com"
}
```

**Request Schema**: Uses `UpdateEmailRequest` from `schemas/auth.py`

**Success Response (200)**:
```json
{
  "message": "Email update initiated. Please check your new email to confirm."
}
```

**Error Responses**:
- `401 Unauthorized`: Invalid token
- `400 Bad Request`: Email already in use
- `422 Unprocessable Entity`: Invalid email format

---

## 7. DELETE /auth/delete-account

**Purpose**: Permanently delete user account and all associated data

**Authentication**: Required (Bearer token)

**Response Model**: `AuthMessageResponse`

**Request Body**: None

**Success Response (200)**:
```json
{
  "message": "Account deleted successfully"
}
```

**Error Responses**:
- `401 Unauthorized`: Invalid token
- `500 Internal Server Error`: Deletion failed

**Side Effects**:
- User record removed from `auth.users`
- Profile removed from `public.profiles`
- All quizzes, submissions, and files remain (orphaned)

---

## 8. POST /auth/forgot-password

**Purpose**: Request password reset email

**Authentication**: None required

**Response Model**: `AuthMessageResponse`

**Request Body**:
```json
{
  "email": "user@example.com"
}
```

**Request Schema**: Uses `ForgotPasswordRequest` from `schemas/auth.py`

**Success Response (200)** (always returns success to prevent email enumeration):
```json
{
  "message": "If an account exists with this email, a password reset link has been sent."
}
```

**Note**: Always returns 200 even if email doesn't exist (security feature)

---

## 9. POST /auth/reset-password

**Purpose**: Reset password using token from recovery email

**Authentication**: None required (uses recovery token)

**Response Model**: `Dict[str, Any]`

**Request Body**:
```json
{
  "token": "eyJhbGc...",
  "refresh_token": "eyJhbGc...",
  "new_password": "NewPassword123!"
}
```

**Request Schema**: Uses `ResetPasswordRequest` from `schemas/auth.py`

**Field Validation**:
- `token`: Required recovery access token
- `refresh_token`: Optional refresh token
- `new_password`: Minimum 8 characters

**Success Response (200)**:
```json
{
  "message": "Password reset successful",
  "access_token": "eyJhbGc...",
  "refresh_token": "eyJhbGc..."
}
```

**Error Responses**:
- `400 Bad Request`: Invalid or expired token
- `422 Unprocessable Entity`: Password validation failed

---

## 10. GET /auth/confirm

**Purpose**: Confirm email address (called from email link)

**Authentication**: None required (uses confirmation token)

**Query Parameters**:
- `token` (required): Email confirmation token from Supabase
- `type` (optional): Confirmation type (`signup`, `email_change`, `recovery`)

**Success Response**: HTML redirect to frontend success page

**Error Response**: HTML redirect to frontend error page

**Note**: This endpoint is designed to be called from email links, not programmatically

---

## 11. POST /auth/resend-verification

**Purpose**: Resend email verification link

**Authentication**: None required

**Response Model**: `Dict[str, Any]`

**Request Body**:
```json
{
  "email": "user@example.com"
}
```

**Request Schema**: Uses `ResendVerificationRequest` from `schemas/auth.py`

**Success Response (200)** (always returns success to prevent email enumeration):
```json
{
  "message": "If an account exists with this email, a verification link has been sent."
}
```

---

## Response Schemas Reference

### AuthMessageResponse
```python
class AuthMessageResponse(BaseModel):
    message: str
```

### UserInfoResponse
```python
class UserInfoResponse(BaseModel):
    user_id: str
    email: str
    display_name: Optional[str]
    account_tier: Literal["free", "basic", "educator"]
    role: Literal["user", "admin", "moderator"]
    current_quiz_count: int
    quizzes_attempted: int
    quota_limit: int
    quota_exceeded: bool
    created_at: Optional[str]
```

---

## Security Features

### Email Enumeration Prevention
- `forgot-password` always returns success
- `resend-verification` always returns success
- Never reveals if email exists or not

### Token Management
- JWTs issued by Supabase
- Access tokens expire (configurable)
- Refresh tokens for session renewal
- Tokens invalidated on logout

### Password Requirements
- Minimum 8 characters
- Additional complexity enforced by Supabase (configurable)

### Email Verification
- Required before full account access
- Automatic email sent on signup
- Resend capability provided

---

## Common Error Patterns

### 401 Unauthorized
```json
{
  "detail": "Not authenticated"
}
```
**Cause**: Missing, invalid, or expired Bearer token

### 422 Unprocessable Entity
```json
{
  "detail": [
    {
      "loc": ["body", "password"],
      "msg": "ensure this value has at least 8 characters",
      "type": "value_error.any_str.min_length"
    }
  ]
}
```
**Cause**: Pydantic validation failed

### 500 Internal Server Error
```json
{
  "detail": "Internal server error message"
}
```
**Cause**: Database error, Supabase error, or unexpected exception

---

## Usage Examples

### Complete User Journey

1. **Signup**:
```bash
curl -X POST /auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "Pass123!", "name": "John"}'
```

2. **Verify Email** (click link in email)

3. **Login**:
```bash
curl -X POST /auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "Pass123!"}'
# → Returns access_token
```

4. **Get Profile**:
```bash
curl -X GET /auth/me \
  -H "Authorization: Bearer {access_token}"
```

5. **Change Password**:
```bash
curl -X PATCH /auth/change-password \
  -H "Authorization: Bearer {access_token}" \
  -H "Content-Type: application/json" \
  -d '{"new_password": "NewPass456!"}'
```

---

## Implementation Notes

- All auth operations use Supabase Auth backend
- User profiles stored in `public.profiles` table
- Email verification required for account activation
- Row-Level Security (RLS) enforces data access control
- Tier quotas managed via `user_tier_info` view

---

## Future Enhancements

- [ ] OAuth integration (Google, GitHub)
- [ ] Two-factor authentication (2FA)
- [ ] Session management dashboard
- [ ] Account recovery options
- [ ] Password strength meter

---

**Contract Status**: ✅ Complete  
**Security Audit**: ✅ Passed  
**Production Ready**: ✅ Yes
