# quizify Development Guidelines

Auto-generated from all feature plans. Last updated: 2025-10-22

## Project Overview
Quizify is a FastAPI-based quiz generation platform that creates educational quizzes from multiple content sources (text, files, URLs). The system uses AI (OpenAI GPT-4) to generate intelligent quiz questions with tiered user quotas managed via Supabase.

### Current Architecture
- **Single Instance Deployment**: Currently runs as a single FastAPI instance on Railway
- **Stateful Operations**: Browser slot management, user quota tracking, and session management handled in-memory
- **Authentication**: Uses Supabase JWT tokens with both service role and user-authenticated clients for RLS enforcement

## Active Technologies
- **Backend**: Python 3.12+, FastAPI 0.1.0
- **Database**: Supabase (PostgreSQL + Auth + Storage)
- **AI Services**: OpenAI GPT-4 for quiz generation
- **Validation**: Pydantic v2 for request/response schemas
- **Document Processing**: PyPDF2, python-docx for file parsing
- **Web Scraping**: Playwright (headless Chrome), Trafilatura for content extraction
- **Security**: SSRF protection, DNS rebinding prevention, container-aware Chrome security

## Scalability & Resource Management
### Current Capacity (Single Instance)
- **Concurrent Users**: ~3-5 users (limited by browser slots)
- **Daily Active Users**: ~50-100 users maximum
- **Browser Limit**: 3 concurrent browser instances per user (in-memory tracking)
- **Main Bottlenecks**: 
  - Database queries (50-200ms per call, no caching)
  - Browser resource management (single-instance coordination)
  - No horizontal scaling support (in-memory state)

### Future Scaling Plan
- **Horizontal Scaling**: Requires Redis for shared state management
- **Redis Use Cases**: Browser slot coordination, user quota caching, session management
- **Target Capacity**: 50-100+ concurrent users with multiple instances

## Database Schema Notes
- **User Tiers**: Stored in `public.profiles` table (NOT `auth.users` - Supabase locks that down)
- **Tier Management**: Join `auth.users` with `public.profiles` via `user_tier_info` view
- **Quota Tracking**: Use `user_tier_info` view which includes current_quiz_count and quota_limit
- **Content Source**: `quizzes.content_source_type` tracks if quiz is from file/url/text
- **File Size**: `user_files.file_size_bytes` stores file size (10MB max = 10485760 bytes)

## Project Structure
```
api/              # FastAPI route handlers
handlers/         # Business logic handlers
services/         # Core services (AI, DB, tier, quota)
schemas/          # Pydantic models
middleware/       # Auth & request middleware
migrations/       # Database migrations
tests/            # pytest test suite
```

## Commands
pytest                    # Run tests
ruff check .             # Lint code
psql -f migrations/001_add_missing_features.sql  # Apply migration

## Code Style
Python 3.12+: Follow standard conventions, use type hints, async/await for I/O

## Testing Guidelines
- Write tests in `tests/` directory organized by type (unit, integration, contract)
- Use pytest for test execution
- Follow TDD: Write tests before implementation
- Mock external services (OpenAI, Supabase) in unit tests
- Integration tests should validate end-to-end flows

## Recent Changes
- 2025-10-22: Updated documentation to reflect current single-instance architecture and scalability constraints
- 2025-10-19: Fixed quiz retrieval by using authenticated Supabase client for consistency with RLS policies
- 2025-10-19: Enhanced web scraping security - container-aware Chrome arguments, removed --single-process flag
- 2025-10-04: Database migrations complete - added tier management via profiles table, content source tracking, file size validation, search indexes
- 2025-10-04: Updated schemas - UserProfile, UserTierInfo, WebQuizRequest, content_source fields
- 2025-10-03: Added web scraping dependencies (playwright, trafilatura, tenacity)

## Important Database Patterns

### Query User Tier:
```python
# Use the view for quota checks
result = supabase.table("user_tier_info").select("*").eq("id", user_id).single()
# Returns: account_tier, current_quiz_count, quota_limit, quota_exceeded
```

### Update User Tier:
```python
# Update profiles table, NOT auth.users
supabase.table("profiles").update({"account_tier": "basic"}).eq("id", user_id)
```

### Track Quiz Source:
```python
# When creating quiz from URL:
quiz_data = {
    "title": "...",
    "content_source_type": "url",  # or "file" or "text"
    "content_source_reference": "https://..."  # or file_id or None
}
```

## Domain-Specific Conventions
- **Quiz Generation**: All quiz generation flows through handlers in `handlers/` which call `services/ai_service.py`
- **Content Sources**: Support three types: text input, file upload (PDF/DOCX), and URL scraping
- **File Size Limits**: 10MB maximum (10485760 bytes) - validate before processing
- **Tier System**: free (5 quizzes), basic (20 quizzes), premium (unlimited)
- **Authentication**: All quiz endpoints require Supabase JWT token in Authorization header
- **Browser Management**: 3 concurrent browser slots per user for URL scraping (enforced in-memory)
- **User Quota Enforcement**: Validated before quiz generation to prevent wasted AI API calls

## Important Architectural Patterns

### Authenticated vs Service Role Clients
```python
# For user-scoped operations (enforces RLS):
if user_token:
    supabase = get_authed_supabase_client(user_token)  # Uses anon key + user JWT
else:
    supabase = get_supabase()  # Uses service_role key (bypasses RLS)

# Always use authenticated client for quiz retrieval to ensure RLS consistency
```

### Browser Slot Management (Current Implementation)
```python
# In-memory tracking (single instance only)
_active_browsers = defaultdict(int)  # {user_id: browser_count}
MAX_CONCURRENT_BROWSERS = 3  # Per user limit

# Acquire slot before scraping
await _acquire_browser_slot(user_id)
try:
    # Scrape content
finally:
    await _release_browser_slot(user_id)  # Always release
```

### Security Considerations
- **SSRF Protection**: Validates URLs against private IP ranges (IPv4/IPv6)
- **DNS Rebinding Prevention**: Re-validates hostname resolution before connection
- **Container Detection**: Automatically adjusts Chrome security flags based on environment
- **User Enumeration Prevention**: Logs use truncated user IDs, generic error messages to clients

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->