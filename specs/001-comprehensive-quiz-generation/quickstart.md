# Quickstart: Testing Tier Management & Missing Features

**Feature**: Comprehensive Quiz Generation Platform  
**Date**: 2025-10-03  
**Purpose**: Rapid validation of new tier management, quota enforcement, search/filter, and validation features

---

## Prerequisites

```bash
# 1. Ensure Python 3.12+ and dependencies installed
python --version  # Should be 3.12+
pip install -r requirements.txt

# 2. Set up environment variables
cp .env.example .env
# Edit .env with your Supabase credentials + ADMIN_UPGRADE_TOKEN

# 3. Apply database migration (tier column)
# TODO: Create migration file in migrations/ directory
psql $DATABASE_URL -f migrations/001_add_user_tiers.sql

# 4. Start FastAPI server
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

---

## Test Flow 1: User Tier Upgrade

**Objective**: Verify tier upgrade from free → basic increases quota from 5 to 100

### Steps

```bash
# 1. Sign up new user (defaults to free tier)
curl -X POST http://localhost:8000/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "testuser@example.com",
    "password": "SecurePass123!",
    "name": "Test User"
  }'
# Expected: 201 Created, user_id returned

# 2. Login to get auth token
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "testuser@example.com",
    "password": "SecurePass123!"
  }'
# Expected: 200 OK, cookies set with access_token

# 3. Check current tier (free, quota=5)
# TODO: Add GET /api/auth/profile endpoint to return tier
curl -X GET http://localhost:8000/api/auth/profile \
  -H "Authorization: Bearer <token_from_step2>"
# Expected: {"account_tier": "free", "quota": 5}

# 4. Upgrade to basic tier
curl -X POST http://localhost:8000/api/auth/upgrade-tier \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "target_tier": "basic",
    "verification_token": "<ADMIN_UPGRADE_TOKEN from .env>"
  }'
# Expected: 200 OK, new_tier="basic", quota=100

# 5. Verify upgrade persisted
curl -X GET http://localhost:8000/api/auth/profile \
  -H "Authorization: Bearer <token>"
# Expected: {"account_tier": "basic", "quota": 100}
```

**Success Criteria**:
- ✅ New users default to "free" tier
- ✅ Upgrade endpoint changes tier from "free" to "basic"
- ✅ Quota increases from 5 to 100 after upgrade
- ✅ Invalid verification token returns 403

---

## Test Flow 2: Quiz Quota Enforcement

**Objective**: Verify free tier users cannot create 6th quiz (quota limit)

### Steps

```bash
# 1. Login as free tier user
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "free@example.com", "password": "pass"}' \
  | jq -r '.access_token')

# 2. Create 5 quizzes (up to quota limit)
for i in {1..5}; do
  curl -X POST http://localhost:8000/api/quiz/generate/text \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
      \"title\": \"Test Quiz $i\",
      \"content\": \"This is test content for quiz $i with sufficient length for generation\",
      \"num_questions\": 3
    }"
  echo "Created quiz $i"
done
# Expected: 5x 200 OK responses

# 3. Attempt to create 6th quiz (should be rejected)
curl -X POST http://localhost:8000/api/quiz/generate/text \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Quiz 6 - Should Fail",
    "content": "This quiz should be rejected due to quota limit",
    "num_questions": 3
  }'
# Expected: 403 Forbidden
# Response: {"detail": "Quiz quota exceeded for free tier (5/5). Upgrade to basic for 100 quizzes.", ...}

# 4. Upgrade to basic tier
curl -X POST http://localhost:8000/api/auth/upgrade-tier \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"target_tier": "basic", "verification_token": "<ADMIN_TOKEN>"}'

# 5. Retry 6th quiz creation (now should succeed)
curl -X POST http://localhost:8000/api/quiz/generate/text \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Quiz 6 - Now Succeeds",
    "content": "This quiz should succeed after upgrade to basic tier",
    "num_questions": 3
  }'
# Expected: 200 OK
```

**Success Criteria**:
- ✅ Free tier blocked at 5 quizzes with clear error message
- ✅ Error includes current_count, quota_limit, user_tier
- ✅ After upgrade to basic, can create more quizzes
- ✅ Quota check happens BEFORE quiz generation (fast rejection)

---

## Test Flow 3: Search and Filter Quizzes

**Objective**: Verify title search and date range filtering work correctly

### Steps

```bash
# 1. Create test quizzes with specific titles and dates
# (Manually set created_at for testing, or wait between creations)
curl -X POST http://localhost:8000/api/quiz/generate/text \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Python Programming Basics",
    "content": "Learn Python fundamentals...",
    "num_questions": 5
  }'

curl -X POST http://localhost:8000/api/quiz/generate/text \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Advanced Python Techniques",
    "content": "Master advanced Python...",
    "num_questions": 5
  }'

curl -X POST http://localhost:8000/api/quiz/generate/text \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "JavaScript Fundamentals",
    "content": "Introduction to JavaScript...",
    "num_questions": 5
  }'

# 2. Search by title: "python" (case-insensitive)
curl -X GET "http://localhost:8000/api/quiz/my-quizzes?title=python" \
  -H "Authorization: Bearer $TOKEN"
# Expected: 200 OK, array with 2 quizzes (both Python titles)

# 3. Search by title: "PYTHON" (case-insensitive)
curl -X GET "http://localhost:8000/api/quiz/my-quizzes?title=PYTHON" \
  -H "Authorization: Bearer $TOKEN"
# Expected: 200 OK, same 2 quizzes (case doesn't matter)

# 4. Search by title: "javascript"
curl -X GET "http://localhost:8000/api/quiz/my-quizzes?title=javascript" \
  -H "Authorization: Bearer $TOKEN"
# Expected: 200 OK, array with 1 quiz (JavaScript Fundamentals)

# 5. Search with no matches
curl -X GET "http://localhost:8000/api/quiz/my-quizzes?title=nonexistent" \
  -H "Authorization: Bearer $TOKEN"
# Expected: 200 OK, empty array []

# 6. Filter by date range (today's quizzes)
TODAY=$(date +%Y-%m-%d)
curl -X GET "http://localhost:8000/api/quiz/my-quizzes?start_date=$TODAY&end_date=$TODAY" \
  -H "Authorization: Bearer $TOKEN"
# Expected: 200 OK, array with all 3 quizzes created today

# 7. Combined search: title + date
curl -X GET "http://localhost:8000/api/quiz/my-quizzes?title=python&start_date=$TODAY" \
  -H "Authorization: Bearer $TOKEN"
# Expected: 200 OK, array with 2 Python quizzes created today
```

**Success Criteria**:
- ✅ Title search is case-insensitive (Python = python = PYTHON)
- ✅ Title search uses partial match (finds "Python Programming" with query "python")
- ✅ Empty search results return empty array (not error)
- ✅ Date range filtering inclusive (start_date <= created_at <= end_date)
- ✅ Combined filters work together (AND logic)

---

## Test Flow 4: File Type Restrictions by Tier

**Objective**: Verify free tier cannot upload DOCX, but basic/educator can

### Steps

```bash
# 1. Create test files
echo "This is a test PDF content" > test.txt
echo "application/pdf mock" > test.pdf
echo "DOCX mock content" > test.docx

# 2. Login as free tier user
FREE_TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "free@example.com", "password": "pass"}' \
  | jq -r '.access_token')

# 3. Upload TXT file as free user (allowed)
curl -X POST http://localhost:8000/api/files/upload \
  -H "Authorization: Bearer $FREE_TOKEN" \
  -F "file=@test.txt"
# Expected: 200 OK

# 4. Upload PDF file as free user (allowed)
curl -X POST http://localhost:8000/api/files/upload \
  -H "Authorization: Bearer $FREE_TOKEN" \
  -F "file=@test.pdf"
# Expected: 200 OK

# 5. Attempt to upload DOCX as free user (rejected)
curl -X POST http://localhost:8000/api/files/upload \
  -H "Authorization: Bearer $FREE_TOKEN" \
  -F "file=@test.docx"
# Expected: 403 Forbidden
# Response: {"detail": "DOCX files require basic or educator tier...", ...}

# 6. Upgrade to basic tier
curl -X POST http://localhost:8000/api/auth/upgrade-tier \
  -H "Authorization: Bearer $FREE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"target_tier": "basic", "verification_token": "<ADMIN_TOKEN>"}'

# 7. Retry DOCX upload as basic user (now allowed)
curl -X POST http://localhost:8000/api/files/upload \
  -H "Authorization: Bearer $FREE_TOKEN" \
  -F "file=@test.docx"
# Expected: 200 OK
```

**Success Criteria**:
- ✅ Free tier can upload PDF and TXT
- ✅ Free tier cannot upload DOCX (403 with upgrade message)
- ✅ Basic/Educator tiers can upload all types (PDF, TXT, DOCX)
- ✅ Error message includes tier information

---

## Test Flow 5: File Size Limit (10MB)

**Objective**: Verify files over 10MB are rejected

### Steps

```bash
# 1. Create 9MB test file (under limit)
dd if=/dev/zero of=9mb.pdf bs=1M count=9

# 2. Create 11MB test file (over limit)
dd if=/dev/zero of=11mb.pdf bs=1M count=11

# 3. Upload 9MB file (should succeed)
curl -X POST http://localhost:8000/api/files/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@9mb.pdf"
# Expected: 200 OK

# 4. Upload 11MB file (should be rejected)
curl -X POST http://localhost:8000/api/files/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@11mb.pdf"
# Expected: 413 Payload Too Large
# Response: {"detail": "File size exceeds 10MB limit", "file_size_bytes": 11534336, "max_size_bytes": 10485760}

# Cleanup
rm 9mb.pdf 11mb.pdf
```

**Success Criteria**:
- ✅ Files under 10MB accepted
- ✅ Files over 10MB rejected with 413 status
- ✅ Error includes actual file size and limit in bytes

---

## Test Flow 6: 75% Question Generation Threshold

**Objective**: Verify quiz creation fails if AI generates <75% of requested questions

### Steps

**Note**: This test requires mocking AI responses or using a test environment where AI can be controlled.

```python
# In tests/integration/test_generation_threshold.py

async def test_75_percent_threshold():
    # Mock OpenAI to return only 7 questions when 10 requested (70%)
    with mock.patch('services.ai_services.openai_service.generate_quiz') as mock_gen:
        mock_gen.return_value = [question1, question2, ..., question7]  # 7 questions
        
        response = client.post(
            "/api/quiz/generate/text",
            json={"title": "Test", "content": "...", "num_questions": 10},
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Should be rejected (7/10 = 70% < 75%)
        assert response.status_code == 400
        assert "minimum 75% required" in response.json()["detail"]
        assert response.json()["questions_generated"] == 7
        assert response.json()["questions_requested"] == 10

async def test_75_percent_threshold_exact():
    # Mock OpenAI to return exactly 15 questions when 20 requested (75%)
    with mock.patch('services.ai_services.openai_service.generate_quiz') as mock_gen:
        mock_gen.return_value = [q1, ..., q15]  # 15 questions
        
        response = client.post(
            "/api/quiz/generate/text",
            json={"title": "Test", "content": "...", "num_questions": 20},
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Should succeed (15/20 = 75% exactly)
        assert response.status_code == 200
```

**Success Criteria**:
- ✅ Generation with ≥75% questions succeeds
- ✅ Generation with <75% questions fails with 400 error
- ✅ Error includes questions_generated, questions_requested, threshold
- ✅ No partial quiz data saved when threshold not met

---

## Running All Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run all contract tests
pytest tests/contract/ -v

# Run all integration tests
pytest tests/integration/ -v

# Run specific test file
pytest tests/contract/test_upgrade_tier.py -v

# Run with coverage
pytest --cov=. --cov-report=html
```

---

## Test Flow 7: Web URL Quiz Generation

**Objective**: Verify quiz generation from web page URLs with security validation

### Steps

```bash
# 1. Sign up and login as basic tier user (repeat steps from Flow 1)
# Or upgrade existing user to basic tier

# 2. Generate quiz from Wikipedia article
curl -X POST http://localhost:8000/api/quiz/generate/url \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://en.wikipedia.org/wiki/Artificial_Intelligence",
    "title": "AI Fundamentals Quiz",
    "num_questions": 10,
    "question_types": ["multiple_choice", "true_false"]
  }'
# Expected: 201 Created, quiz returned with content_source_type="url"

# 3. Verify content source tracking
curl -X GET http://localhost:8000/api/quiz/$QUIZ_ID \
  -H "Authorization: Bearer $ACCESS_TOKEN"
# Expected: content_source_reference contains the Wikipedia URL

# 4. Test tier restriction (free tier blocked)
# Create a free tier user and attempt URL generation
curl -X POST http://localhost:8000/api/quiz/generate/url \
  -H "Authorization: Bearer $FREE_USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "title": "Test Quiz",
    "num_questions": 5,
    "question_types": ["multiple_choice"]
  }'
# Expected: 403 Forbidden - tier requirement error

# 5. Test security validation (private IP blocked)
curl -X POST http://localhost:8000/api/quiz/generate/url \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "http://192.168.1.1/admin",
    "title": "Blocked Quiz",
    "num_questions": 5,
    "question_types": ["multiple_choice"]
  }'
# Expected: 403 Forbidden - security violation error

# 6. Test localhost blocking
curl -X POST http://localhost:8000/api/quiz/generate/url \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "http://localhost:8080/data",
    "title": "Blocked Quiz",
    "num_questions": 5,
    "question_types": ["multiple_choice"]
  }'
# Expected: 403 Forbidden - security violation error

# 7. Test insufficient content handling
curl -X POST http://localhost:8000/api/quiz/generate/url \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",  # Minimal content page
    "title": "Short Content Quiz",
    "num_questions": 10,
    "question_types": ["multiple_choice"]
  }'
# Expected: 400 Bad Request - insufficient content or questions generated

# 8. Test timeout handling (optional - requires slow URL)
# This test may take 30+ seconds to complete
curl -X POST http://localhost:8000/api/quiz/generate/url \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "http://httpstat.us/200?sleep=35000",
    "title": "Timeout Test",
    "num_questions": 5,
    "question_types": ["multiple_choice"]
  }'
# Expected: 408 Request Timeout after retry attempts
```

### Validation Checklist

- [ ] URL quiz generation works for basic/educator tiers
- [ ] Free tier users blocked from URL generation (403)
- [ ] Private IPs blocked (192.168.x.x, 10.x.x.x, 127.0.0.1)
- [ ] Localhost URLs blocked
- [ ] Content validation enforced (100 char minimum)
- [ ] 75% question threshold enforced for URL content
- [ ] Timeout protection works (30s limit)
- [ ] Quiz stored with content_source_type='url'
- [ ] content_source_reference contains original URL
- [ ] Playwright successfully handles JavaScript-rendered pages

---

## Running Contract Tests

```bash
# Run all contract tests
pytest tests/contract/ -v

# Run all integration tests
pytest tests/integration/ -v

# Run specific test file
pytest tests/contract/test_upgrade_tier.py -v
pytest tests/contract/test_generate_quiz_from_url.py -v

# Run with coverage
pytest --cov=. --cov-report=html
```

---

## Expected Outcomes

After completing all test flows:

1. **Tier Management**: Users can upgrade tiers, quotas enforced correctly
2. **Quota Enforcement**: Free tier limited to 5 quizzes, upgrade increases limit
3. **Search/Filter**: Title search (case-insensitive) and date filtering work
4. **File Type Restrictions**: Free tier blocked from DOCX uploads
5. **File Size Limits**: Files >10MB rejected with clear error
6. **Generation Threshold**: Quizzes with <75% questions rejected
7. **Web Scraping**: URLs work for paid tiers, security validated, content extracted properly

**All tests passing** = Ready for production deployment.

---

**Status**: Quickstart guide complete - ready for developer use
