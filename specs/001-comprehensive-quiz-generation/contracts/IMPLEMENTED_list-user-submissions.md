# API Contract: List User Submissions

**Status**: ✅ IMPLEMENTED  
**Endpoint**: `GET /submissions`  
**Authentication**: Required (Bearer token)  
**Response Model**: `UserSubmissionsResponse`  
**Version**: 1.0  
**Last Updated**: 2025-10-28

---

## Overview

Retrieves all quiz submissions (attempts) for the authenticated user with summary information. This endpoint allows users to view their complete quiz attempt history across all quizzes.

---

## Request

### HTTP Method
```
GET /submissions
```

### Headers
```http
Authorization: Bearer <jwt_token>
Content-Type: application/json
```

### Query Parameters
None

### Request Body
None (GET request)

---

## Response

### Success Response (200 OK)

```json
## Response

### Success Response (200 OK)

```json
{
  "user_id": "760602fe-b19f-472a-b65e-060f9e195529",
  "total_submissions": 5,
  "submissions": [
    {
      "id": "sub123-...",
      "quiz_id": "quiz456-...",
      "user_id": "760602fe-b19f-472a-b65e-060f9e195529",
      "score": 90,
      "total_questions": 10,
      "correct_count": 9,
      "wrong_count": 1,
      "submitted_at": "2025-10-27T15:00:00Z"
    },
    {
      "id": "sub789-...",
      "quiz_id": "quiz111-...",
      "user_id": "760602fe-b19f-472a-b65e-060f9e195529",
      "score": 75,
      "total_questions": 20,
      "correct_count": 15,
      "wrong_count": 5,
      "submitted_at": "2025-10-26T10:00:00Z"
    }
  ]
}
```

### Response Model

**Type**: `UserSubmissionsResponse`

**Schema Documentation**:
```python
class UserSubmissionsResponse(BaseModel):
    """Response for listing all user's quiz submissions"""
    user_id: str  # User's UUID
    total_submissions: int  # Total number of submissions (>= 0)
    submissions: List[QuizSubmission]  # Ordered by submitted_at DESC
```

### Response Fields
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `user_id` | string (UUID) | Authenticated user's ID |
| `total_submissions` | integer | Total number of submissions found |
| `submissions` | array | List of submission summaries (ordered by most recent first) |
| `submissions[].id` | string (UUID) | Submission ID |
| `submissions[].quiz_id` | string (UUID) | Quiz that was attempted |
| `submissions[].user_id` | string (UUID) | User ID (same as top-level user_id) |
| `submissions[].score` | integer | Score percentage (0-100, rounded to nearest integer) |
| `submissions[].total_questions` | integer | Number of questions in the quiz |
| `submissions[].correct_count` | integer | Number of correct answers |
| `submissions[].wrong_count` | integer | Number of wrong answers |
| `submissions[].submitted_at` | string (ISO 8601) | Submission timestamp |

### Error Responses

#### 401 Unauthorized
```json
{
  "detail": "Authentication required"
}
```

**Cause**: No JWT token provided or token is invalid/expired

#### 500 Internal Server Error
```json
{
  "detail": "Failed to retrieve submissions. Please try again."
}
```

**Cause**: Database error or unexpected server error

---

## Implementation Details

### Authentication
- **JWT Token Required**: Yes
- **Token Validation**: Via `get_current_user_id` dependency
- **User Context**: Automatically filtered by authenticated user ID

### Database Operations

#### Query
```sql
SELECT id, quiz_id, user_id, score, total_questions, correct_count, wrong_count, submitted_at
FROM submissions
WHERE user_id = ?
ORDER BY submitted_at DESC
```

#### RLS Enforcement
- Uses **authenticated Supabase client** with user token
- Row-Level Security ensures users only see their own submissions
- Query explicitly filters by `user_id` from JWT token

### Performance Considerations
- **Indexed Lookup**: `submissions.user_id` should have index
- **Sorting**: `submitted_at DESC` for most recent first
- **No Pagination**: Returns all submissions (consider adding pagination for users with many attempts)
- **Summary Only**: Does NOT include detailed answers (use `GET /submission/{id}` for full details)

### Security
- ✅ **Authentication Required**: JWT token mandatory
- ✅ **Authorization**: Users only see their own submissions (RLS + explicit filter)
- ✅ **No Sensitive Data**: Response excludes correct answers and detailed question data
- ✅ **Rate Limiting**: Should be added at API gateway level

---

## Usage Examples

### cURL
```bash
curl -X GET "https://api.quizify.com/submissions" \
  -H "Authorization: Bearer eyJhbGc..." \
  -H "Content-Type: application/json"
```

### JavaScript (Fetch)
```javascript
const response = await fetch('/submissions', {
  method: 'GET',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  }
});

const data = await response.json();
console.log(`You've attempted ${data.total_submissions} quizzes`);
```

### Python (httpx)
```python
headers = {"Authorization": f"Bearer {token}"}
response = httpx.get("/submissions", headers=headers)
data = response.json()

for submission in data["submissions"]:
    print(f"Quiz {submission['quiz_id']}: {submission['score']}%")
```

---

## Related Endpoints

| Endpoint | Purpose | Relationship |
|----------|---------|--------------|
| `GET /submission/{submission_id}` | Get detailed submission | Get full details of a specific submission |
| `GET /quiz/{quiz_id}/submissions` | List attempts for specific quiz | Filtered version showing only one quiz's attempts |
| `POST /quiz/{quiz_id}/submit` | Submit quiz answers | Creates a new submission |
| `GET /auth/me` | Get user info | Shows `quizzes_attempted` count (total) |

---

## Frontend Integration

### Display User's Quiz History
```javascript
async function showQuizHistory() {
  const response = await fetch('/submissions');
  const data = await response.json();
  
  return (
    <div>
      <h2>Your Quiz History ({data.total_submissions} attempts)</h2>
      <ul>
        {data.submissions.map(sub => (
          <li key={sub.id}>
            Quiz {sub.quiz_id}: {sub.score}% 
            ({sub.correct_count}/{sub.total_questions} correct)
            - {new Date(sub.submitted_at).toLocaleString()}
          </li>
        ))}
      </ul>
    </div>
  );
}
```

### Track Progress Over Time
```javascript
// Group submissions by quiz to show improvement
const submissionsByQuiz = {};
data.submissions.forEach(sub => {
  if (!submissionsByQuiz[sub.quiz_id]) {
    submissionsByQuiz[sub.quiz_id] = [];
  }
  submissionsByQuiz[sub.quiz_id].push(sub);
});

// Show improvement for each quiz
Object.entries(submissionsByQuiz).forEach(([quizId, attempts]) => {
  const scores = attempts.map(a => a.score);
  console.log(`Quiz ${quizId}: Attempts ${scores.length}, Best: ${Math.max(...scores)}%`);
});
```

---

## Testing

### Test Cases

#### 1. **Happy Path**: User with submissions
```bash
# Given: User has 3 quiz attempts
# When: GET /submissions
# Then: Returns 200 with 3 submissions ordered by date (newest first)
```

#### 2. **Empty State**: User with no submissions
```bash
# Given: New user with no quiz attempts
# When: GET /submissions
# Then: Returns 200 with empty submissions array, total_submissions = 0
```

#### 3. **Authentication**: Missing token
```bash
# Given: No Authorization header
# When: GET /submissions
# Then: Returns 401 Unauthorized
```

#### 4. **Authorization**: Cannot see other users' submissions
```bash
# Given: User A and User B both have submissions
# When: User A calls GET /submissions
# Then: Response only contains User A's submissions (RLS enforced)
```

#### 5. **Ordering**: Most recent first
```bash
# Given: User has submissions from different dates
# When: GET /submissions
# Then: Submissions ordered by submitted_at DESC
```

---

## Known Limitations

1. **No Pagination**: Returns all submissions at once
   - **Impact**: Could be slow for users with hundreds of attempts
   - **Mitigation**: Consider adding `?limit=` and `?offset=` query params

2. **No Filtering**: Cannot filter by date range or quiz
   - **Impact**: Users must filter client-side
   - **Mitigation**: Use `GET /quiz/{quiz_id}/submissions` for single-quiz filtering

3. **No Aggregation**: Raw submissions only, no statistics
   - **Impact**: Client must calculate average score, improvement trends, etc.
   - **Mitigation**: Consider adding `GET /submissions/stats` endpoint

4. **No Quiz Metadata**: Response doesn't include quiz title/details
   - **Impact**: Client needs separate quiz lookup for display names
   - **Mitigation**: Could join with quizzes table (performance tradeoff)

---

## Future Enhancements

### Priority 1 (High Value)
- [ ] Add pagination (`?limit=20&offset=0`)
- [ ] Include quiz metadata (title, created_at) in response
- [ ] Add date range filtering (`?start_date=&end_date=`)

### Priority 2 (Medium Value)
- [ ] Add sorting options (`?sort_by=score&order=desc`)
- [ ] Include performance stats (average score, improvement trend)
- [ ] Add quiz filtering (`?quiz_id=xyz`)

### Priority 3 (Nice to Have)
- [ ] Export to CSV functionality
- [ ] Graphical performance charts data
- [ ] Comparison with other users (anonymized)

---

## Change Log

| Date | Version | Changes | Author |
|------|---------|---------|--------|
| 2025-10-28 | 1.1 | Fixed response validation: Added user_id field to submissions array | System |
| 2025-10-28 | 1.0 | Initial implementation | System |

---

## Status Summary

| Aspect | Status | Notes |
|--------|--------|-------|
| Implementation | ✅ Complete | Fully functional |
| Authentication | ✅ Complete | JWT required |
| Authorization | ✅ Complete | RLS enforced |
| Documentation | ✅ Complete | This document |
| Testing | ⚠️ Manual only | Automated tests recommended |
| Performance | ⚠️ Unoptimized | No pagination, could be slow |
| Error Handling | ✅ Complete | 401, 500 handled |
