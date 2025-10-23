# Actual vs Specified API Contracts Summary

**Last Updated**: 2025-10-23 (Corrected after code verification)  
**Branch**: test/quiz-generation-and-taking-endpoints  
**Purpose**: Document what's ACTUALLY implemented vs what was specified

---

## Overview

This folder contains two sets of API contracts:

### 📋 **Original Contracts** (Specification)
Files without `IMPLEMENTED_` prefix show the **intended design** from the feature spec:
- `generate-quiz-quota.md` - What SHOULD be implemented
- `upgrade-tier.md` - What SHOULD be implemented
- `search-quizzes.md` - What SHOULD be implemented
- `generate-quiz-from-url.md` - What SHOULD be implemented (NOW IMPLEMENTED ✅)
- `file-upload-validation.md` - What SHOULD be implemented

### ✅ **Actual Implementation Contracts** (Reality)
Files with `IMPLEMENTED_` prefix show what's **currently in the codebase**:
- `IMPLEMENTED_generate-quiz-from-text.md` - Actual behavior (HAS quota validation + size limit)
- `IMPLEMENTED_get-my-quizzes.md` - Actual behavior of quiz listing
- `IMPLEMENTED_generate-quiz-from-file.md` - Actual behavior (HAS quota validation)

---

## What's Implemented


### ✅ Endpoints That Exist

| Endpoint | Status | Notes |
|----------|--------|-------|
| `POST /api/quiz/generate-text` | ✅ Works | ✅ Has quota validation (Line 321) + 10MB limit (Line 336) |
| `POST /api/quiz/generate-file` | ✅ Works | ✅ Has quota validation (Line 112) |
| `POST /api/quiz/generate/{file_id}` | ✅ Works | ✅ Has quota validation (Line 250) |
| `POST /api/quiz/generate-url` | ✅ Works | ✅ Has quota validation (Line 512) + SSRF protection |
| `GET /api/quiz/my-quizzes` | ✅ Works | No search/filter params |
| `GET /api/quiz/{quiz_id}` | ✅ Works | Fully functional |
| `DELETE /api/quiz/{quiz_id}` | ✅ Works | Fully functional |
| `POST /api/quiz/{quiz_id}/submit` | ✅ Works | ✅ Scoring + detailed results |
| `GET /api/submission/{submission_id}` | ✅ Works | ✅ Authorization enforced (own submissions only) |
| `POST /api/files/upload` | ✅ Works | ⚠️ Missing 10MB size validation |

### ❌ Endpoints That Don't Exist

| Endpoint | Priority | Effort |
|----------|----------|--------|
| `POST /api/tier/upgrade` | 🟡 MEDIUM | 3-4 hours (needs payment integration) |
| `GET /api/quiz/search` | 🟡 MEDIUM | 2-3 hours (query params + filtering) |
| `GET /api/submissions/history` | 🟡 MEDIUM | 2-3 hours (list user's submissions) |

### ❌ Endpoints That Don't Exist

| Endpoint | Priority | Effort |
|----------|----------|--------|
| `POST /api/tier/upgrade` | � MEDIUM | 3-4 hours (needs payment integration) |
| `GET /api/quiz/search` | 🟡 MEDIUM | 2-3 hours (query params + filtering) |

---

## Key Differences: Spec vs Reality (CORRECTED)

### 1. Quiz Generation (Text & File)

**Specified**:
- ✅ Check quota before generation
- ✅ Return 403 if quota exceeded
- ✅ Validate 75% generation threshold
- ✅ Return question count in response

**Actual**:
- ✅ **Quota checking IS implemented** (validate_user_quota in all handlers)
- ✅ **Tier validation works** (enforces free/basic/educator limits)
- ❌ No 75% threshold checking (generates fewer if content insufficient)
- ⚠️ Text endpoint doesn't return questions array
- ✅ File endpoint returns questions array

**Impact**: Minimal - Only threshold validation missing (non-critical).

---

### 2. Quiz Listing

**Specified**:
- ✅ Search by title (`?title=python`)
- ✅ Filter by date range (`?start_date=2025-01-01&end_date=2025-12-31`)
- ✅ Case-insensitive search
- ✅ Date validation

**Actual**:
- ❌ No query parameters
- ❌ Returns ALL quizzes
- ✅ Authorization works (only user's quizzes)

**Impact**: Poor UX for users with many quizzes; all filtering must be done client-side.

---

### 3. Tier Management

**Specified**:
- ✅ Upgrade endpoint exists
- ✅ Verification token validation
- ✅ Update profiles.account_tier
- ✅ Return new quota limits

**Actual**:
- ❌ Endpoint doesn't exist
- ❌ No way to upgrade from free tier
- ✅ Database schema ready (profiles table exists)

**Impact**: Users stuck on free tier; no monetization possible.

---

### 4. Web Scraping

**Specified**:
- ✅ Generate quiz from URL
- ✅ Tier-gated (basic/educator only)
- ✅ URL validation (no private IPs)
- ✅ Content extraction with Playwright

**Actual**:
- ❌ Endpoint doesn't exist
- ✅ Dependencies installed (playwright, trafilatura)

**Impact**: Premium feature missing; no differentiation for paid tiers.

---

### 5. File Upload Validation

**Specified**:
- ✅ 10MB file size limit
- ✅ Return 413 if too large
- ✅ Save file_size_bytes to database

**Actual**:
- ⚠️ **File size enforced during quiz generation** (10MB limit in text processing)
- ❌ **No size limit in /api/files/upload endpoint** (DoS risk)
- ✅ File type validation works
- ✅ Content length validation works (50 char min)
- ⚠️ file_size_bytes not saved to database

**Impact**: Medium - upload endpoint could accept huge files, but generation will fail.

---

## Critical Missing Features (CORRECTED)

### 🔴 HIGH Priority (Blocking Production)

1. **File Upload Size Validation**
   - **Why**: `/api/files/upload` has no size limit (DoS risk)
   - **Impact**: Users can upload 1GB+ files, exhaust storage/memory
   - **Effort**: 1-2 hours
   - **Fix**: Add MAX_FILE_SIZE check in `file_handlers.py`

### 🟡 MEDIUM Priority (UX/Premium Features)

2. **Quiz Search/Filter**
   - **Why**: Users with many quizzes have poor UX
   - **Impact**: Bad user experience, client-side performance issues
   - **Effort**: 2-3 hours
   - **Blockers**: None

3. **Tier Upgrade Endpoint**
   - **Why**: Users can't self-service upgrade (admin must do it)
   - **Impact**: Admin bottleneck, poor UX
   - **Effort**: 3-4 hours
   - **Blockers**: Need payment integration or verification token strategy

### 🟢 LOW Priority (Polish)

4. **75% Question Threshold**
   - **Why**: Ensure sufficient questions generated
   - **Impact**: Minor - potential server issues with huge files
   - **Effort**: 1 hour
   - **Blockers**: None

---

## Testing Status

### Unit Tests
- ❌ No unit tests for quiz generation handlers
- ❌ No unit tests for quota validation (doesn't exist)
- ❌ No unit tests for tier management (doesn't exist)

### Integration Tests
- ❌ No contract tests verifying request/response formats
- ❌ No end-to-end tests for quiz generation flow
- ❌ No tests for search/filter functionality (doesn't exist)

### Recommendation
Before implementing missing features, set up contract testing framework to ensure future implementations match specs.

---

## Database Schema Status

### ✅ Ready for Use
```sql
-- Tier management (READY)
CREATE TABLE public.profiles (
  id UUID PRIMARY KEY,
  account_tier TEXT DEFAULT 'free'
);

CREATE VIEW user_tier_info AS ... -- Calculates quota usage

-- Content source tracking (READY)
ALTER TABLE quizzes 
  ADD COLUMN content_source_type TEXT,
  ADD COLUMN content_source_reference TEXT;

-- File size tracking (READY)
ALTER TABLE user_files
  ADD COLUMN file_size_bytes INTEGER;
```

All database migrations have been applied. Implementation just needs to use these existing fields.

---

## Recommended Implementation Order

### Phase 1: Core Monetization (1-2 days)
1. **Quota Enforcement** 
   - Add to `generate_quiz_from_text()`
   - Add to `generate_quiz_from_file_openai()`
   - Query `user_tier_info` view
   - Return 403 with proper error

2. **Tier Upgrade Endpoint**
   - Create `POST /api/auth/upgrade-tier`
   - Update `profiles.account_tier`
   - Admin token validation (MVP)

### Phase 2: User Experience (1 day)
3. **Search/Filter Quizzes**
   - Add query params to `get_user_quizzes_handler()`
   - Update database query with ILIKE
   - Add date range filtering

### Phase 3: Premium Features (1-2 days)
4. **Web URL Generation**
   - Create web scraping service
   - Add tier check (basic/educator only)
   - Create endpoint

### Phase 4: Polish (1-2 hours)
5. **File Size Validation**
   - Add 10MB limit check
   - Return 413 error
   - Save file_size_bytes

---

## How to Use This Documentation

### For Developers
1. Read `IMPLEMENTED_*.md` files to understand **current behavior**
2. Read original contract files to understand **intended behavior**
3. Use the gap analysis to prioritize work

### For Frontend Developers
1. Use `IMPLEMENTED_*.md` files for **current integration**
2. Don't implement features from original contracts until backend is ready
3. Plan for future features (quota errors, search, etc.)

### For QA/Testing
1. Test against `IMPLEMENTED_*.md` specifications
2. Don't expect features from original contracts to work
3. File bugs for deviations from `IMPLEMENTED_*.md` docs

---

## Next Steps

1. ✅ Review this documentation with team
2. ⏳ Create GitHub issues for missing features
3. ⏳ Implement Phase 1 (quota + tier upgrade)
4. ⏳ Update API documentation (OpenAPI) to match reality
5. ⏳ Add contract tests for all endpoints

---

**Maintained By**: GitHub Copilot  
**Last Updated**: 2025-10-08  
**Status**: Living document - update after each implementation
