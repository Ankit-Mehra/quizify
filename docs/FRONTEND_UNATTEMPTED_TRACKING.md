# Unattempted Question Tracking - Frontend Integration Guide

**Feature**: Enhanced submission tracking to distinguish between wrong answers and unattempted questions  
**Date**: 2026-02-05  
**PR**: #195  
**Status**: ✅ Implemented and Tested

---

## Overview

Submissions now track **unattempted/skipped questions** separately from wrong answers, enabling users to distinguish between:
- Questions they **answered incorrectly** (wrong_count)
- Questions they **intentionally skipped** (unattempted_count)

This improves user experience by providing more accurate feedback and analytics.

---

## Summary of Changes

### New Fields Added (All Backward Compatible)

| Schema | New Field | Type | Default | Description |
|--------|-----------|------|---------|-------------|
| `SubmissionResponse` | `unattempted_count` | `int` | `0` | Number of unattempted questions |
| `QuizSubmission` | `unattempted_count` | `int` | `0` | Number of unattempted questions |
| `SubmissionReviewResponse` | `unattempted_count` | `int` | `0` | Number of unattempted questions |
| `DetailedResult` | `is_unattempted` | `bool` | `false` | Whether this question was skipped |
| `QuestionReviewDetail` | `is_unattempted` | `bool` | `false` | Whether this question was skipped |

### Score Calculation Change

**Previous Formula**:
```
score = correct / (correct + wrong) * 100
```

**New Formula** (Option B - prevents gaming):
```
score = correct / (correct + wrong + unattempted) * 100
```

**Example**:
- 6 correct, 2 wrong, 2 unattempted
- Score = 6 / (6 + 2 + 2) = 60%

---

## Type-Aware Unattempted Detection

The backend now uses type-aware logic to detect unattempted questions:

| Question Type | Unattempted Condition | Notes |
|--------------|----------------------|--------|
| `multiple_choice` | Empty string (`""`), `null`, or whitespace-only | |
| `fill_blank` | Empty string (`""`), `null`, or whitespace-only | |
| `true_false` | `null`, empty string, or non-boolean string | `false` is a **valid answer** |
| `matching` | Empty list (`[]`), `null`, or all values are `-1` | `[0,0,0,0]` is **valid** (first option selected) |

---

## API Contract Changes

### 1. POST `/api/quiz/{quiz_id}/submit`

#### Response Schema (Updated)

```typescript
interface SubmissionResponse {
  id: string;                   // UUID
  total_questions: number;      // Total questions (gt 0)
  correct_count: number;        // Number correct (ge 0)
  wrong_count: number;          // Number wrong - attempted but incorrect (ge 0)
  unattempted_count: number;    // 🆕 Number unattempted/skipped (ge 0, default 0)
  score: number;                // Percentage 0-100 (includes unattempted in denominator)
  detailed_results: DetailedResult[];
}

interface DetailedResult {
  question_id: string;                          // UUID
  question_type: string;                        // "multiple_choice" | "true_false" | "fill_blank" | "matching"
  question: string;                             // Question text
  your_answer: string | boolean | number[];    // User's submitted answer
  correct_answer: string | boolean | number[]; // Correct answer
  is_correct: boolean;                          // Whether answer was correct
  is_unattempted: boolean;                      // 🆕 Whether question was skipped (default false)
}
```

#### Example Response

```json
{
  "id": "3bb9f910-86fb-4654-b2d4-d71f0083980a",
  "total_questions": 10,
  "correct_count": 6,
  "wrong_count": 2,
  "unattempted_count": 2,
  "score": 60,
  "detailed_results": [
    {
      "question_id": "a1b2c3d4-...",
      "question_type": "multiple_choice",
      "question": "What is the capital of France?",
      "your_answer": "Paris",
      "correct_answer": "Paris",
      "is_correct": true,
      "is_unattempted": false
    },
    {
      "question_id": "e5f6g7h8-...",
      "question_type": "fill_blank",
      "question": "The process by which plants make food is called _____.",
      "your_answer": "photosynthesis",
      "correct_answer": "photosynthesis",
      "is_correct": true,
      "is_unattempted": false
    },
    {
      "question_id": "i9j0k1l2-...",
      "question_type": "multiple_choice",
      "question": "Which element has symbol 'Au'?",
      "your_answer": "Silver",
      "correct_answer": "Gold",
      "is_correct": false,
      "is_unattempted": false
    },
    {
      "question_id": "m3n4o5p6-...",
      "question_type": "true_false",
      "question": "Water boils at 100°C at sea level.",
      "your_answer": "",
      "correct_answer": "true",
      "is_correct": false,
      "is_unattempted": true
    }
  ]
}
```

---

### 2. GET `/api/submission/{submission_id}`

#### Response Schema (Updated)

```typescript
interface QuizSubmission {
  id: string;                   // UUID
  quiz_id: string;              // UUID
  user_id: string;              // UUID
  score: number;                // Percentage 0-100 (ge 0, le 100)
  correct_count: number;        // Number correct (ge 0)
  wrong_count: number;          // Number wrong - attempted but incorrect (ge 0)
  unattempted_count: number;    // 🆕 Number unattempted/skipped (ge 0, default 0)
  total_questions: number;      // Total questions (gt 0)
  submitted_at: string;         // ISO 8601 timestamp
  quiz_title: string | null;    // Quiz title (may be null)
}
```

#### Example Response

```json
{
  "id": "3bb9f910-86fb-4654-b2d4-d71f0083980a",
  "quiz_id": "7c8d9e0f-1234-5678-9abc-def012345678",
  "user_id": "12345678-1234-1234-1234-123456789012",
  "score": 60,
  "correct_count": 6,
  "wrong_count": 2,
  "unattempted_count": 2,
  "total_questions": 10,
  "submitted_at": "2026-02-05T14:30:00Z",
  "quiz_title": "Biology Quiz"
}
```

---

### 3. GET `/api/submissions`

#### Response Schema (Updated)

```typescript
interface UserSubmissionsResponse {
  user_id: string;              // UUID
  total_submissions: number;    // Total count (ge 0)
  submissions: QuizSubmission[]; // List with unattempted_count included
}
```

#### Example Response

```json
{
  "user_id": "12345678-1234-1234-1234-123456789012",
  "total_submissions": 3,
  "submissions": [
    {
      "id": "3bb9f910-86fb-4654-b2d4-d71f0083980a",
      "quiz_id": "7c8d9e0f-1234-5678-9abc-def012345678",
      "user_id": "12345678-1234-1234-1234-123456789012",
      "score": 60,
      "correct_count": 6,
      "wrong_count": 2,
      "unattempted_count": 2,
      "total_questions": 10,
      "submitted_at": "2026-02-05T14:30:00Z",
      "quiz_title": "Biology Quiz"
    }
  ]
}
```

---

### 4. GET `/api/quiz/{quiz_id}/submissions`

#### Response Schema (Updated)

```typescript
interface QuizSubmissionsResponse {
  quiz_id: string;              // UUID
  user_id: string;              // UUID
  total_attempts: number;       // Number of attempts (ge 0)
  submissions: QuizSubmission[]; // List with unattempted_count included
}
```

---

### 5. GET `/api/submission/{submission_id}/review`

#### Response Schema (Updated)

```typescript
interface SubmissionReviewResponse {
  submission_id: string;        // UUID
  quiz_id: string;              // UUID
  quiz_title: string | null;    // Quiz title
  user_id: string;              // UUID
  score: number;                // Percentage 0-100
  correct_count: number;        // Number correct
  wrong_count: number;          // Number wrong - attempted but incorrect
  unattempted_count: number;    // 🆕 Number unattempted/skipped (ge 0, default 0)
  total_questions: number;      // Total questions
  submitted_at: string;         // ISO 8601 timestamp
  questions: QuestionReviewDetail[];
}

interface QuestionReviewDetail {
  question_id: string;
  question_type: string;
  question: string;
  your_answer: string | boolean | number[];
  correct_answer: string | boolean | number[];
  is_correct: boolean;
  is_unattempted: boolean;      // 🆕 Whether question was skipped (default false)
  explanation: string;
  // Optional enhanced fields
  options?: string[];
  distractor_explanations?: Record<string, string>;
  bloom_level?: string;
  difficulty?: string;
  concept_name?: string;
  left?: string[];
  right?: string[];
}
```

#### Example Response

```json
{
  "submission_id": "3bb9f910-86fb-4654-b2d4-d71f0083980a",
  "quiz_id": "7c8d9e0f-1234-5678-9abc-def012345678",
  "quiz_title": "Biology Quiz",
  "user_id": "12345678-1234-1234-1234-123456789012",
  "score": 60,
  "correct_count": 6,
  "wrong_count": 2,
  "unattempted_count": 2,
  "total_questions": 10,
  "submitted_at": "2026-02-05T14:30:00Z",
  "questions": [
    {
      "question_id": "a1b2c3d4-...",
      "question_type": "multiple_choice",
      "question": "What is photosynthesis?",
      "your_answer": "Process of making food",
      "correct_answer": "Process of making food",
      "is_correct": true,
      "is_unattempted": false,
      "explanation": "Photosynthesis is the process by which plants convert light energy into chemical energy."
    },
    {
      "question_id": "e5f6g7h8-...",
      "question_type": "true_false",
      "question": "Water boils at 100°C at sea level.",
      "your_answer": "",
      "correct_answer": "true",
      "is_correct": false,
      "is_unattempted": true,
      "explanation": "At standard atmospheric pressure (sea level), water boils at 100°C."
    }
  ]
}
```

---

## Frontend Implementation Guide

### 1. Display Submission Summary

Update your submission summary component to show three separate counts:

```typescript
interface SubmissionSummaryProps {
  submission: SubmissionResponse;
}

function SubmissionSummary({ submission }: SubmissionSummaryProps) {
  return (
    <div className="submission-summary">
      <h2>Quiz Results</h2>
      <div className="score-display">
        <span className="score">{submission.score}%</span>
      </div>
      
      <div className="stats-grid">
        <div className="stat correct">
          <span className="count">{submission.correct_count}</span>
          <span className="label">Correct</span>
        </div>
        
        <div className="stat wrong">
          <span className="count">{submission.wrong_count}</span>
          <span className="label">Wrong</span>
        </div>
        
        {/* 🆕 Show unattempted count */}
        <div className="stat unattempted">
          <span className="count">{submission.unattempted_count}</span>
          <span className="label">Skipped</span>
        </div>
        
        <div className="stat total">
          <span className="count">{submission.total_questions}</span>
          <span className="label">Total</span>
        </div>
      </div>
    </div>
  );
}
```

### 2. Display Detailed Results

Show different visual feedback for unattempted vs wrong answers:

```typescript
interface DetailedResultsProps {
  results: DetailedResult[];
}

function DetailedResults({ results }: DetailedResultsProps) {
  return (
    <div className="detailed-results">
      {results.map((result) => (
        <div 
          key={result.question_id}
          className={`result-card ${
            result.is_unattempted 
              ? 'unattempted' 
              : result.is_correct 
                ? 'correct' 
                : 'wrong'
          }`}
        >
          <div className="question-header">
            <span className="question-type">{result.question_type}</span>
            
            {/* 🆕 Show appropriate icon */}
            {result.is_unattempted ? (
              <span className="icon skip">⊘</span>
            ) : result.is_correct ? (
              <span className="icon correct">✓</span>
            ) : (
              <span className="icon wrong">✗</span>
            )}
          </div>
          
          <p className="question">{result.question}</p>
          
          {/* 🆕 Show different message for unattempted */}
          {result.is_unattempted ? (
            <div className="unattempted-message">
              <p>You did not answer this question</p>
              <p className="correct-answer">
                <strong>Correct answer:</strong> {formatAnswer(result.correct_answer)}
              </p>
            </div>
          ) : (
            <>
              <div className="answer-comparison">
                <div className="your-answer">
                  <strong>Your answer:</strong> {formatAnswer(result.your_answer)}
                </div>
                {!result.is_correct && (
                  <div className="correct-answer">
                    <strong>Correct answer:</strong> {formatAnswer(result.correct_answer)}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      ))}
    </div>
  );
}

function formatAnswer(answer: string | boolean | number[]): string {
  if (Array.isArray(answer)) {
    return JSON.stringify(answer);
  }
  if (typeof answer === 'boolean') {
    return answer ? 'True' : 'False';
  }
  return answer.toString();
}
```

### 3. Analytics Dashboard

Track unattempted questions to identify patterns:

```typescript
interface QuizAnalytics {
  totalQuestions: number;
  correctCount: number;
  wrongCount: number;
  unattemptedCount: number;
  accuracyRate: number;        // correct / (correct + wrong)
  attemptRate: number;         // (correct + wrong) / total
  scoreRate: number;           // correct / total
}

function calculateAnalytics(submission: QuizSubmission): QuizAnalytics {
  const totalAttempted = submission.correct_count + submission.wrong_count;
  
  return {
    totalQuestions: submission.total_questions,
    correctCount: submission.correct_count,
    wrongCount: submission.wrong_count,
    unattemptedCount: submission.unattempted_count,
    
    // Accuracy = correct answers out of attempted questions
    accuracyRate: totalAttempted > 0 
      ? (submission.correct_count / totalAttempted) * 100 
      : 0,
    
    // Attempt rate = how many questions did they try?
    attemptRate: (totalAttempted / submission.total_questions) * 100,
    
    // Score rate = official score (includes unattempted as wrong)
    scoreRate: submission.score,
  };
}

function AnalyticsDashboard({ submission }: { submission: QuizSubmission }) {
  const analytics = calculateAnalytics(submission);
  
  return (
    <div className="analytics">
      <h3>Performance Breakdown</h3>
      
      <div className="metric">
        <span className="label">Overall Score</span>
        <span className="value">{analytics.scoreRate.toFixed(1)}%</span>
        <span className="subtitle">
          {analytics.correctCount} correct out of {analytics.totalQuestions} total
        </span>
      </div>
      
      <div className="metric">
        <span className="label">Accuracy Rate</span>
        <span className="value">{analytics.accuracyRate.toFixed(1)}%</span>
        <span className="subtitle">
          Out of {analytics.correctCount + analytics.wrongCount} attempted questions
        </span>
      </div>
      
      <div className="metric">
        <span className="label">Attempt Rate</span>
        <span className="value">{analytics.attemptRate.toFixed(1)}%</span>
        <span className="subtitle">
          You attempted {analytics.correctCount + analytics.wrongCount} of {analytics.totalQuestions} questions
        </span>
      </div>
      
      {analytics.unattemptedCount > 0 && (
        <div className="insight warning">
          <p>
            You skipped {analytics.unattemptedCount} question{analytics.unattemptedCount > 1 ? 's' : ''}. 
            Try to attempt all questions to improve your score!
          </p>
        </div>
      )}
    </div>
  );
}
```

### 4. Submission List with Filters

Allow users to filter by completion status:

```typescript
interface SubmissionListProps {
  submissions: QuizSubmission[];
}

function SubmissionList({ submissions }: SubmissionListProps) {
  const [filter, setFilter] = React.useState<'all' | 'completed' | 'partial'>('all');
  
  const filteredSubmissions = submissions.filter(sub => {
    if (filter === 'all') return true;
    if (filter === 'completed') return sub.unattempted_count === 0;
    if (filter === 'partial') return sub.unattempted_count > 0;
    return true;
  });
  
  return (
    <div className="submission-list">
      <div className="filters">
        <button 
          className={filter === 'all' ? 'active' : ''}
          onClick={() => setFilter('all')}
        >
          All ({submissions.length})
        </button>
        <button 
          className={filter === 'completed' ? 'active' : ''}
          onClick={() => setFilter('completed')}
        >
          Fully Completed ({submissions.filter(s => s.unattempted_count === 0).length})
        </button>
        <button 
          className={filter === 'partial' ? 'active' : ''}
          onClick={() => setFilter('partial')}
        >
          Partially Completed ({submissions.filter(s => s.unattempted_count > 0).length})
        </button>
      </div>
      
      <div className="submissions">
        {filteredSubmissions.map(sub => (
          <div key={sub.id} className="submission-card">
            <h4>{sub.quiz_title || 'Untitled Quiz'}</h4>
            <div className="stats">
              <span className="score">{sub.score}%</span>
              <span className="correct">{sub.correct_count} correct</span>
              <span className="wrong">{sub.wrong_count} wrong</span>
              {sub.unattempted_count > 0 && (
                <span className="unattempted">{sub.unattempted_count} skipped</span>
              )}
            </div>
            <time>{new Date(sub.submitted_at).toLocaleDateString()}</time>
          </div>
        ))}
      </div>
    </div>
  );
}
```

---

## CSS Styling Suggestions

```css
/* Submission summary stats */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1rem;
}

.stat.correct {
  background: #d4edda;
  border-color: #28a745;
}

.stat.wrong {
  background: #f8d7da;
  border-color: #dc3545;
}

.stat.unattempted {
  background: #fff3cd;
  border-color: #ffc107;
}

.stat.total {
  background: #d1ecf1;
  border-color: #17a2b8;
}

/* Result cards */
.result-card.correct {
  border-left: 4px solid #28a745;
  background: #f8fff9;
}

.result-card.wrong {
  border-left: 4px solid #dc3545;
  background: #fff8f8;
}

.result-card.unattempted {
  border-left: 4px solid #ffc107;
  background: #fffef8;
}

.unattempted-message {
  padding: 1rem;
  background: #fff3cd;
  border-radius: 4px;
  margin-top: 0.5rem;
}

.icon.skip {
  color: #ffc107;
  font-size: 1.5rem;
}

.icon.correct {
  color: #28a745;
  font-size: 1.5rem;
}

.icon.wrong {
  color: #dc3545;
  font-size: 1.5rem;
}
```

---

## Backward Compatibility

### ✅ Existing Frontends Will Continue to Work

All new fields have default values, so existing frontends that don't know about `unattempted_count` will:
- Receive `unattempted_count: 0` in all responses
- Receive `is_unattempted: false` for all questions
- Continue to see the same score calculation (backward compatible for new submissions)

### 📋 Migration for Existing Submissions

- **Old submissions** (created before this feature): `unattempted_count = 0` (database default)
- **Review endpoint**: Dynamically calculates `is_unattempted` from stored answers even for old submissions
- **No data migration needed**: All existing submissions remain valid

---

## Testing Checklist

### Backend (Already Complete ✅)

- ✅ 41 unit tests for `is_unattempted()` function
- ✅ 6 integration tests for submission scoring with unattempted tracking
- ✅ Tests verify score calculation: `6/10 = 60%` formula
- ✅ Tests verify `is_unattempted` flag in detailed results
- ✅ Ruff linting passes
- ✅ Database migration applied and verified

### Frontend (Recommended Tests)

- [ ] Display `unattempted_count` in submission summary
- [ ] Show different visual feedback for unattempted vs wrong answers
- [ ] Verify score calculation matches backend (60% for 6 correct, 2 wrong, 2 unattempted)
- [ ] Test with old submissions (unattempted_count should default to 0)
- [ ] Test filtering submissions by completion status
- [ ] Test analytics dashboard calculations

---

## Examples of Unattempted Detection

### Multiple Choice

```javascript
// ✅ Attempted - valid answer
{ question_id: "...", user_answer: "Option A" }

// ❌ Unattempted - empty string
{ question_id: "...", user_answer: "" }

// ❌ Unattempted - whitespace
{ question_id: "...", user_answer: "   " }

// ❌ Unattempted - null
{ question_id: "...", user_answer: null }
```

### True/False

```javascript
// ✅ Attempted - boolean true
{ question_id: "...", user_answer: true }

// ✅ Attempted - boolean false (IMPORTANT: false is valid!)
{ question_id: "...", user_answer: false }

// ✅ Attempted - string "true"
{ question_id: "...", user_answer: "true" }

// ✅ Attempted - string "false"
{ question_id: "...", user_answer: "false" }

// ❌ Unattempted - empty string
{ question_id: "...", user_answer: "" }

// ❌ Unattempted - invalid string
{ question_id: "...", user_answer: "yes" }

// ❌ Unattempted - number
{ question_id: "...", user_answer: 1 }
```

### Matching

```javascript
// ✅ Attempted - valid indices
{ question_id: "...", user_answer: [0, 1, 2, 3] }

// ✅ Attempted - all zeros (first option selected for all)
{ question_id: "...", user_answer: [0, 0, 0, 0] }

// ❌ Unattempted - all -1 values (common "not selected" pattern)
{ question_id: "...", user_answer: [-1, -1, -1, -1] }

// ❌ Unattempted - empty array
{ question_id: "...", user_answer: [] }

// ❌ Unattempted - null
{ question_id: "...", user_answer: null }

// ✅ Attempted - JSON string (will be parsed)
{ question_id: "...", user_answer: "[0, 1, 2, 3]" }
```

### Fill in the Blank

```javascript
// ✅ Attempted - valid answer
{ question_id: "...", user_answer: "photosynthesis" }

// ✅ Attempted - single character
{ question_id: "...", user_answer: "H" }

// ❌ Unattempted - empty string
{ question_id: "...", user_answer: "" }

// ❌ Unattempted - whitespace
{ question_id: "...", user_answer: "   " }

// ❌ Unattempted - tabs/newlines
{ question_id: "...", user_answer: "\t\n" }

// ❌ Unattempted - null
{ question_id: "...", user_answer: null }
```

---

## Common Pitfalls to Avoid

### ❌ DON'T: Treat `false` as unattempted

```typescript
// WRONG - false is a valid answer for true_false questions!
if (!result.your_answer) {
  showUnattemptedMessage();
}
```

### ✅ DO: Use the `is_unattempted` flag

```typescript
// CORRECT - trust the backend's type-aware detection
if (result.is_unattempted) {
  showUnattemptedMessage();
}
```

### ❌ DON'T: Calculate score without unattempted

```typescript
// WRONG - doesn't match backend calculation
const score = (correct / (correct + wrong)) * 100;
```

### ✅ DO: Use the score provided by the backend

```typescript
// CORRECT - backend already calculated it correctly
const score = submission.score; // Includes unattempted in denominator
```

### ❌ DON'T: Assume `unattempted_count` exists in old submissions

```typescript
// WRONG - might be undefined for very old API versions
const skipped = submission.unattempted_count;
```

### ✅ DO: Provide a fallback default

```typescript
// CORRECT - backward compatible
const skipped = submission.unattempted_count || 0;
```

---

## API Error Handling

No new error codes introduced. Existing error handling remains valid:

| Code | Scenario | Action |
|------|----------|--------|
| 400 | Invalid submission data | Show validation errors |
| 403 | Unauthorized access | Redirect to login |
| 404 | Submission/quiz not found | Show error message |
| 500 | Server error | Show retry option |

---

## Related Documentation

- [FRONTEND_SUBMISSION_REVIEW.md](./FRONTEND_SUBMISSION_REVIEW.md) - Detailed submission review endpoint
- [FRONTEND_ENHANCED_QUIZ_API.md](./FRONTEND_ENHANCED_QUIZ_API.md) - Quiz generation API
- [FRONTEND_MATCHING_ANSWERS.md](./FRONTEND_MATCHING_ANSWERS.md) - Matching question format

---

## Support

If you encounter issues:
1. Check that you're using the latest API version
2. Verify the `unattempted_count` field is present in responses
3. Check browser console for type errors
4. Contact backend team if scores don't match expectations

---

## Changelog

### 2026-02-05 - v1.0.0 (PR #195)
- ✅ Added `unattempted_count` field to all submission schemas
- ✅ Added `is_unattempted` flag to detailed results
- ✅ Updated score calculation to include unattempted questions
- ✅ Implemented type-aware unattempted detection
- ✅ Added database migration (column + constraint)
- ✅ Added 47 comprehensive tests (41 unit + 6 integration)
- ✅ Maintained full backward compatibility

---

**Last Updated**: February 5, 2026  
**Status**: Production Ready ✅
