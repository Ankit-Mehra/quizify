# API Contract: Quiz Generation with Quota Enforcement

**Endpoint**: `POST /api/quiz/generate/text`  
**Purpose**: Generate quiz from text input with tier quota validation  
**Authentication**: Required (Bearer token or cookie)  
**Authorization**: Must not exceed tier quota

---

## Request

### Headers
```
Authorization: Bearer <jwt_token>
Content-Type: application/json
```

### Body
```json
{
  "title": "string",
  "content": "string",
  "num_questions": 10,
  "question_type": ["multiple_choice", "true_false", "fill_blank", "matching", "mixed"]
}
```

### Field Validation
- `title`: **Required**, non-empty string, max 255 characters
- `content`: **Required**, min 10 characters
- `num_questions`: **Optional**, integer 1-50, default 10
- `question_type`: **Optional**, array of valid types, default ["mixed"]

### Business Rules (NEW)
- **Quota check** BEFORE generation:
  - Free tier: Current quiz count < 5
  - Basic tier: Current quiz count < 100
  - Educator tier: Current quiz count < 500
- **Generation threshold**: Must generate ≥75% of requested questions or fail
- If quota exceeded: Return 403 Forbidden (do not generate)
- If threshold not met: Return 400 Bad Request (rollback any partial data)

---

## Response

### Success (200 OK)
```json
{
  "quiz_id": "uuid",
  "title": "Python Basics Quiz",
  "message": "Quiz generated successfully",
  "questions_generated": 10,
  "questions_requested": 10
}
```

### Errors

**403 Forbidden** (Quota exceeded - NEW)
```json
{
  "detail": "Quiz quota exceeded for free tier (5/5). Upgrade to basic for 100 quizzes.",
  "current_count": 5,
  "quota_limit": 5,
  "user_tier": "free"
}
```

**400 Bad Request** (Insufficient questions generated - NEW)
```json
{
  "detail": "AI generated only 7/10 questions (minimum 75% required)",
  "questions_generated": 7,
  "questions_requested": 10,
  "threshold": 0.75
}
```

**400 Bad Request** (Content too short)
```json
{
  "detail": "Content must be at least 10 characters"
}
```

**401 Unauthorized**
```json
{
  "detail": "Authentication required"
}
```

**500 Internal Server Error** (AI service failure)
```json
{
  "detail": "Quiz generation failed: OpenAI API error"
}
```

---

## Contract Test Scenarios

### Quota Enforcement Tests

1. **Free tier at quota limit**
   - User with 5 existing quizzes (free tier)
   - POST /api/quiz/generate/text with valid content
   - Expect 403 Forbidden with quota details

2. **Free tier below quota**
   - User with 3 existing quizzes (free tier)
   - POST /api/quiz/generate/text with valid content
   - Expect 200 OK with quiz created

3. **Basic tier at quota limit**
   - User with 100 existing quizzes (basic tier)
   - POST /api/quiz/generate/text with valid content
   - Expect 403 Forbidden

4. **Educator tier below quota**
   - User with 450 existing quizzes (educator tier)
   - POST /api/quiz/generate/text with valid content
   - Expect 200 OK with quiz created

### 75% Threshold Tests

5. **Generation meets threshold** (mock AI response)
   - Request 10 questions, AI returns 8 (80%)
   - Expect 200 OK with quiz created

6. **Generation below threshold** (mock AI response)
   - Request 10 questions, AI returns 6 (60%)
   - Expect 400 Bad Request with threshold error

7. **Generation exactly at threshold** (mock AI response)
   - Request 20 questions, AI returns 15 (75%)
   - Expect 200 OK with quiz created

### Existing Validation Tests (unchanged)

8. **Valid request**
   - Send valid title, content, num_questions
   - Expect 200 OK

9. **Missing authentication**
   - Omit Authorization header
   - Expect 401 Unauthorized

10. **Invalid num_questions** (51)
    - Send num_questions=51
    - Expect 422 Unprocessable Entity (Pydantic validation)

---

## OpenAPI Schema Updates

```yaml
/api/quiz/generate/text:
  post:
    summary: Generate quiz from text with quota enforcement
    tags:
      - Quiz Generation
    security:
      - BearerAuth: []
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - title
              - content
            properties:
              title:
                type: string
                maxLength: 255
              content:
                type: string
                minLength: 10
              num_questions:
                type: integer
                minimum: 1
                maximum: 50
                default: 10
              question_type:
                type: array
                items:
                  type: string
                  enum: [multiple_choice, true_false, fill_blank, matching, mixed]
                default: [mixed]
    responses:
      '200':
        description: Quiz generated successfully
        content:
          application/json:
            schema:
              type: object
              properties:
                quiz_id:
                  type: string
                  format: uuid
                title:
                  type: string
                message:
                  type: string
                questions_generated:
                  type: integer
                questions_requested:
                  type: integer
      '400':
        description: Bad request (content too short or insufficient questions generated)
      '401':
        description: Unauthorized
      '403':
        description: Forbidden (quota exceeded)
        content:
          application/json:
            schema:
              type: object
              properties:
                detail:
                  type: string
                current_count:
                  type: integer
                quota_limit:
                  type: integer
                user_tier:
                  type: string
                  enum: [free, basic, educator]
      '500':
        description: AI service error
```

---

**Contract Test File**: `tests/contract/test_generate_quiz_quota.py`  
**Status**: Specification complete - ready for test generation
