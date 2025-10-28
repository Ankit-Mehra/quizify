# API Contract: List Quiz Submissions

**Status**: ✅ IMPLEMENTED  
**Endpoint**: `GET /quiz/{quiz_id}/submissions`  
**Authentication**: Required (Bearer token)  
**Response Model**: `QuizSubmissionsResponse`  
**Version**: 1.0  
**Last Updated**: 2025-10-28

---

## Overview

Retrieves all attempts (submissions) for a specific quiz by the authenticated user. This endpoint is useful for tracking progress on a particular quiz, showing improvement over multiple attempts.

---

## Request

### HTTP Method
```
GET /quiz/{quiz_id}/submissions
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `quiz_id` | string (UUID) | ✅ Yes | The quiz ID to get submissions for |

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
{
  "quiz_id": "quiz789-abc123-...",
  "user_id": "760602fe-b19f-472a-b65e-060f9e195529",
  "total_attempts": 2,
  "submissions": [
    {
      "id": "sub123-...",
      "quiz_id": "quiz789-...",
      "user_id": "760602fe-b19f-472a-b65e-060f9e195529",
      "score": 90.0,
      "total_questions": 10,
      "correct_count": 9,
      "wrong_count": 1,
      "submitted_at": "2025-10-27T15:00:00Z"
    },
    {
      "id": "sub456-...",
      "quiz_id": "quiz789-...",
      "user_id": "760602fe-b19f-472a-b65e-060f9e195529",
      "score": 70.0,
      "total_questions": 10,
      "correct_count": 7,
      "wrong_count": 3,
      "submitted_at": "2025-10-26T10:00:00Z"
    }
  ]
}
```

### Response Model

**Type**: `QuizSubmissionsResponse`

**Schema Documentation**:
```python
class QuizSubmissionsResponse(BaseModel):
    """Response for listing all attempts for a specific quiz"""
    quiz_id: str  # Quiz UUID
    user_id: str  # User's UUID
    total_attempts: int  # Number of attempts on this quiz (>= 0)
    submissions: List[QuizSubmission]  # Ordered by submitted_at DESC
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `quiz_id` | string (UUID) | The quiz ID from the request |
| `user_id` | string (UUID) | Authenticated user's ID |
| `total_attempts` | integer | Number of times user attempted this quiz |
| `submissions` | array | List of submissions (ordered by most recent first) |
| `submissions[].id` | string (UUID) | Submission ID |
| `submissions[].quiz_id` | string (UUID) | Quiz ID (same as parent) |
| `submissions[].user_id` | string (UUID) | User ID (same as top-level user_id) |
| `submissions[].score` | integer | Score percentage (0-100, rounded to nearest integer) |
| `submissions[].total_questions` | integer | Number of questions |
| `submissions[].correct_count` | integer | Correct answers |
| `submissions[].wrong_count` | integer | Wrong answers |
| `submissions[].submitted_at` | string (ISO 8601) | Submission timestamp |

### Empty State (200 OK)
```json
{
  "quiz_id": "quiz789-...",
  "user_id": "760602fe-...",
  "total_attempts": 0,
  "submissions": []
}
```

**When**: User hasn't attempted this quiz yet

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
  "detail": "Failed to retrieve quiz submissions. Please try again."
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
SELECT id, quiz_id, score, total_questions, correct_count, wrong_count, submitted_at
FROM submissions
WHERE quiz_id = ? AND user_id = ?
ORDER BY submitted_at DESC
```

#### RLS Enforcement
- Uses **authenticated Supabase client** with user token
- Row-Level Security ensures users only see their own submissions
- Query filters by both `quiz_id` (from path) and `user_id` (from JWT)

### Performance Considerations
- **Composite Index**: `submissions(quiz_id, user_id, submitted_at DESC)` recommended
- **Sorting**: Most recent attempts first for progress tracking
- **Lightweight**: Summary data only (no detailed answers)
- **Scoped Query**: Filtered to single quiz (faster than all submissions)

### Security
- ✅ **Authentication Required**: JWT token mandatory
- ✅ **Authorization**: Users only see their own attempts (RLS + explicit filter)
- ✅ **Quiz Validation**: No validation if quiz exists (returns empty array)
- ✅ **No Cross-User Leakage**: Cannot see other users' attempts on same quiz

---

## Usage Examples

### cURL
```bash
curl -X GET "https://api.quizify.com/quiz/abc123-def456/submissions" \
  -H "Authorization: Bearer eyJhbGc..." \
  -H "Content-Type: application/json"
```

### JavaScript (Fetch)
```javascript
const quizId = 'abc123-def456-...';
const response = await fetch(`/quiz/${quizId}/submissions`, {
  method: 'GET',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  }
});

const data = await response.json();
console.log(`You've attempted this quiz ${data.total_attempts} times`);
```

### Python (httpx)
```python
quiz_id = "abc123-def456-..."
headers = {"Authorization": f"Bearer {token}"}
response = httpx.get(f"/quiz/{quiz_id}/submissions", headers=headers)
data = response.json()

# Show improvement over attempts
for i, submission in enumerate(data["submissions"], 1):
    print(f"Attempt {i}: {submission['score']}%")
```

---

## Related Endpoints

| Endpoint | Purpose | Relationship |
|----------|---------|--------------|
| `GET /submissions` | List all user submissions | Broader view (all quizzes) |
| `GET /submission/{submission_id}` | Get detailed submission | Get full details of a specific attempt |
| `POST /quiz/{quiz_id}/submit` | Submit quiz answers | Creates a new submission for this quiz |
| `GET /quiz/{quiz_id}` | Get quiz details | Get the quiz being attempted |

---

## Frontend Integration

### Show Quiz Attempt History
```javascript
async function showQuizAttempts(quizId) {
  const response = await fetch(`/quiz/${quizId}/submissions`);
  const data = await response.json();
  
  return (
    <div>
      <h3>Your Attempts ({data.total_attempts})</h3>
      {data.submissions.length === 0 ? (
        <p>You haven't attempted this quiz yet.</p>
      ) : (
        <ul>
          {data.submissions.map((sub, index) => (
            <li key={sub.id}>
              Attempt {data.total_attempts - index}: {sub.score}% 
              ({sub.correct_count}/{sub.total_questions})
              - {new Date(sub.submitted_at).toLocaleString()}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

### Track Improvement
```javascript
function calculateImprovement(submissions) {
  if (submissions.length < 2) return null;
  
  const scores = submissions.map(s => s.score).reverse(); // Oldest to newest
  const firstScore = scores[0];
  const lastScore = scores[scores.length - 1];
  const improvement = lastScore - firstScore;
  
  return {
    firstScore,
    lastScore,
    improvement,
    improvedPercentage: ((improvement / firstScore) * 100).toFixed(1)
  };
}

// Usage
const improvement = calculateImprovement(data.submissions);
if (improvement && improvement.improvement > 0) {
  console.log(`You improved by ${improvement.improvement}% (${improvement.improvedPercentage}% increase)`);
}
```

### Show Best Score
```javascript
function getBestAttempt(submissions) {
  if (submissions.length === 0) return null;
  
  return submissions.reduce((best, current) => 
    current.score > best.score ? current : best
  );
}

const bestAttempt = getBestAttempt(data.submissions);
console.log(`Your best score: ${bestAttempt.score}%`);
```

---

## Testing

### Test Cases

#### 1. **Happy Path**: User with multiple attempts
```bash
# Given: User attempted quiz 3 times
# When: GET /quiz/{quiz_id}/submissions
# Then: Returns 200 with 3 submissions ordered by date (newest first)
```

#### 2. **First Attempt**: User hasn't attempted quiz
```bash
# Given: User has never attempted this quiz
# When: GET /quiz/{quiz_id}/submissions
# Then: Returns 200 with empty submissions array, total_attempts = 0
```

#### 3. **Authentication**: Missing token
```bash
# Given: No Authorization header
# When: GET /quiz/{quiz_id}/submissions
# Then: Returns 401 Unauthorized
```

#### 4. **Authorization**: Cannot see other users' attempts
```bash
# Given: User A and User B both attempted same quiz
# When: User A calls GET /quiz/{quiz_id}/submissions
# Then: Response only contains User A's submissions (not User B's)
```

#### 5. **Non-existent Quiz**: Quiz doesn't exist
```bash
# Given: quiz_id doesn't exist in database
# When: GET /quiz/{quiz_id}/submissions
# Then: Returns 200 with empty array (no error)
```

#### 6. **Ordering**: Newest first
```bash
# Given: User attempted quiz on 3 different dates
# When: GET /quiz/{quiz_id}/submissions
# Then: Submissions ordered by submitted_at DESC (most recent first)
```

---

## Use Cases

### 1. **Progress Tracking**
Show users their improvement on a specific quiz over time:
```
Attempt 1: 60% → Attempt 2: 75% → Attempt 3: 90%
```

### 2. **Quiz Retake Button**
Enable/disable retake based on attempts:
```javascript
const attempts = data.total_attempts;
const bestScore = Math.max(...data.submissions.map(s => s.score));

if (bestScore === 100) {
  showMessage("Perfect score! You mastered this quiz!");
} else if (attempts >= 3) {
  showMessage(`You've tried ${attempts} times. Best score: ${bestScore}%`);
} else {
  showButton("Try Again");
}
```

### 3. **Learning Analytics**
Identify which quizzes need more practice:
```javascript
// Get all quizzes user attempted
const allQuizzes = await fetch('/quiz/my-quizzes').then(r => r.json());

// For each quiz, get attempt history
const quizAnalytics = await Promise.all(
  allQuizzes.map(async quiz => {
    const attempts = await fetch(`/quiz/${quiz.id}/submissions`).then(r => r.json());
    const avgScore = attempts.submissions.reduce((sum, s) => sum + s.score, 0) / attempts.total_attempts;
    
    return {
      quizId: quiz.id,
      title: quiz.title,
      attempts: attempts.total_attempts,
      avgScore: avgScore.toFixed(1)
    };
  })
);

// Sort by average score to find weakest areas
const needsPractice = quizAnalytics
  .filter(q => q.avgScore < 70)
  .sort((a, b) => a.avgScore - b.avgScore);
```

---

## Known Limitations

1. **No Quiz Validation**: Doesn't check if quiz_id exists
   - **Impact**: Returns empty array for invalid quiz IDs
   - **Mitigation**: Client should validate quiz exists before calling

2. **No Pagination**: Returns all attempts at once
   - **Impact**: Could be slow if user attempted quiz hundreds of times
   - **Mitigation**: Unlikely scenario (most users attempt 1-5 times)

3. **No Date Filtering**: Cannot filter by date range
   - **Impact**: Client must filter client-side
   - **Mitigation**: Low priority (quiz-specific queries are already scoped)

4. **No Quiz Metadata**: Response doesn't include quiz title
   - **Impact**: Client needs separate quiz lookup
   - **Mitigation**: Client typically already has quiz object from context

---

## Future Enhancements

### Priority 1 (High Value)
- [ ] Include quiz metadata (title, created_at) in response
- [ ] Add statistics (average score, improvement trend)
- [ ] Highlight best attempt in response

### Priority 2 (Medium Value)
- [ ] Add pagination for users with many attempts
- [ ] Include time spent per attempt (if tracked)
- [ ] Compare with other users' performance (anonymized)

### Priority 3 (Nice to Have)
- [ ] Date range filtering
- [ ] Export to CSV
- [ ] Visual progress chart data

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
| Performance | ✅ Good | Scoped to single quiz |
| Error Handling | ✅ Complete | 401, 500 handled |
