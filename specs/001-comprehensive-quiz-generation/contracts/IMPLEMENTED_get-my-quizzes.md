# API Contract: Get User Quizzes (ACTUAL IMPLEMENTATION)

**Endpoint**: `GET /api/quiz/my-quizzes`  
**Status**: ✅ IMPLEMENTED (No search/filter)  
**Authentication**: Required (Bearer token)  
**Last Updated**: 2025-10-08

---

## Request

### Headers
```
Authorization: Bearer <jwt_token>
```

### Query Parameters (ACTUAL)
**❌ NONE** - No query parameters supported

The endpoint currently accepts NO query parameters. All filtering must be done client-side.

### Examples
```
GET /api/quiz/my-quizzes
# Returns ALL quizzes for authenticated user

# These do NOT work (parameters ignored):
GET /api/quiz/my-quizzes?title=biology  ❌
GET /api/quiz/my-quizzes?start_date=2025-10-01  ❌
```

### Current Business Rules
- ✅ Returns ALL quizzes created by authenticated user
- ❌ No server-side filtering by title
- ❌ No server-side filtering by date
- ❌ No pagination (could be slow with many quizzes)
- ✅ Authorization enforced (only user's own quizzes)

---

## Response

### Success (200 OK) - ACTUAL
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "Python Basics Quiz",
    "created_by": "660e8400-e29b-41d4-a716-446655440001",
    "created_at": "2025-10-03T14:30:00.123456+00:00",
    "question_count": 10
  },
  {
    "id": "660e8400-e29b-41d4-a716-446655440002",
    "title": "JavaScript Advanced",
    "created_by": "660e8400-e29b-41d4-a716-446655440001",
    "created_at": "2025-10-02T10:15:00.654321+00:00",
    "question_count": 15
  }
]
```

**Response Schema**: `List[MyQuizzesResponse]`

**Field Details**:
- `id`: UUID string
- `title`: Quiz title as stored
- `created_by`: User ID (UUID string)
- `created_at`: ISO 8601 timestamp with timezone
- `question_count`: Integer (number of questions in quiz)

### Empty Result (200 OK)
```json
[]
```

**When**: User has created no quizzes yet

---

## Errors (ACTUAL)

### 401 Unauthorized
```json
{
  "detail": "Authentication required"
}
```

**Triggered when**:
- No Bearer token provided
- Invalid/expired token
- Authentication dependency fails

### 500 Internal Server Error
```json
{
  "detail": "<error_message>"
}
```

**Triggered when**:
- Database query fails
- Supabase connection error
- Unexpected exceptions

---

## Implementation Details

### Code Location
- **Route**: `api/quiz_routes.py` - Line 122
- **Handler**: `handlers/quiz_handlers.py` - `get_user_quizzes_handler()` (Line 268)
- **Service**: `services/db_services/supabase_quiz.py` - `get_user_quizzes()`
- **Schema**: `schemas/quiz.py` - `MyQuizzesResponse`

### Handler Code
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

**Note**: No parameters besides `current_user_id` - no filtering capability

### Database Query
The `get_user_quizzes()` function queries:
```sql
SELECT id, title, created_by, created_at, 
       (SELECT COUNT(*) FROM quiz_questions WHERE quiz_id = quizzes.id) as question_count
FROM quizzes
WHERE created_by = <current_user_id>
ORDER BY created_at DESC  -- Assumption: most recent first
```

**Performance Note**: No LIMIT clause - could return thousands of quizzes

---

## Missing Features vs Contract

| Feature | Contract | Actual | Priority |
|---------|----------|--------|----------|
| Title search (`?title=`) | ✅ Required | ❌ Missing | 🟡 MEDIUM |
| Date filter (`?start_date=`) | ✅ Required | ❌ Missing | 🟡 MEDIUM |
| Date filter (`?end_date=`) | ✅ Required | ❌ Missing | 🟡 MEDIUM |
| Date validation | ✅ Required | ❌ Missing | 🟡 MEDIUM |
| Pagination | ⚠️ Recommended | ❌ Missing | 🟢 LOW |
| Case-insensitive search | ✅ Required | ❌ Missing | 🟡 MEDIUM |

---

## Recommendations

### 1. Add Search/Filter Parameters (MEDIUM Priority)

Update handler signature:
```python
from datetime import date
from typing import Optional

async def get_user_quizzes_handler(
    current_user_id: str = Depends(get_current_user_id),
    title: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
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
            end_date=end_date
        )
        return quizzes
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### 2. Update Database Service

Modify `get_user_quizzes()` in `supabase_quiz.py`:
```python
def get_user_quizzes(
    user_id: str,
    title: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
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
        end_datetime = date(end_date.year, end_date.month, end_date.day + 1)
        query = query.lt("created_at", end_datetime.isoformat())
    
    result = query.order("created_at", desc=True).execute()
    return result.data
```

### 3. Add Pagination (LOW Priority)

```python
async def get_user_quizzes_handler(
    current_user_id: str = Depends(get_current_user_id),
    title: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    page: int = 1,
    page_size: int = 50  # Default 50 per page
):
    # Calculate offset
    offset = (page - 1) * page_size
    
    quizzes = get_user_quizzes(
        current_user_id,
        title=title,
        start_date=start_date,
        end_date=end_date,
        limit=page_size,
        offset=offset
    )
    
    return {
        "quizzes": quizzes,
        "page": page,
        "page_size": page_size,
        "has_more": len(quizzes) == page_size
    }
```

---

## Test Coverage Status

### Unit Tests
- ⚠️ No unit tests for this handler
- Should test: filtering logic, date validation, empty results

### Integration Tests
- ⚠️ No integration tests
- Should test: database query with filters, authorization, pagination

---

## Example Usage (ACTUAL)

### Current Usage
```bash
# Get all quizzes (only way to use endpoint)
curl -X GET "https://api.quizify.ca/api/quiz/my-quizzes" \
  -H "Authorization: Bearer <token>"
```

### Desired Usage (After Implementation)
```bash
# Search by title
curl -X GET "https://api.quizify.ca/api/quiz/my-quizzes?title=python" \
  -H "Authorization: Bearer <token>"

# Filter by date range
curl -X GET "https://api.quizify.ca/api/quiz/my-quizzes?start_date=2025-10-01&end_date=2025-10-31" \
  -H "Authorization: Bearer <token>"

# Combined filters
curl -X GET "https://api.quizify.ca/api/quiz/my-quizzes?title=quiz&start_date=2025-10-01" \
  -H "Authorization: Bearer <token>"
```

---

## Performance Considerations

### Current Performance
- ⚠️ **No LIMIT**: Could return thousands of quizzes (slow)
- ⚠️ **No pagination**: Client must load all quizzes at once
- ✅ **Indexed**: Assuming `created_by` has index

### With Filtering (After Implementation)
- ✅ **Server-side filtering**: Reduces data transfer
- ✅ **ILIKE with indexes**: Fast title search if indexed
- ✅ **Date range queries**: Fast with indexed `created_at`

### Recommended Indexes
```sql
-- Add index on title for case-insensitive search
CREATE INDEX idx_quizzes_title_lower ON quizzes (LOWER(title));

-- Add composite index for common queries
CREATE INDEX idx_quizzes_user_date ON quizzes (created_by, created_at DESC);
```

---

**Contract Version**: Actual Implementation as of 2025-10-08  
**Differs from Spec**: Yes (missing search/filter parameters)  
**Production Ready**: ⚠️ PARTIAL - Works but lacks search/filter, could be slow with many quizzes
