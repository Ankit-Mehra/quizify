# GitHub Issues for Missing API Features

**Generated**: 2025-10-12  
**Branch**: test/quiz-generation-and-taking-endpoints  
**Status**: Updated after implementation review

---

## ✅ COMPLETED FEATURES

### ~~Issue #1: Implement Quiz Quota Enforcement~~ ✅ DONE

**Status**: **COMPLETED** - Implemented in handlers/quiz_handlers.py

**Implementation Details**:
- ✅ `validate_user_quota()` function created (lines 26-64)
- ✅ Queries `user_tier_info` view via `get_user_tier_info()`
- ✅ Returns 403 with detailed error format including current_count, quota_limit, user_tier
- ✅ Integrated into all 3 generation endpoints:
  - `generate_quiz_from_text()` - line 272
  - `generate_quiz_from_file_openai()` - line 81
  - `generate_quiz_from_fileid()` - line 209
- ✅ 13 integration tests passing in `tests/test_quota_integration.py`
- ✅ Quota checked BEFORE AI generation to prevent wasted API calls

**Completed**: October 2025

---

### ~~Issue #2: Admin Tier Management~~ ✅ DONE

**Status**: **COMPLETED** - Admin manual tier upgrade implemented

**Implementation Details**:
- ✅ Admin endpoint: `PUT /admin/users/{user_id}/tier` in `api/admin_routes.py`
- ✅ Handler: `update_user_tier()` in `handlers/admin_handlers.py` (lines 202-280)
- ✅ Admins can manually upgrade users to basic/educator tiers
- ✅ 30 admin tests passing in `tests/test_admin_api.py`
- ✅ RBAC role management also implemented

**Note**: Self-service Stripe upgrade is planned for v1.1 (not blocking for MVP)

**Completed**: October 2025

---

## 🟡 MEDIUM PRIORITY (Premium Features & UX)

### Issue #3: Add Search and Filter to Quiz Listing

**Title**: Add query parameters to GET /api/quiz/my-quizzes for search/filter

**Labels**: `priority: medium`, `type: enhancement`, `area: backend`, `ux`

**Description**:

The quiz listing endpoint returns ALL quizzes without any filtering capability. This creates poor UX for users with many quizzes and forces all filtering to be done client-side.

**Problem**:
- Cannot search quizzes by title
- Cannot filter by date range
- ALL quizzes loaded at once (performance issue with 100+ quizzes)
- Client-side filtering is inefficient

**Requirements**:
1. Add optional query parameters to `GET /api/quiz/my-quizzes`:
   - `title` (string, optional): Case-insensitive partial match
   - `start_date` (ISO 8601 date, optional): Created on or after
   - `end_date` (ISO 8601 date, optional): Created on or before

2. Examples:
   ```
   GET /api/quiz/my-quizzes?title=python
   GET /api/quiz/my-quizzes?start_date=2025-10-01&end_date=2025-10-31
   GET /api/quiz/my-quizzes?title=quiz&start_date=2025-10-01
   ```

3. Validation:
   - start_date must be <= end_date (return 400 if not)
   - Dates must be valid ISO 8601 format (YYYY-MM-DD)

4. Database query changes:
   - Use `.ilike('title', f'%{title}%')` for case-insensitive search
   - Use `.gte('created_at', start_date)` for start date
   - Use `.lt('created_at', end_date + 1 day)` for end date (inclusive)

**Implementation Steps**:
1. Update handler signature in `handlers/quiz_handlers.py`:
   ```python
   async def get_user_quizzes_handler(
       current_user_id: str = Depends(get_current_user_id),
       title: Optional[str] = None,
       start_date: Optional[date] = None,
       end_date: Optional[date] = None
   ):
   ```
2. Add date validation logic
3. Update `get_user_quizzes()` in `services/db_services/supabase_quiz.py` to accept filters
4. Add database query filters conditionally

**Performance Considerations**:
- Add index on `LOWER(title)` for fast case-insensitive search
- Existing index on `created_by` should help
- Add composite index on `(created_by, created_at DESC)` for date filters

**Development Workflow**:
1. Create feature branch from `test/quiz-generation-and-taking-endpoints`:
   ```bash
   git checkout test/quiz-generation-and-taking-endpoints
   git pull origin test/quiz-generation-and-taking-endpoints
   git checkout -b feature/quiz-search-filter
   ```
2. Implement the feature
3. Write tests (see acceptance criteria below)
4. Ensure all tests pass
5. Create PR to `test/quiz-generation-and-taking-endpoints` branch

**Acceptance Criteria**:
- [ ] Can search by title (case-insensitive, partial match)
- [ ] Can filter by start_date (inclusive)
- [ ] Can filter by end_date (inclusive)
- [ ] Can combine multiple filters
- [ ] Returns 400 if start_date > end_date
- [ ] Returns 400 for invalid date formats
- [ ] Empty filters return all quizzes (backward compatible)
- [ ] **Unit tests written** for filter logic and date validation
- [ ] **Integration tests written** for various query parameter combinations
- [ ] **All existing tests still pass** after implementation
- [ ] **Test coverage**: Title search, date filters, combined filters, validation errors

**Related Files**:
- `api/quiz_routes.py` (route already exists, just update)
- `handlers/quiz_handlers.py::get_user_quizzes_handler()`
- `services/db_services/supabase_quiz.py::get_user_quizzes()`
- `tests/test_quiz_search.py` (NEW)

**Contract Reference**: `specs/001-comprehensive-quiz-generation/contracts/search-quizzes.md`

**Estimated Effort**: 2-3 hours

---

### Issue #4: Implement Quiz Generation from Web URL
   {
     "target_tier": "basic" | "educator",
     "verification_token": "string"
   }
   ```
3. Validation:
   - User must be authenticated
   - target_tier must be "basic" or "educator" (not "free")
   - verification_token must be valid (MVP: admin-issued token)
   - Current tier must be "free" (no lateral moves in MVP)
4. Update `profiles.account_tier` column
5. Return response:
   ```json
   {
     "message": "Account upgraded successfully",
     "user_id": "uuid",
     "new_tier": "basic",
     "quota": 100
   }
   ```

**Error Responses**:
- 400: Invalid target_tier or already at that tier
- 401: Authentication required
- 403: Invalid verification token

**Database Schema**:
✅ Already ready - `profiles.account_tier` column exists

**Implementation Steps**:
1. Create route in `api/auth_routes.py`
2. Create handler in `handlers/auth_handlers.py`
3. Create schema in `schemas/user.py` (TierUpgradeRequest, TierUpgradeResponse)
4. Add verification token validation logic (MVP: simple string match)
5. Update `profiles` table via Supabase client

**Future Enhancements** (Out of scope for MVP):
- Payment gateway integration (Stripe)
- .edu email verification for educator tier
- Automatic tier downgrades on expiry

**Development Workflow**:
1. Create feature branch from `deploy/production`:
   ```bash
   git checkout deploy/production
   git pull origin deploy/production
   git checkout -b feature/tier-upgrade-endpoint
   ```
2. Implement the feature
3. Write tests (see acceptance criteria below)
4. Ensure all tests pass
5. Create PR to `deploy/production` branch

**Acceptance Criteria**:
- [ ] Endpoint exists and is documented in OpenAPI
- [ ] Free tier users can upgrade to basic with valid token
- [ ] Free tier users can upgrade to educator with valid token
- [ ] Invalid tokens return 403
- [ ] Already upgraded users get friendly error
- [ ] profiles.account_tier is updated in database
- [ ] Response includes new quota limits
- [ ] **Unit tests written** for tier upgrade logic
- [ ] **Integration tests written** for endpoint with various scenarios
- [ ] **All existing tests still pass** after implementation
- [ ] **Test coverage**: Token validation, database updates, error cases

**Related Files**:
- `api/auth_routes.py` (create endpoint)
- `handlers/auth_handlers.py` (create handler)
- `schemas/user.py` (add request/response models)
- `services/db_services/supabase_auth.py` (add update_user_tier function)

**Contract Reference**: `specs/001-comprehensive-quiz-generation/contracts/upgrade-tier.md`

**Estimated Effort**: 3-4 hours

---

## 🟡 MEDIUM PRIORITY (UX & Premium Features)

### Issue #3: Add Search and Filter to Quiz Listing

**Title**: Add query parameters to GET /api/quiz/my-quizzes for search/filter

**Labels**: `priority: medium`, `type: feature`, `area: backend`, `enhancement`

**Description**:

The quiz listing endpoint returns ALL quizzes without any filtering capability. This creates poor UX for users with many quizzes and forces all filtering to be done client-side.

**Problem**:
- Cannot search quizzes by title
- Cannot filter by date range
- ALL quizzes loaded at once (performance issue with 100+ quizzes)
- Client-side filtering is inefficient

**Requirements**:
1. Add optional query parameters to `GET /api/quiz/my-quizzes`:
   - `title` (string, optional): Case-insensitive partial match
   - `start_date` (ISO 8601 date, optional): Created on or after
   - `end_date` (ISO 8601 date, optional): Created on or before

2. Examples:
   ```
   GET /api/quiz/my-quizzes?title=python
   GET /api/quiz/my-quizzes?start_date=2025-10-01&end_date=2025-10-31
   GET /api/quiz/my-quizzes?title=quiz&start_date=2025-10-01
   ```

3. Validation:
   - start_date must be <= end_date (return 400 if not)
   - Dates must be valid ISO 8601 format (YYYY-MM-DD)

4. Database query changes:
   - Use `.ilike('title', f'%{title}%')` for case-insensitive search
   - Use `.gte('created_at', start_date)` for start date
   - Use `.lt('created_at', end_date + 1 day)` for end date (inclusive)

**Implementation Steps**:
1. Update handler signature in `handlers/quiz_handlers.py`:
   ```python
   async def get_user_quizzes_handler(
       current_user_id: str = Depends(get_current_user_id),
       title: Optional[str] = None,
       start_date: Optional[date] = None,
       end_date: Optional[date] = None
   ):
   ```
2. Add date validation logic
3. Update `get_user_quizzes()` in `services/db_services/supabase_quiz.py` to accept filters
4. Add database query filters conditionally

**Performance Considerations**:
- Add index on `LOWER(title)` for fast case-insensitive search
- Existing index on `created_by` should help
- Add composite index on `(created_by, created_at DESC)` for date filters

**Development Workflow**:
1. Create feature branch from `deploy/production`:
   ```bash
   git checkout deploy/production
   git pull origin deploy/production
   git checkout -b feature/quiz-search-filter
   ```
2. Implement the feature
3. Write tests (see acceptance criteria below)
4. Ensure all tests pass
5. Create PR to `deploy/production` branch

**Acceptance Criteria**:
- [ ] Can search by title (case-insensitive, partial match)
- [ ] Can filter by start_date (inclusive)
- [ ] Can filter by end_date (inclusive)
- [ ] Can combine multiple filters
- [ ] Returns 400 if start_date > end_date
- [ ] Returns 400 for invalid date formats
- [ ] Empty filters return all quizzes (backward compatible)
- [ ] **Unit tests written** for filter logic and date validation
- [ ] **Integration tests written** for various query parameter combinations
- [ ] **All existing tests still pass** after implementation
- [ ] **Test coverage**: Title search, date filters, combined filters, validation errors

**Related Files**:
- `api/quiz_routes.py` (route already exists, just update)
- `handlers/quiz_handlers.py::get_user_quizzes_handler()`
- `services/db_services/supabase_quiz.py::get_user_quizzes()`
- `tests/test_quiz_search.py` (NEW)

**Contract Reference**: `specs/001-comprehensive-quiz-generation/contracts/search-quizzes.md`

**Estimated Effort**: 2-3 hours

---

### Issue #4: Implement Quiz Generation from Web URL

**Title**: Add POST /api/quiz/generate/url endpoint with web scraping

**Labels**: `priority: medium`, `type: feature`, `area: backend`, `premium`

**Description**:

Premium feature for basic and educator tier users to generate quizzes from web page URLs. This is a key differentiator for paid tiers but is currently missing.

**Problem**:
- No way to generate quiz from web URLs
- Premium feature missing (nothing to justify paid tiers)
- Dependencies (Playwright, trafilatura) installed but unused
- Contract specified but not implemented

**Requirements**:
1. Create new endpoint: `POST /api/quiz/generate/url`
2. Request body:
   ```json
   {
     "url": "https://en.wikipedia.org/wiki/Machine_Learning",
     "title": "Machine Learning Quiz",
     "num_questions": 10,
     "question_types": ["multiple_choice", "true_false"]
   }
   ```
3. Validation:
   - URL must be valid HTTP/HTTPS
   - URL cannot be private IP (127.0.0.1, 192.168.x.x, 10.x.x.x)
   - URL cannot be localhost
   - Max URL length: 2048 chars
   - User must be basic or educator tier (403 for free tier)
4. Web scraping:
   - Use Playwright for browser automation
   - Use trafilatura for content extraction
   - Timeout: 30 seconds
   - Extract 100 char min, 500KB max
   - User agent: Custom to avoid blocking
5. Save with:
   - `content_source_type='url'`
   - `content_source_reference=<url>`

**Implementation Steps**:
1. Create web scraping service: `services/web_scraping_service.py`
   - `validate_url()` - Check format, no private IPs
   - `scrape_content()` - Playwright + trafilatura
   - `extract_text()` - Clean and validate content
2. Create handler: `handlers/quiz_handlers.py::generate_quiz_from_url()`
   - Check tier (reject free tier with 403)
   - Check quota
   - Call web scraping service
   - Generate quiz
   - Save with content_source_type='url'
3. Create route: `api/quiz_routes.py`
4. Add schema: `schemas/quiz.py::WebQuizRequest`


**Error Responses**:
- 400: Invalid URL format
- 403: Free tier users cannot use this feature
- 403: Quota exceeded
- 404: URL not found
- 408: Request timeout (30s)
- 422: Content too short (<100 chars)
- 422: Content too large (>500KB)
- 500: Scraping failed

**Security Considerations**:
- ⚠️ **SSRF Prevention**: Block private IPs, localhost, internal domains
- ⚠️ **Timeout**: 30 second max to prevent hanging
- ⚠️ **Content Size**: Limit to 500KB to prevent memory issues
- ⚠️ **Rate Limiting**: Consider per-user rate limits (future)

**Development Workflow**:
1. Create feature branch from `test/quiz-generation-and-taking-endpoints`:
   ```bash
   git checkout test/quiz-generation-and-taking-endpoints
   git pull origin test/quiz-generation-and-taking-endpoints
   git checkout -b feature/web-url-quiz-generation
   ```
2. Implement the feature
3. Write tests (see acceptance criteria below)
4. Ensure all tests pass
5. Install Playwright browsers: `playwright install chromium`
6. Create PR to `test/quiz-generation-and-taking-endpoints` branch

**Acceptance Criteria**:
- [ ] Endpoint exists for basic/educator tiers
- [ ] Free tier users get 403 with upgrade message
- [ ] URL validation blocks private IPs
- [ ] Web scraping extracts content with Playwright
- [ ] Timeout after 30 seconds
- [ ] Content validation (100 char min, 500KB max)
- [ ] Quiz saved with content_source_type='url'
- [ ] content_source_reference contains original URL
- [ ] **Unit tests written** for URL validation and SSRF prevention
- [ ] **Unit tests written** for content extraction logic
- [ ] **Integration tests written** with mocked web scraping
- [ ] **All existing tests still pass** after implementation
- [ ] **Test coverage**: Tier checking, URL validation, scraping, error handling

**Dependencies**:
- ✅ `playwright==1.40.0` already installed
- ✅ `trafilatura==1.6.2` already installed
- ❌ Need to install Playwright browsers: `playwright install chromium`

**Related Files**:
- `services/web_scraping_service.py` (NEW)
- `api/quiz_routes.py` (add route)
- `handlers/quiz_handlers.py` (add handler)
- `schemas/quiz.py` (WebQuizRequest schema already exists)

**Contract Reference**: `specs/001-comprehensive-quiz-generation/contracts/generate-quiz-from-url.md`

**Estimated Effort**: 6-8 hours

---

## 🟢 LOW PRIORITY (Polish & Security)

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

**Acceptance Criteria**:
- [ ] Files > 10MB return 413 error
- [ ] Error message specifies the 10MB limit
- [ ] file_size_bytes saved to quiz_metadata table
- [ ] Files <= 10MB work as before
- [ ] **Unit tests written** for file size validation logic
- [ ] **Integration tests written** with files at boundary (9MB, 10MB, 11MB)
- [ ] **All existing tests still pass** after implementation
- [ ] **Test coverage**: Size validation, error messages, metadata storage

**Related Files**:
- `handlers/quiz_handlers.py::generate_quiz_from_file_openai()`
- `tests/test_file_upload_validation.py` (NEW)

**Contract Reference**: `specs/001-comprehensive-quiz-generation/contracts/file-upload-validation.md`

**Estimated Effort**: 1-2 hours

---

## Issue Summary

**Total Issues**: 5 (2 completed ✅, 3 remaining)

**Priority Breakdown**:
- ✅ HIGH: 2 issues COMPLETED (Quota + Admin Tier Management)
- 🟡 MEDIUM: 2 issues remaining (Search + Web Scraping)
- 🟢 LOW: 1 issue remaining (File Size Validation)

**Remaining Estimated Effort**: 9-13 hours

**Recommended Implementation Order**:
1. Issue #3 (Search/Filter) - 2-3 hours - Better UX for existing features
2. Issue #5 (File Size) - 1-2 hours - Security & stability
3. Issue #4 (Web Scraping) - 6-8 hours - Premium feature differentiation

---

## Notes

**Recent Changes (October 2025)**:
- ✅ Quota enforcement fully implemented with 13 passing integration tests
- ✅ Admin tier management implemented with 30 passing tests
- ✅ All 3 quiz generation endpoints (text, file, file-id) have quota validation
- ✅ Self-service Stripe upgrade moved to v1.1 (not blocking for MVP)

**Next Steps**:
1. Test existing endpoints with Postman collections (created in `postman/` directory)
2. Update documentation to reflect quota implementation
3. Implement remaining medium/low priority features as time allows

**Note**: These issues are based on implementation analysis as of 2025-10-12 on the `test/quiz-generation-and-taking-endpoints` branch.
