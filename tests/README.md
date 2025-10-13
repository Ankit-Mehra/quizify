# Quota Validation Tests

This directory contains tests for the quota validation feature implemented in the quiz generation endpoints.

## Test Files

### `test_quota_validation.py`
Unit tests for the quota validation logic:
- `TestGetUserTierInfo`: Tests for the `get_user_tier_info()` database function
  - Success case with valid user
  - Error case when user not found
  
- `TestValidateUserQuota`: Tests for the `validate_user_quota()` validation function
  - Free tier: under limit (passes), at limit (403 error)
  - Basic tier: under limit (passes), at limit (403 error)
  - Educator tier: under limit (passes), at limit (403 error)

### `test_quota_integration.py`
Integration tests for the quiz generation endpoints with quota enforcement:
- `TestQuotaEnforcementTextEndpoint`: Tests for `/api/quiz/generate/text`
  - Free tier scenarios (under/at limit)
  - Basic tier scenarios (under/at limit)
  - Educator tier scenarios (under/at limit)
  
- `TestQuotaEnforcementFileEndpoint`: Tests for `/api/quiz/generate/file`
  - Free tier scenarios (under/at limit)
  - Basic tier scenarios (under/at limit)
  
- `TestQuotaCheckBeforeGeneration`: Verification tests
  - Ensures quota check happens BEFORE AI generation (no API waste)
  - Tests for both text and file endpoints

## Running the Tests

### Prerequisites
```bash
pip install -r requirements.txt
```

### Run All Tests
```bash
pytest tests/ -v
```

### Run Specific Test Files
```bash
# Unit tests only
pytest tests/test_quota_validation.py -v

# Integration tests only
pytest tests/test_quota_integration.py -v
```

### Run Specific Test Classes
```bash
# Test quota validation logic
pytest tests/test_quota_validation.py::TestValidateUserQuota -v

# Test text endpoint quota enforcement
pytest tests/test_quota_integration.py::TestQuotaEnforcementTextEndpoint -v
```

### Run with Coverage
```bash
pytest tests/ --cov=handlers --cov=services/db_services --cov-report=html
```

## Expected Results

All tests should pass. The tests verify:
1. ✅ Free tier users cannot generate more than 5 quizzes
2. ✅ Basic tier users cannot generate more than 100 quizzes
3. ✅ Educator tier users cannot generate more than 500 quizzes
4. ✅ 403 error returned with proper format when quota exceeded
5. ✅ Error message includes current count, limit, and tier
6. ✅ Quota check happens BEFORE AI generation (don't waste API calls)

## Test Coverage

The tests cover:
- `handlers/quiz_handlers.py::validate_user_quota()`
- `handlers/quiz_handlers.py::generate_quiz_from_text()`
- `handlers/quiz_handlers.py::generate_quiz_from_file_openai()`
- `services/db_services/supabase_quiz.py::get_user_tier_info()`

## Error Response Format

When quota is exceeded, the API returns HTTP 403 with:
```json
{
  "detail": "Quiz quota exceeded for free tier (5/5). Upgrade to basic for 100 quizzes.",
  "current_count": 5,
  "quota_limit": 5,
  "user_tier": "free"
}
```
