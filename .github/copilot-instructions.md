# quizify Development Guidelines

Auto-generated from all feature plans. Last updated: 2025-10-04

## Project Overview
Quizify is a FastAPI-based quiz generation platform that creates educational quizzes from multiple content sources (text, files, URLs). The system uses AI (OpenAI GPT-4) to generate intelligent quiz questions with tiered user quotas managed via Supabase.

## Active Technologies
- Python 3.12+ + FastAPI 0.1.0, Supabase (PostgreSQL + Auth + Storage), OpenAI GPT-4, Pydantic v2, PyPDF2, python-docx, playwright, trafilatura (001-comprehensive-quiz-generation)

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

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->