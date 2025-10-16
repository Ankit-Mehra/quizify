# GitHub Issues for Quizify API

**Generated**: October 12, 2025  
**Branch**: `test/quiz-generation-and-taking-endpoints`  
**Status**: Updated after implementation review

---

## 📋 Overview

This document tracks feature development issues for the Quizify API. Issues are organized by priority and include detailed specifications for implementation.

**Current Status**:
- ✅ **3 issues COMPLETED** (Quota enforcement, Admin tier management, Web URL scraping)
- 🟡 **1 issue PENDING** (Search/filter)
- 🟢 **1 issue PENDING** (File size validation)

**Total Remaining Effort**: 3-5 hours

---

## ✅ COMPLETED FEATURES

### Issue #1: Quiz Quota Enforcement ✅

**Status**: COMPLETED (October 2025)

**What was implemented**:
- Created `validate_user_quota()` function in `handlers/quiz_handlers.py` (lines 26-64)
- Integrated quota validation into all 3 quiz generation endpoints:
  - `generate_quiz_from_text()` - line 272
  - `generate_quiz_from_file_openai()` - line 81
  - `generate_quiz_from_fileid()` - line 209
- Returns 403 with detailed error format when quota exceeded
- 13 integration tests passing in `tests/test_quota_integration.py`
- Quota checked BEFORE AI generation to prevent wasted API calls

**Implementation location**: `handlers/quiz_handlers.py`

---

### Issue #2: Admin Tier Management ✅

**Status**: COMPLETED (October 2025)

**What was implemented**:
- Admin endpoint: `PUT /admin/users/{user_id}/tier`
- Handler: `update_user_tier()` in `handlers/admin_handlers.py` (lines 202-280)
- Admins can manually upgrade users between free/basic/educator tiers
- 30 admin tests passing in `tests/test_admin_api.py`
- RBAC role management also implemented

**Note**: Self-service Stripe payment upgrade is planned for v1.1 (not blocking for MVP)

**Implementation location**: `api/admin_routes.py`, `handlers/admin_handlers.py`

---

### Issue #4: Quiz Generation from Web URL ✅

**Status**: COMPLETED (October 2025)

**What was implemented**:
- Web scraping service with SSRF protection: `services/web_scraping_service.py` (182 lines)
- Handler with tier and quota checking: `handlers/quiz_handlers.py` lines 412-489
- API endpoint: `POST /api/quiz/generate/url` (status 201)
- **SSRF Protection**: Blocks localhost, private IPs (10.x, 192.168.x, 172.16-31.x, 169.254.x)
- **Tier Enforcement**: Free tier users get 403 with upgrade message
- **Web Scraping**: Playwright + Trafilatura with 30-second timeout
- **Content Validation**: Min 100 chars, max 500KB with auto-truncation
- **26 tests passing**:
  - 19 unit tests in `tests/test_web_scraping_service.py` (URL validation, SSRF, content handling)
  - 7 integration tests in `tests/test_url_quiz_generation.py` (tier/quota enforcement, error scenarios)
- Database storage with `content_source_type='url'` and `content_source_reference`
- Playwright browser binaries installed (Chromium 120.0.6099.28)

**Implementation location**: `services/web_scraping_service.py`, `handlers/quiz_handlers.py`, `api/quiz_routes.py`


---

## 🟡 MEDIUM PRIORITY

### Issue #3: Add Search and Filter to Quiz Listing

**Title**: Implement query parameters for quiz search and filtering

**Labels**: `priority: medium`, `type: enhancement`, `area: backend`, `ux-improvement`

---

#### Description

The `GET /api/quiz/my-quizzes` endpoint currently returns ALL user quizzes without any filtering capability. This creates poor UX for users with many quizzes and forces all filtering to be done client-side, leading to performance issues.

---

#### Problem Statement

**Current behavior**:
- Endpoint returns all quizzes for a user without pagination or filtering
- No way to search quizzes by title
- No way to filter by date range
- Users with 100+ quizzes face performance issues
- All filtering must be done client-side (inefficient)

**Impact**:
- Poor user experience for active users
- Unnecessary data transfer
- Slow client-side rendering with large datasets

---

#### Requirements

**1. Add Optional Query Parameters**:
- `title` (string, optional): Case-insensitive partial match
- `start_date` (ISO 8601 date, optional): Filter quizzes created on or after this date
- `end_date` (ISO 8601 date, optional): Filter quizzes created on or before this date

**2. Example Usage**:
```bash
# Search by title
GET /api/quiz/my-quizzes?title=python

# Filter by date range
GET /api/quiz/my-quizzes?start_date=2025-10-01&end_date=2025-10-31

# Combined filters
GET /api/quiz/my-quizzes?title=machine&start_date=2025-10-01
```

**3. Validation Rules**:
- `start_date` must be <= `end_date` (return 400 if violated)
- Dates must be valid ISO 8601 format (YYYY-MM-DD)
- Empty/missing parameters return all quizzes (backward compatible)
- Invalid date format returns 400 with clear error message

**4. Response Format** (unchanged):
```json
[
  {
    "id": "uuid",
    "title": "Python Basics Quiz",
    "created_at": "2025-10-12T10:30:00Z",
    "question_count": 10,
    "content_source_type": "text"
  }
]
```

---

#### Implementation Steps

**Step 1**: Update handler signature
```python
# File: handlers/quiz_handlers.py
from datetime import date
from typing import Optional

async def get_user_quizzes_handler(
    current_user_id: str = Depends(get_current_user_id),
    title: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
):
    # Validate date range
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date must be less than or equal to end_date"
        )
    
    # Call updated service function
    quizzes = get_user_quizzes(
        current_user_id, 
        title=title,
        start_date=start_date,
        end_date=end_date
    )
    return quizzes
```

**Step 2**: Update database service
```python
# File: services/db_services/supabase_quiz.py

def get_user_quizzes(
    user_id: str,
    title: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
) -> List[Dict]:
    query = supabase.table("quizzes").select("*").eq("created_by", user_id)
    
    # Apply filters conditionally
    if title:
        query = query.ilike("title", f"%{title}%")
    
    if start_date:
        query = query.gte("created_at", start_date.isoformat())
    
    if end_date:
        # Make end_date inclusive (end of day)
        end_datetime = datetime.combine(end_date, time.max)
        query = query.lte("created_at", end_datetime.isoformat())
    
    result = query.order("created_at", desc=True).execute()
    return result.data
```

**Step 3**: Update route (no changes needed - FastAPI auto-parses query params)

**Step 4**: Add database indexes for performance
```sql
-- Migration file: migrations/002_add_quiz_search_indexes.sql

-- Index for case-insensitive title search
CREATE INDEX IF NOT EXISTS idx_quizzes_title_lower 
ON quizzes (LOWER(title));

-- Composite index for filtered queries
CREATE INDEX IF NOT EXISTS idx_quizzes_user_created 
ON quizzes (created_by, created_at DESC);
```

---

#### Error Responses

| Status Code | Condition | Response Body |
|-------------|-----------|---------------|
| 400 | `start_date` > `end_date` | `{"detail": "start_date must be less than or equal to end_date"}` |
| 400 | Invalid date format | `{"detail": "Invalid date format. Use YYYY-MM-DD"}` |
| 401 | Missing/invalid auth token | `{"detail": "Authentication required"}` |

---

#### Security Considerations

- ✅ **No SQL injection risk**: Using Supabase query builder with parameterized queries
- ✅ **Authorization**: User can only filter their own quizzes (enforced by `created_by` filter)
- ✅ **Input validation**: FastAPI/Pydantic validates date formats automatically
- ✅ **Performance**: Indexes prevent slow queries on large datasets

---

#### Development Workflow

```bash
# 1. Create feature branch
git checkout test/quiz-generation-and-taking-endpoints
git pull origin test/quiz-generation-and-taking-endpoints
git checkout -b feature/quiz-search-filter

# 2. Implement changes
# - Update handlers/quiz_handlers.py
# - Update services/db_services/supabase_quiz.py
# - Create migration file for indexes

# 3. Write tests
# - Create tests/test_quiz_search.py
# - Test title search (exact, partial, case-insensitive)
# - Test date filters (start, end, combined)
# - Test validation errors (invalid dates, start > end)

# 4. Run tests
pytest tests/test_quiz_search.py -v

# 5. Ensure all existing tests pass
pytest

# 6. Create PR to test/quiz-generation-and-taking-endpoints
```

---

#### Acceptance Criteria

**Functional Requirements**:
- [ ] Can search quizzes by title (case-insensitive, partial match)
- [ ] Can filter quizzes by start_date (inclusive)
- [ ] Can filter quizzes by end_date (inclusive)
- [ ] Can combine multiple filters (title + dates)
- [ ] Empty filters return all quizzes (backward compatible)
- [ ] Returns 400 if start_date > end_date with clear error message
- [ ] Returns 400 for invalid date formats

**Test Coverage**:
- [ ] Unit tests for date validation logic
- [ ] Integration tests for title search (exact, partial, case variations)
- [ ] Integration tests for date filters (start only, end only, both)
- [ ] Integration tests for combined filters
- [ ] Tests for error cases (invalid dates, reversed date range)
- [ ] All existing 43 tests still pass

**Performance**:
- [ ] Database indexes created for efficient queries
- [ ] Query execution time < 100ms for datasets with 1000+ quizzes

**Documentation**:
- [ ] API endpoint documentation updated (if using OpenAPI/Swagger)
- [ ] Contract documentation updated in specs folder

---

#### Related Files

**Files to modify**:
- `handlers/quiz_handlers.py` - Update `get_user_quizzes_handler()` signature
- `services/db_services/supabase_quiz.py` - Update `get_user_quizzes()` with filters
- `api/quiz_routes.py` - No changes needed (query params auto-parsed)

**Files to create**:
- `tests/test_quiz_search.py` - New test file
- `migrations/002_add_quiz_search_indexes.sql` - Database indexes

---

#### Contract Reference

`specs/001-comprehensive-quiz-generation/contracts/search-quizzes.md`

---

#### Estimated Effort

**2-3 hours** (breakdown):
- Handler updates: 30 minutes
- Service layer updates: 45 minutes
- Database migration: 15 minutes
- Test writing: 60 minutes
- Testing and debugging: 30 minutes

---

## 🟢 LOW PRIORITY

### Issue #5: Add File Size Limit to File Upload

**Title**: Enforce 10MB file size limit on quiz generation from files

**Labels**: `priority: low`, `type: bug`, `area: backend`, `security`

**Description**:

The file upload endpoint currently has no file size limit, allowing users to upload arbitrarily large files that could crash the server or cause memory issues.

**Problem**:
- No maximum file size enforced
- Could accept multi-GB files
- Could cause OOM errors during text extraction
- Could be used for DoS attacks

**Requirements**:
1. Add file size validation BEFORE processing
2. Maximum size: 10MB (10,485,760 bytes)
3. Return 413 Payload Too Large if exceeded
4. Save `file_size_bytes` to database metadata

**Implementation**:
```python
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

async def generate_quiz_from_file_openai(...):
    file_bytes = await file.read()
    
    # Validate size
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is 10MB."
        )
    
    # ... rest of handler
```

**Also Save to Metadata**:
```python
metadata = {
    # ... existing fields
    "file_size_bytes": len(file_bytes),  # ADD THIS
}
```

**Development Workflow**:
1. Create feature branch from `test/quiz-generation-and-taking-endpoints`:
   ```bash
   git checkout test/quiz-generation-and-taking-endpoints
   git pull origin test/quiz-generation-and-taking-endpoints
   git checkout -b feature/file-size-validation
   ```
2. Implement the feature
3. Write tests (see acceptance criteria below)
4. Ensure all tests pass
5. Create PR to `test/quiz-generation-and-taking-endpoints` branch


### Issue #5: File Size Validation for Upload

**Title**: Enforce 10MB file size limit on quiz generation from file uploads

**Labels**: `priority: low`, `type: security`, `area: backend`, `dos-prevention`

---

#### Description

Add file size validation to the file upload endpoint to prevent users from uploading arbitrarily large files that could crash the server, cause out-of-memory errors, or be used for denial-of-service attacks.

---

#### Problem Statement

**Current behavior**:
- No maximum file size enforced on `POST /api/quiz/generate/file`
- Server could accept multi-GB files
- Could cause out-of-memory (OOM) errors during PDF/DOCX text extraction
- Could be exploited for DoS attacks
- No file size metadata saved to database

**Security risk**: **Medium** - Could be used to exhaust server resources

---

#### Requirements

**1. File Size Validation**:
- Maximum file size: **10MB** (10,485,760 bytes)
- Validation must happen BEFORE file processing
- Return HTTP 413 (Payload Too Large) if exceeded

**2. Metadata Storage**:
- Save `file_size_bytes` to quiz metadata
- Include in existing metadata dict

**3. Error Response**:
```json
{
  "detail": "File too large. Maximum file size is 10MB (10485760 bytes). Your file is 15728640 bytes."
}
```

---

#### Implementation Steps

**Step 1**: Add validation constant and check in handler

```python
# File: handlers/quiz_handlers.py

# Add constant at top of file
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB = 10,485,760 bytes

async def generate_quiz_from_file_openai(
    file: UploadFile = File(...),
    title: str = Form(...),
    num_questions: int = Form(10),
    question_type: List[str] = Form(["mixed"]),
    current_user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token)
):
    # Existing content type check...
    if file.content_type not in ["application/pdf", "text/plain", ...]:
        raise HTTPException(status_code=400, detail="...")
    
    # Validate quota...
    validate_user_quota(current_user_id)
    
    try:
        # Read file
        file_bytes = await file.read()
        file_size = len(file_bytes)
        
        # ADD THIS: Validate file size
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum file size is 10MB ({MAX_FILE_SIZE} bytes). Your file is {file_size} bytes."
            )
        
        # Extract text (existing code)
        if file.content_type == "application/pdf":
            parsed_text = extract_text_from_pdf(file_bytes)
        # ... rest of extraction logic
        
        # ... generate quiz ...
        
        # MODIFY THIS: Add file_size_bytes to metadata
        metadata = {
            "quiz_id": quiz_id,
            "content_type": "file",
            "file_name": file.filename,
            "file_type": file.content_type,
            "file_size_bytes": file_size,  # ADD THIS LINE
            "word_count": len(parsed_text.split()),
            "created_by": current_user_id,
            "created_at": datetime.now().isoformat(),
            "question_count": num_questions
        }
        save_metadata(metadata)
        
        # ... rest of handler
```

**Step 2**: No database schema changes needed (metadata is JSON)

**Step 3**: Write tests

```python
# File: tests/test_file_upload_validation.py

import pytest
from fastapi import UploadFile
from io import BytesIO

def test_file_size_validation_under_limit():
    """Files under 10MB should be accepted."""
    # Create 9MB file
    file_content = b"x" * (9 * 1024 * 1024)
    # Test passes

def test_file_size_validation_at_limit():
    """Files exactly 10MB should be accepted."""
    # Create 10MB file
    file_content = b"x" * (10 * 1024 * 1024)
    # Test passes

def test_file_size_validation_over_limit():
    """Files over 10MB should be rejected with 413."""
    # Create 11MB file
    file_content = b"x" * (11 * 1024 * 1024)
    # Test expects 413 response

def test_file_size_metadata_saved():
    """File size should be saved in metadata."""
    # Upload 5MB file
    # Check metadata includes "file_size_bytes": 5242880
```

---

#### Error Responses

| Status Code | Condition | Response Body |
|-------------|-----------|---------------|
| 413 | File > 10MB | `{"detail": "File too large. Maximum file size is 10MB (10485760 bytes). Your file is {size} bytes."}` |
| 400 | Unsupported file type | `{"detail": "Only PDF, DOCX, or TXT files are supported."}` (existing) |
| 403 | Quota exceeded | `{"detail": "Quiz quota exceeded..."}` (existing) |

---

#### Security Considerations

🛡️ **DoS Prevention**:
- ✅ Hard limit prevents memory exhaustion
- ✅ Early validation before expensive text extraction
- ✅ Clear error message helps legitimate users

📊 **Metadata Tracking**:
- ✅ File size stored for auditing
- ✅ Can identify patterns of abuse
- ✅ Future: Implement rate limiting based on total upload size

⚡ **Performance**:
- ✅ Validation is O(1) - just check byte count
- ✅ Happens before any file processing
- ✅ No additional database queries needed

---

#### Development Workflow

```bash
# 1. Create feature branch
git checkout test/quiz-generation-and-taking-endpoints
git pull origin test/quiz-generation-and-taking-endpoints
git checkout -b feature/file-size-validation

# 2. Implement changes
# - Add MAX_FILE_SIZE constant
# - Add size validation check
# - Update metadata dict

# 3. Write tests
# - Create tests/test_file_upload_validation.py
# - Test boundary conditions (9MB, 10MB, 11MB)
# - Test metadata includes file_size_bytes

# 4. Run new tests
pytest tests/test_file_upload_validation.py -v

# 5. Ensure all existing tests still pass
pytest

# 6. Create PR to test/quiz-generation-and-taking-endpoints
```

---

#### Acceptance Criteria

**Functional Requirements**:
- [ ] Files larger than 10MB return 413 Payload Too Large
- [ ] Error message specifies the 10MB limit and actual file size
- [ ] Files exactly 10MB or smaller are accepted
- [ ] `file_size_bytes` field added to quiz metadata
- [ ] File size validation happens BEFORE text extraction
- [ ] All existing file upload functionality still works

**Test Coverage**:
- [ ] Unit test for file size validation logic
- [ ] Integration test with 9MB file (should pass)
- [ ] Integration test with 10MB file (should pass)
- [ ] Integration test with 11MB file (should fail with 413)
- [ ] Integration test verifies metadata includes file_size_bytes
- [ ] All existing 43 tests still pass

**Edge Cases**:
- [ ] Empty file (0 bytes) handled gracefully
- [ ] File size calculation accurate for binary files
- [ ] Works for all supported file types (PDF, DOCX, TXT)

---

#### Related Files

**Files to modify**:
- `handlers/quiz_handlers.py` - Add size validation to `generate_quiz_from_file_openai()`

**Files to create**:
- `tests/test_file_upload_validation.py` - New test file for size validation

**No schema changes needed** - Metadata is stored as JSON, already flexible

---

#### Contract Reference

`specs/001-comprehensive-quiz-generation/contracts/file-upload-validation.md`

---

#### Estimated Effort

**1-2 hours** (breakdown):
- Implementation: 30 minutes (add constant, check, metadata field)
- Test writing: 45 minutes (boundary tests, metadata verification)
- Testing and debugging: 30 minutes

---

## 📊 Issue Summary

### Statistics

**Total Issues**: 5

**Status Breakdown**:
- ✅ **Completed**: 3 issues (Quota enforcement, Admin tier management, Web URL scraping)
- 🟡 **Medium Priority**: 1 issue (Search/filter)
- 🟢 **Low Priority**: 1 issue (File size validation)

**Effort Breakdown**:
- Issue #3 (Search): 2-3 hours
- Issue #5 (File Size): 1-2 hours
- **Total Remaining**: 3-5 hours

---

### Recommended Implementation Order

**Priority 1**: Issue #5 (File Size Validation) - 1-2 hours
- **Why first**: Security fix, simple implementation, low risk
- **Value**: Protects server from resource exhaustion
- **Dependencies**: None

**Priority 2**: Issue #3 (Search/Filter) - 2-3 hours
- **Why second**: Improves UX for existing features
- **Value**: Better experience for users with many quizzes
- **Dependencies**: None

---

### Recent Changes (October 2025)

✅ **Successfully Implemented**:
- Quota enforcement with 13 passing integration tests
- Admin tier management with 30 passing tests
- **Web URL quiz generation** with 26 passing tests (19 unit + 7 integration)
- All 3 quiz generation endpoints validated for quota
- Quota checked BEFORE AI calls (cost optimization)
- SSRF protection for web scraping (blocks private IPs, localhost)
- Playwright + Trafilatura integration with 30-second timeout

📝 **Documentation Status**:
- Contract specs need updating to reflect quota implementation
- README needs revision to show actual vs. planned features
- Two Postman collections created for endpoint testing

🎯 **Next Steps**:
1. Test endpoints with Postman collections (`postman/` directory)
2. Implement remaining 2 issues (3-5 hours total)
3. Update documentation to match actual implementation
4. Consider v1.1 features (Stripe integration, advanced search)

---

### Development Notes

**Testing Strategy**:
- All new features must include unit AND integration tests
- All existing tests must continue passing
- Mock external services (OpenAI, Playwright) in tests
- Use pytest fixtures for common test setup

**Branch Strategy**:
- Base branch: `test/quiz-generation-and-taking-endpoints`
- Feature branches: `feature/<issue-name>`
- PR target: `test/quiz-generation-and-taking-endpoints`
- After testing: Merge to `development`, then `deploy/production`

**Security Checklist**:
- [x] SSRF prevention for URL scraping (Issue #4) ✅
- [ ] File size limits enforced (Issue #5)

- [ ] Quota enforcement active (✅ Done)
- [ ] Tier-based feature gating (✅ Admin done, URL needed)
- [ ] Input validation on all user inputs

---

## 📚 References

**Contract Documentation**:
- `specs/001-comprehensive-quiz-generation/contracts/`
- `specs/001-comprehensive-quiz-generation/SPECIFICATION_ANALYSIS_REPORT.md`
- `specs/001-comprehensive-quiz-generation/NEXT_STEPS.md`

**Test Files**:
- `tests/test_quota_integration.py` (13 tests ✅)
- `tests/test_admin_api.py` (30 tests ✅)

**Postman Collections**:
- `postman/Quizify_Quiz_Generation.postman_collection.json`
- `postman/Quizify_Quiz_Taking.postman_collection.json`

**Key Source Files**:
- `handlers/quiz_handlers.py` - Quiz generation handlers
- `handlers/admin_handlers.py` - Admin tier management
- `api/quiz_routes.py` - Quiz API routes
- `schemas/quiz.py` - Request/response models

---

**Document Version**: 2.0  
**Last Updated**: October 12, 2025  
**Maintained By**: Development Team

