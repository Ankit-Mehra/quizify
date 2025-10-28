# API Contract Documentation - Complete Index

**Last Updated**: 2025-10-28  
**Status**: ✅ All Contracts Complete and Accurate

---

## Overview

This document provides an index of all implemented API endpoints with links to their detailed contracts. All contracts have been verified against actual implementation and include accurate response_model information.

---

## Contract Categories

### 1. Authentication & User Management (11 endpoints)
**File**: `IMPLEMENTED_auth-endpoints.md`

| Endpoint | Method | Response Model | Description |
|----------|--------|----------------|-------------|
| `/auth/signup` | POST | `Dict[str, Any]` | Register new user |
| `/auth/login` | POST | `Dict[str, Any]` | Authenticate user |
| `/auth/logout` | POST | `AuthMessageResponse` | End session |
| `/auth/me` | GET | `UserInfoResponse` | Get user profile |
| `/auth/change-password` | PATCH | `AuthMessageResponse` | Update password |
| `/auth/update-email` | PATCH | `AuthMessageResponse` | Update email |
| `/auth/delete-account` | DELETE | `AuthMessageResponse` | Delete account |
| `/auth/forgot-password` | POST | `AuthMessageResponse` | Request reset |
| `/auth/reset-password` | POST | `Dict[str, Any]` | Reset password |
| `/auth/confirm` | GET | HTML Redirect | Confirm email |
| `/auth/resend-verification` | POST | `Dict[str, Any]` | Resend email |

### 2. Quiz Generation (4 endpoints)

#### Text-Based Generation
**File**: `IMPLEMENTED_generate-quiz-from-text.md`
- `POST /quiz/generate/text`
- Response: `QuizGenerationResponse`
- Quota: Free (5), Basic (20), Educator (500)

#### File-Based Generation
**File**: `IMPLEMENTED_generate-quiz-from-file.md`
- `POST /quiz/generate/file`
- Response: `QuizGenerationResponse`
- Accepts: PDF, DOCX (10MB max)

#### URL-Based Generation
**File**: `IMPLEMENTED_generate-quiz-from-url.md`
- `POST /quiz/generate/url`
- Response: `QuizGenerationResponse`
- Features: SSRF protection, browser slots (3 concurrent), HTML & PDF support

#### File ID Generation
**File**: `IMPLEMENTED_generate-quiz-from-file.md` (documented as variant)
- `POST /quiz/generate/{file_id}`
- Response: `QuizGenerationResponse`
- Uses previously uploaded file

### 3. Quiz Management (4 endpoints)

#### List User Quizzes
**File**: `IMPLEMENTED_get-my-quizzes.md`
- `GET /quiz/my-quizzes`
- Response: `List[MyQuizzesResponse]`
- Includes: question count, attempt count

#### Get Quiz by ID
**File**: `IMPLEMENTED_get-quiz-by-id.md`
- `GET /quiz/{quiz_id}`
- Response: `QuizzesResponse`
- Returns: Full quiz with all questions

#### Get Quiz Metadata
**File**: `IMPLEMENTED_get-quiz-metadata.md`
- `GET /quiz/metadata`
- Response: `List[QuizMetadata]`
- Returns: Content source tracking (text/file/url)

#### Delete Quiz
**File**: `IMPLEMENTED_delete-quiz.md`
- `DELETE /quiz/{quiz_id}`
- Response: `DeleteQuizResponse`
- Cascades: Deletes all submissions

### 4. Quiz Submissions (4 endpoints)

#### Submit Quiz Answers
**File**: `IMPLEMENTED_submit-quiz.md`
- `POST /quiz/{quiz_id}/submit`
- Response: `SubmissionResponse`
- Returns: Score, detailed results

#### Get Submission by ID
**File**: `IMPLEMENTED_get-submission.md`
- `GET /submission/{submission_id}`
- Response: `QuizSubmission`
- Returns: Submission summary (no detailed answers)

#### List User Submissions
**File**: `IMPLEMENTED_list-user-submissions.md`
- `GET /submissions`
- Response: `UserSubmissionsResponse`
- Returns: All submissions by user

#### List Quiz Submissions
**File**: `IMPLEMENTED_list-quiz-submissions.md`
- `GET /quiz/{quiz_id}/submissions`
- Response: `QuizSubmissionsResponse`
- Returns: All submissions for specific quiz

### 5. Admin User Management (4 endpoints)
**File**: `IMPLEMENTED_admin-endpoints.md`

| Endpoint | Method | Response Model | Description |
|----------|--------|----------------|-------------|
| `/admin/users` | GET | `List[UserWithTier]` | List all users |
| `/admin/users/{user_id}` | GET | `UserWithTier` | Get user details |
| `/admin/users/{user_id}/tier` | PUT | `AdminUpdateResponse` | Update tier |
| `/admin/users/{user_id}/role` | PUT | `AdminUpdateResponse` | Update role |

**Features**: RBAC enforcement, self-protection (admin can't change own role)

### 6. File Management (4 endpoints)
**File**: `IMPLEMENTED_file-endpoints.md`

| Endpoint | Method | Response Model | Description |
|----------|--------|----------------|-------------|
| `/files/upload` | POST | `FileUploadResponse` | Upload PDF/DOCX |
| `/files/metadata` | GET | `List[FileMetadataResponse]` | List user files |
| `/files/{file_id}` | GET | Binary Stream | Download file |
| `/files/{file_id}` | DELETE | `FileDeleteResponse` | Delete file |

**Limits**: 10MB max, PDF/DOCX only

---

## Response Schema Summary

### Authentication Schemas (schemas/auth.py)
- `AuthMessageResponse`: Simple message response
- `UserInfoResponse`: User profile with tier and quota info
- `AuthSuccessResponse`: Login/signup success with tokens
- `AdminUpdateResponse`: Admin action confirmation

### Quiz Schemas (schemas/quiz.py)
- `QuizGenerationResponse`: Quiz creation result
- `QuizzesResponse`: Full quiz with questions
- `MyQuizzesResponse`: Quiz list item with counts
- `QuizMetadata`: Content source tracking
- `DeleteQuizResponse`: Deletion confirmation

### Submission Schemas (schemas/submission.py)
- `SubmissionResponse`: Quiz grading results
- `QuizSubmission`: Submission summary
- `UserSubmissionsResponse`: User's submission list
- `QuizSubmissionsResponse`: Quiz's submission list

### User Schemas (schemas/user.py)
- `UserWithTier`: User profile with tier info
- `UserTierUpdate`: Tier change request
- `RoleUpdate`: Role change request

### File Schemas (schemas/files.py)
- `FileUploadResponse`: File upload result
- `FileMetadataResponse`: File list item
- `FileDeleteResponse`: File deletion confirmation

---

## Contract Verification Status

### ✅ Verified (All 31 endpoints)

**Authentication**: All 11 endpoints verified
**Quiz Generation**: All 4 endpoints verified
**Quiz Management**: All 4 endpoints verified
**Submissions**: All 4 endpoints verified
**Admin**: All 4 endpoints verified
**Files**: All 4 endpoints verified

### Verification Criteria
- ✅ Response model names match route definitions
- ✅ Request/response examples match actual schemas
- ✅ Error codes documented match handler behavior
- ✅ Security features documented (RLS, RBAC, SSRF)
- ✅ Implementation details accurate
- ✅ Use cases and examples provided

---

## Architecture Notes

### Authentication
- **Provider**: Supabase Auth
- **Token Type**: JWT Bearer tokens
- **Email Verification**: Required for account activation
- **Security**: Email enumeration prevention

### Database
- **Provider**: Supabase (PostgreSQL)
- **Security**: Row-Level Security (RLS) on all user data
- **Access**: Authenticated client for RLS, service role for admin

### AI Services
- **Provider**: OpenAI GPT-4
- **Purpose**: Quiz question generation
- **Input**: Text, PDF/DOCX content, or scraped web content

### Web Scraping
- **Tool**: Playwright (headless Chrome)
- **Security**: SSRF protection, DNS rebinding prevention
- **Concurrency**: 3 browser slots per user (in-memory)

### File Storage
- **Provider**: Supabase Storage
- **Structure**: `user_files/{user_id}/{file_id}.{ext}`
- **Limits**: 10MB max, PDF/DOCX only

---

## Common Response Patterns

### Success (200/201)
```json
{
  "message": "Success message",
  "data": { /* response model */ }
}
```

### Authentication Error (401)
```json
{
  "detail": "Not authenticated"
}
```

### Authorization Error (403)
```json
{
  "detail": "You do not have permission to perform this action"
}
```

### Not Found (404)
```json
{
  "detail": "Resource not found"
}
```

### Validation Error (422)
```json
{
  "detail": [
    {
      "loc": ["body", "field_name"],
      "msg": "error message",
      "type": "error_type"
    }
  ]
}
```

---

## Security Features

### Row-Level Security (RLS)
- Enforced on: quizzes, submissions, user_files, profiles
- Ensures: Users can only access their own data
- Implementation: Supabase policies with authenticated client

### Role-Based Access Control (RBAC)
- Roles: user, admin, moderator
- Admin endpoints: Require `role = 'admin'`
- Self-protection: Admins can't change own role

### SSRF Protection
- URL validation: Blocks private IP ranges
- DNS rebinding prevention: Re-validates hostname
- Allowlist: Only HTTP/HTTPS schemes

### Rate Limiting
- Browser slots: 3 concurrent per user
- Quota limits: Based on account tier
- Validation: Checked before expensive operations

---

## Testing Coverage

### Contract Tests
- Request/response schema validation
- Error response verification
- Authentication/authorization checks
- RLS policy enforcement

### Integration Tests
- End-to-end quiz generation flows
- Submission and grading accuracy
- File upload and retrieval
- Admin user management

### Security Tests
- SSRF attack prevention
- RLS bypass attempts
- RBAC enforcement
- Token validation

---

## Future Contract Updates

### Planned Endpoints
- [ ] `POST /auth/oauth/{provider}` - OAuth integration
- [ ] `GET /quiz/search` - Quiz search functionality
- [ ] `PUT /quiz/{quiz_id}` - Quiz editing
- [ ] `POST /admin/users/{user_id}/suspend` - User suspension
- [ ] `GET /stats/dashboard` - User analytics

### Enhancement Areas
- Pagination for list endpoints
- Filtering and search capabilities
- Bulk operations (batch delete, batch update)
- Webhook notifications
- Rate limiting headers

---

## Migration from Spec to Implementation

### Original Spec Files (Not Updated)
Located in `specs/001-comprehensive-quiz-generation/contracts/`:
- `generate-quiz-from-url.md` (original spec)
- `generate-quiz-quota.md` (quota design spec)
- `file-upload-validation.md` (validation spec)
- `search-quizzes.md` (future feature spec)
- `upgrade-tier.md` (future feature spec)

### Implemented Contracts (Current Truth)
All files prefixed with `IMPLEMENTED_` reflect actual implementation and should be used as source of truth.

---

## Document Maintenance

### Update Triggers
- API endpoint changes
- Response model schema changes
- Error handling modifications
- Security policy updates
- New endpoint additions

### Update Process
1. Modify implementation (code)
2. Test changes thoroughly
3. Update corresponding IMPLEMENTED_*.md contract
4. Update this index if needed
5. Run contract verification tests

### Verification Commands
```bash
# Run API contract tests
pytest tests/contract/

# Verify response models match routes
ruff check api/*.py

# Check schema consistency
pytest tests/test_schemas.py
```

---

**Documentation Status**: ✅ Complete  
**Last Full Audit**: 2025-10-28  
**Next Review**: 2025-11-28  
**Maintained By**: Development Team
