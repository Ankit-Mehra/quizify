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

## 🔄 MANDATORY WORKFLOW FOR ALL CODE CHANGES

**IMPORTANT**: Follow this workflow for EVERY code change, feature, or bug fix. Do not skip steps.

**Tools**: This workflow uses the **GitHub MCP Server** to automate GitHub operations including:
- Checking for existing PRs and reviews
- Requesting Copilot reviews
- Reading review comments and feedback
- Adding comments to PRs
- Resolving review conversations
- Managing PR state and merge operations

### Phase 1: Pre-Implementation Review
1. **Understand Requirements**: Clarify the task/feature requirements before coding
2. **Check Existing Code**: Search for similar patterns in the codebase to maintain consistency
3. **Plan Architecture**: Identify which files need changes and potential impact areas

### Phase 2: Implementation
4. **Write Code**: Implement the feature/fix following project conventions
5. **Self-Review Checklist** (MANDATORY before commit):
   - ✅ **Security**: No hardcoded secrets, proper input validation, SQL injection prevention
   - ✅ **DRY Principles**: No duplicated code, reusable functions/handlers extracted
   - ✅ **Type Safety**: All type hints defined, Pydantic schemas validated
   - ✅ **Error Handling**: Proper try-except blocks, meaningful HTTPException messages
   - ✅ **Performance**: Optimized database queries, efficient async operations, proper indexing
   - ✅ **Authentication**: Proper JWT validation, RLS policies enforced, user context maintained
   - ✅ **Database**: Correct table usage (profiles not auth.users), proper migrations created
   - ✅ **API Design**: RESTful conventions, proper status codes, consistent response schemas
   - ✅ **Logical Flaws**: Edge cases handled, null checks, boundary conditions, quota enforcement
   - ✅ **Testing**: Unit tests for business logic, integration tests for endpoints
   - ✅ **Documentation**: Docstrings for functions/classes, inline comments for complex logic

6. **Fix Issues**: Address any problems found in self-review

### Phase 3: Git Workflow
7. **Stage Changes**: `git add -A` (or specific files)
8. **Commit with Conventional Commits**:
   ```bash
   git commit -m "type: brief description
   
   - Detailed change 1
   - Detailed change 2
   - Security/DRY/performance improvements"
   ```
   Types: `feat`, `fix`, `refactor`, `docs`, `style`, `test`, `chore`, `perf`, `ci`

9. **Push to Remote**: `git push origin <branch-name>`

### Phase 4: Pull Request & Review Cycle
10. **Check for Existing PR** (use GitHub MCP): 
    - Use `github_search_pull_requests` to find PR for current branch
    - If PR exists for current branch → skip to step 12
    - If no PR exists → proceed to step 11

11. **Create Pull Request** (use GitHub MCP):
    - Use `github_create_pull_request` with base: `deploy/production`
    - Include comprehensive PR description:
      - Summary of changes
      - Why this change is needed
      - Testing performed (pytest results, manual testing)
      - API contract changes (if any)
      - Database migrations (if any)
      - Breaking changes (if any)

12. **Check Existing Reviews and Comments** (use GitHub MCP):
    - Use `github_pull_request_read` with method `get_reviews` to check for existing reviews
    - Use `github_pull_request_read` with method `get_review_comments` to read feedback
    - If reviews exist → skip to step 13 to analyze feedback
    - If no reviews exist → proceed to step 12b

12b. **Request GitHub Copilot Review** (use GitHub MCP): 
    - Use `github_request_copilot_review` to request automated review

13. **Review Analysis** (CRITICAL - use GitHub MCP):
    - Use `github_pull_request_read` to read ALL review comments
    - Read ALL Copilot review comments carefully
    - Read ALL human reviewer comments carefully
    - Categorize feedback:
      - 🔴 Critical: Security, bugs, breaking changes, SQL injection → MUST fix
      - 🟡 Important: Performance, maintainability, best practices, async patterns → SHOULD fix
      - 🟢 Nice-to-have: Style preferences, minor optimizations → Consider fixing
    - For each applicable comment:
      - Implement the suggested fix
      - Add explanatory comments if needed
      - Update tests if behavior changes
      - Use `github_add_comment_to_pending_review` or reply to comment explaining what was fixed or why it wasn't applicable

14. **Apply Feedback**:
    - Make code changes based on review
    - Run self-review checklist again (step 5)
    - Run tests: `pytest tests/ -v`
    - Commit changes: `git commit -m "fix: address Copilot review feedback - [specific issue]"`
    - Push: `git push origin <branch-name>`

15. **Check for New Comments** (use GitHub MCP): 
    - Use `github_pull_request_read` to check if Copilot has provided new feedback after push
    - If new comments exist → go to step 13 to analyze
    - If no new comments → proceed to step 15b

15b. **Re-request Copilot Review** (use GitHub MCP): 
    - Use `github_request_copilot_review` to request review again after addressing feedback

16. **Repeat Review Cycle**: 
    - **MINIMUM 3 ITERATIONS** of steps 12-15
    - Continue until Copilot has no more critical/important feedback
    - Or until you've addressed all reasonable suggestions (document why if not applicable)

### Phase 5: Merge Preparation
17. **Final Checks**:
    - All CI/CD checks passing (pytest, ruff linting)
    - No merge conflicts with target branch
    - All review feedback addressed or justified
    - **All GitHub review comments resolved** (both Copilot and human reviewers)
    - Responded to every review comment with explanation of fix or justification
    - Database migrations tested
    - API documentation updated if endpoints changed
    - CHANGELOG.md updated for significant changes

18. **Request Human Review** (if applicable):
    - Tag specific reviewers based on area of change
    - Respond promptly to human reviewer comments
    - Mark conversations as resolved after addressing feedback

19. **Merge Request**:
    - Verify all review comment threads are resolved
    - Comment on PR: "Ready for merge - all reviews addressed, all comments resolved, checks passing"
    - Wait for approval from maintainer/senior developer
    - Merge into `deploy/production` branch
    - Do not squash/rebase unless instructed

### Phase 6: Post-Merge
20. **Cleanup**:
    - Do not delete branch until confirmed no hotfixes needed
    - Update local deploy/production: `git checkout deploy/production && git pull origin deploy/production`
    - Monitor logs for any production issues
    - Verify deployment on Railway or production environment

21. **Documentation**:
    - Update README.md if user-facing features added
    - Update API documentation if endpoints changed
    - Add to knowledge base if complex problem solved

---

## 🚨 NEVER SKIP THESE

- ❌ Never commit without running the self-review checklist
- ❌ Never skip Copilot review request
- ❌ Never merge without addressing critical security/bug issues
- ❌ Never push secrets, API keys, or database credentials
- ❌ Never use `--force` push without explicit approval
- ❌ Never merge your own PR without review (unless trivial docs/typos)
- ❌ Never bypass RLS policies without justification
- ❌ Never modify auth.users table directly (use profiles table)

---

## 🎯 Additional Best Practices

### Security
- Use environment variables for all secrets (`.env` file, never commit)
- Validate all user inputs with Pydantic schemas
- Use parameterized queries (SQLAlchemy/Supabase handles this)
- Implement rate limiting for API endpoints
- Always use authenticated Supabase client for user operations
- Validate file uploads (size, type, content)
- Implement SSRF protection for URL inputs
- Keep dependencies updated (`pip list --outdated`)

### Performance
- Use async/await for all I/O operations
- Batch database queries when possible
- Implement proper database indexes
- Cache frequently accessed data (consider Redis)
- Use connection pooling for external services
- Monitor API response times
- Optimize AI token usage

### Code Quality
- Keep functions small (< 50 lines ideal)
- Use descriptive variable/function names
- Extract magic numbers to config constants
- Write pure functions when possible
- Use early returns to reduce nesting
- Add unit tests for business logic
- Use type hints consistently

### FastAPI Specific
- Use dependency injection for shared logic
- Implement proper response models (Pydantic)
- Use background tasks for long operations
- Add proper OpenAPI documentation
- Use HTTPException with proper status codes
- Implement request validation at route level
- Use middleware for cross-cutting concerns

### Database Best Practices
- Always use migrations for schema changes
- Test migrations in development first
- Use `user_tier_info` view for quota checks
- Update `profiles` table for user tier changes
- Track content sources in quiz metadata
- Implement proper RLS policies
- Use indexes for frequently queried fields

### Testing
- Write unit tests for handlers and services
- Write integration tests for API endpoints
- Mock external services (OpenAI, Supabase) in unit tests
- Test authentication/authorization flows
- Test error cases and edge conditions
- Use pytest fixtures for test data
- Aim for >80% code coverage

### Git Commit Messages
Follow Conventional Commits:
```
feat: add Redis-based browser slot management
fix: resolve race condition in quota enforcement
refactor: extract file validation to separate service
perf: optimize database queries with indexes
docs: add API documentation for submission endpoints
test: add integration tests for web scraping flow
chore: update dependencies to latest versions
```

---

## 📋 Quick Reference Checklist

Before every commit, verify:
- [ ] Code follows project structure and conventions
- [ ] All type hints added (mypy compatible)
- [ ] Linting passes (`ruff check .`)
- [ ] Tests pass (`pytest tests/ -v`)
- [ ] No hardcoded secrets or credentials
- [ ] Security best practices followed
- [ ] DRY principles applied
- [ ] Error handling implemented
- [ ] Proper async/await usage
- [ ] Database queries optimized
- [ ] Comments added for complex logic
- [ ] Manual testing completed

Before every PR:
- [ ] Branch up to date with deploy/production
- [ ] Descriptive PR title and description
- [ ] Database migrations included (if needed)
- [ ] API contract documented (if changed)
- [ ] Self-review completed
- [ ] Ready for Copilot review

Before merge:
- [ ] 3+ Copilot review iterations completed
- [ ] All critical feedback addressed
- [ ] All review comments resolved or justified
- [ ] Responded to every GitHub review comment
- [ ] CI/CD checks passing (pytest, ruff)
- [ ] No merge conflicts with deploy/production
- [ ] Human approval received (if required)
- [ ] Deployment plan ready (if significant change)

<!-- MANUAL ADDITIONS END -->