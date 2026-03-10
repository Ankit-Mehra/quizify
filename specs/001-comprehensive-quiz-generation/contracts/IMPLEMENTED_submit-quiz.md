# API Contract: Submit Quiz (ACTUAL IMPLEMENTATION)

**Endpoint**: `POST /api/quiz/{quiz_id}/submit`  
**Status**: ✅ FULLY IMPLEMENTED  
**Authentication**: Required (Bearer token)  
**Response Model**: `SubmissionResponse`  
**Last Updated**: 2025-10-28

---

## Request

### Headers
```
Authorization: Bearer <jwt_token>
Content-Type: application/json
```

### URL Parameters
- `quiz_id` (UUID): The ID of the quiz being submitted

### Body
```json
{
  "quiz_id": "123e4567-e89b-12d3-a456-426614174000",
  "total_questions": 10,
  "answers": [
    {
      "question_id": "789e4567-e89b-12d3-a456-426614174001",
      "user_answer": "Paris"
    },
    {
      "question_id": "789e4567-e89b-12d3-a456-426614174002",
      "user_answer": "True"
    }
  ]
}
```

### Field Validation (ACTUAL)
- `quiz_id`: **Required**, UUID format
  - ✅ **Must match URL path parameter** (validated, returns 400 if mismatch)
- `total_questions`: **Required**, integer > 0 (validated by Pydantic `gt=0`)
- `answers`: **Required**, array of answer objects
  - `question_id`: **Required**, UUID format
  - `user_answer`: **Required**, string (any format accepted)

### Validation Rules
1. ✅ **Quiz ID Consistency**: Body `quiz_id` must match URL path `quiz_id`
2. ✅ **Quiz Exists**: Quiz must exist in database (returns 404 if not found)
3. ✅ **Total Questions**: Must be positive integer
4. ✅ **Question IDs**: Must exist in database (invalid questions skipped in evaluation)
5. ✅ **Authorization**: User must be authenticated (JWT token required)

---

## Response

### Success Response (200 OK)
```json
{
  "id": "abc12345-e89b-12d3-a456-426614174999",
  "total_questions": 10,
  "correct_count": 7,
  "wrong_count": 3,
  "score": 70,
  "detailed_results": [
    {
      "question_id": "789e4567-e89b-12d3-a456-426614174001",
      "question": "What is the capital of France?",
      "your_answer": "Paris",
      "correct_answer": "Paris",
      "is_correct": true
    },
    {
      "question_id": "789e4567-e89b-12d3-a456-426614174002",
      "question": "Python is a compiled language",
      "your_answer": "True",
      "correct_answer": "False",
      "is_correct": false
    }
  ]
}
```

### Response Fields
- `id` (UUID): Submission ID for future reference
- `total_questions` (int): Total number of questions in quiz
- `correct_count` (int): Number of correct answers
- `wrong_count` (int): Number of wrong answers
- `score` (int): Percentage score (0-100), rounded to nearest integer
- `detailed_results` (array): Detailed results for each question
  - `question_id` (UUID): Question identifier
  - `question` (string): Question text
  - `your_answer` (string): User's submitted answer
  - `correct_answer` (string): Correct answer
  - `is_correct` (boolean): Whether answer was correct

---

## Error Responses

### 400 Bad Request - Quiz ID Mismatch
```json
{
  "detail": "Quiz ID in URL does not match quiz ID in request body"
}
```
**Cause**: Path parameter `quiz_id` doesn't match body `quiz_id`

---

### 401 Unauthorized
```json
{
  "detail": "Not authenticated"
}
```
**Cause**: Missing or invalid JWT token

---

### 404 Not Found - Quiz Not Found
```json
{
  "detail": "Quiz not found. Please verify the quiz ID."
}
```
**Cause**: Quiz with given `quiz_id` doesn't exist in database

---

### 422 Unprocessable Entity
```json
{
  "detail": [
    {
      "loc": ["body", "total_questions"],
      "msg": "ensure this value is greater than 0",
      "type": "value_error.number.not_gt"
    }
  ]
}
```
**Cause**: Validation errors (e.g., `total_questions` ≤ 0, invalid UUID format)

---

### 500 Internal Server Error
```json
{
  "detail": "Error processing questions"
}
```
**Cause**: Database error fetching questions or parsing question models

---

## Implementation Details

### Answer Evaluation Logic
1. **Fetch Questions**: Retrieves all questions by their IDs from database
2. **Parse Models**: Converts raw database records to typed Pydantic models
3. **Case-Insensitive Matching**: Compares answers after `.strip().lower()`
4. **Score Calculation**: `(correct / total_questions) * 100`, rounded to integer
5. **Database Storage**: 
   - Saves submission to `submissions` table
   - Saves each answer to `answers` table with correctness flag

### Question Type Support
Supports all 4 question types:
- ✅ `multiple_choice` → `MCQQuestion`
- ✅ `true_false` → `TrueFalseQuestion`
- ✅ `fill_blank` → `FillBlankQuestion`
- ✅ `matching` → `MatchingQuestion`

### Scoring Logic
```python
# Answer comparison (case-insensitive)
is_correct = str(user_answer).strip().lower() == str(correct_answer).strip().lower()

# Score calculation (integer percentage)
score = int(round((correct / total_questions) * 100))
```

### Database Operations
1. **Submission Record**: Saved to `submissions` table
   - Fields: `id`, `user_id`, `quiz_id`, `correct_count`, `wrong_count`, `score`, `total_questions`, `submitted_at`
2. **Answer Records**: Saved to `answers` table (one per question)
   - Fields: `id`, `submission_id`, `question_id`, `user_answer`, `correct_answer`, `is_correct`

---

## Authorization

### User ID Extraction
- JWT token decoded to extract `user_id` (from `sub` claim)
- User ID stored as UUID in submission record
- Used for ownership verification when retrieving submissions

### Access Control
- ✅ **Create Submission**: Any authenticated user can submit any quiz
- ✅ **View Submission**: Users can only view their own submissions (enforced in GET endpoint)

---

## Edge Cases Handled

### Missing Questions
If a `question_id` in submission doesn't exist or fails parsing:
- ⚠️ Question is **skipped** (not counted as wrong)
- Warning logged: `"Unknown question type"` or `"Failed to parse question"`
- Submission continues processing remaining questions

**Impact**: If user submits answers for non-existent questions, they won't be scored (neither correct nor wrong).

### Malformed Question Data
If database returns invalid question structure:
- ⚠️ Pydantic `ValidationError` caught
- Question skipped with warning log
- Submission continues

---

## Performance Considerations

### Current Performance
- ✅ **Batch Question Fetch**: All questions fetched in single DB query
- ✅ **Async Handler**: Non-blocking request handling
- ⚠️ **No Timeout**: Could hang on large submissions
- ⚠️ **No Rate Limiting**: Users can submit unlimited times

### Scalability
- **Small Quizzes** (≤20 questions): ~200-500ms response time
- **Medium Quizzes** (20-50 questions): ~500-1000ms response time
- **Database Load**: 1 quiz lookup + 1 question batch fetch + 1 submission insert + N answer inserts

---

## Example Usage

### Valid Submission (All Correct)
**Request**:
```bash
curl -X POST "https://api.quizify.com/api/quiz/123e4567-e89b-12d3-a456-426614174000/submit" \
  -H "Authorization: Bearer eyJhbGc..." \
  -H "Content-Type: application/json" \
  -d '{
    "quiz_id": "123e4567-e89b-12d3-a456-426614174000",
    "total_questions": 3,
    "answers": [
      {"question_id": "q1", "user_answer": "Paris"},
      {"question_id": "q2", "user_answer": "True"},
      {"question_id": "q3", "user_answer": "42"}
    ]
  }'
```

**Response**: 200 OK with score=100 (if all answers correct)

---

### Invalid Submission (Quiz ID Mismatch)
**Request**:
```json
{
  "quiz_id": "different-uuid",
  "total_questions": 3,
  "answers": [...]
}
```

**Response**: 400 Bad Request
```json
{
  "detail": "Quiz ID in URL does not match quiz ID in request body"
}
```

---

## Known Limitations

1. ⚠️ **No Duplicate Prevention**: User can submit same quiz multiple times
2. ⚠️ **No Time Tracking**: Doesn't track quiz start time or duration
3. ⚠️ **Missing Questions Not Counted**: If question IDs are invalid, they're silently skipped
4. ⚠️ **No Partial Credit**: Answers are either 100% correct or wrong (no fuzzy matching)
5. ⚠️ **Case-Sensitive for Non-Text**: Numeric answers compared as strings (could cause issues)

---

## Recommendations

### HIGH Priority
1. **Add Duplicate Prevention**: Check if user already submitted this quiz (or allow retakes with tracking)
2. **Fix Missing Question Handling**: Count missing questions as wrong, or return 400 error

### MEDIUM Priority
3. **Add Time Tracking**: Record quiz start/end times for analytics
4. **Improve Answer Comparison**: Use type-aware comparison (e.g., numeric tolerance for numbers)
5. **Add Rate Limiting**: Prevent submission spam

### LOW Priority
6. **Add Partial Credit**: Support fuzzy matching for text answers
7. **Add Quiz Attempt Limit**: Enforce max attempts per quiz

---

**Contract Version**: Actual Implementation as of 2025-10-23  
**Differs from Spec**: N/A (no original spec existed)  
**Production Ready**: ✅ YES - Core functionality works, but lacks duplicate prevention

