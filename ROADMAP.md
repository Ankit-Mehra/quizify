# Quizify Roadmap

**Last reviewed:** 2026-11-02  
**Scope:** Repository specifications, implementation, tests, migrations, deployment notes, and scaling plans

## Product direction

Quizify is an AI-powered learning API that turns text, documents, and public web pages into interactive quizzes. The core learning loop is:

```text
content source → extraction → AI question generation → saved quiz
       → quiz attempt → scoring, explanations, and learning history
```

The roadmap should optimize for a safe, reliable learning loop, straightforward self-hosting, and open-source adoption. Multi-instance scale follows measured demand; a commercial offering is an optional product decision, not a prerequisite for the core project.

### Open-source licensing and commercial scope

Quizify is distributed under [Apache License 2.0](./LICENSE). Apache licensing permits commercial use and selling software; it neither requires monetization nor rules it out. See the [Apache Software Foundation licensing FAQ](https://www.apache.org/foundation/license-faq.html).

For this roadmap, prioritize an independently deployable open-source API. Self-hosting should not require a Quizify subscription, checkout flow, or project-operated billing service; operators supply the necessary infrastructure and AI credentials and remain responsible for those services' costs. Usage limits remain configurable resource controls, not restrictions imposed by the source license.

Any future paid hosting or support belongs in the deferred commercial track below. No commercial offering is committed here. The existing tier-based implementation remains part of the current-state inventory; changing the roadmap does not remove those limits from the code.

## Current state

The implementation already provides a substantial MVP. The table below reflects the source code and tests as they exist now; older status documents are treated as historical when they conflict with the implementation.

| Area | Current state | Main evidence | Roadmap implication |
| --- | --- | --- | --- |
| Authentication | Supabase signup/login, JWT validation, bearer or cookie access tokens, password/email/account operations; refresh middleware does not propagate the new token to the current request or persist a rotated refresh token | [`api/auth_routes.py`](./api/auth_routes.py), [`handlers/auth_handlers.py`](./handlers/auth_handlers.py), [`middleware/auto_refresh.py`](./middleware/auto_refresh.py) | Fix refresh correctness, credential-changing flows, cookie-only behavior, and token handling |
| Quiz generation | Text, PDF, DOCX, TXT, file-ID, and URL generation paths exist | [`api/quiz_routes.py`](./api/quiz_routes.py), [`handlers/quiz_handlers.py`](./handlers/quiz_handlers.py) | Close entitlement, size, threshold, validation, and failure-cleanup gaps |
| AI generation | OpenAI structured-output path with smart chunking and asynchronous calls; Gemini code exists but is not the active path | [`services/ai_services/chunking_service.py`](./services/ai_services/chunking_service.py), [`services/ai_services/openai_service.py`](./services/ai_services/openai_service.py), [`services/ai_services/gemini_service.py`](./services/ai_services/gemini_service.py) | Add quality controls, retries, provider boundaries, cost visibility, and eventually background jobs |
| Source extraction | PDF/DOCX/TXT upload extraction and Playwright + Trafilatura web extraction exist; stored DOCX reuse falls back to binary-to-text decoding, and generation can skip later chunks of long documents | [`services/ai_services/doc_service.py`](./services/ai_services/doc_service.py), [`services/db_services/supabase_file.py`](./services/db_services/supabase_file.py), [`services/ai_services/chunking_service.py`](./services/ai_services/chunking_service.py) | Fix existing reuse and coverage bugs before richer extraction features |
| Quiz library | List, retrieve, metadata, and delete endpoints exist | [`services/db_services/supabase_quiz.py`](./services/db_services/supabase_quiz.py) | Add server-side search, date filters, pagination, and owner-safe mutations |
| Quiz taking | Submission scoring and answer persistence exist, including detailed results | [`api/submission_routes.py`](./api/submission_routes.py), [`handlers/submission_handler.py`](./handlers/submission_handler.py) | Validate complete quiz ownership/answer sets and make writes atomic |
| File management | Upload, metadata, signed download URL, and delete endpoints exist; file size is stored | [`handlers/file_handlers.py`](./handlers/file_handlers.py), [`services/db_services/supabase_file.py`](./services/db_services/supabase_file.py) | Enforce the 10 MB limit before processing and make deletion transactional and ownership-safe |
| Quotas and tiers | Quota checks run on four generation paths: text, uploaded file, stored-file ID, and URL; checks are separate from persistence, and quotas count currently stored quizzes | [`handlers/quiz_handlers.py`](./handlers/quiz_handlers.py), [`migrations/001_add_missing_features.sql`](./migrations/001_add_missing_features.sql), [`handlers/admin_handlers.py`](./handlers/admin_handlers.py) | Define deployment-configurable usage policies and make admission atomic; billing is optional |
| Database security | RLS policies exist, but own-row policies do not protect role/tier columns or server-calculated scores from otherwise permitted writes | [`migrations/005_fix_rls_insert_policies.sql`](./migrations/005_fix_rls_insert_policies.sql), [`migrations/007_add_answers_and_profiles_rls.sql`](./migrations/007_add_answers_and_profiles_rls.sql) | Verify actual grants, protect privileged fields, and test both API and direct-database access |
| Web security | Initial-host IP checks and DNS revalidation exist; redirects/subrequests have no explicit destination guard, and browser limits are per user rather than process-wide | [`services/web_scraping_service.py`](./services/web_scraping_service.py), [`tests/test_ssrf_protection.py`](./tests/test_ssrf_protection.py) | Close SSRF connection-path gaps and add bounded single-instance resource controls before scale-out |
| Deployment | Docker/Railway deployment path exists; the service is documented as a single instance | [`Dockerfile`](./Dockerfile), [`docs/DEPLOYMENT.md`](./docs/DEPLOYMENT.md), [`docs/SCALING_STRATEGY.md`](./docs/SCALING_STRATEGY.md) | Establish reproducible CI, health/readiness checks, migration discipline, and observable rollouts |
| Testing | Contract, integration, quota, admin, SSRF, and scraping tests are present | [`tests/`](./tests), [`pytest.ini`](./pytest.ini) | Make the suite runnable in a supported CI matrix and add tests for the known gaps |
| Distributed state | Redis design, contracts, and task breakdown are documented, but no Redis service implementation is present | [`specs/006-redis-integration/`](./specs/006-redis-integration/) | Implement only after scale triggers or when multi-instance deployment becomes a real requirement |

### Review verification (2026-11-02)

- Python 3.14.0 successfully collected **156 tests** outside the execution sandbox. The earlier framework-load failure was a sandbox restriction, not evidence of a missing runtime.
- **46 focused tests passed** across [`tests/test_quota_validation.py`](./tests/test_quota_validation.py), [`tests/test_admin_api.py`](./tests/test_admin_api.py), and [`tests/test_url_quiz_generation.py`](./tests/test_url_quiz_generation.py). This is not a full-suite pass or certification of a supported Python version.
- Deployed database grants, policies, and schema were not inspected. Database risks below are grounded in checked-in migrations; verify the effective permissions in a disposable or staging environment.

## Important contract drift to resolve first

The repository contains several generations of planning documents. Before treating the roadmap as an execution backlog, make these decisions canonical:

1. **Tier names and quotas:** the checked-in quota view and handler messages use `free = 5`, `basic = 100`, and `educator = 500`. [`README.md`](./README.md) and [`.github/copilot-instructions.md`](./.github/copilot-instructions.md) still mention `basic = 20` and `premium = unlimited`. Separate these historical hosted-product assumptions from operator-configurable limits. Define whether a limit applies to stored quizzes, cumulative generations, or a time window; the current count decreases when a quiz is deleted.
2. **URL and DOCX access:** the historical feature specification restricts these sources to basic/educator users, while the URL route advertises all tiers and the handler does not enforce the restriction. Resolve this as an operator-configurable source-access policy, not an assumed requirement for a paid Quizify account.
3. **Generation threshold:** the specification requires accepting at least 75% of requested questions, but the current handlers do not reject under-filled AI output.
4. **File-size enforcement:** 10 MB is documented and file size is persisted, but the upload and file-generation handlers do not reject an oversized payload before extraction or storage.
5. **Scrape timeout:** the specification calls for a 30-second page-load limit; the current service first allows 60 seconds and then retries at 30 seconds.
6. **Documentation status:** the [main feature spec](./specs/001-comprehensive-quiz-generation/spec.md) says “Implementation Complete.” Its [analysis report](./specs/001-comprehensive-quiz-generation/SPECIFICATION_ANALYSIS_REPORT.md) correctly acknowledges quota enforcement, while several [older implementation contracts](./specs/001-comprehensive-quiz-generation/contracts/) still describe it as missing. Reconcile those specific documents without discarding already-correct findings.
7. **Response contracts:** current generation handlers return saved `questions`, while older contracts say some generation paths omit them. The public API contract must choose one stable response shape.

These are not cosmetic inconsistencies. They affect resource controls, access policy, frontend integration, testing, and operational expectations. Subscription-specific behavior applies only if a separate commercial offering is chosen.

## Roadmap at a glance

| Release | Focus | Outcome | Priority |
| --- | --- | --- | --- |
| **0.1 — Contract baseline** | Reconcile specs, docs, limits, and test expectations | One authoritative product/API contract | P0 |
| **0.2 — Production correctness** | Database authority, SSRF boundaries, bounded resources, refresh, quota and data integrity | Safe and predictable MVP | P0 security / P1 correctness |
| **0.3 — API and learning UX** | Search/filter, pagination, consistent responses, history, observability basics | Usable product for active users | P1 |
| **0.4 — AI quality and reliability** | Quality gates, retries, provenance, async jobs, cost controls | More trustworthy quiz generation | P1 |
| **0.5 — Open-source adoption** | Self-hosting, deployment configuration, contributor and release guidance | Independently deployable community project | P1 |
| **0.6 — Scale-out** | Redis-backed coordination/cache, workers, horizontal deployment | Multi-instance operation when justified | P2 |
| **Optional — Commercial hosting** | Paid hosting/support and billing only after a product decision | Separate service offering, if desired | Deferred / not required |
| **1.x — Learning platform expansion** | Analytics, adaptive learning, collaboration, richer ingestion | Broader learning product | P2/P3 |

Milestones describe proposed scope, not fixed dates or strictly serial gates. Run **0.1 contract work and 0.2 security remediation in parallel**: ownership, privilege, and SSRF fixes must not wait for documentation reconciliation. Single-instance resource safety also belongs in 0.2, not in the Redis milestone.

## 0.1 — Contract baseline and release hygiene

**Goal:** make the intended product and the actual API agree, while urgent security fixes proceed independently.

### Deliverables

- Define a deployment-neutral usage/source-access policy. Decide whether to retain the existing `free`, `basic`, and `educator` labels as optional deployment presets or replace them with simpler operator-defined limits; keep administrative roles separate from these policies.
- Specify quota accounting: stored inventory versus cumulative/time-window generation usage, reset boundaries if applicable, deletion behavior, failed-generation reservation release, and policy-change behavior. This decision informs atomic admission in 0.2 and self-hosting configuration in 0.5; billing-period rules belong only to the optional commercial track.
- Update [`README.md`](./README.md), [`.github/copilot-instructions.md`](./.github/copilot-instructions.md), the active feature specification, API contracts, deployment docs, and Postman collections to match that model.
- Mark stale gap reports as historical or update them; remove contradictory “complete” and “not implemented” claims.
- Publish a small API contract matrix for every current endpoint: authentication mode, request shape, response shape, status codes, ownership rules, and side effects.
- Decide whether generation responses always include questions. Prefer one stable shape with `questions`, `questions_requested`, and `questions_generated`.
- Record and test a supported runtime matrix based on the Python 3.12 deployment target and any additional explicitly supported versions. Preserve the observed Python 3.14 collection result separately from support certification; validate reproducible dependency installation and full-suite behavior in CI.
- Add a versioned base schema and a documented migration sequence that can initialize an empty database. [`migrations/001_add_missing_features.sql`](./migrations/001_add_missing_features.sql) currently assumes existing tables rather than creating the base schema; include storage bucket/policy setup and cascade behavior in the reproducible environment.

### Exit criteria

- No conflicting quota, tier, timeout, or response-shape statements remain in active documentation.
- Every public endpoint has one current contract and at least one automated contract test.
- A clean environment can install dependencies, import the app, collect tests, and run the baseline suite.
- A disposable database can be initialized from checked-in setup/migrations, and effective grants/RLS policies can be tested without relying on undocumented dashboard changes.

## 0.2 — Production correctness and tenant safety

**Goal:** close the issues that can create data leaks, unexpected cost, invalid quizzes, or irreconcilable records.

### P0 — Immediate security boundaries

#### Close ownership and authorization gaps

- Restrict `profiles.role` and `profiles.account_tier` to trusted administrative operations, including a billing integration only if the optional commercial track is adopted. The [profile policy](./migrations/007_add_answers_and_profiles_rls.sql) checks the row ID but not privileged columns; with authenticated write grants, a direct database request could bypass admin endpoints.
- Protect server-calculated submission scores and answer correctness from direct client writes. Own-row RLS is not proof that every field in the row should be editable.
- Make quiz deletion explicitly owner-scoped; the current delete path accepts only a quiz ID and delegates to a service-role database client.
- Make file deletion resolve the stored record, verify ownership, derive the storage path from the record, then delete database and storage records safely. Do not trust a client-supplied filename to reconstruct the path.
- Audit service-role database calls and use authenticated clients where user-scoped permissions are appropriate. Keep privileged fields and grading behind narrowly authorized trusted operations rather than mechanically giving users write access to all their own records.
- Ensure URL generation, file-ID generation, quiz retrieval, metadata retrieval, submissions, and admin actions all use the same ownership rules.
- Test ordinary-user attempts to promote their role, change tier, forge scores, and access another user's data through both the API and direct Supabase access using the actual grants/policies.

#### Close SSRF connection-path gaps

- Validate or deny unsafe destinations for initial navigation, every redirect, and browser subrequests, including JavaScript-initiated fetches. The [current scraper](./services/web_scraping_service.py) checks the original hostname but does not explicitly guard subsequent destinations.
- Enforce allowed destinations at connection time through an egress-control or equivalent connection-bound mechanism. Repeating application DNS lookups does not pin the address Chromium actually connects to.
- Revisit Chromium flags, especially `--disable-web-security`, and keep the browser sandbox enabled wherever the deployment environment permits it.
- Add regression tests for public-to-private redirects, private-address subrequests, and DNS changes between validation and connection; reconcile the historical security audit with these remaining boundaries.

### P1 — Required MVP correctness and resource safety

#### Enforce shared preflight validation and bounded work

- Enforce the 10 MB upload limit with bounded reads/request handling, before loading an unrestricted payload into memory, extracting text, calling AI, or uploading to storage. Apply it to standalone upload and file-generation paths.
- Move the text-content byte-size check before the AI call; it currently happens afterward in [`handlers/quiz_handlers.py`](./handlers/quiz_handlers.py).
- Share title, question-type, and 1–50 question-count validation across JSON and multipart generation paths. Reject empty/invalid type selections and define how `mixed` interacts with explicit types; the multipart form currently lacks the JSON schema's count/type constraints.
- Validate content type using both declared MIME type and file signature/format where practical.
- Enforce operator-configured source-access policies consistently, including stored-file reuse, following the decision in 0.1. Do not make self-hosted URL/DOCX access depend on a project-operated paid upgrade; preserve authentication and resource safeguards in every deployment.
- Apply consistent URL limits: maximum URL length, maximum extracted content size in bytes, minimum meaningful content, page-load timeout, total operation timeout, and bounded retries.
- Add per-user/IP rate limits plus process-wide browser and AI concurrency budgets. Per-user browser counters alone cannot bound total single-instance resource usage; apply distributed coordination later in 0.6.
- Replace blocking network calls inside async middleware/handlers with nonblocking I/O or bounded thread offloading, and set explicit connection/read/overall deadlines. In particular, [`middleware/auto_refresh.py`](./middleware/auto_refresh.py) currently uses synchronous HTTP without timeouts.

#### Make quota admission and generation durable

- After defining quota semantics in 0.1, atomically reserve capacity in the authoritative database before expensive work. Concurrent requests for the same last available slot must not all pass a separate read-only quota check; release/refund reservations on failure according to the chosen policy.
- Reject generated output below `ceil(0.75 × questions_requested)` after validating question type and semantics. Return requested/generated counts, record actual question counts, and do not persist an invalid quiz.
- Validate every generated question against the requested type, required fields, option counts, correct-answer shape, and source/explanation requirements.
- Define behavior for duplicate questions, empty output, provider timeouts, malformed structured output, and partial provider failure.
- Use format-aware extraction for stored files, especially DOCX: [`parse_file_from_supabase`](./services/db_services/supabase_file.py) currently falls back to decoding DOCX ZIP bytes as text instead of extracting document content.
- Fix long-document coverage: [`generate_quizzes_single_async`](./services/ai_services/chunking_service.py) stops scheduling later chunks when there are more chunks than requested questions. Define a coverage/sampling strategy that does not silently ignore the document tail, with regression cases spanning the beginning, middle, and end.
- Prevent orphaned files, quizzes, questions, and metadata when a later step fails. Add compensating cleanup or a database transaction/outbox pattern; keep a successfully stored source available for retry when generation fails.
- Add idempotency support for retried generation requests so a client retry neither creates duplicate quizzes nor consumes multiple quota reservations.

#### Make submissions authoritative

- Derive the question set from the requested quiz and verify every submitted question belongs to that quiz.
- Reject missing answers, duplicate answers, unknown question IDs, and a client-supplied `total_questions` that does not match the quiz.
- Compare answers by question type: booleans as booleans, strings normalized intentionally, and matching answers as validated index lists rather than stringified values.
- Include explanations in detailed results, as required by the product spec.
- Save the submission and all answers atomically, or provide a recoverable state for partial writes.
- Add submission-history listing and aggregate progress only after the underlying records are trustworthy.

#### Make admin changes and audit records consistent

- Reconcile the role-audit payload with migrations: [`handlers/admin_handlers.py`](./handlers/admin_handlers.py) writes `security_context`, but [`migrations/004_add_rbac_roles.sql`](./migrations/004_add_rbac_roles.sql) does not define that column. Add the migration or change the payload, and verify against a freshly initialized database.
- Commit a role change and its audit entry in one transaction, with authorization and last-admin checks enforced atomically. The current handler performs separate operations and reports success even when audit insertion fails.
- Protect audit records against unauthorized alteration/deletion and verify that failed audit writes cannot leave an untracked privilege change.

#### Harden authentication and security

- Propagate refreshed authentication to dependencies in the same request before forwarding it; the current middleware sets only the outgoing access-token cookie after the handler has already run.
- Persist a rotated refresh token as well as the access token, and test repeated refresh, expiry, invalidation, and concurrent refresh behavior.
- Register and test the refresh-session endpoint, or remove the dead route code and document the middleware-owned refresh flow.
- Make cookie-only authentication work consistently for email updates and every protected operation; do not require a bearer header in one protected handler when cookies are the production mechanism.
- Change password through the authenticated user context rather than accepting an email supplied by the client and using an admin update path.
- Define account-deletion cleanup for profiles, files, quizzes, metadata, submissions, answers, and storage objects; verify the database cascade policy.
- Remove token prefixes from debug logs and replace them with a non-reversible request/session identifier.

### Exit criteria

- Cross-user read, update, and delete tests fail closed for every resource type; ordinary users cannot change privileged profile fields or graded results through direct database access.
- Unsafe redirects, subrequests, and connection-time DNS changes cannot reach private/reserved destinations.
- Oversized, unsupported, or malformed requests are rejected before AI calls, extraction, or storage side effects. Under-generated/invalid AI output is rejected after generation without persisting an invalid quiz; a stored source remains available for retry.
- Concurrent requests cannot exceed authoritative quota capacity, and failed/retried requests follow the documented reservation and idempotency policy.
- A request with an expired access token and valid refresh token succeeds after refresh without a client retry, and subsequent refreshes use the latest token.
- DOCX reuse extracts meaningful document text, long-document tests cover later sections, and process-wide concurrency limits hold under load.
- Role changes and their audit records succeed or fail together against the checked-in schema.
- A failed generation or submission leaves no untracked partial record.
- Security, quota, scraper, file, and submission tests pass in CI.

## 0.3 — API maturity and learning UX

**Goal:** make the MVP pleasant and predictable for users with a growing quiz library.

### Deliverables

- Add `title`, `start_date`, and `end_date` filters to `GET /api/quiz/my-quizzes` with validated inclusive date semantics.
- Add pagination, stable sorting, and a response envelope containing page metadata; do not load an unbounded quiz library into memory.
- Add indexes that match the actual query patterns and verify query plans with representative data.
- Standardize error responses and generation responses across text, file, file-ID, and URL paths.
- Return the persisted file ID from file upload; do not use the original filename as the public identifier.
- Make file metadata ordering and signed-URL expiration explicit and consistent with the contract.
- Add a submission-history endpoint with pagination and optional quiz/date filters.
- Add a health endpoint and a readiness check that distinguish process health from Supabase/OpenAI/Redis dependency health.
- Generate and publish an OpenAPI snapshot or contract-diff check so route changes are visible before deployment.
- Add API versioning or an explicit compatibility policy before making breaking response changes.

### Exit criteria

- A user can find a quiz in a large library without client-side scanning.
- Frontend integration can rely on one response/error convention.
- Health and readiness checks support safe Railway deploys and rollback decisions.

## 0.4 — AI quality, reliability, and cost control

**Goal:** improve the educational value and operational predictability of generated quizzes.

### Deliverables

- Centralize provider configuration, model selection, prompt versioning, and generation timeouts.
- Add bounded retries with backoff for transient provider failures and distinguish retryable errors from invalid content.
- Validate structured output before persistence and capture a safe provider/model/prompt version for auditability.
- Preserve source excerpts for each question and surface explanations in quiz-taking responses.
- Test mixed-question distribution, exact counts, minimum 75% acceptance, duplicate detection, and malformed provider output.
- Add a generation job abstraction. Keep a synchronous path for small requests, but support `queued → running → completed/failed` for large documents and slow URLs.
- Track token usage, latency, provider failures, generated-question yield, and estimated cost per quiz without logging source secrets or tokens.
- Add optional OCR or richer document extraction only after measuring demand from image-only PDFs and table-heavy documents.

### Exit criteria

- Generation success, latency, yield, and cost are measurable by source type and model.
- Users receive deterministic status and retry behavior for slow or failed jobs.
- Quality regression tests catch schema-valid but educationally poor output patterns.

## 0.5 — Open-source adoption and self-hosting

**Goal:** make Quizify easy to deploy, operate, and contribute to without a commercial-service dependency.

### Deliverables

- Provide a clean self-hosting guide covering configuration, AI credentials, Supabase Auth/Storage, migrations, startup, and health checks, building on the reproducible setup from 0.1.
- Make usage limits and enabled source types operator-configurable rather than requiring hard-coded paid-tier assignments or access to a Quizify billing service.
- Document infrastructure/API cost responsibilities and distinguish freely available source code from the cost of running external services.
- Provide contributor setup, test instructions, issue-reporting guidance, and versioned release notes.
- Document applicable third-party licenses and preserve required license/attribution notices in distributions.
- Keep any future commercial integration separable from normal application startup and core generation/submission workflows. Authentication, ownership checks, and resource safeguards remain required in self-hosted deployments.

### Exit criteria

- A new operator can deploy from the documented setup and complete the learning loop using their own infrastructure/credentials without subscribing to a Quizify service.
- Documented usage/source configuration is enforced and does not weaken security controls.
- A contributor can install dependencies and run the documented tests, and released distributions include applicable licensing information.

## 0.6 — Scale-out and distributed operations

**Goal:** support more traffic and more than one API instance without duplicating state or losing resource controls.

The Redis design is already specified in [`specs/006-redis-integration/`](./specs/006-redis-integration/), but the implementation should be trigger-based rather than schedule-based.

### Trigger conditions

Start this release when one or more of the following is true. The user-count thresholds below are historical planning estimates, not measured capacity guarantees; confirm the need with latency, queue, and resource-utilization measurements.

- daily active users consistently exceed roughly 100;
- concurrent users exceed roughly 20;
- a second API instance is needed for availability or deployments;
- in-memory browser-slot coordination causes incorrect limits;
- tier/quota reads or quiz-library reads become a measured latency bottleneck.

### Deliverables

- Implement Redis client/configuration with connection health checks, timeouts, and explicit outage behavior per service. A read cache may fall back to the authoritative database; multi-instance slot/rate enforcement must not silently fall back to independent counters that exceed global limits.
- Move browser-slot acquisition/release to atomic distributed operations with TTLs and crash recovery.
- Cache user tier/quota displays and other safe read-heavy data with invalidation on quiz creation/deletion, quota reservation/release/reset where applicable, profile or operator-policy changes, and billing events only if that optional integration exists. Keep quota admission atomic in the authoritative database rather than trusting a cached availability check.
- Add observability for cache hit rate, stale data, lock/slot leakage, and Redis availability.
- Keep Supabase Auth as the source of truth for identity; do not create a second session authority in Redis unless a separate requirement justifies it.
- Move long-running generation/scraping to worker processes and keep API instances responsive.
- Define graceful degradation: what remains available if Redis, OpenAI, Playwright, or Supabase is unavailable.
- Deploy multiple instances behind Railway/platform routing, with migration sequencing, canary checks, rollback, and load tests.

### Exit criteria

- Two or more instances enforce the same per-user browser and rate limits.
- Cached usage reflects generation/deletion and entitlement changes, and cache outages/stale entries cannot bypass authoritative quotas or distributed resource budgets.
- Restarting an instance does not leak slots or lose job state.
- Load tests meet the documented latency/error targets with dependency failures injected.

## Optional — Commercial hosting or support (decision deferred)

**Status:** not part of the required open-source milestones. Apache 2.0 permits a commercial offering, but choosing a business model is separate from licensing and is not a dependency for 0.1–0.6 or 1.x.

If a paid hosted service is later chosen, scope a separate specification for:

- hosting/support plans and a clear boundary between service allowances and the Apache-licensed project;
- a payment provider, checkout, subscriptions, cancellation/grace periods, and signed/idempotent webhooks;
- verifiable hosted-account entitlements, auditable support overrides, and safe out-of-order event handling;
- notifications and tests covering payment success/failure, duplicate events, cancellation, and manual overrides;
- operation of the open-source API without commercial credentials, subscription verification, or mandatory contact with a project-operated service.

Only prioritize this track after an explicit decision to offer a commercial service. It does not replace the resource-safety, security, or self-hosting work above.

## 1.x — Product expansion candidates

Some valuable possibilities, but they should follow the reliability work above and can not be treated as committed scope yet:

- progress dashboard with submission history, topic-level performance, and spaced-repetition recommendations;
- quiz editing, regeneration of individual questions, and versioned quiz revisions;
- sharing, classroom/educator workflows, assignments, and cohort analytics;
- additional source connectors such as presentations, spreadsheets, audio/transcripts, and OCR-heavy documents;
- collaborative quiz authoring and public/private sharing controls;
- model/provider comparison, human quality review, and adaptive difficulty;
- export/import formats such as JSON, CSV, or LMS-compatible packages.

Each candidate should first get a focused specification with measurable acceptance criteria and a data-retention/privacy decision.

## Cross-cutting engineering standards

Every roadmap item should include:

- an API contract and negative cases;
- unit, contract, and integration coverage appropriate to the risk;
- ownership and privileged-field authorization tests, including direct database access where applicable, for every new user-scoped resource;
- structured logs with correlation IDs and no credentials/tokens;
- timeout, retry, and idempotency behavior for external calls;
- migration, rollback, and data-cleanup steps;
- documentation updates in the same change as the implementation;
- a measurable exit criterion rather than “production-ready” as a label.

## Recommended first sprint

1. Start P0 database privilege/ownership and SSRF fixes immediately, with regression tests. In parallel, define deployment-neutral usage/source-access policies, quota accounting/deletion behavior, timeouts, and response contracts.
2. Establish reproducible CI on the supported runtime matrix and a clean-database migration/grants baseline. Preserve the review result of 156 tests collected and 46 focused tests passed as limited evidence, not a full-suite pass.
3. Add regression cases for atomic quota admission, same-request refresh and token rotation, bounded uploads and multipart validation, the 75% threshold, DOCX reuse, long-document coverage, submission completeness, and transactional role auditing.
4. Implement the P1 correctness and single-instance resource-safety fixes, then align contracts and deployment guidance with the verified behavior.
5. Add server-side quiz search/date filters and pagination after ownership and response contracts stabilize. Follow with self-hosting/adoption work; Redis follows measured need, and billing remains a deferred option rather than a required milestone.

This parallel sequence prioritizes security fixes without waiting for documentation cleanup, then closes the correctness and resource-control gaps needed for a trustworthy MVP. These are planned changes; updating this document does not mark any implementation fix complete.

## Source documents reviewed

- [Project license](./LICENSE) and [Apache Software Foundation licensing FAQ](https://www.apache.org/foundation/license-faq.html)
- [Primary quiz-generation specification](./specs/001-comprehensive-quiz-generation/spec.md), [plan](./specs/001-comprehensive-quiz-generation/plan.md), [research](./specs/001-comprehensive-quiz-generation/research.md), [tasks](./specs/001-comprehensive-quiz-generation/tasks.md), [analysis report](./specs/001-comprehensive-quiz-generation/SPECIFICATION_ANALYSIS_REPORT.md), and [next steps](./specs/001-comprehensive-quiz-generation/NEXT_STEPS.md)
- [Primary API contracts](./specs/001-comprehensive-quiz-generation/contracts/)
- [Redis integration research, contracts, plan, and tasks](./specs/006-redis-integration/)
- [README and environment template](./README.md), [`.env.example`](./.env.example), and [deployment guide](./docs/DEPLOYMENT.md)
- [Capacity analysis](./docs/CURRENT_CAPACITY_ANALYSIS.md), [scaling strategy](./docs/SCALING_STRATEGY.md), and [security audit](./docs/SECURITY_AUDIT_REPORT.md)
- [RLS implementation notes](./docs/RLS_SECURITY_IMPLEMENTATION.md), [tier-management plan](./docs/TIER_MANAGEMENT_PLAN.md), and [deployment quick reference](./docs/RAILWAY_DEPLOYMENT_QUICKREF.md)
- Active route, handler, service, schema, migration, and test trees under [`api/`](./api/), [`handlers/`](./handlers/), [`services/`](./services/), [`schemas/`](./schemas/), [`migrations/`](./migrations/), and [`tests/`](./tests/)

The archived specification under [`specs/_archive/`](./specs/_archive/) and the `.specify` templates were treated as historical/process context, not as current product commitments.
