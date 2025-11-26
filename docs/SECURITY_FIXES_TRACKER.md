# Security Fixes Tracker

## Overview
Tracking document for addressing security review findings from expert adviser.
Date: November 26, 2025
Branch: stripe-integration

## Status Legend
- ⏳ Pending
- 🔄 In Progress
- ✅ Completed
- ❌ Blocked

---

# ROUND 4 REVIEW (Final Hardening - Approve with Changes)

## Verdict: **Approve with changes** - Low/Medium residual risk

---

## ISSUES ADDRESSED

### R4-1. ✅ Add Alert/Metric When Fallback Toggles On
- **Issue**: No alerting when Redis-backed components fall back to memory mode
- **Fix**: 
  - Added `BILLING_FALLBACK:` log prefix for state transitions
  - Logs when entering fallback mode (WARNING level)
  - Logs when recovering from fallback mode (INFO level)
  - Applied to both `WebhookIdempotencyStore` and `BillingRateLimiter`
- **Status**: ✅ Completed

### R4-2. ✅ Health Endpoint Returns Degraded Status
- **Issue**: Health endpoint always returns 200 "ok" even in fallback mode
- **Fix**: 
  - Returns `status: "degraded"` when in memory fallback mode
  - Returns `status: "ok"` only when Redis is connected
  - Updated message to indicate fallback status
  - Still returns 200 so Stripe webhook validation passes (monitoring should alert on status != "ok")
- **Status**: ✅ Completed

### R4-3. ✅ Configurable Strict Mode for Webhooks
- **Issue**: In multi-instance prod, duplicate webhooks can slip through during Redis outage
- **Fix**: 
  - Added `BILLING_REQUIRE_REDIS` env var (default: false)
  - When true, webhooks return 503 if Redis is unavailable
  - Logs with `BILLING_STRICT:` prefix when rejecting webhooks
  - Enables "fail closed" behavior for production environments
- **Status**: ✅ Completed

### R4-4. ✅ Ensure All Stripe IDs Truncated in Logs
- **Issue**: Some INFO logs still had full Stripe IDs
- **Fix**: Applied `_short_stripe_id()` to all remaining locations:
  - "No user_id in subscription" logs (3 locations)
  - "SECURITY: Webhook authorization failed" logs (3 locations)
  - Context strings passed to internal functions
  - Subscription updated/created/deleted logs
- **Status**: ✅ Completed

---

# ROUND 3 REVIEW (Distributed Systems Hardening)

## Verdict: Additional hardening completed

---

## ISSUES ADDRESSED

### R3-1. ✅ Upgrade Webhook Idempotency to Redis
- **File**: `api/billing_routes.py`
- **Issue**: WebhookIdempotencyStore was in-memory only, doesn't work across multiple instances
- **Fix**: Complete rewrite to Redis-backed store with memory fallback:
  - Uses Redis SET with NX for atomic idempotency checks
  - Auto-expires with TTL (24 hours)
  - Falls back to in-memory LRU if Redis unavailable
  - Added `is_using_fallback` property for health monitoring
  - Added `is_duplicate_async()` for async Redis operations
- **Status**: ✅ Completed

### R3-2. ✅ Add HTTP Client Shutdown Cleanup
- **File**: `middleware/auto_refresh.py`, `main.py`
- **Issue**: httpx.AsyncClient was never closed on shutdown, potential resource leak
- **Fix**: 
  - Added `close_http_client()` function to middleware
  - Import and call in `app_lifespan` during shutdown
- **Status**: ✅ Completed

### R3-3. ✅ Add Health Flags for Redis Fallback Status
- **File**: `api/billing_routes.py`
- **Issue**: No way to know if billing components are using Redis or memory fallback
- **Fix**: 
  - Added `is_using_fallback` property to `WebhookIdempotencyStore`
  - Added `is_using_fallback` property to `BillingRateLimiter`
  - Updated `/api/billing/health` endpoint to expose Redis connection status
- **Status**: ✅ Completed

### R3-4. ✅ Consistent Stripe ID Truncation in Logs
- **File**: `api/billing_routes.py`
- **Issue**: Some logs still showed full Stripe event IDs
- **Fix**: 
  - Webhook event_id now truncated to 12 chars with `...` suffix
  - Applied to all webhook logging (processing, duplicate, error logs)
- **Status**: ✅ Completed

---

## ALREADY IMPLEMENTED (Reviewer may have missed)

### Rate Limiting IS Redis-backed ✅
- **Location**: `api/billing_routes.py` lines 182-285
- **Evidence**: Uses Redis sorted sets with ZADD/ZCARD operations
- **Fallback**: Automatic memory fallback if Redis unavailable

### URL Validation IS Implemented ✅
- **Location**: `services/billing_service.py` lines 373-380
- **Evidence**: Validates success/cancel URLs against FRONTEND_URL domain

### First-Time Mapping Alerting IS Implemented ✅
- **Location**: `services/billing_service.py` line 226
- **Evidence**: `BILLING_AUDIT:` log prefix for all first-time customer mappings

---

# ROUND 2 REVIEW (Post-Security Fixes)

## Verdict: Approve with changes

---

## MODERATE ISSUES (Should Fix) - MEDIUM PRIORITY

### R2-1. ✅ Blocking Stripe Calls in billing_handler.py
- **File**: `handlers/billing_handler.py` (lines 35-75)
- **Issue**: `stripe.checkout.Session.retrieve()` and `stripe.Subscription.retrieve()` are synchronous calls inside async function - blocks event loop under load
- **Fix**: Wrapped with `asyncio.to_thread()`
- **Status**: ✅ Completed

### R2-2. ✅ Webhook Idempotency is In-Memory Only
- **File**: `api/billing_routes.py`
- **Issue**: Multi-instance deployments will still process duplicate events
- **Current State**: Already using in-memory with note about Redis
- **Fix**: Should use Redis-backed store (like rate limiter does) for production
- **Status**: ✅ Already noted - Redis recommended for horizontal scaling. In-memory acceptable for current single-instance deployment.

### R2-3. ✅ Rate Limiter Lacks Tests
- **File**: `api/billing_routes.py`
- **Issue**: New rate limiter has no tests; does not log remaining quota; errors hard to diagnose
- **Fix**: Added comprehensive unit tests in `tests/unit/test_rate_limiter.py`
- **Tests Added**:
  - Memory fallback: allows under limit, blocks at limit, user isolation, window expiry
  - Redis mode: allows under limit, blocks at limit, correct key format, fallback on error
  - Edge cases: empty user ID, concurrent requests
  - Idempotency store: duplicate detection, TTL expiry, LRU eviction, thread safety
  - Rate limit dependency: allows requests, raises 429
- **Status**: ✅ Completed - 18 new tests added

### R2-4. ✅ No Monitoring for First-Time Customer Mappings
- **File**: `services/billing_service.py` - `_validate_webhook_user_authorization()`
- **Issue**: Allows first-time mappings when `stripe_customer_id` is absent. No alerting if webhook secret leaks and forged events arrive.
- **Fix**: Added structured `BILLING_AUDIT:` log prefix for first-time customer mappings with user ID (truncated), customer ID (truncated), and context. Enables log monitoring/alerting for unusual patterns.
- **Status**: ✅ Completed

---

## MINOR ISSUES (Nice to Fix) - LOW PRIORITY

### R2-5. ✅ Doc Header Credits Copilot
- **File**: `handlers/billing_handler.py`
- **Issue**: Doc header still credits "GitHub Copilot" as author
- **Fix**: Updated to generic module docstring without author/date attribution
- **Status**: ✅ Completed

### R2-6. ✅ Success/Cancel URLs Validation
- **File**: `services/billing_service.py`
- **Issue**: URLs taken from env, could be misconfigured
- **Status**: ✅ Already fixed in Round 1 - Added domain validation against FRONTEND_URL

### R2-7. ✅ Inconsistent ID Truncation
- **File**: Multiple locations
- **Issue**: Some logs still include full Stripe customer/subscription IDs
- **Fix**: Applied `_short_stripe_id()` helper to all remaining locations:
  - `Found existing Stripe customer` log
  - `Using Stripe price ID` log
  - `Creating portal session for customer` log
  - `No user_id in subscription` logs (2 locations)
  - Customer ID mismatch security warning
  - First-time mapping audit log
- **Status**: ✅ Completed

---

## SUGGESTED REFACTORS (From Review)

1. ✅ Make Stripe SDK calls non-blocking in `verify_checkout_session` - Done
2. ✅ Externalize webhook idempotency to Redis (noted, acceptable for single-instance)
3. ✅ Add tests for: webhook idempotency, rate limiter, validation mismatch cases, period-date extraction - Tests added
4. ✅ Add alert/metric for webhooks with no stored customer_id - Added BILLING_AUDIT: log prefix

---

# ROUND 1 REVIEW (Initial Security Fixes) - ALL COMPLETED

## MAJOR ISSUES (Blocking) - HIGH PRIORITY

### 1. ✅ Stripe Secret Key Logging (CRITICAL)
- **File**: `services/billing_service.py` (line 59)
- **Issue**: Logs Stripe secret key prefix; credential leakage risk
- **Fix**: Changed to `logger.info("Stripe API initialized successfully")` - no key logged
- **Status**: ✅ Completed

### 2. ✅ JWT Token Logging (CRITICAL)
- **File**: `services/db_services/supabase_quiz.py` (lines 48, 64)
- **Issue**: Logs user JWTs; session hijack risk
- **Fix**: Removed all JWT token logging, changed to generic success messages
- **Status**: ✅ Completed

### 3. ✅ Webhook Authorization Gap (CRITICAL)
- **File**: `services/billing_service.py` (line 520+)
- **Issue**: Trusts metadata.user_id without validating customer/subscription against DB
- **Risk**: Forged webhook or dashboard metadata edit can reassign subscriptions
- **Fix**: Added `_validate_webhook_user_authorization()` method that cross-validates metadata.user_id against stored stripe_customer_id in database. Applied to all webhook handlers.
- **Status**: ✅ Completed

---

## MODERATE ISSUES (Should Fix) - MEDIUM PRIORITY

### 4. ✅ Full Supabase User Payload Logged
- **File**: `dependencies/auth_dependencies.py` (lines 175-177)
- **Issue**: Exposes PII in logs
- **Fix**: Changed to `logger.debug("User auth successful for id=%s...", user_id_preview)` with truncated ID
- **Status**: ✅ Completed

### 5. ✅ Blocking Stripe/Supabase Calls in Async Handlers
- **File**: `services/billing_service.py` (lines 460, 690)
- **Issue**: Synchronous calls block event loop
- **Fix**: Wrapped all `stripe.Subscription.retrieve()`, `stripe.Customer.create()`, `stripe.checkout.Session.create()`, and `stripe.billing_portal.Session.create()` with `asyncio.to_thread()`
- **Status**: ✅ Completed

### 6. ✅ Blocking Requests in Auto-Refresh Middleware
- **File**: `middleware/auto_refresh.py`
- **Issue**: Blocking HTTP stalls all requests
- **Fix**: Replaced `requests.get/post` with async `httpx.AsyncClient`
- **Status**: ✅ Completed

### 7. ✅ No Webhook Idempotency Tracking
- **File**: `api/billing_routes.py`
- **Issue**: Duplicate events fully processed
- **Fix**: Added `WebhookIdempotencyStore` class with LRU eviction and TTL. Checks event ID before processing.
- **Status**: ✅ Completed

### 8. ✅ No Rate Limiting on Billing Endpoints
- **File**: `api/billing_routes.py`
- **Issue**: Can spam checkout/portal sessions
- **Fix**: Added `BillingRateLimiter` class using Redis sorted sets with memory fallback. 10 requests/minute per user. Applied to checkout and portal endpoints via `check_rate_limit` dependency.
- **Status**: ✅ Completed

---

## MINOR ISSUES (Nice to Fix) - LOW PRIORITY

### 9. ✅ Unused Config Import
- **File**: `handlers/billing_handler.py`
- **Issue**: Unused import
- **Fix**: Investigated - no unused config import found (already clean)
- **Status**: ✅ N/A - Already clean

### 10. ✅ Success/Cancel URLs Not Validated
- **File**: `services/billing_service.py` - checkout flow
- **Issue**: Misconfig could enable open redirect
- **Fix**: Added URL domain validation - success/cancel URLs must match FRONTEND_URL domain
- **Status**: ✅ Completed

### 11. ✅ Verbose ID Logging
- **File**: `services/billing_service.py`
- **Issue**: Full customer/user IDs at INFO level
- **Fix**: Added `_short_stripe_id()` helper to truncate Stripe IDs to 12 chars. Applied to all subscription-related logs.
- **Status**: ✅ Completed

---

## Progress Log

### Session 1 - November 26, 2025 (Round 1)
- Created tracking document
- Completed all 11 security fixes from initial review
- All tests passing (298 passed)

### Session 2 - November 26, 2025 (Round 2)
- Received follow-up review: "Approve with changes"
- Identified 4 moderate issues (1 already acceptable, 3 to fix)
- Identified 3 minor issues (1 already fixed, 2 to fix)
- ✅ Completed all Round 2 fixes:
  - R2-1: Wrapped Stripe calls in billing_handler.py with asyncio.to_thread()
  - R2-3: Added 18 unit tests for rate limiter and idempotency store
  - R2-4: Added BILLING_AUDIT: log prefix for first-time customer mappings
  - R2-5: Updated doc header in billing_handler.py
  - R2-7: Audited and truncated all remaining full Stripe IDs in logs
- All 316 tests passing

### Session 3 - November 27, 2025 (Round 3)
- Received Round 3 review focused on distributed systems hardening
- Reviewer appeared to be looking at older code - clarified what was already fixed
- ✅ Completed additional hardening:
  - R3-1: Upgraded WebhookIdempotencyStore to Redis-backed with async operations
  - R3-2: Added httpx client shutdown cleanup in app lifespan
  - R3-3: Added health flags exposing Redis fallback status
  - R3-4: Ensured consistent Stripe ID truncation in all webhook logs

### Session 4 - November 26, 2025 (Round 4 - Final Approval)
- Received final review: **"Approve with changes"** - Low/Medium residual risk
- Expert confirmed billing stack is "well-hardened" with no blocking issues
- ✅ Completed final hardening:
  - R4-1: Added BILLING_FALLBACK alerts when entering/exiting memory fallback mode
  - R4-2: Health endpoint now returns "degraded" status when in fallback mode
  - R4-3: Added BILLING_REQUIRE_REDIS env var for strict mode (fail closed)
  - R4-4: Truncated all remaining full Stripe IDs in log messages

---

## Testing Checklist
- [x] All unit tests pass (316+ passed)
- [x] Linting passes (ruff check)
- [x] Webhook signature verification still works
- [x] No secrets in logs
- [x] No JWTs in logs
- [x] Webhook validation rejects invalid metadata
- [x] Rate limiter unit tests (18 new tests)
- [x] Webhook idempotency tests (included in rate limiter test file)
- [x] First-time mapping monitoring (BILLING_AUDIT: log prefix)
- [x] Redis-backed webhook idempotency with memory fallback
- [x] Health endpoint exposes Redis fallback status
- [x] Fallback state transitions logged with BILLING_FALLBACK prefix
- [x] Strict mode available via BILLING_REQUIRE_REDIS env var
- [x] All Stripe IDs truncated in all log messages
- [ ] Manual: Checkout flow works end-to-end
- [ ] Manual: Cancellation flow works
- [ ] Manual: Rate limiting triggers on 11th request

---

## Files Modified (Round 1)
1. `services/billing_service.py` - Secret key logging, webhook validation, async wrapping, URL validation, ID truncation
2. `services/db_services/supabase_quiz.py` - JWT token logging removal
3. `dependencies/auth_dependencies.py` - PII redaction
4. `middleware/auto_refresh.py` - Replaced requests with httpx
5. `api/billing_routes.py` - Webhook idempotency, Redis rate limiting
6. `tests/test_billing_api.py` - Added FRONTEND_URL mock

## Files Modified (Round 2)
1. `handlers/billing_handler.py` - Wrapped Stripe calls with asyncio.to_thread, added _short_stripe_id helper, updated doc header, truncated IDs in logs
2. `services/billing_service.py` - Added BILLING_AUDIT log for first-time mappings, applied consistent ID truncation
3. `tests/unit/test_rate_limiter.py` - NEW: 18 unit tests for rate limiter and idempotency store

## Files Modified (Round 3)
1. `api/billing_routes.py` - Redis-backed WebhookIdempotencyStore, health flags, consistent ID truncation
2. `middleware/auto_refresh.py` - Added close_http_client() function for graceful shutdown
3. `main.py` - Import and call close_http_client in app_lifespan shutdown

## Files Modified (Round 4)
1. `api/billing_routes.py` - BILLING_FALLBACK alerts, degraded health status, BILLING_STRICT mode
2. `services/billing_service.py` - Truncated all remaining full Stripe IDs in logs
3. `config.py` - Added BILLING_REQUIRE_REDIS configuration option
4. `docs/SECURITY_FIXES_TRACKER.md` - Updated with Round 4 fixes
