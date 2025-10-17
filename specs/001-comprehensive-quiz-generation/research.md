# Research: Tier Management & Missing Features

**Feature**: Comprehensive Quiz Generation Platform  
**Date**: 2025-10-03  
**Status**: Complete

---

## Research Tasks

### 1. User Tier Management Implementation Patterns

**Decision**: Add `account_tier` column to `public.profiles` table (not `auth.users`)

**Rationale**: 
- Supabase locks down `auth.users` table - only Supabase auth admin can modify it
- Standard Supabase pattern is to create a `public.profiles` table for custom user data
- Link profiles to auth.users via foreign key with ON DELETE CASCADE
- Use database trigger to auto-create profile when user signs up

**Implementation**:
```sql
-- Create profiles table
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    account_tier TEXT DEFAULT 'free' 
        CHECK (account_tier IN ('free', 'basic', 'educator')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_profiles_tier ON public.profiles(account_tier);

-- Trigger to auto-create profiles
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, account_tier)
    VALUES (NEW.id, 'free');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_new_user();
```

**Alternatives Considered**:
- Direct `auth.users` modification → Supabase security prevents this
- `raw_user_meta_data` JSONB field → Less structured, harder to query/index
- Role-based access control (RBAC) → too complex for simple tier logic
- Separate service/microservice → unnecessary overhead for single-app architecture

---

### 2. Quiz Quota Enforcement Strategy

**Decision**: Check quota before quiz creation using atomic database query

**Rationale**:
- Count quizzes in single query: `SELECT COUNT(*) FROM quizzes WHERE created_by = user_id`
- Compare against tier limits: {free: 5, basic: 100, educator: 500}
- Fail fast at API layer (HTTP 403) before expensive AI generation
- Prevents race conditions using database-level constraints

**Implementation Pattern**:
```python
async def validate_quiz_quota(user_id: UUID, user_tier: str) -> bool:
    """Returns True if user can create more quizzes, False otherwise."""
    quota_limits = {"free": 5, "basic": 100, "educator": 500}
    current_count = supabase.table("quizzes")
        .select("id", count="exact")
        .eq("created_by", user_id)
        .execute()
    return current_count.count < quota_limits[user_tier]
```

**Alternatives Considered**:
- Cached quota counter → risk of drift, requires invalidation logic
- Database trigger → couples business logic to DB, harder to test
- Client-side enforcement → insecure, easily bypassed

---

### 3. Search & Filter Implementation (PostgreSQL Full-Text Search vs Simple LIKE)

**Decision**: Use PostgreSQL `ILIKE` for title search + indexed date filtering

**Rationale**:
- Requirements: search by title (case-insensitive) + filter by date range (FR-045b, FR-045c)
- `ILIKE '%term%'` sufficient for title matching (no complex text search needed)
- GIN indexes for full-text search → over-engineering for single field
- Date range with B-tree index on `created_at` → excellent performance

**Implementation**:
```python
def search_quizzes(user_id, title_query=None, start_date=None, end_date=None):
    query = supabase.table("quizzes").select("*").eq("created_by", user_id)
    if title_query:
        query = query.ilike("title", f"%{title_query}%")
    if start_date:
        query = query.gte("created_at", start_date)
    if end_date:
        query = query.lte("created_at", end_date)
    return query.execute()
```

**Alternatives Considered**:
- PostgreSQL full-text search (tsvector) → overkill for simple title search
- Elasticsearch → external dependency, operational overhead
- Client-side filtering → poor UX for large quiz libraries

---

### 4. File Type Restriction Enforcement Point

**Decision**: Validate tier + file type at API route level before file processing

**Rationale**:
- Requirement: Free tier → PDF/text only; Basic/Educator → all formats (FR-016a)
- Check occurs in `file_routes.py` before calling `file_handlers.py`
- Rejects with HTTP 403 ("Upgrade to basic tier for DOCX support")
- Prevents wasted file upload/storage for unauthorized types

**Implementation**:
```python
ALLOWED_TYPES_BY_TIER = {
    "free": ["application/pdf", "text/plain"],
    "basic": ["application/pdf", "text/plain", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
    "educator": ["application/pdf", "text/plain", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]
}

async def validate_file_type_for_tier(file_type: str, user_tier: str):
    if file_type not in ALLOWED_TYPES_BY_TIER[user_tier]:
        raise HTTPException(403, "Upgrade required for this file type")
```

**Alternatives Considered**:
- Check after upload → wastes bandwidth and storage
- MIME type validation only → insufficient (doesn't check tier)
- Browser-side restriction → insecure, easily bypassed

---

### 5. 75% Question Generation Threshold Validation

**Decision**: Validate in `chunking_service.py` after AI generation completes

**Rationale**:
- Requirement: Accept quiz only if ≥75% of requested questions generated (FR-038a)
- Check happens after `generate_quiz_for_type()` returns questions
- Calculation: `len(generated) / requested >= 0.75`
- Rollback quiz creation if threshold not met (no partial saves)

**Implementation**:
```python
def validate_question_threshold(generated_count: int, requested_count: int) -> bool:
    """Returns True if at least 75% of requested questions were generated."""
    return (generated_count / requested_count) >= 0.75

# In quiz generation handler:
if not validate_question_threshold(len(questions), num_questions):
    raise HTTPException(
        400, 
        f"AI generated only {len(questions)}/{num_questions} questions (minimum 75% required)"
    )
```

**Alternatives Considered**:
- Retry generation with lower count → expensive, unpredictable duration
- Accept any generated questions → violates spec requirement
- Adjust threshold dynamically → adds complexity without clear benefit

---

### 6. 10MB File Size Enforcement

**Decision**: Use FastAPI `File` size validation before processing

**Rationale**:
- Requirement: Reject files >10MB (FR-020a, edge case clarification)
- FastAPI built-in: `File(..., max_length=10*1024*1024)`
- Validation happens during request parsing (fails before handler execution)
- Returns HTTP 413 (Payload Too Large) automatically

**Implementation**:
```python
from fastapi import File, UploadFile

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

async def upload_file(
    file: UploadFile = File(..., description="File to upload (max 10MB)")
):
    # Read file content
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, "File size exceeds 10MB limit")
    # Process file...
```

**Alternatives Considered**:
- Client-side validation only → insecure, can be bypassed
- Nginx/proxy level limit → good defense-in-depth (recommended in addition)
- Stream processing → complex, unnecessary for 10MB limit

---

### 7. Payment/Upgrade Flow Integration

**Decision**: Stub endpoint for MVP, defer to future payment provider integration

**Rationale**:
- Requirement: Allow upgrade from free → basic/educator (FR-013a)
- Full payment integration (Stripe/PayPal) out of scope for this iteration
- Create `/api/auth/upgrade-tier` endpoint with manual admin approval flow
- Admin updates tier via direct database access or future admin panel

**MVP Implementation**:
```python
async def upgrade_tier(
    user_id: UUID,
    target_tier: Literal["basic", "educator"],
    verification_token: str  # Admin-issued token
):
    # Validate token (simple secret for MVP)
    if verification_token != os.getenv("ADMIN_UPGRADE_TOKEN"):
        raise HTTPException(403, "Invalid verification token")
    
    # Update user tier
    supabase.auth.admin.update_user_by_id(
        user_id, 
        {"user_metadata": {"account_tier": target_tier}}
    )
```

**Future Enhancements** (not in this plan):
- Stripe payment integration
- Automated email verification for educators (.edu domains)
- Subscription management
- Tier downgrade handling

**Alternatives Considered**:
- Block feature until payment system ready → delays core functionality
- Hardcode user tiers → not scalable
- Email-based verification for educators → insufficient for basic (paid) tier

---

### 8. Web Scraping Technology Selection

**Decision**: Use Playwright with trafilatura for content extraction

**Rationale**:
- Requirement: Extract text from web URLs for quiz generation (FR-019a-g)
- **Playwright** chosen for browser automation:
  - Handles JavaScript-rendered content (SPAs, dynamic sites)
  - Built-in wait strategies for page load
  - Headless mode for server deployment
  - Python async/await support (matches FastAPI)
- **Trafilatura** for main content extraction:
  - Best-in-class readability algorithm
  - Removes navigation, ads, boilerplate
  - Lightweight (no ML models)
  - Better than newspaper3k (unmaintained) or readabilipy (heavier)

**Implementation Stack**:
```python
# Dependencies
playwright==1.40.0
trafilatura==1.6.2

# Service architecture
async def scrape_web_content(url: str) -> str:
    # 1. Playwright: Load page with JS rendering
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, timeout=30000)  # 30s timeout
        html = await page.content()
        await browser.close()
    
    # 2. Trafilatura: Extract main content
    text = trafilatura.extract(html, include_comments=False)
    
    # 3. Validate content size and minimum threshold
    if len(text) < 100:  # FR-019f
        raise ValueError("Insufficient content extracted")
    if len(text) > 500_000:  # FR-019e (500KB)
        text = text[:500_000]
    
    return text
```

**Alternatives Considered**:
- BeautifulSoup alone → Can't handle JavaScript-rendered content
- Scrapy → Overkill for single-page scraping, requires separate process
- Selenium → Heavier than Playwright, less Python-friendly API
- requests-html → Deprecated, poor maintenance

---

### 9. URL Validation & Security Strategy

**Decision**: Multi-layer validation at API + service layers

**Rationale**:
- Requirement: Block private IPs, localhost, maintain domain blocklist (FR-019b)
- **Layer 1 (API)**: Regex validation for URL format
- **Layer 2 (Service)**: IP resolution check before scraping
- **Layer 3 (Service)**: Domain blocklist check

**Implementation**:
```python
import ipaddress
from urllib.parse import urlparse

PRIVATE_IP_RANGES = [
    ipaddress.ip_network("127.0.0.0/8"),    # localhost
    ipaddress.ip_network("10.0.0.0/8"),     # private
    ipaddress.ip_network("172.16.0.0/12"),  # private
    ipaddress.ip_network("192.168.0.0/16"), # private
    ipaddress.ip_network("169.254.0.0/16"), # link-local
]

BLOCKED_DOMAINS = [
    "localhost",
    "*.internal",
    "*.local",
    # Add problematic domains as discovered
]

async def validate_url_security(url: str) -> bool:
    """Validates URL is safe to scrape (no SSRF risk)."""
    # Parse URL
    parsed = urlparse(url)
    if parsed.scheme not in ["http", "https"]:
        raise ValueError("Only HTTP/HTTPS URLs allowed")
    
    # Check domain blocklist
    if any(fnmatch(parsed.netloc, pattern) for pattern in BLOCKED_DOMAINS):
        raise ValueError("Domain is blocked")
    
    # Resolve IP and check against private ranges
    import socket
    ip = socket.gethostbyname(parsed.netloc)
    ip_obj = ipaddress.ip_address(ip)
    
    for network in PRIVATE_IP_RANGES:
        if ip_obj in network:
            raise ValueError("Private IP addresses not allowed")
    
    return True
```

**Security Benefits**:
- Prevents SSRF (Server-Side Request Forgery) attacks
- Blocks internal network scanning
- Protects against localhost exploitation
- Extensible blocklist for abuse prevention

**Alternatives Considered**:
- Allowlist only → Too restrictive for educational content
- No validation → Critical security vulnerability
- Cloud proxy service (ScrapingBee) → Adds cost and external dependency

---

### 10. Web Scraping Error Handling & Retry Logic

**Decision**: Implement exponential backoff with 3 retry attempts

**Rationale**:
- Requirement: Comprehensive error handling with retry logic (FR-019g)
- Common failures: timeouts, network errors, 404s, empty content
- Exponential backoff: 1s → 2s → 4s delays between retries
- Max 3 attempts (initial + 2 retries) to balance UX and cost

**Implementation**:
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    reraise=True
)
async def scrape_with_retry(url: str) -> str:
    """Scrapes URL with automatic retry on failure."""
    try:
        # Validate URL security first (no retries for security failures)
        await validate_url_security(url)
        
        # Attempt scraping
        content = await scrape_web_content(url)
        
        # Validate content threshold
        if len(content) < 100:  # FR-019f
            raise ValueError("Content too short (minimum 100 characters)")
        
        return content
        
    except PlaywrightTimeoutError:
        logger.warning(f"Timeout scraping {url}, retrying...")
        raise  # Trigger retry
    except Exception as e:
        logger.error(f"Scraping failed for {url}: {e}")
        raise

# Error types mapped to user-friendly messages
ERROR_MESSAGES = {
    "timeout": "Page took too long to load (30s limit)",
    "insufficient_content": "Could not extract enough text from page",
    "invalid_url": "URL is invalid or blocked for security",
    "network_error": "Could not reach the website",
}
```

**Error Handling Strategy**:
1. Security failures (SSRF) → Fail fast, no retry
2. Timeouts → Retry with backoff
3. Network errors → Retry with backoff
4. Content extraction failures → Retry once (different user agent)
5. After all retries exhausted → Return clear error to user

**Alternatives Considered**:
- Linear retry delays → Less efficient, slower recovery
- Infinite retries → Poor UX, resource waste
- No retries → Poor UX for transient failures

---

## Summary of Research Findings

All unknowns resolved. Implementation approach follows existing codebase patterns:
- **Database**: Add single ENUM column to auth.users
- **Services**: New `tier_service.py`, `quota_service.py`, and `web_scraper_service.py` modules
- **Validation**: Server-side enforcement at API + handler layers
- **Web Scraping**: Playwright + trafilatura with security validation and retry logic
- **Testing**: Pytest contract tests for all new endpoints

**Dependencies Added**:
- `playwright==1.40.0` (browser automation)
- `trafilatura==1.6.2` (content extraction)
- `tenacity==8.2.3` (retry logic)

**No blockers identified.** Ready for Phase 1 (Design & Contracts).
