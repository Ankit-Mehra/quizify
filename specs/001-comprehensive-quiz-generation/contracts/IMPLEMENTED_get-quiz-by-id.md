# API Contract: Get Quiz by ID (ACTUAL IMPLEMENTATION)

**Endpoint**: `GET /quiz/{quiz_id}`  
**Module**: Quiz Management  
**Status**: ✅ FULLY IMPLEMENTED  
**Last Updated**: 2025-10-28

---

## Overview

Retrieve complete quiz data including all questions, answers, and metadata. Used for displaying quizzes to users before or during quiz-taking.

---

## Request Specification

**Authentication**: Required (Bearer token)

**Path Parameters**:
- `quiz_id` (UUID, required): Unique identifier of the quiz

**Headers**:
```
Authorization: Bearer {access_token}
```

**Query Parameters**: None

---

## Response Specification

**Response Model**: `QuizzesResponse`

**HTTP Status**: 200 OK

**Success Response**:
```json
{
  "quiz_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "user_id": "760602fe-b19f-472a-b65e-060f9e195529",
  "title": "Python Basics Quiz",
  "created_at": "2025-10-28T10:30:00Z",
  "questions": [
    {
      "question_id": "q1",
      "question_text": "What is a variable in Python?",
      "options": [
        "A container for storing data values",
        "A function that returns data",
        "A type of loop",
        "A class definition"
      ],
      "correct_answer": "A container for storing data values"
    },
    {
      "question_id": "q2",
      "question_text": "Which keyword is used to define a function?",
      "options": [
        "func",
        "define",
        "def",
        "function"
      ],
      "correct_answer": "def"
    }
  ]
}
```

**Response Fields**:

- `quiz_id` (string): UUID of the quiz
- `user_id` (string): UUID of the quiz creator
- `title` (string): Quiz title
- `created_at` (ISO timestamp): When quiz was created
- `questions` (array): List of question objects
  - `question_id` (string): Unique identifier for question within quiz
  - `question_text` (string): The question prompt
  - `options` (array of strings): Answer choices (typically 4 options)
  - `correct_answer` (string): The correct answer (must match one option exactly)

---

## Error Responses

### 401 Unauthorized
```json
{
  "detail": "Not authenticated"
}
```
**Cause**: Missing or invalid Bearer token

### 403 Forbidden
```json
{
  "detail": "You do not have permission to access this quiz"
}
```
**Cause**: User trying to access another user's quiz

### 404 Not Found
```json
{
  "detail": "Quiz not found"
}
```
**Cause**: Quiz ID doesn't exist in database

### 500 Internal Server Error
```json
{
  "detail": "Failed to retrieve quiz: {error_details}"
}
```
**Cause**: Database error or corrupted quiz data

---

## Security Features

### Row-Level Security (RLS)
- Users can only access their own quizzes
- Enforced by Supabase RLS policies on `quizzes` table
- Uses authenticated Supabase client (not service role)

### Access Control
- Quiz ownership verified via `user_id` match
- No public quiz access (all quizzes private by default)

---

## Implementation Details

### Database Query
1. Authenticates user from Bearer token
2. Queries `quizzes` table with user-scoped client
3. Filters by `quiz_id` and implicitly by `user_id` (RLS)
4. Returns quiz JSON from `quiz_data` column

### Data Structure
- Quiz stored as JSONB in `quizzes.quiz_data` column
- Schema validated on generation (not on retrieval)
- Questions array can have variable length (typically 5-10)

### Handler Function
Located in: `handlers/quiz_handlers.py::get_quiz_by_id_handler()`

---

## Usage Examples

### Basic Quiz Retrieval
```bash
curl -X GET "/quiz/a1b2c3d4-e5f6-7890-abcd-ef1234567890" \
  -H "Authorization: Bearer {access_token}"
```

### Using with Frontend
```javascript
// Fetch quiz for display
const response = await fetch(`/quiz/${quizId}`, {
  headers: {
    'Authorization': `Bearer ${accessToken}`
  }
});
const quizData = await response.json();

// Render questions
quizData.questions.forEach(q => {
  console.log(q.question_text);
  q.options.forEach(opt => console.log(`  - ${opt}`));
});
```

---

## Response Schema Reference

### QuizzesResponse
```python
class Question(BaseModel):
    question_id: str
    question_text: str
    options: List[str]
    correct_answer: str

class QuizzesResponse(BaseModel):
    quiz_id: str
    user_id: str
    title: str
    created_at: str
    questions: List[Question]
```

---

## Integration Points

### Quiz Taking Flow
1. **List Quizzes**: `GET /quiz/my-quizzes` → Get available quizzes
2. **Get Quiz Details**: `GET /quiz/{quiz_id}` → Load full quiz
3. **Display to User**: Show questions and options
4. **Submit Answers**: `POST /quiz/{quiz_id}/submit` → Grade quiz

### Content Source Reference
```json
// Quiz metadata (not included in this endpoint)
{
  "content_source_type": "text|file|url",
  "content_source_reference": "file_id or url"
}
```
**Note**: Use `GET /quiz/metadata` to get content source information

---

## Performance Considerations

- **Query Speed**: ~50-100ms (single row lookup by indexed PK)
- **Response Size**: Varies by question count (typically 5-20 KB)
- **Caching**: No caching implemented (always fresh from DB)

---

## Common Use Cases

1. **Quiz Preview**: Display quiz before taking it
2. **Quiz Taking**: Load questions for user to answer
3. **Quiz Review**: Show questions after submission (compare with answers)
4. **Quiz Editing**: Load current quiz for admin edits (future feature)

---

## Testing Considerations

### Test Cases
- ✅ Retrieve own quiz successfully
- ✅ Cannot retrieve another user's quiz (403)
- ✅ Invalid quiz_id returns 404
- ✅ Response matches QuizzesResponse schema
- ✅ All questions have valid structure
- ✅ correct_answer matches one of the options

### Test Data
- Quiz with 5 questions
- Quiz with 10 questions
- Non-existent quiz_id
- Another user's quiz_id

---

## Known Limitations

- No pagination (returns entire quiz, could be large)
- No partial retrieval (can't get just question count)
- No quiz versioning (edits would overwrite)
- No caching (every request hits database)

---

## Future Enhancements

- [ ] Public quiz sharing (optional setting)
- [ ] Quiz preview without authentication
- [ ] Pagination for very large quizzes (>50 questions)
- [ ] Partial response fields (e.g., exclude correct_answer)
- [ ] Quiz edit history/versioning
- [ ] Response caching for performance

---

**Contract Status**: ✅ Complete  
**Security Audit**: ✅ Passed  
**RLS Enforcement**: ✅ Active  
**Production Ready**: ✅ Yes
