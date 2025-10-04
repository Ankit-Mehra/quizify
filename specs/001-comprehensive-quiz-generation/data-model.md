# Data Model: Tier Management & Enhanced Features

**Feature**: Comprehensive Quiz Generation Platform  
**Date**: 2025-10-03  
**Status**: Complete

---

## Database Schema Changes

### 1. User Entity Enhancement

**Existing**: Managed by Supabase Auth (`auth.users` table)

**New Field**:
```sql
-- Migration: Add tier column
ALTER TABLE auth.users 
ADD COLUMN IF NOT EXISTS account_tier TEXT DEFAULT 'free' 
CHECK (account_tier IN ('free', 'basic', 'educator'));

CREATE INDEX idx_users_tier ON auth.users(account_tier);
```

**Updated User Model** (`schemas/user.py`):
```python
from pydantic import BaseModel
from datetime import datetime
from typing import Literal

class User(BaseModel):
    email: str
    password: str  # Hashed by Supabase Auth
    account_tier: Literal["free", "basic", "educator"] = "free"
    
class UserProfile(BaseModel):
    """Public user profile without sensitive data"""
    id: str
    email: str
    account_tier: Literal["free", "basic", "educator"]
    created_at: datetime
```

**Validation Rules**:
- `account_tier` must be one of: 'free', 'basic', 'educator'
- Default value: 'free' (enforced by database)
- Cannot be null
- Updates logged in audit trail

**Relationships**:
- User → Quizzes (1:many) with quota constraints by tier
- User → Files (1:many) with file type restrictions by tier

---

### 2. Quiz Entity (No Schema Changes Required)

**Existing Schema** (already correct):
```sql
CREATE TABLE quizzes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    created_by UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_quizzes_user ON quizzes(created_by);
CREATE INDEX idx_quizzes_created_at ON quizzes(created_at);
CREATE INDEX idx_quizzes_title ON quizzes USING gin(title gin_trgm_ops);  -- For search
```

**Note**: Add GIN index for title search (if not exists):
```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- Trigram extension for fuzzy matching
CREATE INDEX IF NOT EXISTS idx_quizzes_title_search 
ON quizzes USING gin(to_tsvector('english', title));
```

**Validation Rules**:
- Quota enforcement before insert:
  - Free: COUNT(quizzes WHERE created_by = user_id) < 5
  - Basic: COUNT(quizzes WHERE created_by = user_id) < 100
  - Educator: COUNT(quizzes WHERE created_by = user_id) < 500
- Title: minimum 1 character, maximum 255 characters
- created_at: auto-generated, immutable

---

### 3. Files Entity (Add Size Validation)

**Existing Schema**:
```sql
CREATE TABLE files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    original_filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    uploaded_at TIMESTAMP DEFAULT NOW()
);
```

**New Field** (optional - can track in application):
```sql
ALTER TABLE files ADD COLUMN IF NOT EXISTS file_size_bytes INTEGER;
```

**Validation Rules**:
- `file_size_bytes`: Must be ≤ 10,485,760 (10MB) enforced at application level
- `file_type` restrictions by tier:
  - Free: 'application/pdf', 'text/plain' only
  - Basic/Educator: All supported types including 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

**Updated Files Schema** (`schemas/files.py`):
```python
class FileMetadata(BaseModel):
    id: str
    user_id: str
    original_filename: str
    file_type: str
    storage_path: str
    uploaded_at: datetime
    file_size_bytes: int  # New field
```

---

### 4. Quiz Content Source Tracking (New)

**Purpose**: Track whether quiz was generated from file upload or web URL

**New Field** (add to quizzes table):
```sql
ALTER TABLE quizzes ADD COLUMN IF NOT EXISTS content_source_type TEXT DEFAULT 'file'
CHECK (content_source_type IN ('file', 'url'));

ALTER TABLE quizzes ADD COLUMN IF NOT EXISTS content_source_reference TEXT;
-- For 'file': stores file_id (UUID)
-- For 'url': stores the scraped URL (text)

CREATE INDEX idx_quizzes_source_type ON quizzes(content_source_type);
```

**Updated Quiz Schema** (`schemas/quiz.py`):
```python
from typing import Literal, Optional

class QuizCreate(BaseModel):
    title: str
    num_questions: int
    question_types: List[QuestionType]
    content_source_type: Literal["file", "url"]
    file_id: Optional[str] = None  # Required if content_source_type='file'
    url: Optional[str] = None  # Required if content_source_type='url'

class QuizMetadata(BaseModel):
    id: str
    title: str
    created_by: str
    created_at: datetime
    content_source_type: Literal["file", "url"]
    content_source_reference: str  # file_id or URL
```

**Validation Rules**:
- `content_source_type='file'` → `content_source_reference` must be valid file_id
- `content_source_type='url'` → `content_source_reference` must be valid HTTP/HTTPS URL
- URL source only allowed for basic/educator tiers (enforced at API layer)

---

### 5. Questions Entity (Add Generation Validation)

**Existing Schema** (no changes):
```sql
CREATE TABLE questions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    quiz_id UUID REFERENCES quizzes(id) ON DELETE CASCADE,
    type TEXT NOT NULL,  -- 'multiple_choice', 'true_false', 'fill_blank', 'matching'
    question TEXT NOT NULL,
    options JSONB,  -- Varies by type
    correct_answer JSONB,
    explanation TEXT,
    source TEXT  -- Source text excerpt
);
```

**New Validation Rule** (application-level):
- After generation: `COUNT(questions WHERE quiz_id = X) / requested_count >= 0.75`
- If validation fails: Rollback quiz creation transaction

---

## Entity Relationships

```
User (auth.users)
├── account_tier: ENUM('free', 'basic', 'educator')
│
├──[1:many]── Quizzes
│   ├── Quota: {free: 5, basic: 100, educator: 500}
│   ├── Searchable by: title (ILIKE), created_at (date range)
│   ├── content_source_type: ENUM('file', 'url')
│   ├── content_source_reference: file_id OR url
│   └──[1:many]── Questions
│       └── Validation: count >= 0.75 * requested
│
└──[1:many]── Files
    ├── Size limit: 10MB (all tiers)
    └── Type restrictions: {free: [PDF, TXT], basic/educator: [PDF, TXT, DOCX, URL]}
```

---

## State Transitions

### User Tier Lifecycle

```
[New User] 
    → account_tier = 'free' (default)
    → Can create 5 quizzes
    → Can upload PDF/TXT only
    ↓
[Upgrade Request] (via payment or verification)
    → account_tier = 'basic' OR 'educator'
    → Quota increased: 100 or 500
    → Can upload DOCX files
    ↓
[Active Paid User]
    → Continues until subscription ends (future scope)
    ↓
[Downgrade] (future scope - not implemented)
    → If quiz count > new quota → prevent downgrade OR soft-delete excess
```

**Immutable States**:
- User cannot downgrade if existing quiz count exceeds target tier quota
- Tier transitions logged in audit trail
- No automatic downgrades on payment failure (future scope)

---

## Migration Plan

### Phase 1: Database Changes
```sql
-- 1. Add tier column
ALTER TABLE auth.users 
ADD COLUMN account_tier TEXT DEFAULT 'free' 
CHECK (account_tier IN ('free', 'basic', 'educator'));

-- 2. Add content source tracking to quizzes
ALTER TABLE quizzes ADD COLUMN content_source_type TEXT DEFAULT 'file'
CHECK (content_source_type IN ('file', 'url'));

ALTER TABLE quizzes ADD COLUMN content_source_reference TEXT;

-- 3. Create indexes
CREATE INDEX idx_users_tier ON auth.users(account_tier);
CREATE INDEX idx_quizzes_source_type ON quizzes(content_source_type);
CREATE INDEX IF NOT EXISTS idx_quizzes_title_trgm ON quizzes USING gin(title gin_trgm_ops);

-- 4. Add file size column (optional)
ALTER TABLE files ADD COLUMN file_size_bytes INTEGER;
```

### Phase 2: Backfill Existing Data
```sql
-- Set all existing users to 'free' tier (already default)
-- No action needed if column has DEFAULT 'free'

-- Verify data integrity
SELECT account_tier, COUNT(*) FROM auth.users GROUP BY account_tier;
SELECT created_by, COUNT(*) as quiz_count FROM quizzes GROUP BY created_by HAVING COUNT(*) > 5;
```

### Phase 3: Application Code Updates
- Update `schemas/user.py` with `account_tier` field
- Add `services/tier_service.py` for tier management
- Add `services/quota_service.py` for quota checks
- Update all quiz/file handlers to enforce validations

---

## Validation Summary

| Entity | Field | Validation Rule | Enforcement Point |
|--------|-------|-----------------|-------------------|
| User | account_tier | ENUM('free','basic','educator') | Database constraint |
| Quiz | count per user | ≤ tier quota | API handler (pre-creation) |
| Quiz | content_source_type | ENUM('file','url') | Database constraint |
| Quiz | url source | Only basic/educator tiers | API handler (pre-creation) |
| Quiz | title search | ILIKE pattern | Database query |
| Quiz | date filter | Between start/end | Database query |
| Question | count | ≥ 75% of requested | API handler (post-generation) |
| File | file_type | Matches tier allowlist | API handler (pre-upload) |
| File | size | ≤ 10MB | API handler (pre-upload) |
| URL | security validation | No private IPs/localhost | Service layer (pre-scrape) |
| URL | content size | ≤ 500KB extracted | Service layer (post-scrape) |
| URL | content minimum | ≥ 100 characters | Service layer (post-scrape) |

---

## Testing Considerations

**Data Model Tests**:
1. User tier default value on signup
2. Tier constraint validation (reject invalid tiers)
3. Quiz quota enforcement per tier
4. Search query performance with title ILIKE
5. Date range filter accuracy
6. 75% question threshold validation
7. File type restriction by tier
8. File size limit enforcement

**Contract Tests** (to be generated):
- `/api/auth/upgrade-tier` → User tier update
- `/api/quiz/my-quizzes?title=X&start_date=Y` → Search/filter
- `/api/files/upload` → Tier + size validation

---

**Status**: Data model complete. Ready for contract generation (Phase 1 step 2).
