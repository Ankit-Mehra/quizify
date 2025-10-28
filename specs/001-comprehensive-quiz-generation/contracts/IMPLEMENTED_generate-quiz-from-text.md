# API Contract: Generate Quiz from Text (ACTUAL IMPLEMENTATION)

**Endpoint**: `POST /api/quiz/generate/text`  
**Status**: ✅ FULLY IMPLEMENTED  
**Authentication**: Required (Bearer token)  
**Response Model**: `QuizGenerationResponse`  
**Last Updated**: 2025-10-28

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
  "title": "Python Basics Quiz",
  "content": "Python is a high-level programming language...",
  "num_questions": 10,
  "question_type": ["multiple_choice", "true_false", "fill_blank", "matching", "mixed"]
}
```

### Field Validation (ACTUAL)
- `title`: **Required**, string (no explicit max length validation)
- `content`: **Required**, string (no explicit min length validation)
- `num_questions`: **Optional**, integer 1-50 (default: 10), validated by Pydantic `Field(10, gt=0, le=50)`
- `question_type`: **Optional**, array of valid types, default `["mixed"]`
  - Valid types: `"multiple_choice"`, `"true_false"`, `"fill_blank"`, `"matching"`, `"mixed"`

### Current Business Rules
- ✅ **Quota checking enabled** - Uses `validate_user_quota()` before generation
- ✅ **Tier-based limits enforced** - Free: 5, Basic: 20, Educator: 500 quizzes
- ✅ **User authentication required** - Returns 401 if not authenticated
- ✅ **Content saved to Supabase Storage** - As `{title}.txt` file
- ✅ **Metadata saved to database** - Includes word count, timestamps
- ✅ **Returns generated questions** - Questions array included in response

---

## Response

### Success (200 OK) - ACTUAL

**Response Model**: `QuizGenerationResponse`

```json
{
  "quiz_id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "Python Basics Quiz",
  "message": "Quiz generated successfully from text",
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
  ]
}
```

### Response Fields
- `quiz_id` (string): UUID of the created quiz
- `title` (string): Quiz title
- `message` (string): Success message
- `questions` (array, optional): List of generated questions with database IDs
- `source_url` (string, optional): Not present for text-based quizzes
- `file_id` (string, optional): Not present for text-based quizzes

---

## Errors (ACTUAL)

### 401 Unauthorized
```json
{
  "detail": "Authentication required to generate quiz"
}
```

**Triggered when**:
- No Bearer token provided
- Invalid/expired token
- `current_user_id` is undefined

### 403 Forbidden - Quota Exceeded
```json
{
  "detail": "Quiz generation quota exceeded. You have created X/Y quizzes. Please upgrade your tier for more quota."
}
```

**Triggered when**:
- User has reached their tier's quiz quota
- Free tier: 5 quizzes
- Basic tier: 20 quizzes  
- Educator tier: 500 quizzes

### 422 Unprocessable Entity
```json
{
  "detail": "Validation error message"
}
```

**Triggered when**:
- `num_questions` not in range 1-50
- `question_type` contains invalid values
- Pydantic validation fails

### 500 Internal Server Error
```json
{
  "detail": "Error generating quiz: <error_message>"
}
```

**Triggered when**:
- AI service (OpenAI) fails
- Database save fails
- Supabase storage fails
- Unexpected exceptions

---

## Side Effects (ACTUAL)

When quiz generation succeeds, the following actions occur:

1. **Generate Questions**
   - Calls `generate_quizzes_single_async()` from chunking service
   - Uses OpenAI GPT-4 to generate questions

2. **Save Quiz to Database**
   - Calls `save_quiz_to_database()` 
   - Saves quiz and questions to `quizzes` and `quiz_questions` tables
   - Associates quiz with `current_user_id`

3. **Save Content to Supabase Storage**
   - Converts text content to bytes: `data.content.encode('utf-8')`
   - Saves as file: `{title}.txt` in user's folder
   - Content type: `text/plain`

4. **Save Metadata**
   - Saves to `quiz_metadata` table
   - Fields: `quiz_id`, `content_type="text"`, `file_name`, `file_type="text/plain"`, `word_count`, `created_by`, `created_at`, `question_count`

---

## Missing Features vs Contract

| Feature | Contract | Actual | Priority |
|---------|----------|--------|----------|
| Quota validation | ✅ Required | ❌ Missing | 🔴 HIGH |
| Tier checking | ✅ Required | ❌ Missing | 🔴 HIGH |
| 75% threshold | ✅ Required | ❌ Missing | 🟡 MEDIUM |
| Min content length | ✅ 10 chars | ❌ Not validated | 🟢 LOW |
| Max title length | ✅ 255 chars | ❌ Not validated | 🟢 LOW |
| Return question count | ✅ Required | ❌ Missing | 🟢 LOW |
| 403 quota exceeded | ✅ Required | ❌ Missing | 🔴 HIGH |
| 400 threshold fail | ✅ Required | ❌ Missing | 🟡 MEDIUM |

---

## Implementation Notes

### Code Location
- **Route**: `api/quiz_routes.py` - Line 62
- **Handler**: `handlers/quiz_handlers.py` - `generate_quiz_from_text()` (Line 207)
- **Schema**: `schemas/quiz.py` - `TextQuizRequest` (Line 94)

### Dependencies
- `services/ai_services/chunking_service.py` - `generate_quizzes_single_async()`
- `services/db_services/supabase_quiz.py` - `save_quiz_to_database()`, `save_metadata()`
- `services/db_services/supabase_file.py` - `save_file_to_supabase()`

### Database Tables Modified
- `quizzes` - Quiz record
- `quiz_questions` - Individual questions
- `quiz_metadata` - Quiz metadata
- Supabase Storage - `{user_id}/{title}.txt`

---

## Test Coverage Status

### Unit Tests
- ⚠️ No dedicated unit tests for this endpoint
- Should test: quota validation (when implemented), content validation, error handling

### Integration Tests  
- ⚠️ No contract tests verifying request/response format
- Should test: end-to-end flow, database persistence, storage upload

---

## Recommendations

1. **Add Quota Validation** (HIGH Priority)
   ```python
   # Before generation
   user_tier_info = get_user_tier_info(current_user_id)
   if user_tier_info["quota_exceeded"]:
       raise HTTPException(
           status_code=403,
           detail={
               "detail": f"Quiz quota exceeded for {user_tier_info['account_tier']} tier...",
               "current_count": user_tier_info["current_quiz_count"],
               "quota_limit": user_tier_info["quota_limit"],
               "user_tier": user_tier_info["account_tier"]
           }
       )
   ```

2. **Add Content Validation** (LOW Priority)
   ```python
   if len(data.content.strip()) < 10:
       raise HTTPException(
           status_code=400,
           detail="Content must be at least 10 characters"
       )
   ```

3. **Add Generation Threshold** (MEDIUM Priority)
   ```python
   if len(quizzes) < (data.num_questions * 0.75):
       raise HTTPException(
           status_code=400,
           detail={
               "detail": f"AI generated only {len(quizzes)}/{data.num_questions} questions (minimum 75% required)",
               "questions_generated": len(quizzes),
               "questions_requested": data.num_questions,
               "threshold": 0.75
           }
       )
   ```

4. **Update Response Format** (LOW Priority)
   - Add `questions_generated` and `questions_requested` fields to match contract

---

**Contract Version**: Actual Implementation as of 2025-10-23 (Corrected)  
**Differs from Spec**: Partially (missing 75% threshold validation, min content length)  
**Production Ready**: ✅ YES - Has quota validation (Line 321) + 10MB size limit (Line 336-340)
