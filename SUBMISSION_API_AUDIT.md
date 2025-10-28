# Submission API Audit Report
**Date**: 2025-10-28  
**Scope**: Comprehensive review of submission schemas, APIs, handlers, and contracts

---

## Executive Summary

### Where Submission Models Are Used

1. **schemas/submission.py** - Defines 6 Pydantic models:
   - `AnswerSubmission` - For submitting individual answers
   - `QuizSubmissionRequest` - Request payload for POST /quiz/{quiz_id}/submit
   - `QuizSubmission` - Summary response (NO answers field)
   - `QuizAnswer` - Individual answer record
   - `DetailedResult` - Result for one question
   - `SubmissionResponse` - Response after submitting quiz (WITH detailed_results)

2. **api/submission_routes.py** - Uses:
   - `SubmissionResponse` - response_model for POST /quiz/{quiz_id}/submit ✅
   - `QuizSubmission` - response_model for GET /submission/{submission_id} ✅
   - ❌ NO response_model for GET /submissions
   - ❌ NO response_model for GET /quiz/{quiz_id}/submissions

3. **handlers/submission_handler.py** - Uses:
   - `QuizSubmission` - For get_submission return
   - `QuizAnswer` - When saving individual answers
   - `QuizSubmissionRequest` - For submit_quiz parameter

4. **services/db_services/supabase_submission.py** - Uses:
   - `QuizSubmission` - Return type for get_submission_by_id ⚠️ **BUG**
   - `QuizAnswer` - Parameter for save_answer

---

## Critical Issues Found

### 🔴 Issue 1: QuizSubmission Schema Mismatch (CRITICAL BUG)

**Location**: `services/db_services/supabase_submission.py:168-188`

**Problem**: `get_submission_by_id()` tries to create a `QuizSubmission` with an `answers` parameter, but the schema doesn't support it.

**Code**:
```python
return QuizSubmission(
    id=UUID(submission["id"]),
    quiz_id=UUID(submission["quiz_id"]),
    user_id=UUID(submission["user_id"]),
    score=submission["score"],
    total_questions=submission["total_questions"],
    correct_count=submission["correct_count"],
    wrong_count=submission["wrong_count"],
    submitted_at=submission["submitted_at"],
    answers=[...]  # ❌ QuizSubmission doesn't have 'answers' field!
)
```

**Schema Reality**:
```python
class QuizSubmission(BaseModel):
    """Complete submission record stored in database"""
    id: UUID
    quiz_id: UUID
    user_id: UUID
    score: int
    correct_count: int
    wrong_count: int
    total_questions: int
    submitted_at: datetime
    # ❌ NO answers field!
```

**Impact**: This will cause a **Pydantic ValidationError** when anyone calls `GET /submission/{submission_id}`. The endpoint is broken!

**Fix Required**:
1. Remove the `answers` parameter from `get_submission_by_id()` (lines 179-188)
2. The function should only return summary data (which is what the contract documents)

---

### 🔴 Issue 2: Field Name Mismatch in get_submission_by_id()

**Location**: `services/db_services/supabase_submission.py:180-185`

**Problem**: Code tries to access `ans["submitted_answer"]` but the database column is `user_answer`.

**Code**:
```python
answers=[
    QuizAnswer(
        question_id=UUID(ans["question_id"]),
        submitted_answer=ans["submitted_answer"],  # ❌ Wrong field name!
        is_correct=ans["is_correct"],
        correct_answer=ans.get("correct_answer")
    )
    for ans in answers_data.data
]
```

**Schema Reality**:
```python
class QuizAnswer(BaseModel):
    """Individual answer record with correctness evaluation"""
    id: UUID
    submission_id: UUID
    question_id: UUID
    user_answer: Union[str, bool, List[int]]  # ✅ Correct field name
    correct_answer: Union[str, bool, List[int]]
    is_correct: bool
```

**Database Reality**:
When saving answers (line 119-126):
```python
save_answer(QuizAnswer(
    id=uuid4(),
    submission_id=new_submission.id,
    question_id=result["question_id"],
    user_answer=result["your_answer"],  # ✅ Uses 'user_answer'
    correct_answer=result["correct_answer"],
    is_correct=result["is_correct"]
), user_token)
```

**Impact**: Even if we fix Issue 1, this will cause a **KeyError** because `submitted_answer` doesn't exist in the database.

**Fix Required**: Change `submitted_answer` to `user_answer` (but this is moot since we should remove the entire answers block per Issue 1).

---

### 🟡 Issue 3: Missing Response Models for List Endpoints

**Location**: `api/submission_routes.py:70-92`

**Problem**: No `response_model` defined for list endpoints.

**Current State**:
```python
# GET /submissions - NO response_model
router.add_api_route(
    path="/submissions",
    endpoint=list_user_submissions,
    methods=["GET"],
    summary="List My Submissions",
    description="..."
    # ❌ NO response_model
)

# GET /quiz/{quiz_id}/submissions - NO response_model
router.add_api_route(
    path="/quiz/{quiz_id}/submissions",
    endpoint=list_quiz_submissions,
    methods=["GET"],
    summary="List Quiz Attempts",
    description="..."
    # ❌ NO response_model
)
```

**Handler Returns**:
```python
# list_user_submissions returns:
{
    "user_id": str,
    "total_submissions": int,
    "submissions": List[dict]  # List of submission summaries
}

# list_quiz_submissions returns:
{
    "quiz_id": str,
    "user_id": str,
    "total_attempts": int,
    "submissions": List[dict]  # List of submission summaries
}
```

**Impact**: 
- No automatic response validation by FastAPI
- API documentation (OpenAPI) won't show proper response structure
- Clients can't rely on type-safe contracts

**Fix Required**: Create proper response schemas:
```python
class UserSubmissionsResponse(BaseModel):
    user_id: str
    total_submissions: int
    submissions: List[QuizSubmission]

class QuizSubmissionsResponse(BaseModel):
    quiz_id: str
    user_id: str
    total_attempts: int
    submissions: List[QuizSubmission]
```

---

## Contract Verification Results

### ✅ IMPLEMENTED_submit-quiz.md - ACCURATE
- Documents `response_model=SubmissionResponse` ✅
- Documents request validation (quiz_id matching) ✅
- Documents error responses (400, 401, 404, 422, 500) ✅
- Documents scoring logic ✅
- Documents database operations ✅

**Status**: Contract matches implementation perfectly.

---

### ✅ IMPLEMENTED_get-submission.md - ACCURATE (Despite Bug)
- Documents `response_model=QuizSubmission` ✅
- Correctly states "does NOT include detailed_results" ✅
- Documents authorization logic (403 for wrong user) ✅
- Documents error responses ✅

**Status**: Contract accurately describes INTENDED behavior. However, the actual implementation has a bug (tries to add answers field). Once bug is fixed, contract will be accurate.

---

### ⚠️ IMPLEMENTED_list-user-submissions.md - PARTIALLY ACCURATE
- Documents request/response structure ✅
- Documents authentication ✅
- Response structure matches handler return ✅

**Issue**: Contract shows example response, but API route has no `response_model` to enforce it.

**Recommendation**: Add `UserSubmissionsResponse` schema and set as response_model.

---

### ⚠️ IMPLEMENTED_list-quiz-submissions.md - PARTIALLY ACCURATE
- Documents request/response structure ✅
- Documents authentication ✅
- Response structure matches handler return ✅

**Issue**: Contract shows example response, but API route has no `response_model` to enforce it.

**Recommendation**: Add `QuizSubmissionsResponse` schema and set as response_model.

---

## Why These Models Exist

### Purpose of Each Schema

1. **AnswerSubmission** - Input validation for individual answers
   - Used in: `QuizSubmissionRequest.answers`
   - Why: Type-safe input, prevents malformed answer submissions

2. **QuizSubmissionRequest** - Input validation for quiz submission
   - Used in: `POST /quiz/{quiz_id}/submit` endpoint
   - Why: Validates quiz_id, total_questions, and answers array format

3. **QuizSubmission** - Summary response WITHOUT detailed answers
   - Used in: `GET /submission/{submission_id}` response
   - Why: Lightweight summary data (score, counts, timestamp)
   - Design choice: Detailed answers require separate endpoint (future enhancement)

4. **QuizAnswer** - Individual answer record for database
   - Used in: Saving each answer to `answers` table
   - Why: Track correctness per question for analytics

5. **DetailedResult** - Question-level feedback for user
   - Used in: `SubmissionResponse.detailed_results`
   - Why: Show user what they got right/wrong immediately after submission

6. **SubmissionResponse** - Rich response after quiz submission
   - Used in: `POST /quiz/{quiz_id}/submit` response
   - Why: User gets immediate feedback on performance with question-by-question breakdown

---

## Recommendations

### Priority 1 (CRITICAL - Fix Immediately)

1. **Fix get_submission_by_id() Bug**
   ```python
   # Remove lines 179-188 (answers parameter)
   return QuizSubmission(
       id=UUID(submission["id"]),
       quiz_id=UUID(submission["quiz_id"]),
       user_id=UUID(submission["user_id"]),
       score=submission["score"],
       total_questions=submission["total_questions"],
       correct_count=submission["correct_count"],
       wrong_count=submission["wrong_count"],
       submitted_at=submission["submitted_at"]
       # ✅ NO answers parameter
   )
   ```

### Priority 2 (HIGH - Add Type Safety)

2. **Create Response Schemas for List Endpoints**
   - Add `UserSubmissionsResponse` to schemas/submission.py
   - Add `QuizSubmissionsResponse` to schemas/submission.py
   - Update routes to use these as response_model

3. **Add Missing Tests**
   - Test `GET /submission/{submission_id}` (currently broken)
   - Test `GET /submissions`
   - Test `GET /quiz/{quiz_id}/submissions`

### Priority 3 (MEDIUM - Future Enhancement)

4. **Consider Adding Detailed Answers Endpoint**
   - Create `GET /submission/{submission_id}/answers` endpoint
   - Return `List[QuizAnswer]` with full answer details
   - Update contracts to document this future enhancement

---

## Database Column Verification

### answers Table Columns (Inferred from Code)
Based on how we save answers:
```python
{
    "id": UUID,
    "submission_id": UUID,
    "question_id": UUID,
    "user_answer": Union[str, bool, List[int]],  # ✅ Not 'submitted_answer'
    "correct_answer": Union[str, bool, List[int]],
    "is_correct": bool
}
```

### submissions Table Columns
```python
{
    "id": UUID,
    "user_id": UUID,
    "quiz_id": UUID,
    "score": int,  # INTEGER (0-100)
    "total_questions": int,
    "correct_count": int,
    "wrong_count": int,
    "submitted_at": datetime
}
```

---

## Testing Checklist

### Before Deploy (Critical)
- [ ] Test `POST /quiz/{quiz_id}/submit` - should work (already working)
- [ ] Test `GET /submission/{submission_id}` - will FAIL until bug fixed
- [ ] Test `GET /submissions` - should work (no schema issues)
- [ ] Test `GET /quiz/{quiz_id}/submissions` - should work (no schema issues)

### After Bug Fix
- [ ] Verify `GET /submission/{submission_id}` returns QuizSubmission without answers
- [ ] Verify authorization (403) when accessing other user's submission
- [ ] Add response_model to list endpoints
- [ ] Update API docs if needed

---

## Summary

**Submission models are used** in:
1. ✅ Request validation (QuizSubmissionRequest, AnswerSubmission)
2. ✅ Response typing (SubmissionResponse, QuizSubmission)
3. ✅ Database operations (QuizSubmission, QuizAnswer)

**Why they exist**:
- Type safety and validation
- API contract enforcement
- Separation of concerns (summary vs detailed responses)
- Database schema mapping

**Critical issues**:
- 🔴 `get_submission_by_id()` has Pydantic validation bug
- 🔴 Field name mismatch (submitted_answer vs user_answer)
- 🟡 Missing response_model on list endpoints

**Contracts accuracy**:
- ✅ submit-quiz.md - Perfect
- ✅ get-submission.md - Accurate (describes intended behavior)
- ⚠️ list-user-submissions.md - Accurate but missing type enforcement
- ⚠️ list-quiz-submissions.md - Accurate but missing type enforcement
