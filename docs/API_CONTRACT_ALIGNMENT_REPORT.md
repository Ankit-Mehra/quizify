# API Contract Alignment Report

**Generated**: 2025-10-08  
**Branch**: development  
**Status**: ⚠️ MISALIGNED - Multiple contracts not implemented

---

## Summary

Analyzed 5 API contracts from `specs/001-comprehensive-quiz-generation/contracts/` against actual implementation in `api/`, `handlers/`, and `services/`.

### Alignment Status

| Contract | Status | Priority | Notes |
|----------|--------|----------|-------|
| **generate-quiz-quota.md** | ❌ NOT IMPLEMENTED | HIGH | Quota validation missing |
| **upgrade-tier.md** | ❌ NOT IMPLEMENTED | HIGH | Endpoint doesn't exist |
| **search-quizzes.md** | ❌ NOT IMPLEMENTED | MEDIUM | No search/filter params |
| **generate-quiz-from-url.md** | ❌ NOT IMPLEMENTED | MEDIUM | Endpoint doesn't exist |
| **file-upload-validation.md** | ⚠️ PARTIAL | LOW | Basic validation exists |

---

## Detailed Findings

### 1. ❌ Quiz Generation with Quota Enforcement

**Contract**: `generate-quiz-quota.md`  
**Endpoint**: `POST /api/quiz/generate/text`  
**Status**: Endpoint exists but missing quota logic

#### What's Missing:

- ❌ Quota check before generation (should return 403 if exceeded)
- ❌ Tier-based quota limits (free: 5, basic: 100, educator: 500)
- ❌ 75% generation threshold validation
- ❌ Proper error responses for quota exceeded

#### Current Implementation:

```python
# handlers/quiz_handlers.py - generate_quiz_from_text()
# ❌ No quota validation
# ❌ No tier checking
# ✅ Basic content validation exists
```

#### Required Changes:

1. Add `check_user_quota()` before quiz generation
2. Query `user_tier_info` view to get current count and limit
3. Return 403 with proper error structure if quota exceeded
4. Validate 75% generation threshold
5. Add error responses matching contract

#### Contract Error Response (Missing):

```json
{
  "detail": "Quiz quota exceeded for free tier (5/5). Upgrade to basic for 100 quizzes.",
  "current_count": 5,
  "quota_limit": 5,
  "user_tier": "free"
}
```

---

### 2. ❌ User Tier Management

**Contract**: `upgrade-tier.md`  
**Endpoint**: `POST /api/auth/upgrade-tier`  
**Status**: Endpoint does NOT exist

#### What's Missing:

- ❌ Entire endpoint not implemented
- ❌ Tier upgrade logic
- ❌ Verification token validation
- ❌ Database update to profiles table

#### Current Implementation:

```bash
# api/auth_routes.py
grep "upgrade" api/auth_routes.py
# No matches found
```

#### Database Schema Ready:
- ✅ `profiles.account_tier` column exists (via migrations)
- ✅ `user_tier_info` view exists
- ❌ No handler/route to update tier

#### Required Changes:
1. Create `POST /api/auth/upgrade-tier` route
2. Add handler in `handlers/auth_handlers.py`:
   - Validate verification token
   - Update `profiles.account_tier`
   - Return new tier and quota
3. Add business rule: Only free → basic/educator (no lateral moves)
4. Error handling for invalid tokens, duplicate upgrades

---

### 3. ❌ Quiz Search and Filter
**Contract**: `search-quizzes.md`  
**Endpoint**: `GET /api/quiz/my-quizzes`  
**Status**: Endpoint exists but missing query parameters

#### What's Missing:
- ❌ `title` query parameter (case-insensitive search)
- ❌ `start_date` query parameter (ISO 8601 filter)
- ❌ `end_date` query parameter (ISO 8601 filter)
- ❌ Date validation (start_date <= end_date)
- ❌ ILIKE query for title search

#### Current Implementation:
```python
# handlers/quiz_handlers.py - get_user_quizzes_handler()
async def get_user_quizzes_handler(
    current_user_id: str = Depends(get_current_user_id)
):
    # ❌ No query parameters accepted
    # Returns ALL quizzes without filtering
```

#### Required Changes:
1. Add optional query parameters:
   ```python
   async def get_user_quizzes_handler(
       current_user_id: str = Depends(get_current_user_id),
       title: Optional[str] = None,
       start_date: Optional[date] = None,
       end_date: Optional[date] = None
   ):
   ```
2. Update `get_user_quizzes()` in `services/db_services/supabase_quiz.py`:
   - Add `.ilike('title', f'%{title}%')` if title provided
   - Add `.gte('created_at', start_date)` if start_date provided
   - Add `.lte('created_at', end_date)` if end_date provided
3. Add date validation (start <= end)
4. Add error handling for invalid dates

---

### 4. ❌ Generate Quiz from Web URL
**Contract**: `generate-quiz-from-url.md`  
**Endpoint**: `POST /api/quiz/generate/url`  
**Status**: Endpoint does NOT exist

#### What's Missing:
- ❌ Entire endpoint not implemented
- ❌ Web scraping with Playwright/trafilatura
- ❌ Tier restriction (basic/educator only, 403 for free tier)
- ❌ URL validation (no private IPs, localhost)
- ❌ Content extraction from web pages

#### Dependencies Installed:
- ✅ `playwright==1.40.0` in requirements.txt
- ✅ `trafilatura==1.6.2` in requirements.txt
- ❌ No service/handler code exists

#### Required Changes:
1. Create `POST /api/quiz/generate/url` route
2. Add handler in `handlers/quiz_handlers.py`:
   - Validate URL format
   - Check tier (reject free tier with 403)
   - Scrape content using Playwright + trafilatura
   - Extract text (min 100 chars, max 500KB)
   - Generate quiz from extracted content
3. Add service in `services/web_scraping_service.py`:
   - URL validation (no private IPs)
   - Playwright browser automation
   - Content extraction
   - Error handling (timeout, 404, blocked)
4. Save with `content_source_type='url'` and `content_source_reference=url`

#### Contract Features:
- URL length: max 2048 chars
- Content length: 100 char min, 500KB max
- Timeout: 30 seconds
- User agent: Configurable via `SCRAPER_USER_AGENT` environment variable (default: QuizifyBot/1.0)

---

### 5. ⚠️ File Upload Validation
**Contract**: `file-upload-validation.md`  
**Endpoint**: `POST /api/quiz/generate/file`  
**Status**: Partially implemented

#### What's Working:
- ✅ File type validation (PDF, DOCX, TXT)
- ✅ Content extraction (PyPDF2, python-docx)
- ✅ Minimum content length (50 chars)
- ✅ Basic error messages

#### What's Missing:
- ⚠️ File size limit not enforced (contract says 10MB)
- ⚠️ No validation of file_size_bytes in database
- ⚠️ Error response doesn't match contract format exactly

#### Current Implementation:
```python
# handlers/quiz_handlers.py - generate_quiz_from_file_openai()
MIN_CONTENT_LENGTH = 50  # ✅ Matches contract

# ⚠️ No file size check before processing
# ⚠️ No file_size_bytes saved to database
```

#### Required Changes:
1. Add file size validation:
   ```python
   MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
   if len(file_bytes) > MAX_FILE_SIZE:
       raise HTTPException(status_code=413, detail="File too large. Maximum 10MB.")
   ```
2. Save `file_size_bytes` to database when storing file metadata
3. Align error messages with contract format

---

## Database Schema Status

### ✅ Ready for Implementation:
```sql
-- Profiles table with tier
CREATE TABLE public.profiles (
  id UUID REFERENCES auth.users PRIMARY KEY,
  account_tier TEXT DEFAULT 'free' CHECK (account_tier IN ('free', 'basic', 'educator'))
);

-- View for quota checking
CREATE VIEW user_tier_info AS
SELECT 
  u.id,
  p.account_tier,
  COUNT(q.id) as current_quiz_count,
  CASE p.account_tier
    WHEN 'free' THEN 5
    WHEN 'basic' THEN 100
    WHEN 'educator' THEN 500
  END as quota_limit,
  COUNT(q.id) >= CASE p.account_tier ... END as quota_exceeded
FROM auth.users u
LEFT JOIN public.profiles p ON u.id = p.id
LEFT JOIN public.quizzes q ON u.id = q.created_by
GROUP BY u.id, p.account_tier;

-- Content source tracking
ALTER TABLE quizzes 
  ADD COLUMN content_source_type TEXT CHECK (content_source_type IN ('text', 'file', 'url')),
  ADD COLUMN content_source_reference TEXT;

-- File size tracking
ALTER TABLE user_files
  ADD COLUMN file_size_bytes INTEGER;
```

### Schema Objects Used in Contracts:
- ✅ `user_tier_info` view (for quota checks)
- ✅ `profiles.account_tier` (for tier upgrades)
- ✅ `quizzes.content_source_type` (for URL tracking)
- ✅ `user_files.file_size_bytes` (for file validation)

---

## Implementation Priority

### 🔴 HIGH Priority (Blocking Core Features)
1. **Quota Enforcement** (`generate-quiz-quota.md`)
   - Prevents unlimited quiz generation
   - Required for tier monetization
   - Estimated effort: 4-6 hours

2. **Tier Upgrade** (`upgrade-tier.md`)
   - Required for users to access basic/educator features
   - Monetization blocker
   - Estimated effort: 3-4 hours

### 🟡 MEDIUM Priority (Enhanced Features)
3. **Search/Filter Quizzes** (`search-quizzes.md`)
   - Improves UX for users with many quizzes
   - Low complexity
   - Estimated effort: 2-3 hours

4. **Web URL Generation** (`generate-quiz-from-url.md`)
   - Differentiator feature (tier-gated)
   - Dependencies already installed
   - Estimated effort: 6-8 hours (web scraping complexity)

### 🟢 LOW Priority (Polish)
5. **File Upload Validation** (`file-upload-validation.md`)
   - Already mostly working
   - Just needs size limit enforcement
   - Estimated effort: 1 hour

---

## Recommended Action Plan

### Phase 1: Core Monetization (HIGH Priority)
**Estimated Time**: 1-2 days

1. ✅ Implement quota enforcement
   - Add quota check to `generate_quiz_from_text()`
   - Add quota check to `generate_quiz_from_file_openai()`
   - Query `user_tier_info` view
   - Return 403 with proper error structure

2. ✅ Implement tier upgrade endpoint
   - Create `POST /api/auth/upgrade-tier`
   - Update `profiles.account_tier`
   - Add verification token validation (MVP: admin token)
   - Return new tier and quota limits

### Phase 2: User Experience (MEDIUM Priority)
**Estimated Time**: 1 day

3. ✅ Add search/filter to my-quizzes
   - Add query parameters (title, start_date, end_date)
   - Update database query with filters
   - Add date validation

### Phase 3: Premium Features (MEDIUM Priority)
**Estimated Time**: 1-2 days

4. ✅ Implement web URL quiz generation
   - Create web scraping service (Playwright + trafilatura)
   - Add tier check (basic/educator only)
   - Create `POST /api/quiz/generate/url` endpoint
   - Handle timeouts and errors

### Phase 4: Polish (LOW Priority)
**Estimated Time**: 1-2 hours

5. ✅ Complete file upload validation
   - Add 10MB size limit check
   - Save file_size_bytes to database

---

## Testing Requirements

For each missing feature, add:

### Unit Tests:
- Handler logic (quota checks, tier validation)
- Service functions (web scraping, URL validation)
- Error cases (403, 400, 500)

### Integration Tests:
- Database queries (user_tier_info view)
- Supabase client calls (update profiles)
- End-to-end flows (generate → quota check → save)

### Contract Tests:
- Request/response formats match exactly
- Error codes match contract specs
- Field validation (types, constraints)

---

## Migration Checklist

Before implementing missing features:

- ✅ Run migration `001_add_missing_features.sql` (already applied)
- ✅ Verify `user_tier_info` view exists
- ✅ Verify `profiles.account_tier` column exists
- ✅ Verify `quizzes.content_source_*` columns exist
- ✅ Verify `user_files.file_size_bytes` column exists

---

## Conclusion

**Current State**: 5/5 contracts have implementation gaps

**Impact**: 
- ❌ No quota enforcement → unlimited quiz generation
- ❌ No tier upgrades → users stuck on free tier
- ❌ No web scraping → missing premium feature
- ❌ No search → poor UX for active users

**Recommendation**: Prioritize HIGH priority items (quota + tier upgrade) before any production launch. These are critical for business model and prevent abuse.

**Next Steps**:
1. Review this report with team
2. Create GitHub issues for each missing feature
3. Implement Phase 1 (core monetization)
4. Update API documentation to match implementation
5. Add contract tests for all endpoints

---

**Report Generated By**: GitHub Copilot  
**Date**: 2025-10-08  
**Repository**: quizify (development branch)
