# Tasks: Comprehensive Quiz Generation Platform

**Input**: Design documents from `/specs/001-comprehensive-quiz-generation/`  
**Prerequisites**: plan.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅  
**Branch**: `001-comprehensive-quiz-generation`  
**Date**: 2025-10-03

---

## Overview

This task list implements **missing features** (tier management, quotas, search/filter, web scraping, validation enhancements) and creates comprehensive **tests for existing code** (authentication, quiz generation, file handling, submissions).

**Implementation Status**:
- ✅ **Existing**: Auth, Quiz generation (text/PDF/DOCX), File management, Submissions
- ❌ **Missing**: Tier management, Quotas, Search/filter, Web scraping, Enhanced validation
- 🧪 **Needs Tests**: All existing features lack comprehensive test coverage

**Total Tasks**: 45 (15 setup/tests for existing code + 30 new features)

---

## Phase 3.1: Setup & Dependencies

**Objective**: Install dependencies, configure testing, prepare database

- [x] **T001** Install web scraping dependencies: `uv pip install playwright trafilatura tenacity` ✅
- [x] **T002** Install Playwright browsers: `playwright install chromium` ✅
- [x] **T003** Install testing dependencies: `uv pip install pytest-cov` (pytest, pytest-asyncio, httpx already installed) ✅
- [x] **T004** Create pytest configuration in `pytest.ini` with async support and coverage settings ✅
- [x] **T005** Create test database migration SQL in `migrations/001_add_missing_features.sql` (account_tier, content_source_type, indexes) ✅
- [x] **T006** Apply migration to database: Added content_source tracking to quizzes, search indexes ✅
- [x] **T007** Create `.env.test` with test environment variables (test database, mock tokens) ✅

**Dependencies**: T001-T003 can run in parallel, T005 blocks T006

**Note**: Migration partially applied - auth.users and files table require Supabase dashboard configuration

---

## Phase 3.2: Tests for Existing Code (TDD - MUST FAIL FIRST)

**Objective**: Write comprehensive tests for already-implemented features before refactoring

### 3.2.1: Authentication Tests

- [x] **T008** [P] Contract test POST /api/auth/signup in `tests/contract/test_auth_signup.py`
  - Test valid signup (201 response with user_id)
  - Test duplicate email (400 error)
  - Test invalid email format (422 error)
  - Test weak password (400 error)

- [x] **T009** [P] Contract test POST /api/auth/login in `tests/contract/test_auth_login.py`
  - Test valid login (200 with access/refresh tokens)
  - Test invalid credentials (401 error)
  - Test missing fields (422 error)

- [x] **T010** [P] Contract test POST /api/auth/logout in `tests/contract/test_auth_logout.py`
  - Test successful logout (200)
  - Test logout without auth (401 error)

- [x] **T011** [P] Integration test full auth flow in `tests/integration/test_auth_flow.py`
  - Signup → Login → Access protected endpoint → Logout → Verify token invalid

### 3.2.2: Quiz Generation Tests (Existing Features)

- [x] **T012** [P] Contract test POST /api/quiz/generate (text) in `tests/contract/test_quiz_generate_text.py`
  - Test valid text input (201 with quiz_id and questions)
  - Test insufficient text (<10 chars) (400 error)
  - Test invalid question types (422 error)
  - Test num_questions out of range (422 error)

- [x] **T013** [P] Contract test POST /api/quiz/generate/file (PDF) in `tests/contract/test_quiz_generate_pdf.py`
  - Test valid PDF upload (201 with quiz)
  - Test corrupted PDF (400 error)
  - Test PDF with no extractable text (400 error)

- [ ] **T014** [P] Contract test POST /api/quiz/generate/file (DOCX) in `tests/contract/test_quiz_generate_docx.py`
  - Test valid DOCX upload (201 with quiz)
  - Test corrupted DOCX (400 error)

- [ ] **T015** [P] Integration test quiz generation flow in `tests/integration/test_quiz_generation.py`
  - Upload file → Generate quiz → Verify questions stored → Retrieve quiz

##### 3.2.3. File Management Tests (T016-T018)

- [x] **T016**: Contract test for POST /api/files/upload ✅
  - Valid file upload (DOCX, text)
  - Unsupported file types (400)
  - Empty files (400)
  - Unauthorized (401)
  
- [x] **T017**: Contract test for GET /api/files/metadata ✅
  - List user's files (200)
  - Empty list for new user (200 with empty array)
  - Unauthorized (401)
  
- [x] **T018**: Contract test for DELETE /api/files/{file_id} ✅
  - Valid deletion (204)
  - Delete non-existent file (404)
  - Delete other user's file (403)
  - Unauthorized (401)

### 3.2.4: Submission Tests

- [ ] **T019** [P] Contract test POST /api/submissions in `tests/contract/test_submission_create.py`
  - Test valid submission (201 with scores and results)
  - Test invalid quiz_id (404 error)
  - Test missing answers (422 error)

- [ ] **T020** [P] Contract test GET /api/submissions/{submission_id} in `tests/contract/test_submission_get.py`
  - Test retrieve submission (200 with full results)
  - Test retrieve non-existent (404 error)
  - Test retrieve other user's submission (403 error)

**Dependencies**: All T008-T020 are parallel (different files). MUST run and FAIL before proceeding to Phase 3.3.

---

## Phase 3.3: Tier Management Implementation

**Objective**: Implement user tier system with free/basic/educator tiers

### 3.3.1: Database & Models

- [ ] **T021** Apply database migration from T005 to production database
- [ ] **T022** Update `schemas/user.py` to add `account_tier` field with Literal["free", "basic", "educator"]
- [ ] **T023** [P] Create `services/tier_service.py` with functions:
  - `get_user_tier(user_id: UUID) -> str`
  - `update_user_tier(user_id: UUID, tier: str) -> bool`
  - `get_tier_features(tier: str) -> dict`

### 3.3.2: Tier Upgrade Endpoint

- [ ] **T024** [P] Contract test POST /api/auth/upgrade-tier in `tests/contract/test_upgrade_tier.py`
  - Test free → basic upgrade (200)
  - Test free → educator upgrade (200)
  - Test invalid verification token (403)
  - Test invalid target tier (422)

- [ ] **T025** Create `handlers/tier_handler.py` with `upgrade_user_tier()` function
- [ ] **T026** Add POST /api/auth/upgrade-tier route in `api/auth_routes.py`
- [ ] **T027** Verify T024 contract test now passes

**Dependencies**: T022 blocks T023, T024 must fail before T025-T026, T027 validates

---

## Phase 3.4: Quota Enforcement

**Objective**: Enforce quiz creation limits based on user tier

### 3.4.1: Quota Service

- [ ] **T028** [P] Create `services/quota_service.py` with functions:
  - `get_quota_limit(tier: str) -> int`
  - `get_user_quiz_count(user_id: UUID) -> int`
  - `can_create_quiz(user_id: UUID, tier: str) -> bool`

### 3.4.2: Quota Enforcement in Handlers

- [ ] **T029** [P] Contract test quota enforcement in `tests/contract/test_generate_quiz_quota.py`
  - Test free user at limit (403 error)
  - Test basic user at limit (403 error)
  - Test free user under limit (201 success)

- [ ] **T030** Update `handlers/quiz_handlers.py` to add quota validation before quiz generation
  - Add `validate_quota()` call at start of `generate_quiz()` and `generate_quiz_from_file()`
  - Return HTTP 403 with quota error message if exceeded

- [ ] **T031** Verify T029 contract test now passes

**Dependencies**: T028 blocks T030, T029 must fail before T030

---

## Phase 3.5: Search & Filter

**Objective**: Add search by title and filter by date range for quizzes

### 3.5.1: Database Query Enhancement

- [ ] **T032** [P] Update `services/db_services/supabase_quiz.py` to add `search_user_quizzes()` function:
  - Accept parameters: `user_id`, `title_query` (optional), `start_date` (optional), `end_date` (optional)
  - Use ILIKE for title search
  - Use gte/lte for date filtering
  - Return paginated results

### 3.5.2: Search API Endpoint

- [ ] **T033** [P] Contract test GET /api/quiz/my-quizzes with filters in `tests/contract/test_search_quizzes.py`
  - Test search by title (200 with filtered results)
  - Test filter by date range (200 with filtered results)
  - Test combined title + date filters (200)
  - Test no results (200 with empty array)

- [ ] **T034** Update `handlers/quiz_handlers.py` to add `search_quizzes()` function
- [ ] **T035** Update GET /api/quiz/my-quizzes route in `api/quiz_routes.py` to add query parameters
- [ ] **T036** Verify T033 contract test now passes

**Dependencies**: T032 blocks T034, T033 must fail before T034-T035

---

## Phase 3.6: File Type & Size Validation

**Objective**: Restrict DOCX to paid tiers, enforce 10MB limit

### 3.6.1: Validation Service

- [ ] **T037** [P] Update `schemas/files.py` to add `file_size_bytes` field with max 10MB validation

### 3.6.2: Tier-Based File Validation

- [ ] **T038** [P] Contract test file type restrictions in `tests/contract/test_file_upload_validation.py`
  - Test free user upload DOCX (403 error)
  - Test basic user upload DOCX (201 success)
  - Test file >10MB (413 error)
  - Test file exactly 10MB (201 success)

- [ ] **T039** Update `handlers/file_handlers.py` to add:
  - File size validation (reject >10MB with HTTP 413)
  - Tier-based file type validation (reject DOCX for free tier with HTTP 403)

- [ ] **T040** Update POST /api/files/upload route in `api/file_routes.py` with validation
- [ ] **T041** Verify T038 contract test now passes

**Dependencies**: T037 blocks T039, T038 must fail before T039-T040

---

## Phase 3.7: 75% Question Threshold

**Objective**: Reject quizzes if <75% of requested questions generated

### 3.7.1: Threshold Validation

- [ ] **T042** [P] Update `services/ai_services/chunking_service.py` to add `validate_question_threshold()` function:
  - Calculate percentage: `generated_count / requested_count`
  - Return True if >= 0.75, False otherwise

- [ ] **T043** [P] Integration test 75% threshold in `tests/integration/test_generation_threshold.py`
  - Mock AI to return only 6/10 questions → expect 400 error
  - Mock AI to return 8/10 questions → expect 201 success
  - Mock AI to return 10/10 questions → expect 201 success

- [ ] **T044** Update `handlers/quiz_handlers.py` to validate threshold after AI generation:
  - Call `validate_question_threshold()` after questions generated
  - Rollback quiz creation if threshold not met
  - Return HTTP 400 with clear error message

- [ ] **T045** Verify T043 integration test now passes

**Dependencies**: T042 blocks T044, T043 must fail before T044

---

## Phase 3.8: Web Scraping Implementation

**Objective**: Add web URL quiz generation for basic/educator tiers

### 3.8.1: Web Scraper Service

- [ ] **T046** [P] Create `services/ai_services/web_scraper_service.py` with functions:
  - `validate_url_security(url: str) -> bool` (check private IPs, localhost, blocklist)
  - `scrape_url(url: str) -> str` (Playwright + trafilatura)
  - `extract_main_content(html: str) -> str` (trafilatura extraction)
  - Add exponential backoff retry logic with tenacity

- [ ] **T047** [P] Unit test URL security validation in `tests/unit/test_url_security.py`
  - Test private IPs blocked (192.168.x.x, 10.x.x.x, 127.0.0.1)
  - Test localhost blocked
  - Test valid public URLs allowed

- [ ] **T048** [P] Unit test web scraping in `tests/unit/test_web_scraper.py` (with mocks)
  - Test successful scraping
  - Test timeout handling
  - Test content extraction
  - Test retry logic

### 3.8.2: URL Quiz Generation Endpoint

- [ ] **T049** [P] Contract test POST /api/quiz/generate/url in `tests/contract/test_generate_quiz_from_url.py`
  - Test basic user with valid URL (201 success)
  - Test free user (403 tier restriction error)
  - Test private IP URL (403 security error)
  - Test localhost URL (403 security error)
  - Test insufficient content (400 error)
  - Test timeout (408 error after retries)
  - Test <75% questions generated (400 error)

- [ ] **T050** Update `schemas/quiz.py` to add:
  - `content_source_type` field: Literal["file", "url"]
  - `content_source_reference` field: str

- [ ] **T051** Create `generate_quiz_from_url()` function in `handlers/quiz_handlers.py`:
  - Validate user tier (basic/educator only)
  - Validate quota
  - Call `validate_url_security()`
  - Call `scrape_url()` with timeout/retry
  - Validate content size (100 char min, 500KB max)
  - Chunk content and generate questions
  - Validate 75% threshold
  - Store quiz with content_source_type='url'

- [ ] **T052** Add POST /api/quiz/generate/url route in `api/quiz_routes.py`
- [ ] **T053** Verify T049 contract test now passes

### 3.8.3: Integration Testing

- [ ] **T054** [P] Integration test web scraping flow in `tests/integration/test_web_scraping_flow.py`
  - Test full flow: URL → scrape → extract → chunk → generate → store
  - Test with real Wikipedia URL (or use VCR.py to record HTTP)
  - Verify content_source_reference stored correctly

**Dependencies**: 
- T046-T048 are parallel (different files)
- T049 must fail before T050-T052
- T046 blocks T051
- T050 blocks T051
- T054 runs after T053 passes

---

## Phase 3.9: Integration & Polish

**Objective**: Integration tests, documentation, performance validation

### 3.9.1: Cross-Feature Integration Tests

- [ ] **T055** [P] Integration test tier upgrade + quota flow in `tests/integration/test_tier_quota_flow.py`
  - Create free user → hit quota limit → upgrade to basic → create more quizzes

- [ ] **T056** [P] Integration test search with multiple users in `tests/integration/test_search_multi_user.py`
  - Create users with different quizzes → verify search isolation

- [ ] **T057** [P] Integration test file type restrictions across tiers in `tests/integration/test_file_tier_restrictions.py`
  - Test all file types across all three tiers

### 3.9.2: Performance & Load Testing

- [ ] **T058** [P] Performance test quiz generation in `tests/performance/test_quiz_generation_perf.py`
  - Verify text generation <60s
  - Verify file generation <60s
  - Verify web scraping <30s

- [ ] **T059** [P] Load test quota queries in `tests/performance/test_quota_perf.py`
  - Verify quota check <100ms with 1000 quizzes

### 3.9.3: Documentation & Deployment

- [ ] **T060** [P] Update `README.md` with:
  - New tier management section
  - Web scraping dependencies installation
  - Environment variables for admin upgrade token

- [ ] **T061** [P] Update OpenAPI documentation in `main.py` with new endpoints:
  - POST /api/auth/upgrade-tier
  - GET /api/quiz/my-quizzes (with query params)
  - POST /api/quiz/generate/url

- [ ] **T062** [P] Create deployment guide in `docs/DEPLOYMENT.md`:
  - Database migration steps
  - Playwright installation on server
  - Environment variable configuration

- [ ] **T063** Execute all quickstart test flows from `specs/001-comprehensive-quiz-generation/quickstart.md`
  - Test Flow 1: Tier upgrade
  - Test Flow 2: Quota enforcement
  - Test Flow 3: Search/filter
  - Test Flow 4: File restrictions
  - Test Flow 5: File size limits
  - Test Flow 6: 75% threshold
  - Test Flow 7: Web URL generation

- [ ] **T064** Run full test suite: `pytest tests/ -v --cov=. --cov-report=html`
- [ ] **T065** Verify constitution compliance:
  - API-First: All features exposed via REST
  - Content Agnostic: URL source uses same generation pipeline
  - Service-Oriented: Clear service boundaries maintained
  - Logging: All operations logged
  - Security: Tier validation, URL security, RLS maintained

**Dependencies**: T055-T059 parallel, T060-T062 parallel, T063 after all implementation complete

---

## Dependencies Summary

```
Setup (T001-T007)
  ↓
Tests for Existing Code (T008-T020) [ALL PARALLEL]
  ↓
Tier Management (T021-T027)
  T022 → T023
  T024 (must fail) → T025-T026 → T027 (passes)
  ↓
Quota Enforcement (T028-T031)
  T028 → T030
  T029 (must fail) → T030 → T031 (passes)
  ↓
Search & Filter (T032-T036)
  T032 → T034
  T033 (must fail) → T034-T035 → T036 (passes)
  ↓
File Validation (T037-T041)
  T037 → T039
  T038 (must fail) → T039-T040 → T041 (passes)
  ↓
75% Threshold (T042-T045) [T042, T043 parallel]
  T042 → T044
  T043 (must fail) → T044 → T045 (passes)
  ↓
Web Scraping (T046-T054)
  T046, T047, T048, T049 [ALL PARALLEL]
  T046 → T051
  T050 → T051
  T049 (must fail) → T050-T052 → T053 (passes)
  T053 → T054
  ↓
Polish (T055-T065)
  T055-T059 [ALL PARALLEL]
  T060-T062 [ALL PARALLEL]
  T063 after all implementation
```

---

## Parallel Execution Examples

### Launch Contract Tests for Existing Code (Phase 3.2)
```bash
# All can run simultaneously (different files)
pytest tests/contract/test_auth_signup.py &
pytest tests/contract/test_auth_login.py &
pytest tests/contract/test_auth_logout.py &
pytest tests/contract/test_quiz_generate_text.py &
pytest tests/contract/test_quiz_generate_pdf.py &
pytest tests/contract/test_quiz_generate_docx.py &
pytest tests/contract/test_file_upload.py &
pytest tests/contract/test_files_list.py &
pytest tests/contract/test_file_delete.py &
pytest tests/contract/test_submission_create.py &
pytest tests/contract/test_submission_get.py &
wait
```

### Launch Web Scraping Tests (Phase 3.8.1)
```bash
# All independent tests
pytest tests/unit/test_url_security.py &
pytest tests/unit/test_web_scraper.py &
pytest tests/contract/test_generate_quiz_from_url.py &
wait
```

### Launch Documentation Updates (Phase 3.9.3)
```bash
# All different files
vim README.md &
vim main.py &  # OpenAPI updates
vim docs/DEPLOYMENT.md &
```

---

## Validation Checklist

**Before Starting Implementation**:
- [x] All contracts have corresponding tests (5 contracts → 5 contract test files)
- [x] All entities have model tasks (User tier, Quiz content_source)
- [x] All tests come before implementation (TDD order enforced)
- [x] Parallel tasks truly independent (verified file-level isolation)
- [x] Each task specifies exact file path
- [x] No task modifies same file as another [P] task

**After Completing All Tasks**:
- [ ] All 65 tasks completed and committed
- [ ] All contract tests passing
- [ ] All integration tests passing
- [ ] Test coverage >80%
- [ ] All quickstart flows validated
- [ ] Constitution compliance verified
- [ ] Documentation updated
- [ ] Ready for production deployment

---

## Notes

**TDD Enforcement**: Tests T008-T020 (existing code) and all contract tests (T024, T029, T033, T038, T049) MUST be written and run (expecting failures) BEFORE implementing their corresponding features.

**Parallel Markers**: [P] indicates tasks that can run simultaneously because they:
1. Modify different files
2. Have no dependencies on each other
3. Are independent tests or documentation updates

**Commit Strategy**: Commit after each task or logical group. Example:
- After T001-T007: "Setup dependencies and test infrastructure"
- After T008-T020: "Add contract tests for existing features"
- After T021-T027: "Implement tier management system"

**Test Database**: Use separate test database to avoid polluting production data. Set `TEST_DATABASE_URL` in `.env.test`.

**Web Scraping**: Playwright requires Chromium browser installation (~170MB). Consider using Docker for CI/CD environments.

---

**Status**: Tasks ready for execution. Start with Phase 3.1 (Setup), then Phase 3.2 (write all tests first), then proceed with TDD implementation.

**Estimated Timeline**: 
- Phase 3.1: 1 day
- Phase 3.2: 2-3 days (comprehensive test coverage)
- Phase 3.3-3.8: 5-7 days (implementation with TDD)
- Phase 3.9: 1-2 days (polish and validation)
- **Total**: 9-13 days for 1 developer, 6-8 days for 2 developers (parallel execution)
