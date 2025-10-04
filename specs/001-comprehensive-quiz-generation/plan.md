
# Implementation Plan: Comprehensive Quiz Generation Platform

**Branch**: `001-comprehensive-quiz-generation` | **Date**: 2025-10-03 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-comprehensive-quiz-generation/spec.md`

## Execution Flow (/plan command scope)
```
1. Load feature spec from Input path
   → If not found: ERROR "No feature spec at {path}"
2. Fill Technical Context (scan for NEEDS CLARIFICATION)
   → Detect Project Type from file system structure or context (web=frontend+backend, mobile=app+api)
   → Set Structure Decision based on project type
3. Fill the Constitution Check section based on the content of the constitution document.
4. Evaluate Constitution Check section below
   → If violations exist: Document in Complexity Tracking
   → If no justification possible: ERROR "Simplify approach first"
   → Update Progress Tracking: Initial Constitution Check
5. Execute Phase 0 → research.md
   → If NEEDS CLARIFICATION remain: ERROR "Resolve unknowns"
6. Execute Phase 1 → contracts, data-model.md, quickstart.md, agent-specific template file (e.g., `CLAUDE.md` for Claude Code, `.github/copilot-instructions.md` for GitHub Copilot, `GEMINI.md` for Gemini CLI, `QWEN.md` for Qwen Code, or `AGENTS.md` for all other agents).
7. Re-evaluate Constitution Check section
   → If new violations: Refactor design, return to Phase 1
   → Update Progress Tracking: Post-Design Constitution Check
8. Plan Phase 2 → Describe task generation approach (DO NOT create tasks.md)
9. STOP - Ready for /tasks command
```

**IMPORTANT**: The /plan command STOPS at step 7. Phases 2-4 are executed by other commands:
- Phase 2: /tasks command creates tasks.md
- Phase 3-4: Implementation execution (manual or via tools)

## Summary
This plan focuses on implementing the **missing features** from the comprehensive quiz generation platform specification. The backend already implements core quiz generation (text/PDF/DOCX), authentication, quiz management, and file handling. **Missing components** include: user tier management (free/basic/educator), quiz quotas enforcement, search/filter capabilities, DOCX restriction for free users, web URL quiz generation (paid tiers only), 75% question generation threshold, and 10MB file size validation.

**Implementation Status Analysis**:
- ✅ **Implemented**: Authentication (signup/login/logout/verify), Quiz generation (text/PDF/DOCX), File management, Submissions/scoring, OpenAI integration, Smart chunking
- ❌ **Missing**: User tier management, Quota enforcement, Search/filter quizzes, Tier-based file type restrictions, Web URL scraping & quiz generation, Payment/upgrade flow, 75% generation threshold validation, 10MB file size enforcement

## Technical Context
**Language/Version**: Python 3.12+  
**Primary Dependencies**: FastAPI 0.1.0, Supabase (PostgreSQL + Auth + Storage), OpenAI GPT-4, Pydantic v2, PyPDF2, python-docx, Playwright 1.40.0, trafilatura 1.6.2, tenacity 8.2.3  
**Storage**: Supabase PostgreSQL with Row Level Security, Supabase Storage for files  
**Testing**: pytest (to be added for new features)  
**Target Platform**: Linux server / Cloud deployment (Azure recommended in archived spec 002)  
**Project Type**: Web application (backend API - frontend separate repository recommended)  
**Performance Goals**: Auth <2s, Quiz retrieval <1s, Generation <60s, File upload <10s, Web scraping <30s  
**Constraints**: 10MB file size limit, 1-50 questions per quiz, 8000 token chunks, 75% minimum question generation, 500KB max web content, 100 char minimum web content  
**Scale/Scope**: Support free (5 quizzes), basic (100 quizzes), educator (500 quizzes) tiers; thousands of files per user; web scraping for paid tiers only

**User-Provided Context**: Analyze existing codebase implementation and create plan for missing requirements. Backend core functionality already exists - focus on tier management, quotas, search/filter, web scraping, and validation enhancements.

## Constitution Check
*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Principle I: API-First Architecture** ✅ PASS
- All new tier management features will be exposed through REST APIs
- User tier upgrade endpoint, quota validation endpoint, search/filter endpoints planned
- OpenAPI documentation will be updated for all new endpoints
- No business logic bypasses API layer

**Principle II: Content Source Agnostic** ✅ PASS  
- Existing implementation already supports text, PDF, DOCX with dedicated services
- New file type restrictions (DOCX for paid tiers) enforced at API level, not content processing
- No changes to content processing services required

**Principle III: Service-Oriented Design** ✅ PASS
- Tier management will be implemented as independent service (`tier_service.py`)
- Quota validation as reusable service function (`quota_service.py`)
- Search/filter logic isolated in database service layer
- Clear boundaries maintained between auth, tier management, and quiz services

**Principle IV: Comprehensive Logging & Observability** ✅ PASS
- All tier operations (upgrades, quota checks) will log with structured format
- Quota rejection events logged for monitoring
- Search/filter operations logged at INFO level
- Existing logging infrastructure (`services/logger.py`) will be extended

**Principle V: Security by Design** ✅ PASS
- Tier information stored in user profile with RLS policies
- Quota enforcement validated server-side (never trust client)
- Payment/upgrade flows will require additional authentication
- File size validation prevents DoS attacks (10MB limit)

**Complexity Assessment**: No violations. New features fit within existing architecture patterns. Tier management adds one new database column and service layer - minimal complexity increase.

## Project Structure

### Documentation (this feature)
```
specs/[###-feature]/
├── plan.md              # This file (/plan command output)
├── research.md          # Phase 0 output (/plan command)
├── data-model.md        # Phase 1 output (/plan command)
├── quickstart.md        # Phase 1 output (/plan command)
├── contracts/           # Phase 1 output (/plan command)
└── tasks.md             # Phase 2 output (/tasks command - NOT created by /plan)
```

### Source Code (repository root)
```
quizify/ (Backend API - existing structure)
├── api/                      # FastAPI route definitions
│   ├── auth_routes.py        # ✅ Exists - needs tier upgrade endpoint
│   ├── quiz_routes.py        # ✅ Exists - needs search/filter endpoints
│   ├── file_routes.py        # ✅ Exists - needs tier validation
│   └── submission_routes.py  # ✅ Exists - complete
├── handlers/                 # Business logic handlers
│   ├── auth_handlers.py      # ✅ Exists - needs upgrade_tier handler
│   ├── quiz_handlers.py      # ✅ Exists - needs quota + search logic
│   ├── file_handlers.py      # ✅ Exists - needs tier + size validation
│   └── submission_handler.py # ✅ Exists - complete
├── services/                 # Service layer
│   ├── logger.py             # ✅ Exists - complete
│   ├── ai_services/          # ✅ Exists - needs 75% threshold check
│   │   ├── openai_service.py
│   │   ├── chunking_service.py
│   │   └── doc_service.py
│   └── db_services/          # ✅ Exists - needs tier + search queries
│       ├── supabase_quiz.py  # Needs: get_user_quiz_count, search_quizzes
│       ├── supabase_file.py
│       └── supabase_submission.py
├── schemas/                  # Pydantic models
│   ├── user.py               # ❌ Missing tier field
│   ├── quiz.py               # ✅ Exists - complete
│   ├── files.py              # ✅ Exists - needs size validation
│   └── submission.py         # ✅ Exists - complete
├── dependencies/             # FastAPI dependencies
│   └── auth_dependencies.py  # ✅ Exists - needs get_user_tier
├── middleware/               # Middleware components
│   └── auto_refresh.py       # ✅ Exists - complete
└── tests/                    # ❌ To be created
    ├── contract/             # Contract tests for APIs
    ├── integration/          # Integration tests
    └── unit/                 # Unit tests
```

**Structure Decision**: Single backend project (Option 1) with existing FastAPI structure. All new features integrate into current modular organization. Frontend will be separate repository (not in scope for this plan). Testing directory structure to be created as part of Phase 1.

## Phase 0: Outline & Research
1. **Extract unknowns from Technical Context** above:
   - For each NEEDS CLARIFICATION → research task
   - For each dependency → best practices task
   - For each integration → patterns task

2. **Generate and dispatch research agents**:
   ```
   For each unknown in Technical Context:
     Task: "Research {unknown} for {feature context}"
   For each technology choice:
     Task: "Find best practices for {tech} in {domain}"
   ```

3. **Consolidate findings** in `research.md` using format:
   - Decision: [what was chosen]
   - Rationale: [why chosen]
   - Alternatives considered: [what else evaluated]

**Output**: research.md with all NEEDS CLARIFICATION resolved

## Phase 1: Design & Contracts
*Prerequisites: research.md complete*

1. **Extract entities from feature spec** → `data-model.md`:
   - Entity name, fields, relationships
   - Validation rules from requirements
   - State transitions if applicable

2. **Generate API contracts** from functional requirements:
   - For each user action → endpoint
   - Use standard REST/GraphQL patterns
   - Output OpenAPI/GraphQL schema to `/contracts/`

3. **Generate contract tests** from contracts:
   - One test file per endpoint
   - Assert request/response schemas
   - Tests must fail (no implementation yet)

4. **Extract test scenarios** from user stories:
   - Each story → integration test scenario
   - Quickstart test = story validation steps

5. **Update agent file incrementally** (O(1) operation):
   - Run `.specify/scripts/bash/update-agent-context.sh copilot`
     **IMPORTANT**: Execute it exactly as specified above. Do not add or remove any arguments.
   - If exists: Add only NEW tech from current plan
   - Preserve manual additions between markers
   - Update recent changes (keep last 3)
   - Keep under 150 lines for token efficiency
   - Output to repository root

**Output**: data-model.md, /contracts/*, failing tests, quickstart.md, agent-specific file

## Phase 2: Task Planning Approach
*This section describes what the /tasks command will do - DO NOT execute during /plan*

**Task Generation Strategy**:

The `/tasks` command will break down the implementation into sequential and parallel tasks based on the Phase 1 design artifacts (data-model.md, contracts/, quickstart.md).

**Category 1: Database & Infrastructure** (Sequential)
- Create Supabase migration for account_tier column + indexes
- Add file_size_bytes column to files table
- Create GIN index for quiz title search
- Test migrations in local Supabase instance

**Category 2: Service Layer** (Can be parallel after database)
- Create `services/tier_service.py` (get_user_tier, update_tier functions)
- Create `services/quota_service.py` (validate_quota, get_quota_limits)
- Create `services/ai_services/web_scraper_service.py` (scrape_url, validate_url_security, extract_main_content)
- Add search/filter functions to `services/db_services/supabase_quiz.py`
- Add 75% threshold validation to `services/ai_services/chunking_service.py`

**Category 3: Schema Updates** (Can be parallel with Category 2)
- Update `schemas/user.py` with account_tier field
- Update `schemas/files.py` with file_size_bytes validation
- Update `schemas/quiz.py` with content_source_type and content_source_reference fields

**Category 4: Handler Logic** (Sequential, depends on Category 2 & 3)
- Add tier validation to `handlers/quiz_handlers.py` (quota check before generation)
- Add web URL generation handler to `handlers/quiz_handlers.py` (generate_quiz_from_url)
- Add search/filter logic to quiz handler
- Add tier + size validation to `handlers/file_handlers.py`
- Create `handlers/tier_handler.py` for upgrade endpoint

**Category 5: API Routes** (Sequential, depends on Category 4)
- Add `POST /api/auth/upgrade-tier` endpoint
- Add `POST /api/quiz/generate/url` endpoint for web scraping
- Update `GET /api/quiz/my-quizzes` with query params (title, start_date, end_date)
- Update error responses for quota violations
- Update error responses for tier/size violations

**Category 6: Contract Tests** (Can start in parallel with implementation)
- Create contract test for upgrade-tier endpoint
- Create contract test for search/filter quizzes
- Create contract test for quota enforcement
- Create contract test for file upload validation
- Create contract test for web URL quiz generation

**Category 7: Integration Tests** (After contract tests pass)
- Create integration test for tier workflows (upgrade + quota flow)
- Create integration test for search workflows (search + filter combinations)
- Create integration test for generation threshold (75% validation with mocks)
- Create integration test for web scraping workflow (URL validation, security, content extraction)

**Category 8: Documentation & Deployment** (Final)
- Update OpenAPI schemas with new endpoints
- Update README.md with tier management instructions
- Create deployment guide for Supabase migration
- Update constitution compliance checklist

**Parallelization Opportunities**:
- Service layer + schema updates can run simultaneously (~40% parallelizable)
- All contract tests can run in parallel (independent validations)
- Frontend integration deferred to separate repository (not in scope)

**Estimated Output**: 35-38 numbered, ordered tasks with [P] markers for parallel execution (increased from 30 due to web scraping feature)

**Ordering Strategy**:
- TDD order: Contract tests before implementation 
- Dependency order: Database → Services → Handlers → Routes
- Mark [P] for parallel execution (independent files)

**IMPORTANT**: This phase is executed by the `/tasks` command, NOT by `/plan`

## Phase 3+: Future Implementation
*These phases are beyond the scope of the /plan command*

**Phase 3**: Task execution (/tasks command creates tasks.md)  
**Phase 4**: Implementation (execute tasks.md following constitutional principles)  
**Phase 5**: Validation (run tests, execute quickstart.md, performance validation)

## Complexity Tracking
*Fill ONLY if Constitution Check has violations that must be justified*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |


## Progress Tracking
*This checklist is updated during execution flow*

**Phase Status**:
- [x] Phase 0: Research complete (/plan command) - research.md created
- [x] Phase 1: Design complete (/plan command) - data-model.md, contracts/, quickstart.md created
- [x] Phase 2: Task planning approach documented (/plan command)
- [x] Phase 3: Tasks generated (/tasks command) - tasks.md created with 65 tasks
- [ ] Phase 4: Implementation complete
- [ ] Phase 5: Validation passed

**Gate Status**:
- [x] Initial Constitution Check: PASS (all principles satisfied)
- [x] Post-Design Constitution Check: PASS (no violations introduced)
- [x] All NEEDS CLARIFICATION resolved (research.md complete)
- [x] Complexity deviations documented (none - fits existing patterns)

**Artifacts Created**:
- [x] research.md (10 research decisions documented - includes web scraping)
- [x] data-model.md (5 entity enhancements + migration plan - includes content source tracking)
- [x] contracts/upgrade-tier.md (tier upgrade API contract)
- [x] contracts/search-quizzes.md (search/filter API contract)
- [x] contracts/generate-quiz-quota.md (quota enforcement contract)
- [x] contracts/file-upload-validation.md (file validation contract)
- [x] contracts/generate-quiz-from-url.md (web URL quiz generation contract - NEW)
- [x] quickstart.md (7 test flows documented - includes web scraping)
- [x] .github/copilot-instructions.md (agent context updated)
- [x] tasks.md (65 tasks: 15 tests for existing code + 50 new feature tasks)

**Ready for**: Implementation execution (Phase 4) - Start with T001 (Setup)

---
*Based on Constitution v1.0.0 - See `/memory/constitution.md`*
