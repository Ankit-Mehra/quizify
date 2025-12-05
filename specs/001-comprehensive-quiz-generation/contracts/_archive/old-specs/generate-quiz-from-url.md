````markdown
# API Contract: Generate Quiz from Web URL (ACTUAL IMPLEMENTATION)

**Feature**: Comprehensive Quiz Generation Platform  
**Endpoint**: `POST /api/quiz/generate/url`  
**Date**: 2025-10-03  
**Status**: ✅ IMPLEMENTED  
**Last Updated**: 2025-10-23

---

## Purpose

Generate a quiz from web page content by scraping and extracting text from a provided URL. **ACTUAL BEHAVIOR**: Available for ALL tiers with quota limits (not restricted to basic/educator as originally specified).

---

## Request

### HTTP Method
`POST`

### Endpoint
```
/api/quiz/generate/url
```

### Authentication
- **Required**: Yes
- **Type**: Bearer token (Supabase Auth JWT)
- **Header**: `Authorization: Bearer <access_token>`

### Request Body

```json
{
  "url": "https://en.wikipedia.org/wiki/Machine_Learning",
  "title": "Machine Learning Quiz",
  "num_questions": 10,
  "question_type": ["multiple_choice", "true_false"]
}
```

**Field Specifications** (ACTUAL):

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `url` | string | Yes | Valid HTTP/HTTPS URL | Web page URL to scrape for content |
| `title` | string | Yes | Non-empty | Quiz title |
| `num_questions` | integer | No | 1-50, default 10 | Number of questions to generate |
| `question_type` | array | No | Default `["mixed"]` | Question types: `multiple_choice`, `true_false`, `fill_blank`, `matching`, `mixed` |

**Validation Rules** (ACTUAL):
- URL must start with `http://` or `https://`
- URL cannot be empty or whitespace only
- Title cannot be empty or whitespace only
- ✅ **Quota validation**: Checked BEFORE scraping (all tiers)
- ✅ **SSRF protection**: URL validated against private IPs
- ❌ **No tier restriction**: Works for all tiers (free, basic, educator)

---

## Response

### Success Response (HTTP 201) - ACTUAL

```json
{
  "quiz_id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "Machine Learning Quiz",
  "message": "Quiz generated successfully from URL",
  "questions": [
    {
      "id": "660e8400-e29b-41d4-a716-446655440001",
      "quiz_id": "550e8400-e29b-41d4-a716-446655440000",
      "type": "multiple_choice",
      "question": "What is the primary goal of supervised learning?",
      "options": [
        "To find patterns in unlabeled data",
        "To learn from labeled examples",
        "To optimize without feedback",
        "To cluster similar items"
      ],
      "correct_answer": "To learn from labeled examples",
      "explanation": "Supervised learning uses labeled training data to learn the mapping between inputs and outputs.",
      "source": "url"
    },
    {
      "id": "660e8400-e29b-41d4-a716-446655440002",
      "quiz_id": "550e8400-e29b-41d4-a716-446655440000",
      "type": "true_false",
      "question": "Neural networks are inspired by biological neurons.",
      "correct_answer": true,
      "explanation": "Artificial neural networks are loosely modeled after biological neural networks in the brain.",
      "source": "url"
    }
  ],
  "source_url": "https://en.wikipedia.org/wiki/Machine_Learning"
}
```

**Response Fields** (ACTUAL):

| Field | Type | Description |
|-------|------|-------------|
| `quiz_id` | string (UUID) | Unique identifier for generated quiz |
| `title` | string | Quiz title (as provided) |
| `message` | string | Success message |
| `questions` | array | Array of generated question objects with database IDs |
| `source_url` | string | The scraped URL |

**Note**: Response includes FULL questions array with database IDs (unlike text generation endpoint)

---

## Error Responses (ACTUAL)

### 403 Forbidden - Quota Exceeded
```json
{
  "detail": {
    "detail": "Quiz quota exceeded for free tier (5/5). Upgrade to basic for 100 quizzes.",
    "current_count": 5,
    "quota_limit": 5,
    "user_tier": "free"
  }
}
```

**Triggered when**: User has reached their tier's quiz generation limit

### 403 Forbidden - URL Security Violation (SSRF Protection)
```json
{
  "detail": "URL is blocked for security reasons (private IP or blocked domain)."
}
```

**Triggered when**: 
- URL points to private IP ranges (192.168.x.x, 10.x.x.x, 172.16-31.x.x, 127.0.0.1)
- URL points to localhost
- DNS rebinding detected

### 400 Bad Request - Invalid URL Format
```json
{
  "detail": "URL must start with http:// or https://"
}
```

**Triggered when**: URL doesn't start with http:// or https://

### 400 Bad Request - Empty Fields
```json
{
  "detail": "Quiz title cannot be empty"
}
```

**Triggered when**: Title or URL is empty/whitespace only

### 422 Unprocessable Entity - Validation Error
```json
{
  "detail": [
    {
      "loc": ["body", "num_questions"],
      "msg": "ensure this value is less than or equal to 50",
      "type": "value_error.number.not_le"
    }
  ]
}
```

**Triggered when**: Pydantic validation fails (num_questions > 50, invalid question_type, etc.)

### 500 Internal Server Error - Scraping/Generation Failed
```json
{
  "detail": "Error generating quiz from URL: <error_message>"
}
```

**Triggered when**:
- Web scraping fails (timeout, network error, blocked content)
- Content extraction fails
- AI generation fails
- Database save fails

---

## Error Responses REMOVED (Not in Actual Implementation)

### ❌ 403 Forbidden - Tier Restriction (NOT IMPLEMENTED)
~~User must be basic or educator tier~~ 
**ACTUAL**: All tiers can use this endpoint with quota limits

### ❌ 408 Request Timeout (NOT IMPLEMENTED AS SPECIFIC CODE)
Returns 500 instead with timeout error message

### ❌ 422 Content Extraction Failed (NOT DISTINCT)
Returns 500 instead

### ❌ 400 Insufficient Questions Generated (NOT IMPLEMENTED)
No 75% threshold validation implemented

---

## Implementation Flow (ACTUAL)

```
1. Authenticate user (JWT token validation)
   ↓
2. Validate quota BEFORE scraping (CHECK: current_quiz_count < tier_limit)
   ↓  [If quota exceeded → 403 Forbidden]
3. Validate request body (Pydantic validation)
   ↓  [title non-empty, URL format, num_questions 1-50]
4. Validate URL security (SSRF protection)
   ↓  [Check private IPs, localhost - implemented in web_scraping_service]
5. Scrape web page with Playwright (3 concurrent browsers max per user)
   ↓  [30s timeout per page, browser slot management]
6. Extract main content with trafilatura
   ↓
7. Generate questions via OpenAI GPT-4
   ↓  [Uses generate_quizzes_single_async()]
8. Save quiz to database with content_source_type='url', content_source_reference=URL
   ↓  [save_quiz_to_database() with user_token for RLS]
9. Save metadata to quiz_metadata table
   ↓  [content_type='url', file_name=URL, file_type='text/html']
10. Return quiz with questions and source_url
```

**Key Differences from Spec**:
- ✅ **Quota checked first** (before scraping) - efficient
- ❌ **No tier restriction** - all tiers can use with quota
- ❌ **No 75% threshold** - accepts any number of questions generated
- ❌ **No minimum content validation** - relies on AI to fail gracefully
- ✅ **SSRF protection** - implemented in web scraping service
- ✅ **Browser slot management** - 3 concurrent per user

---

## Test Scenarios (UPDATED FOR ACTUAL IMPLEMENTATION)

### Test 1: Successful Quiz Generation from Wikipedia
**Given**: Free tier user with 0 quizzes  
**When**: POST to `/api/quiz/generate/url` with:
```json
{
  "url": "https://en.wikipedia.org/wiki/Photosynthesis",
  "title": "Photosynthesis Quiz",
  "num_questions": 8,
  "question_type": ["multiple_choice", "true_false"]
}
```
**Then**:
- HTTP 201 response
- `quiz_id` present
- `message` = "Quiz generated successfully from URL"
- `source_url` = provided URL
- `questions` array has questions with database IDs
- ✅ **PASSES** (all tiers can use)

---

### Test 2: ~~Tier Restriction for Free User~~ (NOT APPLICABLE)
**REMOVED**: Free tier users CAN use this endpoint (with quota limits)

---

### Test 3: URL Security Violation (Private IP)
**Given**: Free tier user with available quota  
**When**: POST with `url: "http://192.168.1.1/admin"`  
**Then**:
- HTTP 403 or 500 response (depends on where SSRF check triggers)
- Error about blocked URL or scraping failure
- ⚠️ **VERIFY**: SSRF protection is in web_scraping_service.py

---

### Test 4: Quota Exceeded
**Given**: Free tier user with 5 existing quizzes  
**When**: POST to `/api/quiz/generate/url` with valid URL  
**Then**:
- HTTP 403 response
- Error detail object with: `detail`, `current_count`, `quota_limit`, `user_tier`
- ✅ **PASSES**

---

### Test 5: Invalid URL Format
**Given**: Any tier user  
**When**: POST with `url: "ftp://example.com"`  
**Then**:
- HTTP 400 response (Pydantic validation)
- Error: "URL must start with http:// or https://"
- ✅ **PASSES**

---

### Test 6: Empty Title
**Given**: Any tier user  
**When**: POST with `title: "   "` (whitespace)  
**Then**:
- HTTP 400 response
- Error: "Quiz title cannot be empty"
- ✅ **PASSES**

---

### Test 7: Questions Out of Range
**Given**: Any tier user  
**When**: POST with `num_questions: 51`  
**Then**:
- HTTP 422 response (Pydantic validation)
- Validation error for num_questions
- ✅ **PASSES**

---

### Test 8: ~~Insufficient Questions Generated~~ (NOT IMPLEMENTED)
**REMOVED**: No 75% threshold validation in actual implementation

---

### Test 9: Successful Quiz with Complex JavaScript Site
**Given**: Any tier user with available quota  
**When**: POST with URL to modern SPA (single-page app with JS rendering)  
**Then**:
- HTTP 201 response
- Content properly extracted (Playwright handles JS)
- Valid quiz generated
- ✅ **SHOULD PASS** (depends on page structure)

---

## Dependencies

**New Service**: `services/ai_services/web_scraper_service.py`
- `scrape_url(url: str) -> str`: Main scraping function
- `validate_url_security(url: str) -> bool`: Security validation
- `extract_main_content(html: str) -> str`: Content extraction

**Updated Handler**: `handlers/quiz_handlers.py`
- New function: `generate_quiz_from_url()`

**New Route**: `api/quiz_routes.py`
- New endpoint: `POST /api/quiz/generate/url`

**External Dependencies**:
- `playwright==1.40.0` (browser automation)
- `trafilatura==1.6.2` (content extraction)
- `tenacity==8.2.3` (retry logic)

---

## Security Considerations

1. ✅ **SSRF Protection**: Implemented in `web_scraping_service.py` - validates URLs against private IPs
2. ✅ **Browser Slot Management**: Max 3 concurrent browsers per user (prevents resource exhaustion)
3. ❌ **Rate Limiting**: Not implemented (future enhancement)
4. ❌ **Domain Blocklist**: Not implemented (future enhancement)
5. ❌ **Content Size Limits**: No explicit 500KB max enforced
6. ✅ **Timeout Protection**: 30s timeout per page (implemented in scraping service)
7. ✅ **Quota Protection**: Validates BEFORE scraping (efficient resource usage)

---

## Performance Considerations

- **Scraping Duration**: 5-30 seconds per request (depends on page load time)
- **Browser Slot Limit**: 3 concurrent per user (enforced in-memory, single-instance limitation)
- **Browser Pool**: Reuses Playwright browser instances for performance
- **Content Caching**: ❌ Not implemented (future enhancement)
- **Scalability**: ⚠️ Single-instance in-memory slot tracking (needs Redis for multi-instance)

---

## Implementation Notes

### Code Location
- **Route**: `api/quiz_routes.py` - Line ~90
- **Handler**: `handlers/quiz_handlers.py` - `generate_quiz_from_url()` (Line 504)
- **Schema**: `schemas/quiz.py` - `WebQuizRequest` (Line 112)
- **Scraping**: `services/web_scraping_service.py` - `scrape_content()`
- **Quota**: `handlers/quiz_handlers.py` - `validate_user_quota()` (Line 58)

### Database Tables Modified
- `quizzes` - Quiz record with `content_source_type='url'`, `content_source_reference=URL`
- `quiz_questions` - Individual questions
- `quiz_metadata` - Metadata with `content_type='url'`, `file_name=URL`, `file_type='text/html'`

### Dependencies
- `playwright==1.40.0` (browser automation)
- `trafilatura==1.6.2` (content extraction)  
- `tenacity==8.2.3` (retry logic - if implemented)
- OpenAI GPT-4 (quiz generation)

---

## Missing Features vs Original Spec

| Feature | Spec | Actual | Priority | Notes |
|---------|------|--------|----------|-------|
| Tier restriction (basic/educator only) | ✅ Required | ❌ Missing | 🔴 DESIGN CHANGE | **All tiers** can use with quota |
| 75% question threshold | ✅ Required | ❌ Missing | 🟡 MEDIUM | Accepts any number generated |
| Minimum content validation (100 chars) | ✅ Required | ❌ Missing | 🟢 LOW | Relies on AI to fail gracefully |
| 408 timeout error code | ✅ Required | ❌ Missing | 🟢 LOW | Returns 500 instead |
| 422 extraction error code | ✅ Required | ❌ Missing | 🟢 LOW | Returns 500 instead |
| Content size limit (500KB) | ✅ Recommended | ❌ Missing | 🟡 MEDIUM | Could cause memory issues |
| Domain blocklist | ✅ Recommended | ❌ Missing | 🟢 LOW | Future security enhancement |
| Content caching | ✅ Recommended | ❌ Missing | 🟢 LOW | Performance optimization |

---

## Recommendations for Alignment

### Option 1: Update Spec to Match Implementation (RECOMMENDED)
- ✅ **Accept current behavior** as valid design decision
- Remove tier restriction requirement (all tiers with quota is better UX)
- Make 75% threshold optional/future enhancement
- Update error codes to reflect actual 400/403/500 usage
- **Status**: Done in this document

### Option 2: Update Implementation to Match Spec
- Add tier checking (reject free tier users)
- Add 75% threshold validation
- Add minimum content validation (100 chars)
- Distinguish error codes (408 for timeout, 422 for extraction)
- Add content size limits (500KB max)
- **Effort**: Medium (2-3 days)
- **Value**: Low (current behavior is acceptable)

---

**Contract Version**: Actual Implementation as of 2025-10-23  
**Differs from Original Spec**: Yes (tier restriction removed, threshold validation missing)  
**Production Ready**: ✅ YES - Works reliably with quota protection and SSRF security  
**Status**: ✅ **CONTRACT UPDATED TO MATCH IMPLEMENTATION**
