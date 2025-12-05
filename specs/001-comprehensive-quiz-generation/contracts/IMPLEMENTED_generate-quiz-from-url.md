# API Contract: Generate Quiz from Web URL (ACTUAL IMPLEMENTATION)

**Endpoint**: `POST /api/quiz/generate/url`  
**Status**: ✅ FULLY IMPLEMENTED  
**Authentication**: Required (Bearer token)  
**Response Model**: `QuizGenerationResponse`  
**Last Updated**: 2025-10-28

---

## Overview

Generate a quiz from web page content by scraping and extracting text from a provided URL. Supports both HTML pages and PDF files. When a PDF is detected, it is automatically saved to the user's files for future reference.

---

## Request

### Headers
```
Authorization: Bearer <jwt_token>
Content-Type: application/json
```

### Body
```json
{
  "url": "https://en.wikipedia.org/wiki/Python_(programming_language)",
  "title": "Python Programming Quiz",
  "num_questions": 10,
  "question_type": ["multiple_choice", "true_false", "fill_blank", "matching", "mixed"]
}
```

### Field Validation
- `url`: **Required**, string
  - Must start with `http://` or `https://`
  - Cannot be empty or whitespace only
  - Validated against private IP ranges (SSRF protection)
- `title`: **Required**, string
  - Cannot be empty or whitespace only
- `num_questions`: **Optional**, integer 1-50 (default: 10)
  - Validated by Pydantic `Field(10, gt=0, le=50)`
- `question_type`: **Optional**, array of valid types (default: `["mixed"]`)
  - Valid types: `"multiple_choice"`, `"true_false"`, `"fill_blank"`, `"matching"`, `"mixed"`

### Security & Validation
- ✅ **SSRF Protection**: Blocks private IP ranges (127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
- ✅ **DNS Rebinding Prevention**: Re-validates hostname before connection
- ✅ **Browser Slot Management**: Max 3 concurrent browser instances per user
- ✅ **Quota Enforcement**: Validates user's quiz generation quota before scraping
- ✅ **Tier-based Limits**: Free: 5, Basic: 20, Educator: 500 quizzes

---

## Response

### Success (201 Created) - HTML Page

**Response Model**: `QuizGenerationResponse`

```json
{
  "quiz_id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "Python Programming Quiz",
  "message": "Quiz generated successfully from URL",
  "questions": [
    {
      "id": "q1-uuid",
      "quiz_id": "550e8400-e29b-41d4-a716-446655440000",
      "type": "multiple_choice",
      "question": "What is Python?",
      "options": ["A snake", "A programming language", "A framework", "A database"],
      "correct_answer": "A programming language",
      "explanation": "",
      "source": ""
    }
  ],
  "source_url": "https://en.wikipedia.org/wiki/Python_(programming_language)"
}
```

### Success (201 Created) - PDF URL

```json
{
  "quiz_id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "Research Paper Quiz",
  "message": "Quiz generated successfully from PDF URL (PDF saved to your files)",
  "questions": [...],
  "source_url": "https://example.com/research-paper.pdf",
  "file_id": "file-uuid-123"
}
```

### Response Fields
- `quiz_id` (string): UUID of the created quiz
- `title` (string): Quiz title
- `message` (string): Success message (differs for HTML vs PDF)
- `questions` (array, optional): List of generated questions with database IDs
- `source_url` (string, optional): Original URL that was scraped
- `file_id` (string, optional): File ID if PDF was saved to user_files table

---

## Error Responses

### 401 Unauthorized
```json
{
  "detail": "Authentication required to generate quiz"
}
```
**Cause**: No Bearer token provided or token is invalid/expired

---

### 403 Forbidden - Quota Exceeded
```json
{
  "detail": "Quiz generation quota exceeded. You have created X/Y quizzes. Please upgrade your tier for more quota."
}
```
**Cause**: User has reached their tier's quiz generation quota

---

### 403 Forbidden - SSRF Protection
```json
{
  "detail": "Access to private IP addresses is not allowed for security reasons."
}
```
**Cause**: URL resolves to a private IP address (SSRF protection triggered)

---

### 422 Unprocessable Entity - Invalid URL
```json
{
  "detail": "URL must start with http:// or https://"
}
```
**Cause**: URL doesn't start with valid protocol

---

### 429 Too Many Requests - Browser Slots
```json
{
  "detail": "Maximum concurrent scraping limit reached. Please try again in a moment."
}
```
**Cause**: User has 3 concurrent browser instances running (rate limiting)

---

### 500 Internal Server Error - Scraping Failed
```json
{
  "detail": "Failed to scrape content from URL. The page may be inaccessible or protected."
}
```
**Cause**: 
- Website blocks scraping
- Timeout (> 30 seconds)
- Network error
- Invalid content

---

### 500 Internal Server Error - Quiz Generation
```json
{
  "detail": "Error generating quiz: <error_message>"
}
```
**Cause**:
- AI service (OpenAI) fails
- Database save fails
- Unexpected exceptions

---

## Implementation Details

### Content Extraction

**HTML Pages**:
1. Launch headless Chrome browser (Playwright)
2. Navigate to URL with 30-second timeout
3. Extract main content using Trafilatura library
4. Strip HTML tags and clean text
5. Close browser and release slot

**PDF Files**:
1. Download PDF using httpx
2. Extract text using PyMuPDF (fitz library)
3. Save PDF to user_files table in Supabase
4. Store file_id as content_source_reference

### Quiz Generation Flow
1. **Quota Validation**: Check user's tier quota before scraping
2. **Browser Slot Acquisition**: Wait for available slot (max 3 per user)
3. **Content Scraping**: Extract text from URL (HTML or PDF)
4. **AI Generation**: Generate questions using OpenAI GPT-4
5. **Database Save**: 
   - Save quiz with `content_source_type="url"`
   - Save `content_source_reference` (URL or file_id if PDF)
   - Save questions with IDs
6. **Metadata Save**: Store scraping metadata
7. **Browser Slot Release**: Free up slot for next request

### Database Fields
- `content_source_type`: Always set to `"url"`
- `content_source_reference`: URL for HTML, file_id for PDFs
- `file_type` in metadata: `"text/html"` or `"application/pdf"`

---

## Side Effects

When quiz generation from URL succeeds:

1. **Browser Resource Usage**
   - Temporary headless Chrome instance spawned
   - Automatically cleaned up after scraping
   - Slot released for other requests

2. **PDF File Storage** (if URL points to PDF)
   - PDF downloaded and saved to Supabase Storage
   - File record created in `user_files` table
   - file_id referenced in quiz metadata

3. **Quiz Database Records**
   - Quiz saved to `quizzes` table
   - Questions saved to `questions` table
   - Metadata saved to `quiz_metadata` table

4. **User Quota Updated**
   - Increments user's quiz count
   - Enforced via database view `user_tier_info`

---

## Security Features

### SSRF Protection
- Validates URL format
- Blocks private IP ranges (RFC 1918)
- Blocks localhost and link-local addresses
- Re-validates DNS resolution before connection

### Browser Security
- Sandboxed Chrome process
- Headless mode (no GUI)
- Automatic cleanup on timeout/error
- Container-aware security flags

### Rate Limiting
- Max 3 concurrent browsers per user
- In-memory slot tracking
- Automatic release on completion/error

---

## Performance Considerations

- **Scraping Time**: 5-30 seconds depending on page complexity
- **PDF Processing**: 2-10 seconds for typical PDFs
- **AI Generation**: 10-30 seconds for 10 questions
- **Total Time**: ~20-60 seconds end-to-end
- **Browser Slots**: Limits concurrent load, prevents resource exhaustion

---

## Use Cases

### Academic Research
```bash
# Generate quiz from research paper PDF
POST /api/quiz/generate/url
{
  "url": "https://arxiv.org/pdf/2103.12345.pdf",
  "title": "AI Research Quiz",
  "num_questions": 15
}
# → PDF saved to files, quiz generated, file_id returned
```

### Documentation Learning
```bash
# Generate quiz from documentation page
POST /api/quiz/generate/url
{
  "url": "https://docs.python.org/3/tutorial/",
  "title": "Python Tutorial Quiz",
  "num_questions": 20
}
# → HTML content extracted, quiz generated
```

### Wikipedia Articles
```bash
# Generate quiz from Wikipedia
POST /api/quiz/generate/url
{
  "url": "https://en.wikipedia.org/wiki/Quantum_mechanics",
  "title": "Quantum Mechanics Quiz",
  "num_questions": 10,
  "question_type": ["multiple_choice", "true_false"]
}
```

---

## Known Limitations

1. **JavaScript-Heavy Sites**: May not fully render dynamic content
2. **Paywall Content**: Cannot access subscription-required content
3. **Anti-Scraping Protection**: Some sites block automated access
4. **Large PDFs**: Memory intensive for very large files (>50MB)
5. **Complex Layouts**: May not extract perfectly from complex page structures

---

## Future Enhancements

### High Priority
- [ ] Add retry logic for transient failures
- [ ] Implement caching for frequently scraped URLs
- [ ] Support authentication for protected resources

### Medium Priority
- [ ] Add PDF page range selection
- [ ] Support more file formats (EPUB, Markdown)
- [ ] Improve content extraction quality

### Low Priority
- [ ] Screenshot capture for visual questions
- [ ] Multi-page scraping (follow links)
- [ ] Custom user-agent configuration

---

## Related Endpoints

| Endpoint | Purpose | Relationship |
|----------|---------|--------------|
| `POST /api/quiz/generate/text` | Generate from text | Alternative input method |
| `POST /api/quiz/generate/file` | Generate from upload | Alternative for local files |
| `GET /api/files/{file_id}` | Download saved PDF | Access PDFs saved from URLs |
| `GET /api/quiz/my-quizzes` | List all quizzes | View generated URL quizzes |

---

## Testing

### Test Cases

1. **Valid HTML URL**: Should scrape and generate quiz
2. **Valid PDF URL**: Should download, save, and generate quiz
3. **Private IP**: Should return 403 SSRF error
4. **Invalid URL**: Should return 422 validation error
5. **Quota Exceeded**: Should return 403 quota error
6. **Concurrent Limit**: Should return 429 when >3 browsers active
7. **Timeout**: Should fail gracefully after 30 seconds
8. **Invalid Content**: Should return 500 with helpful message

---

## Change Log

| Date | Version | Changes | Author |
|------|---------|---------|--------|
| 2025-10-28 | 1.0 | Complete contract with PDF support | System |
| 2025-10-03 | 0.9 | Initial implementation | System |

---

**Contract Status**: ✅ Complete and Accurate  
**Implementation Status**: ✅ Fully Functional  
**Security Audit**: ✅ Passed (SSRF protection, rate limiting)
