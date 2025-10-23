````markdown
# API Contract: Quiz Search and Filter

**Endpoint**: `GET /api/quiz/my-quizzes`  
**Purpose**: Retrieve user's quizzes with optional search and date filtering  
**Authentication**: Required (Bearer token or cookie)  
**Authorization**: Returns only quizzes created by authenticated user  
**Status**: ⚠️ PARTIALLY IMPLEMENTED (No search/filter parameters)  
**Last Updated**: 2025-10-23

---

## Request

### Headers
```
Authorization: Bearer <jwt_token>
```

### Query Parameters (SPECIFIED - NOT IMPLEMENTED)
- `title` (optional): ❌ Case-insensitive partial match on quiz title (e.g., `?title=math`) - **NOT IMPLEMENTED**
- `start_date` (optional): ❌ ISO 8601 date (e.g., `?start_date=2025-01-01`) - **NOT IMPLEMENTED**
- `end_date` (optional): ❌ ISO 8601 date (e.g., `?end_date=2025-12-31`) - **NOT IMPLEMENTED**

**ACTUAL BEHAVIOR**: Endpoint accepts **NO query parameters**. All filtering must be done client-side.

### Examples
```
GET /api/quiz/my-quizzes  ✅ Returns ALL user quizzes
GET /api/quiz/my-quizzes?title=biology  ❌ Parameters ignored
GET /api/quiz/my-quizzes?start_date=2025-10-01&end_date=2025-10-31  ❌ Parameters ignored
GET /api/quiz/my-quizzes?title=quiz&start_date=2025-10-01  ❌ Parameters ignored
```

### Business Rules (ACTUAL)
- ✅ Returns ALL quizzes created by authenticated user
- ❌ No server-side filtering by title - **NOT IMPLEMENTED**
- ❌ No server-side filtering by date - **NOT IMPLEMENTED**
- ❌ No pagination (could be slow with many quizzes) - **NOT IMPLEMENTED**
- ✅ Authorization enforced (only user's own quizzes via RLS)
- ⚠️ No LIMIT clause (could return thousands of quizzes)

---

## Response

### Success (200 OK) - ACTUAL
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "Biology Quiz Chapter 5",
    "created_by": "660e8400-e29b-41d4-a716-446655440001",
    "created_at": "2025-10-03T14:30:00.123456+00:00",
    "question_count": 15
  },
  {
    "id": "660e8400-e29b-41d4-a716-446655440002",
    "title": "Math Quiz - Algebra",
    "created_by": "660e8400-e29b-41d4-a716-446655440001",
    "created_at": "2025-10-02T10:15:00.654321+00:00",
    "question_count": 20
  }
]
```

**Note**: Returns array of `MyQuizzesResponse` objects. Always returns ALL user quizzes (no filtering).

### Empty Result (200 OK)
```json
[]
```

### Errors

**401 Unauthorized** - ✅ **IMPLEMENTED**
```json
{
  "detail": "Authentication required"
}
```

**400 Bad Request** (invalid date format) - ❌ **NOT APPLICABLE** (no date parameters accepted)
```json
{
  "detail": "Invalid date format. Use ISO 8601 (YYYY-MM-DD)"
}
```

**400 Bad Request** (start_date > end_date) - ❌ **NOT APPLICABLE** (no date parameters accepted)
```json
{
  "detail": "start_date must be before or equal to end_date"
}
```

**500 Internal Server Error** - ✅ **IMPLEMENTED**
```json
{
  "detail": "<error_message>"
}
```

---

## Contract Test Scenarios

1. **No filters** (retrieve all quizzes)
   - GET /api/quiz/my-quizzes
   - Expect 200 with array of all user's quizzes

2. **Title search match**
   - Create quiz with title "Python Programming"
   - GET /api/quiz/my-quizzes?title=python
   - Expect 200 with quiz in results

3. **Title search no match**
   - GET /api/quiz/my-quizzes?title=nonexistent
   - Expect 200 with empty array []

4. **Date range filter**
   - Create quiz on 2025-10-05
   - GET /api/quiz/my-quizzes?start_date=2025-10-01&end_date=2025-10-10
   - Expect 200 with quiz in results

5. **Date range excludes quiz**
   - Create quiz on 2025-10-15
   - GET /api/quiz/my-quizzes?start_date=2025-10-01&end_date=2025-10-10
   - Expect 200 with empty array (quiz outside range)

6. **Combined title + date filter**
   - Create quiz "Math Test" on 2025-10-05
   - GET /api/quiz/my-quizzes?title=math&start_date=2025-10-01
   - Expect 200 with quiz in results

7. **Invalid date format**
   - GET /api/quiz/my-quizzes?start_date=invalid
   - Expect 400 Bad Request

8. **Start date after end date**
   - GET /api/quiz/my-quizzes?start_date=2025-10-10&end_date=2025-10-01
   - Expect 400 Bad Request

9. **Case-insensitive search**
   - Create quiz "BIOLOGY Quiz"
   - GET /api/quiz/my-quizzes?title=biology
   - Expect 200 with quiz in results

10. **Partial match search**
    - Create quiz "Introduction to Machine Learning"
    - GET /api/quiz/my-quizzes?title=machine
    - Expect 200 with quiz in results

---

## OpenAPI Schema

```yaml
/api/quiz/my-quizzes:
  get:
    summary: Get user quizzes with optional search and filters
    tags:
      - Quiz Management
    security:
      - BearerAuth: []
    parameters:
      - name: title
        in: query
        required: false
        schema:
          type: string
        description: Case-insensitive partial match on quiz title
      - name: start_date
        in: query
        required: false
        schema:
          type: string
          format: date
        description: Filter quizzes created on or after this date (ISO 8601)
      - name: end_date
        in: query
        required: false
        schema:
          type: string
          format: date
        description: Filter quizzes created on or before this date (ISO 8601)
    responses:
      '200':
        description: List of quizzes matching filters
        content:
          application/json:
            schema:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: string
                    format: uuid
                  title:
                    type: string
                  created_by:
                    type: string
                    format: uuid
                  created_at:
                    type: string
                    format: date-time
                  question_count:
                    type: integer
      '400':
        description: Bad request (invalid date format or date range)
      '401':
        description: Unauthorized (missing or invalid token)
```

---

## Implementation Status

### Code Location
- **Route**: `api/quiz_routes.py` - Line 122
- **Handler**: `handlers/quiz_handlers.py` - `get_user_quizzes_handler()` (Line 268)
- **Service**: `services/db_services/supabase_quiz.py` - `get_user_quizzes()`
- **Schema**: `schemas/quiz.py` - `MyQuizzesResponse`

### Actual Implementation
```python
async def get_user_quizzes_handler(
    current_user_id: str = Depends(get_current_user_id)
):
    """Get all quizzes created by the current user."""
    try:
        quizzes = get_user_quizzes(current_user_id)
        return quizzes
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

**Note**: Handler accepts NO parameters besides `current_user_id`. All quizzes are returned without filtering.

### Database Query (Approximate)
```sql
SELECT id, title, created_by, created_at,
       (SELECT COUNT(*) FROM quiz_questions WHERE quiz_id = quizzes.id) as question_count
FROM quizzes
WHERE created_by = <current_user_id>
ORDER BY created_at DESC  -- Assumed
```

### Missing Features

| Feature | Status | Priority | Effort |
|---------|--------|----------|--------|
| Title search (`?title=`) | ❌ Missing | 🟡 MEDIUM | 2 hours |
| Date filter (`?start_date=`, `?end_date=`) | ❌ Missing | 🟡 MEDIUM | 2 hours |
| Date validation | ❌ Missing | 🟡 MEDIUM | Included above |
| Pagination (`?page=`, `?page_size=`) | ❌ Missing | 🟢 LOW | 3 hours |
| Case-insensitive search | ❌ Missing | 🟡 MEDIUM | Included with title |
| LIMIT clause (performance) | ❌ Missing | 🟡 MEDIUM | 30 min |

### Recommendations

#### Option 1: Implement Full Search/Filter (RECOMMENDED)

Update handler:
```python
from datetime import date
from typing import Optional

async def get_user_quizzes_handler(
    current_user_id: str = Depends(get_current_user_id),
    title: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    page: int = 1,
    page_size: int = 50
):
    """Get quizzes with optional filtering by title and date range."""
    
    # Validate date range
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date must be before or equal to end_date"
        )
    
    try:
        quizzes = get_user_quizzes(
            current_user_id,
            title=title,
            start_date=start_date,
            end_date=end_date,
            limit=page_size,
            offset=(page - 1) * page_size
        )
        return quizzes
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

Update `get_user_quizzes()` in `services/db_services/supabase_quiz.py`:
```python
def get_user_quizzes(
    user_id: str,
    title: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = 50,
    offset: int = 0
) -> List[dict]:
    query = supabase.table("quizzes").select(
        "id, title, created_by, created_at, question_count"
    ).eq("created_by", user_id)
    
    # Apply filters
    if title:
        query = query.ilike("title", f"%{title}%")
    if start_date:
        query = query.gte("created_at", start_date.isoformat())
    if end_date:
        # Add one day to include end_date fully
        end_datetime = datetime.combine(end_date, datetime.max.time())
        query = query.lt("created_at", end_datetime.isoformat())
    
    result = query.order("created_at", desc=True)\
                  .limit(limit)\
                  .offset(offset)\
                  .execute()
    return result.data
```

**Effort**: ~4 hours  
**Value**: Medium (improves UX, prevents slow queries with many quizzes)

#### Option 2: Add Pagination Only (MINIMAL)
Just add LIMIT clause to prevent returning thousands of quizzes.

**Effort**: 1 hour  
**Value**: Medium (prevents performance issues)

#### Option 3: Update Spec to Match Current Implementation
Remove search/filter requirements, document actual behavior.

**Effort**: 30 minutes (documentation only)  
**Value**: Low (leaves UX gap)

---

### Recommended Database Indexes
```sql
-- For title search (case-insensitive)
CREATE INDEX idx_quizzes_title_lower ON quizzes (LOWER(title));

-- For date range queries
CREATE INDEX idx_quizzes_created_at ON quizzes (created_at DESC);

-- Composite index for common queries
CREATE INDEX idx_quizzes_user_date ON quizzes (created_by, created_at DESC);
```

---

**Contract Version**: Updated 2025-10-23  
**Implementation Status**: ⚠️ PARTIAL - Returns all quizzes, no filtering  
**Production Ready**: ⚠️ ACCEPTABLE - Works but could be slow with many quizzes  
**Recommended Action**: Implement Option 1 (full search/filter) or at minimum Option 2 (pagination)

**Contract Test File**: `tests/contract/test_search_quizzes.py`  
**Status**: Specification complete - ❌ **SEARCH/FILTER NOT IMPLEMENTED**

````
