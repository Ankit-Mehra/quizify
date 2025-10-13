# GitHub Issues for Quizify API

**Generated**: October 12, 2025  
**Branch**: `test/quiz-generation-and-taking-endpoints`  
**Status**: Updated after implementation review

---

## 📋 Overview

This document tracks feature development issues for the Quizify API. Issues are organized by priority and include detailed specifications for implementation.

**Current Status**:
- ✅ **2 issues COMPLETED** (Quota enforcement, Admin tier management)
- 🟡 **2 issues PENDING** (Search/filter, Web scraping)
- 🟢 **1 issue PENDING** (File size validation)

**Total Remaining Effort**: 9-13 hours

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

### Issue #4: Quiz Generation from Web URL (Premium Feature)

**Title**: Implement web scraping for quiz generation from URLs

**Labels**: `priority: medium`, `type: feature`, `area: backend`, `premium-tier`, `web-scraping`

---

#### Description

Add ability for **basic** and **educator** tier users to generate quizzes directly from web page URLs. This is a premium feature that differentiates paid tiers from the free tier and provides significant value to users who want to create quizzes from online articles, documentation, and educational content.

---

#### Problem Statement

**Current limitations**:
- No way to generate quizzes from web URLs
- Users must manually copy/paste content from web pages
- Premium tiers lack differentiating features
- Dependencies (Playwright, Trafilatura) are installed but unused
- Contract is specified but not implemented

**User impact**:
- Free tier users have limited content sources (text input, file upload)
- Paid tier users don't get additional value for their subscription
- Manual content extraction is time-consuming and error-prone

---

#### Requirements

**1. New Endpoint**:
```
POST /api/quiz/generate/url
```

**2. Request Body**:
```json
{
  "url": "https://en.wikipedia.org/wiki/Machine_Learning",
  "title": "Machine Learning Quiz",
  "num_questions": 10,
  "question_types": ["multiple_choice", "true_false"]
}
```

**3. Request Schema** (already exists in `schemas/quiz.py`):
```python
class WebQuizRequest(BaseModel):
    url: HttpUrl  # Validates URL format
    title: str
    num_questions: int = Field(ge=1, le=50)
    question_type: List[QuestionTypeEnum]
```

**4. Validation Rules**:
- URL must be valid HTTP/HTTPS protocol
- URL cannot be private IP address (127.0.0.1, 192.168.x.x, 10.x.x.x, 172.16.x.x-172.31.x.x)
- URL cannot be localhost or 0.0.0.0
- URL max length: 2048 characters
- **User must be basic or educator tier** (403 for free tier users)
- Quota enforcement still applies

**5. Web Scraping Requirements**:
- Use **Playwright** for browser automation (handles JavaScript-rendered content)
- Use **Trafilatura** for intelligent content extraction (removes nav, ads, footers)
- Timeout: **30 seconds maximum**
- Extracted content: **minimum 100 characters, maximum 500KB**
- Custom user agent to avoid bot detection
- Handle common HTTP errors (404, 403, 500, timeouts)

**6. Database Storage**:
- Save quiz with `content_source_type='url'`
- Save original URL in `content_source_reference` field
- Include scraping metadata (url, scrape_timestamp, content_length)

---

#### Implementation Steps

**Step 1**: Create web scraping service

```python
# File: services/web_scraping_service.py

import re
import ipaddress
from urllib.parse import urlparse
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
import trafilatura
from fastapi import HTTPException

# Constants
MAX_CONTENT_SIZE = 500 * 1024  # 500KB
MIN_CONTENT_SIZE = 100  # 100 characters
SCRAPE_TIMEOUT = 30000  # 30 seconds

# Private IP ranges to block (SSRF prevention)
PRIVATE_IP_RANGES = [
    ipaddress.ip_network('127.0.0.0/8'),    # Localhost
    ipaddress.ip_network('10.0.0.0/8'),     # Private
    ipaddress.ip_network('172.16.0.0/12'),  # Private
    ipaddress.ip_network('192.168.0.0/16'), # Private
    ipaddress.ip_network('169.254.0.0/16'), # Link-local
]

def validate_url(url: str) -> None:
    """Validate URL and prevent SSRF attacks."""
    parsed = urlparse(url)
    
    # Check protocol
    if parsed.scheme not in ['http', 'https']:
        raise HTTPException(
            status_code=400,
            detail="Invalid URL protocol. Only HTTP and HTTPS are allowed."
        )
    
    # Check for localhost
    if parsed.hostname in ['localhost', '0.0.0.0', '127.0.0.1']:
        raise HTTPException(
            status_code=400,
            detail="Cannot scrape localhost URLs."
        )
    
    # Check for private IPs
    try:
        ip = ipaddress.ip_address(parsed.hostname)
        for private_range in PRIVATE_IP_RANGES:
            if ip in private_range:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot scrape private IP addresses."
                )
    except ValueError:
        # Not an IP address, check DNS resolution
        pass

async def scrape_content(url: str) -> str:
    """Scrape content from URL using Playwright + Trafilatura."""
    validate_url(url)
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (compatible; QuizifyBot/1.0; +https://quizify.app/bot)'
            )
            page = await context.new_page()
            
            # Navigate with timeout
            try:
                await page.goto(url, timeout=SCRAPE_TIMEOUT, wait_until='networkidle')
            except PlaywrightTimeout:
                raise HTTPException(
                    status_code=408,
                    detail=f"Request timeout. The page took longer than {SCRAPE_TIMEOUT/1000} seconds to load."
                )
            
            # Get page HTML
            html = await page.content()
            await browser.close()
            
            # Extract main content using Trafilatura
            extracted = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=True,
                no_fallback=False
            )
            
            if not extracted:
                raise HTTPException(
                    status_code=422,
                    detail="Could not extract meaningful content from the page."
                )
            
            # Validate content size
            if len(extracted) < MIN_CONTENT_SIZE:
                raise HTTPException(
                    status_code=422,
                    detail=f"Extracted content too short (minimum {MIN_CONTENT_SIZE} characters)."
                )
            
            if len(extracted) > MAX_CONTENT_SIZE:
                # Truncate to max size
                extracted = extracted[:MAX_CONTENT_SIZE]
            
            return extracted
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error scraping URL: {str(e)}"
        )
```

**Step 2**: Create handler

```python
# File: handlers/quiz_handlers.py

async def generate_quiz_from_url(
    data: WebQuizRequest,
    current_user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token)
):
    """Generate quiz from web URL (basic/educator tier only)."""
    
    # Check user tier (reject free tier)
    tier_info = get_user_tier_info(current_user_id)
    if tier_info["account_tier"] == "free":
        raise HTTPException(
            status_code=403,
            detail={
                "detail": "URL-based quiz generation is a premium feature. Upgrade to basic or educator tier to access this feature.",
                "user_tier": "free",
                "required_tier": "basic",
                "upgrade_url": "/api/admin/users/{user_id}/tier"
            }
        )
    
    # Validate quota
    validate_user_quota(current_user_id)
    
    try:
        # Scrape content
        content = await scrape_content(str(data.url))
        
        # Generate quiz
        quizzes = await generate_quizzes_single_async(
            content,
            data.num_questions,
            question_types=list(data.question_type)
        )
        
        # Save to database
        quiz_id = save_quiz_to_database(data.title, quizzes, current_user_id)
        
        # Save metadata
        metadata = {
            "quiz_id": quiz_id,
            "content_type": "url",
            "content_source_type": "url",
            "content_source_reference": str(data.url),
            "word_count": len(content.split()),
            "content_length": len(content),
            "created_by": current_user_id,
            "created_at": datetime.now().isoformat(),
            "question_count": len(quizzes),
            "scrape_timestamp": datetime.now().isoformat()
        }
        save_metadata(metadata)
        
        return {
            "quiz_id": quiz_id,
            "title": data.title,
            "message": "Quiz generated successfully from URL",
            "source_url": str(data.url)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating quiz from URL: {str(e)}"
        )
```

**Step 3**: Add route

```python
# File: api/quiz_routes.py

router.add_api_route(
    path="/generate/url",
    endpoint=generate_quiz_from_url,
    methods=["POST"],
    summary="Generate Quiz from Web URL",
    description="Generate a quiz from a web page URL. **Premium feature** for basic and educator tiers only.",
    response_model=Dict[str, Any],
    tags=["Quiz Generation"],
    status_code=201
)
```

**Step 4**: Install Playwright browsers

```bash
playwright install chromium
```

---

#### Error Responses

| Status Code | Condition | Response Body |
|-------------|-----------|---------------|
| 400 | Invalid URL format | `{"detail": "Invalid URL protocol. Only HTTP and HTTPS are allowed."}` |
| 400 | Private IP or localhost | `{"detail": "Cannot scrape localhost URLs."}` |
| 403 | Free tier user | `{"detail": "URL-based quiz generation is a premium feature...", "user_tier": "free", "required_tier": "basic"}` |
| 403 | Quota exceeded | `{"detail": "Quiz quota exceeded for basic tier (20/20)...", "current_count": 20, "quota_limit": 20}` |
| 404 | URL not found | `{"detail": "The requested URL returned 404 Not Found."}` |
| 408 | Request timeout | `{"detail": "Request timeout. The page took longer than 30 seconds to load."}` |
| 422 | Content too short | `{"detail": "Extracted content too short (minimum 100 characters)."}` |
| 422 | No extractable content | `{"detail": "Could not extract meaningful content from the page."}` |
| 500 | Scraping failed | `{"detail": "Error scraping URL: {error message}"}` |

---

#### Security Considerations

🔐 **SSRF (Server-Side Request Forgery) Prevention**:
- ✅ Block private IP ranges (10.x.x.x, 192.168.x.x, 172.16-31.x.x)
- ✅ Block localhost (127.0.0.1, 0.0.0.0, localhost)
- ✅ Block link-local addresses (169.254.x.x)
- ✅ Validate URL protocol (only HTTP/HTTPS)

⏱️ **Timeout Protection**:
- ✅ 30-second hard timeout on page loads
- ✅ Prevents hanging requests from slow/malicious servers
- ✅ Frees up resources quickly

💾 **Resource Protection**:
- ✅ Content size limit (500KB max) prevents memory exhaustion
- ✅ Minimum content check (100 chars) prevents abuse
- ✅ Graceful truncation if content exceeds max size

🔒 **Tier Enforcement**:
- ✅ Free tier users blocked with upgrade message
- ✅ Quota still enforced for basic/educator tiers
- ✅ Clear error messages guide users to upgrade

---

#### Development Workflow

```bash
# 1. Create feature branch
git checkout test/quiz-generation-and-taking-endpoints
git pull origin test/quiz-generation-and-taking-endpoints
git checkout -b feature/web-url-quiz-generation

# 2. Install Playwright browsers (one-time setup)
playwright install chromium

# 3. Implement changes
# - Create services/web_scraping_service.py
# - Update handlers/quiz_handlers.py
# - Update api/quiz_routes.py

# 4. Write tests with mocked scraping
# - Create tests/test_web_scraping_service.py (unit tests)
# - Create tests/test_url_quiz_generation.py (integration tests)
# - Mock Playwright and Trafilatura for consistent testing

# 5. Run tests
pytest tests/test_web_scraping_service.py -v
pytest tests/test_url_quiz_generation.py -v

# 6. Ensure all existing tests pass
pytest

# 7. Create PR to test/quiz-generation-and-taking-endpoints
```

---

#### Acceptance Criteria

**Functional Requirements**:
- [ ] Endpoint `POST /api/quiz/generate/url` exists and is accessible
- [ ] Basic and educator tier users can generate quizzes from URLs
- [ ] Free tier users get 403 with upgrade message
- [ ] URL validation blocks private IPs and localhost
- [ ] Playwright successfully scrapes JavaScript-rendered content
- [ ] Trafilatura extracts clean text (no nav/ads/footers)
- [ ] 30-second timeout enforced
- [ ] Content validation (100 char min, 500KB max) works
- [ ] Quiz saved with `content_source_type='url'`
- [ ] `content_source_reference` contains original URL

**Test Coverage**:
- [ ] Unit tests for `validate_url()` - SSRF prevention
- [ ] Unit tests for URL format validation
- [ ] Unit tests for content size validation
- [ ] Integration tests with mocked web scraping
- [ ] Integration tests for tier checking (free/basic/educator)
- [ ] Integration tests for quota enforcement
- [ ] Integration tests for error scenarios (404, timeout, no content)
- [ ] All existing 43 tests still pass

**Performance**:
- [ ] Scraping completes in < 30 seconds for typical pages
- [ ] No memory leaks from Playwright instances
- [ ] Browser instances properly closed after use

**Documentation**:
- [ ] OpenAPI documentation updated with new endpoint
- [ ] Error responses documented
- [ ] Premium tier requirement noted in description

---

#### Dependencies

- ✅ `playwright==1.40.0` - Already installed in requirements.txt
- ✅ `trafilatura==1.6.2` - Already installed in requirements.txt
- ❌ **Playwright browser binaries** - Need to run `playwright install chromium`

**Installation command**:
```bash
playwright install chromium
```

---

#### Related Files

**Files to create**:
- `services/web_scraping_service.py` - New web scraping service

**Files to modify**:
- `handlers/quiz_handlers.py` - Add `generate_quiz_from_url()` handler
- `api/quiz_routes.py` - Add POST /generate/url route

**Schema** (already exists):
- `schemas/quiz.py` - `WebQuizRequest` class already defined

**Files to test**:
- `tests/test_web_scraping_service.py` - New unit tests
- `tests/test_url_quiz_generation.py` - New integration tests

---

#### Contract Reference

`specs/001-comprehensive-quiz-generation/contracts/generate-quiz-from-url.md`

---

#### Estimated Effort

**6-8 hours** (breakdown):
- Web scraping service: 2 hours
- Handler implementation: 1 hour
- Route setup: 30 minutes
- Unit tests (SSRF, validation): 1.5 hours
- Integration tests (mocked scraping): 2 hours
- Testing and debugging: 1-2 hours

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
- ✅ **Completed**: 2 issues (Quota enforcement, Admin tier management)
- 🟡 **Medium Priority**: 2 issues (Search/filter, Web scraping)
- 🟢 **Low Priority**: 1 issue (File size validation)

**Effort Breakdown**:
- Issue #3 (Search): 2-3 hours
- Issue #4 (Web URL): 6-8 hours  
- Issue #5 (File Size): 1-2 hours
- **Total Remaining**: 9-13 hours

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

**Priority 3**: Issue #4 (Web URL) - 6-8 hours
- **Why last**: Most complex, requires external dependencies
- **Value**: Premium feature differentiation
- **Dependencies**: Playwright browser installation

---

### Recent Changes (October 2025)

✅ **Successfully Implemented**:
- Quota enforcement with 13 passing integration tests
- Admin tier management with 30 passing tests
- All 3 quiz generation endpoints validated for quota
- Quota checked BEFORE AI calls (cost optimization)

📝 **Documentation Status**:
- Contract specs need updating to reflect quota implementation
- README needs revision to show actual vs. planned features
- Two Postman collections created for endpoint testing

🎯 **Next Steps**:
1. Test endpoints with Postman collections (`postman/` directory)
2. Implement remaining 3 issues (9-13 hours total)
3. Update documentation to match actual implementation
4. Consider v1.1 features (Stripe integration, URL scraping)

---

### Development Notes

**Testing Strategy**:
- All new features must include unit AND integration tests
- All existing 43 tests must continue passing
- Mock external services (OpenAI, Playwright) in tests
- Use pytest fixtures for common test setup

**Branch Strategy**:
- Base branch: `test/quiz-generation-and-taking-endpoints`
- Feature branches: `feature/<issue-name>`
- PR target: `test/quiz-generation-and-taking-endpoints`
- After testing: Merge to `development`, then `deploy/production`

**Security Checklist**:
- [ ] SSRF prevention for URL scraping (Issue #4)
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
- [ ] **Integration tests written** with files at boundary (9MB, 10MB, 11MB)
- [ ] **All existing tests still pass** after implementation
- [ ] **Test coverage**: Size validation, error messages, metadata storage


**Related Files**:
- `handlers/quiz_handlers.py::generate_quiz_from_file_openai()`
- `tests/test_file_upload_validation.py` (NEW)

**Contract Reference**: `specs/001-comprehensive-quiz-generation/contracts/file-upload-validation.md`

**Estimated Effort**: 1-2 hours

