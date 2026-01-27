# Submission Review Feature - Frontend Integration Guide

## Overview
New endpoint to allow users to review their quiz submissions with detailed answers, explanations, and learning feedback.

## New Endpoint

### `GET /api/submission/{submission_id}/review`

**Purpose:** Retrieve detailed review of a quiz submission showing which questions were answered correctly/incorrectly with full explanations.

**Authorization:** Bearer token required. Users can only access their own submissions.

---

## Request

```http
GET /api/submission/3bb9f910-86fb-4654-b2d4-d71f0083980a/review
Authorization: Bearer <jwt_token>
```

---

## Response Schema

```typescript
interface SubmissionReviewResponse {
  submission_id: string;        // UUID
  quiz_id: string;              // UUID
  quiz_title: string | null;    // Quiz title
  user_id: string;              // UUID
  score: number;                // Percentage 0-100
  correct_count: number;        // Number of correct answers
  wrong_count: number;          // Number of wrong answers
  total_questions: number;      // Total questions answered
  submitted_at: string;         // ISO 8601 timestamp
  questions: QuestionReviewDetail[];
}

interface QuestionReviewDetail {
  question_id: string;                           // UUID
  question_type: string;                         // "multiple_choice" | "true_false" | "fill_blank" | "matching" | "unknown"
  question: string;                              // Question text (may be "[Question no longer available]" if deleted)
  your_answer: string | boolean | number[];     // User's submitted answer
  correct_answer: string | boolean | number[];  // Correct answer
  is_correct: boolean;                           // Whether answer was correct
  explanation: string;                           // Explanation of correct answer (empty string if not available)
  
  // Optional fields (enhanced quiz mode)
  options?: string[] | null;                     // Answer options (for MCQ)
  distractor_explanations?: Record<string, string> | null;  // Explanations for incorrect options
  bloom_level?: string | null;                   // "remember" | "understand" | "apply" | "analyze" | "evaluate" | "create"
  difficulty?: string | null;                    // "easy" | "medium" | "hard"
  concept_name?: string | null;                  // Concept being tested
}
```

---

## Response Example

```json
{
  "submission_id": "3bb9f910-86fb-4654-b2d4-d71f0083980a",
  "quiz_id": "9df26852-dadd-42a4-b443-730a34174647",
  "quiz_title": "Geography Quiz - Countries & Development",
  "user_id": "ad52acf7-506b-43a3-bc57-35334c14b0d4",
  "score": 90,
  "correct_count": 9,
  "wrong_count": 1,
  "total_questions": 10,
  "submitted_at": "2026-01-26T17:44:24.117211Z",
  "questions": [
    {
      "question_id": "36b30895-59a3-4eb0-bac6-d9f3e0799edf",
      "question_type": "multiple_choice",
      "question": "What is a characteristic of a developing country?",
      "your_answer": "Low income jobs",
      "correct_answer": "Low income jobs",
      "is_correct": true,
      "explanation": "Developing countries are typically defined by their low economic status and limited access to resources. Low income jobs are a common trait in these nations.",
      "options": ["High education", "Universal healthcare", "Low income jobs", "Good economy"],
      "distractor_explanations": null,
      "bloom_level": null,
      "difficulty": "medium",
      "concept_name": null
    },
    {
      "question_id": "ece6c5d2-5a9b-41ff-9e10-eaee32713e38",
      "question_type": "true_false",
      "question": "Is the goal of NATO to allow Canada to trade with other countries?",
      "your_answer": "True",
      "correct_answer": "false",
      "is_correct": false,
      "explanation": "NATO's primary goal is not trade, but rather a military alliance for collective defense. The provided text incorrectly states that NATO stands for North Atlantic Trade Organization, when in fact it stands for North Atlantic Treaty Organization.",
      "options": null,
      "distractor_explanations": null,
      "bloom_level": null,
      "difficulty": "medium",
      "concept_name": null
    }
  ]
}
```

---

## Error Responses

### 401 Unauthorized
```json
{
  "detail": "Authentication required"
}
```

### 403 Forbidden
```json
{
  "detail": "You are not authorized to access this submission"
}
```

### 404 Not Found
```json
{
  "detail": "Submission 3bb9f910-86fb-4654-b2d4-d71f0083980a not found"
}
```

---

## Edge Cases & Defensive Handling

### Deleted Questions
If a question was deleted after the submission, the review will still show the answer record with:
- `question_type`: `"unknown"`
- `question`: `"[Question no longer available]"`
- `explanation`: `""` (empty string)
- All optional fields: `null`

**Frontend should handle this gracefully:**
```tsx
{question.question_type === 'unknown' && (
  <div className="deleted-question-notice">
    This question is no longer available. Your answer was recorded as{' '}
    {question.is_correct ? 'correct' : 'incorrect'}.
  </div>
)}
```

### Empty Explanations
Some questions may not have explanations (especially older quizzes). Check for empty string:
```tsx
{question.explanation && question.explanation.length > 0 && (
  <div className="explanation">
    <strong>Explanation:</strong>
    <p>{question.explanation}</p>
  </div>
)}
```

### Answer Type Handling
Different question types return different answer formats:
- **multiple_choice**: `string` (e.g., `"Option A"`)
- **true_false**: `string` (`"True"` or `"False"`) - stored as strings in answers table
- **fill_blank**: `string` (e.g., `"photosynthesis"`)
- **matching**: `string` (JSON array e.g., `"[1,0,2,3]"`) - stored as JSON string

**Frontend should normalize for display:**
```tsx
function formatAnswer(answer: string | boolean | number[], questionType: string): string {
  if (questionType === 'matching' && typeof answer === 'string') {
    try {
      const parsed = JSON.parse(answer);
      return Array.isArray(parsed) ? parsed.join(', ') : answer;
    } catch {
      return answer;
    }
  }
  return String(answer);
}
```

---

## Frontend Implementation Guide

### 1. Fetch Submission Review After Quiz Completion

```typescript
async function getSubmissionReview(submissionId: string): Promise<SubmissionReviewResponse> {
  const response = await fetch(`/api/submission/${submissionId}/review`, {
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${authToken}`,
      'Content-Type': 'application/json'
    }
  });
  
  if (!response.ok) {
    throw new Error(`Failed to fetch review: ${response.statusText}`);
  }
  
  return response.json();
}
```

### 2. Display Review UI

```tsx
function SubmissionReview({ submissionId }: { submissionId: string }) {
  const [review, setReview] = useState<SubmissionReviewResponse | null>(null);
  
  useEffect(() => {
    getSubmissionReview(submissionId).then(setReview);
  }, [submissionId]);
  
  if (!review) return <Loading />;
  
  return (
    <div className="submission-review">
      <h1>{review.quiz_title}</h1>
      <div className="score-summary">
        <div className="score">{review.score}%</div>
        <div className="stats">
          ✅ {review.correct_count} correct | ❌ {review.wrong_count} wrong
        </div>
      </div>
      
      <div className="questions">
        {review.questions.map((q, idx) => (
          <QuestionReviewCard key={q.question_id} question={q} index={idx + 1} />
        ))}
      </div>
    </div>
  );
}

function QuestionReviewCard({ question, index }: { question: QuestionReviewDetail; index: number }) {
  return (
    <div className={`question-card ${question.is_correct ? 'correct' : 'incorrect'}`}>
      <div className="question-header">
        <span className="question-number">Question {index}</span>
        <span className={`result-badge ${question.is_correct ? 'correct' : 'incorrect'}`}>
          {question.is_correct ? '✓ Correct' : '✗ Incorrect'}
        </span>
      </div>
      
      <h3>{question.question}</h3>
      
      {question.options && (
        <div className="options">
          {question.options.map(option => (
            <div 
              key={option}
              className={`
                option 
                ${option === question.correct_answer ? 'correct-answer' : ''}
                ${option === question.your_answer && !question.is_correct ? 'wrong-answer' : ''}
              `}
            >
              {option}
              {option === question.your_answer && <span className="badge">Your Answer</span>}
              {option === question.correct_answer && <span className="badge">Correct</span>}
            </div>
          ))}
        </div>
      )}
      
      {!question.is_correct && (
        <div className="answer-comparison">
          <div className="your-answer">
            <strong>Your Answer:</strong> {String(question.your_answer)}
          </div>
          <div className="correct-answer">
            <strong>Correct Answer:</strong> {String(question.correct_answer)}
          </div>
        </div>
      )}
      
      <div className="explanation">
        <strong>Explanation:</strong>
        <p>{question.explanation}</p>
      </div>
      
      {question.distractor_explanations && !question.is_correct && (
        <div className="distractor-explanations">
          <strong>Why other options are incorrect:</strong>
          <ul>
            {Object.entries(question.distractor_explanations).map(([option, explanation]) => (
              <li key={option}>
                <strong>{option}:</strong> {explanation}
              </li>
            ))}
          </ul>
        </div>
      )}
      
      {question.bloom_level && (
        <div className="metadata">
          <span className="bloom-level">Bloom Level: {question.bloom_level}</span>
          {question.difficulty && <span className="difficulty">Difficulty: {question.difficulty}</span>}
          {question.concept_name && <span className="concept">Concept: {question.concept_name}</span>}
        </div>
      )}
    </div>
  );
}
```

### 3. Navigation Flow

```
User Flow:
1. User completes quiz → POST /api/quiz/{id}/submit
2. Get submission_id from response
3. Navigate to review page: /submissions/{submission_id}/review
4. Fetch detailed review: GET /api/submission/{submission_id}/review
5. Display review with color-coded correct/incorrect answers
6. Show explanations for all questions
```

### 4. Styling Recommendations

```css
.question-card.correct {
  border-left: 4px solid #10b981;  /* Green */
  background: #ecfdf5;
}

.question-card.incorrect {
  border-left: 4px solid #ef4444;  /* Red */
  background: #fef2f2;
}

.option.correct-answer {
  background: #d1fae5;
  border: 2px solid #10b981;
}

.option.wrong-answer {
  background: #fee2e2;
  border: 2px solid #ef4444;
}

.explanation {
  background: #f3f4f6;
  padding: 12px;
  border-radius: 4px;
  margin-top: 12px;
}
```

---

## Use Cases

### 1. Post-Submission Review
After submitting a quiz, immediately show the review screen with all answers and explanations.

### 2. Historical Review
Allow users to revisit past submissions from their submission history:
- GET `/api/submissions` → List all submissions
- Click on submission → Navigate to review page
- GET `/api/submission/{id}/review` → Show full review

### 3. Learning Dashboard
Aggregate review data to show:
- Most missed question types
- Concepts that need improvement
- Bloom levels where user struggles
- Difficulty trends

---

## Backend Implementation Details

### Database Queries
- Joins `submissions`, `answers`, and `questions` tables
- Fetches all question metadata (explanation, options, distractor_explanations, bloom_level, difficulty, concept_name)
- Enforces RLS policies - users can only access their own submissions

### Performance
- Two set-based queries to fetch all data (no per-question N+1 queries)
- Returns full question details in a single API response
- No additional API calls needed for explanations

### Security
- JWT authentication required
- Authorization check: user_id must match submission.user_id
- RLS policies enforced via authenticated Supabase client

---

## Testing

### Manual Testing with cURL

```bash
# 1. Submit a quiz
curl -X POST "http://localhost:8000/api/quiz/{quiz_id}/submit" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "quiz_id": "...",
    "total_questions": 5,
    "answers": [...]
  }'

# 2. Get submission review (use submission_id from step 1)
curl -X GET "http://localhost:8000/api/submission/{submission_id}/review" \
  -H "Authorization: Bearer ${TOKEN}"
```

### Expected Response
- 200 OK with full review including all questions and explanations
- Each question shows: question text, user answer, correct answer, is_correct flag, explanation
- Enhanced quizzes also include: distractor_explanations, bloom_level, difficulty, concept_name

---

## Migration Notes

### Database Schema (Already Exists)
✅ `submissions` table - stores submission summary
✅ `answers` table - stores individual answers with correctness
✅ `questions` table - stores question details and explanations

**No database migrations needed** - this feature uses existing schema.

### API Versioning
This is a **new endpoint** - no breaking changes to existing endpoints.

---

## Related Endpoints

| Endpoint | Purpose | Returns Detailed Answers |
|----------|---------|-------------------------|
| `POST /api/quiz/{id}/submit` | Submit quiz answers | ✅ Yes (immediate feedback) |
| `GET /api/submission/{id}` | Get submission summary | ❌ No (score only) |
| `GET /api/submission/{id}/review` | **Get detailed review** | ✅ **Yes (with explanations)** |
| `GET /api/submissions` | List all user submissions | ❌ No (summaries only) |
| `GET /api/quiz/{id}/submissions` | List quiz attempts | ❌ No (summaries only) |

---

## Future Enhancements

### Potential Additions
- Pagination for quizzes with >50 questions
- Filter review by correct/incorrect/specific concepts
- Bookmark questions for later review
- Export review as PDF
- Share review link with teachers
- Compare multiple attempts side-by-side
- Analytics: time spent per question (requires client-side tracking)

---

## Support

**Questions?** Contact the backend team or refer to:
- API docs: `/docs` (FastAPI Swagger UI)
- Schema definitions: `schemas/submission.py`
- Database service: `services/db_services/supabase_submission.py`
