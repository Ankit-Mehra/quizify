# API Contract: Quiz Search and Filter

**Endpoint**: `GET /api/quiz/my-quizzes`  
**Purpose**: Retrieve user's quizzes with optional search and date filtering  
**Authentication**: Required (Bearer token or cookie)  
**Authorization**: Returns only quizzes created by authenticated user

---

## Request

### Headers
```
Authorization: Bearer <jwt_token>
```

### Query Parameters
- `title` (optional): Case-insensitive partial match on quiz title (e.g., `?title=math`)
- `start_date` (optional): ISO 8601 date (e.g., `?start_date=2025-01-01`) - filter quizzes created on or after this date
- `end_date` (optional): ISO 8601 date (e.g., `?end_date=2025-12-31`) - filter quizzes created on or before this date

### Examples
```
GET /api/quiz/my-quizzes
GET /api/quiz/my-quizzes?title=biology
GET /api/quiz/my-quizzes?start_date=2025-10-01&end_date=2025-10-31
GET /api/quiz/my-quizzes?title=quiz&start_date=2025-10-01
```

### Business Rules
- All parameters optional (no params = return all user's quizzes)
- Title search: case-insensitive, partial match (ILIKE '%title%')
- Date filter: inclusive range (created_at >= start_date AND created_at <= end_date)
- Empty result set if no matches (not an error)
- Maximum 1000 results (pagination recommended for future)

---

## Response

### Success (200 OK)
```json
[
  {
    "id": "uuid",
    "title": "Biology Quiz Chapter 5",
    "created_by": "uuid",
    "created_at": "2025-10-03T14:30:00Z",
    "question_count": 15
  },
  {
    "id": "uuid",
    "title": "Math Quiz - Algebra",
    "created_by": "uuid",
    "created_at": "2025-10-02T10:15:00Z",
    "question_count": 20
  }
]
```

### Empty Result (200 OK)
```json
[]
```

### Errors

**401 Unauthorized**
```json
{
  "detail": "Authentication required"
}
```

**400 Bad Request** (invalid date format)
```json
{
  "detail": "Invalid date format. Use ISO 8601 (YYYY-MM-DD)"
}
```

**400 Bad Request** (start_date > end_date)
```json
{
  "detail": "start_date must be before or equal to end_date"
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

**Contract Test File**: `tests/contract/test_search_quizzes.py`  
**Status**: Specification complete - ready for test generation
