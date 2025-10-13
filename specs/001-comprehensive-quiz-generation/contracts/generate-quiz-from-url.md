# API Contract: Generate Quiz from Web URL

**Feature**: Comprehensive Quiz Generation Platform  
**Endpoint**: `POST /api/quiz/generate/url`  
**Date**: 2025-10-03  
**Status**: New

---

## Purpose

Generate a quiz from web page content by scraping and extracting text from a provided URL. This endpoint is restricted to basic and educator tier users only.

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
  "question_types": ["multiple_choice", "true_false"]
}
```

**Field Specifications**:

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `url` | string | Yes | Valid HTTP/HTTPS URL, max 2048 chars | Web page URL to scrape for content |
| `title` | string | Yes | 1-255 characters | Quiz title |
| `num_questions` | integer | Yes | 5-50 | Number of questions to generate |
| `question_types` | array | Yes | Non-empty, valid types only | Question types: `multiple_choice`, `true_false`, `fill_blank`, `matching` |

**Validation Rules**:
- URL must be valid HTTP or HTTPS
- URL cannot point to private IPs (127.0.0.1, 192.168.x.x, 10.x.x.x, etc.)
- URL cannot point to localhost or internal domains
- User must be basic or educator tier (free tier rejected with 403)
- User must not have exceeded quiz quota for their tier

---

## Response

### Success Response (HTTP 201)

```json
{
  "quiz_id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "Machine Learning Quiz",
  "content_source_type": "url",
  "content_source_reference": "https://en.wikipedia.org/wiki/Machine_Learning",
  "num_questions": 8,
  "created_at": "2025-10-03T14:30:00Z",
  "questions": [
    {
      "id": "660e8400-e29b-41d4-a716-446655440001",
      "type": "multiple_choice",
      "question": "What is the primary goal of supervised learning?",
      "options": [
        "To find patterns in unlabeled data",
        "To learn from labeled examples",
        "To optimize without feedback",
        "To cluster similar items"
      ],
      "correct_answer": "To learn from labeled examples",
      "explanation": "Supervised learning uses labeled training data to learn the mapping between inputs and outputs."
    },
    {
      "id": "660e8400-e29b-41d4-a716-446655440002",
      "type": "true_false",
      "question": "Neural networks are inspired by biological neurons.",
      "correct_answer": true,
      "explanation": "Artificial neural networks are loosely modeled after biological neural networks in the brain."
    }
  ]
}
```

**Response Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `quiz_id` | string (UUID) | Unique identifier for generated quiz |
| `title` | string | Quiz title (as provided) |
| `content_source_type` | string | Always "url" for this endpoint |
| `content_source_reference` | string | The scraped URL |
| `num_questions` | integer | Actual number of questions generated (may be less than requested) |
| `created_at` | string (ISO 8601) | Quiz creation timestamp |
| `questions` | array | Array of generated question objects |

**Note**: `num_questions` in response may be less than requested if:
- Insufficient content was extracted from the URL
- AI could not generate the full requested amount
- Must be ≥75% of requested count (otherwise returns error)

---

## Error Responses

### 400 Bad Request - Invalid URL Format
```json
{
  "detail": "Invalid URL format. Must be HTTP or HTTPS."
}
```

### 400 Bad Request - Insufficient Content
```json
{
  "detail": "Could not extract enough content from URL (minimum 100 characters required)."
}
```

### 400 Bad Request - Insufficient Questions Generated
```json
{
  "detail": "AI generated only 6/10 questions (minimum 75% required). Content may not have sufficient detail."
}
```

### 403 Forbidden - Tier Restriction
```json
{
  "detail": "Web URL quiz generation requires basic or educator tier. Please upgrade your account."
}
```

### 403 Forbidden - URL Security Violation
```json
{
  "detail": "URL is blocked for security reasons (private IP or blocked domain)."
}
```

### 403 Forbidden - Quota Exceeded
```json
{
  "detail": "Quiz quota exceeded. Basic tier: 100 quizzes. Upgrade to educator for 500 quizzes."
}
```

### 408 Request Timeout - Scraping Timeout
```json
{
  "detail": "Page took too long to load (30 second limit). Please try a different URL or try again later."
}
```

### 422 Unprocessable Entity - Content Extraction Failed
```json
{
  "detail": "Could not extract main content from page. URL may require login or contain no text content."
}
```

### 500 Internal Server Error - Scraping Failed
```json
{
  "detail": "Failed to scrape URL after 3 retry attempts. Network error or unreachable URL."
}
```

---

## Implementation Flow

```
1. Authenticate user (JWT token validation)
   ↓
2. Check user tier (must be basic or educator)
   ↓
3. Validate quota (check quiz count < tier limit)
   ↓
4. Validate URL format (regex)
   ↓
5. Validate URL security (no private IPs, blocklist check)
   ↓
6. Scrape web page with Playwright (30s timeout, 3 retries)
   ↓
7. Extract main content with trafilatura
   ↓
8. Validate content (≥100 chars, ≤500KB)
   ↓
9. Chunk content (8000 token limit per chunk)
   ↓
10. Generate questions via OpenAI GPT-4
    ↓
11. Validate question count (≥75% of requested)
    ↓
12. Store quiz with content_source_type='url'
    ↓
13. Return quiz with questions
```

---

## Test Scenarios

### Test 1: Successful Quiz Generation from Wikipedia
**Given**: Basic tier user with 0 quizzes  
**When**: POST to `/api/quiz/generate/url` with:
```json
{
  "url": "https://en.wikipedia.org/wiki/Photosynthesis",
  "title": "Photosynthesis Quiz",
  "num_questions": 8,
  "question_types": ["multiple_choice", "true_false"]
}
```
**Then**:
- HTTP 201 response
- `quiz_id` present
- `content_source_type` = "url"
- `content_source_reference` = provided URL
- `num_questions` ≥ 6 (75% of 8)
- `questions` array has 6-8 questions

---

### Test 2: Tier Restriction for Free User
**Given**: Free tier user with 0 quizzes  
**When**: POST to `/api/quiz/generate/url` with valid URL  
**Then**:
- HTTP 403 response
- Error message about tier requirement

---

### Test 3: URL Security Violation (Private IP)
**Given**: Basic tier user  
**When**: POST with `url: "http://192.168.1.1/admin"`  
**Then**:
- HTTP 403 response
- Error about blocked URL

---

### Test 4: URL Security Violation (Localhost)
**Given**: Basic tier user  
**When**: POST with `url: "http://localhost:8080/data"`  
**Then**:
- HTTP 403 response
- Error about blocked URL

---

### Test 5: Insufficient Content Extracted
**Given**: Basic tier user  
**When**: POST with URL containing <100 characters of text  
**Then**:
- HTTP 400 response
- Error about insufficient content

---

### Test 6: Quota Exceeded
**Given**: Basic tier user with 100 existing quizzes  
**When**: POST to `/api/quiz/generate/url` with valid URL  
**Then**:
- HTTP 403 response
- Error about quota exceeded

---

### Test 7: Timeout Handling
**Given**: Basic tier user  
**When**: POST with URL that takes >30 seconds to load  
**Then**:
- HTTP 408 response after retry attempts
- Error about timeout

---

### Test 8: Content Extraction Failure
**Given**: Basic tier user  
**When**: POST with URL behind paywall/login  
**Then**:
- HTTP 422 response
- Error about content extraction failure

---

### Test 9: Insufficient Questions Generated (Below 75%)
**Given**: Basic tier user  
**When**: POST requesting 20 questions from short article  
**Then**:
- HTTP 400 response
- Error: "AI generated only 12/20 questions (minimum 75% required)"

---

### Test 10: Successful Quiz with Complex JavaScript Site
**Given**: Educator tier user  
**When**: POST with URL to modern SPA (single-page app with JS rendering)  
**Then**:
- HTTP 201 response
- Content properly extracted (Playwright handles JS)
- Valid quiz generated

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

1. **SSRF Protection**: Validate URLs to prevent Server-Side Request Forgery attacks
2. **Rate Limiting**: Consider adding per-user rate limits for scraping (future enhancement)
3. **Domain Blocklist**: Maintain list of blocked domains (malicious sites, rate-limited APIs)
4. **Content Size Limits**: Enforce 500KB max to prevent memory issues
5. **Timeout Protection**: 30s timeout prevents hanging requests
6. **Retry Limits**: Max 3 attempts prevents infinite retry loops

---

## Performance Considerations

- **Scraping Duration**: 5-30 seconds per request (depends on page load time)
- **Concurrent Scraping**: Consider queue system for high load (future enhancement)
- **Browser Pool**: Reuse Playwright browser instances for better performance
- **Content Caching**: Consider caching scraped content by URL (future enhancement)

---

**Status**: Contract complete. Ready for implementation.
