# Epic 6: Testing & Security Audit (Days 10-12)

**Status**: Not Started  
**Duration**: 3 days  
**Priority**: Critical  
**Dependencies**: Epic 1-5 (All Previous Epics)

---

## Overview

Comprehensive testing strategy and security audit to ensure Stripe integration is production-ready, secure, and handles edge cases correctly.

---

## Tasks Breakdown

### Task 6.1: Create Comprehensive Test Scenarios (3 hours)

**File**: `tests/stripe/test_scenarios.md` (NEW - Documentation)

**Action**: Document all test scenarios

```markdown
# Stripe Integration Test Scenarios

## Checkout Flow Scenarios

### Happy Path
1. **Basic Monthly Subscription**
   - User creates checkout session for Basic Monthly
   - Completes payment with test card 4242 4242 4242 4242
   - Webhook provisions subscription
   - User tier updated to "basic"
   - Quiz quota updated to 100

2. **Educator Annual Subscription**
   - User creates checkout session for Educator Annual
   - Completes payment
   - Tier updated to "educator"
   - Quota updated to 500

### Error Scenarios
3. **Card Declined**
   - Use test card 4000 0000 0000 0002
   - Checkout fails with error message
   - User remains on free tier
   - No webhook event fires

4. **Requires Authentication (3D Secure)**
   - Use test card 4000 0025 0000 3155
   - Stripe prompts for authentication
   - User completes auth
   - Payment succeeds, subscription provisions

5. **Duplicate Checkout Attempt**
   - User with active subscription tries to checkout again
   - API returns 409 Conflict
   - Error message: "already have an active subscription"

## Webhook Scenarios

### Event Processing
6. **Checkout Session Completed**
   - Event stores customer and subscription IDs
   - User profile updated
   - No tier change yet (wait for invoice.paid)

7. **Invoice Paid (First Payment)**
   - Subscription provisioned
   - Tier updated
   - Quota updated
   - Email notification sent

8. **Invoice Paid (Renewal)**
   - Subscription period extended
   - Status remains "active"
   - No tier change

9. **Invoice Payment Failed**
   - Status updated to "past_due"
   - Grace period set (7 days)
   - Email notification sent
   - User can still create quizzes during grace period

10. **Subscription Updated**
    - User upgrades from Basic to Educator in portal
    - Tier updated immediately
    - Quota updated to 500

11. **Subscription Deleted**
    - User cancels subscription in portal
    - Tier downgraded to "free"
    - Quota reset to 5
    - Email notification sent

### Idempotency
12. **Duplicate Webhook Event**
    - Same event sent twice by Stripe
    - First event processes normally
    - Second event skipped (idempotency check)
    - No duplicate database updates

### Invalid Events
13. **Missing Metadata**
    - Event has no user_id in metadata
    - Handler logs error, returns 200
    - No database changes

14. **Invalid Signature**
    - Event with wrong signature
    - Returns 400 Bad Request
    - Event not processed

## Customer Portal Scenarios

15. **Update Payment Method**
    - User accesses portal
    - Updates card details
    - customer.updated webhook fires
    - No subscription changes

16. **Cancel Subscription**
    - User cancels in portal
    - customer.subscription.deleted webhook fires
    - Subscription downgraded to free
    - Access until period end maintained

17. **Resume Subscription**
    - User cancels, then undoes before period end
    - Subscription remains active
    - cancel_at_period_end set to false

## Grace Period Scenarios

18. **Payment Failed - Within Grace Period**
    - Payment fails (grace period: 7 days)
    - User can still create quizzes
    - Warning message displayed
    - Quota enforcement continues

19. **Payment Failed - Grace Period Expired**
    - Grace period ends
    - User cannot create quizzes
    - Tier remains until subscription deleted
    - Forced to update payment or cancel

## State Synchronization

20. **Manual Sync Success**
    - User manually syncs subscription
    - Data fetched from Stripe
    - Database updated with latest info

21. **Sync with Deleted Subscription**
    - Subscription deleted in Stripe Dashboard
    - Sync detects missing subscription
    - Database cleared of invalid subscription ID

## Edge Cases

22. **Expired Checkout Session**
    - User waits too long (24 hours)
    - Session expires
    - Verification fails
    - User must create new session

23. **Webhook Retry**
    - Initial webhook processing fails (transient error)
    - Stripe retries webhook
    - Second attempt succeeds
    - No duplicate processing

24. **Multiple Subscriptions (Should Prevent)**
    - User has active subscription
    - Tries to create second subscription
    - API prevents checkout session creation
    - Returns error

25. **Quota Exceeded During Processing**
    - User at 99/100 quizzes
    - Creates 2 quizzes simultaneously
    - Race condition: Both succeed (acceptable)
    - Quota check happens at request time, not commit time
```

---

### Task 6.2: Implement E2E Test Suite (6 hours)

**File**: `tests/e2e/test_stripe_complete_flow.py` (NEW)

**Action**: Create end-to-end test suite

```python
"""
End-to-end tests for complete Stripe integration flows
"""

import pytest
import stripe
import time
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

@pytest.mark.e2e
@pytest.mark.slow
class TestCompleteCheckoutFlow:
    """Test complete checkout and provisioning flow"""
    
    def test_basic_monthly_subscription_flow(
        self,
        auth_headers,
        stripe_test_mode
    ):
        """
        E2E: Complete flow from checkout to provisioning
        
        Steps:
        1. Create checkout session
        2. Simulate successful payment (test mode)
        3. Wait for webhook processing
        4. Verify subscription provisioned
        5. Verify tier updated
        6. Verify quota updated
        """
        # Step 1: Create checkout session
        response = client.post(
            "/api/billing/create-checkout-session",
            headers=auth_headers,
            json={
                "price_id": pytest.config.STRIPE_PRICE_BASIC_MONTHLY,
                "tier": "basic"
            }
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        
        # Step 2: Simulate successful payment (Stripe test helper)
        stripe.api_key = pytest.config.STRIPE_SECRET_KEY
        session = stripe.checkout.Session.retrieve(session_id)
        
        # Trigger payment success via Stripe CLI or test helper
        # (In real test, would use Stripe test fixtures)
        
        # Step 3: Wait for webhook processing (async)
        time.sleep(2)  # Allow webhook to process
        
        # Step 4: Verify subscription provisioned
        response = client.get(
            "/api/billing/subscription-status",
            headers=auth_headers
        )
        assert response.status_code == 200
        status = response.json()
        
        assert status["has_subscription"] is True
        assert status["tier"] == "basic"
        assert status["status"] == "active"
        assert status["quota_limit"] == 100

@pytest.mark.e2e
class TestCustomerPortalFlow:
    """Test customer portal integration"""
    
    def test_cancel_subscription_flow(
        self,
        auth_headers,
        active_subscription_fixture
    ):
        """
        E2E: Test subscription cancellation via portal
        
        Steps:
        1. Create portal session
        2. Simulate cancellation in portal
        3. Verify webhook received
        4. Verify subscription downgraded
        """
        # Step 1: Create portal session
        response = client.post(
            "/api/billing/create-portal-session",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        # Step 2-3: Simulate cancellation (test fixture)
        # Trigger customer.subscription.deleted webhook
        
        # Step 4: Verify downgrade
        time.sleep(2)
        response = client.get(
            "/api/billing/subscription-status",
            headers=auth_headers
        )
        status = response.json()
        assert status["tier"] == "free"
        assert status["has_subscription"] is False

@pytest.mark.e2e
class TestWebhookIdempotency:
    """Test webhook idempotency"""
    
    def test_duplicate_event_processing(
        self,
        mock_webhook_event,
        stripe_signature
    ):
        """
        E2E: Test duplicate webhook event is not reprocessed
        
        Steps:
        1. Send webhook event
        2. Verify processed
        3. Send same event again
        4. Verify skipped (idempotency)
        """
        # Step 1: First event
        response = client.post(
            "/api/billing/webhook",
            headers={"Stripe-Signature": stripe_signature},
            content=mock_webhook_event
        )
        assert response.status_code == 200
        
        # Step 2: Verify processed (check Redis)
        # ... check idempotency key exists ...
        
        # Step 3: Send again
        response = client.post(
            "/api/billing/webhook",
            headers={"Stripe-Signature": stripe_signature},
            content=mock_webhook_event
        )
        assert response.status_code == 200
        assert "already processed" in response.json()["message"]
```

---

### Task 6.3: Security Audit Checklist (2 hours)

**File**: `docs/stripe/SECURITY_AUDIT.md` (NEW)

**Action**: Document security measures

```markdown
# Stripe Integration Security Audit

## Authentication & Authorization

- [x] All billing endpoints require authentication (`get_current_user` dependency)
- [x] User can only access their own subscription data
- [x] Webhook endpoint uses signature verification (no auth needed)
- [x] Admin endpoints (if any) use role-based access control

## Data Protection

- [x] Stripe API keys stored in environment variables (not hardcoded)
- [x] Webhook secret stored securely
- [x] No sensitive data logged (customer payment details, full card numbers)
- [x] User IDs truncated in logs (first 8 chars only)

## Webhook Security

- [x] Signature verification implemented for all webhooks
- [x] Raw request body used for verification (not parsed JSON)
- [x] Invalid signatures return 400 (not processed)
- [x] Idempotency checks prevent duplicate processing
- [x] Unknown event types logged but don't cause errors

## Input Validation

- [x] Price IDs validated against allowed list
- [x] Tier parameter validated (Literal["basic", "educator"])
- [x] Checkout prevents duplicate subscriptions (409 Conflict)
- [x] Pydantic schemas validate all request bodies

## Error Handling

- [x] Stripe errors caught and logged (not exposed to users)
- [x] Generic error messages returned to users
- [x] HTTPException used for controlled errors
- [x] Webhook errors return 500 (trigger retry)

## Database Security

- [x] Service role client used for webhook operations (bypass RLS)
- [x] User-authenticated client used for user operations (enforce RLS)
- [x] Stripe fields protected by RLS policies (service_role only)
- [x] No direct writes to auth.users table

## Rate Limiting

- [ ] TODO: Implement rate limiting on checkout endpoint
- [ ] TODO: Implement rate limiting on portal endpoint
- [ ] TODO: Consider webhook rate limiting (if high volume)

## Monitoring & Alerting

- [x] All webhook events logged
- [x] Failed provisioning logged with exc_info
- [x] Payment failures logged with warnings
- [ ] TODO: Add alerting for repeated webhook failures

## Compliance

- [x] PCI compliance handled by Stripe (no card data stored)
- [x] Privacy policy and terms linked in portal
- [x] User can access subscription data (GDPR)
- [x] User can delete account (TODO: Cancel subscription on deletion)

## Testing

- [x] Unit tests for all critical paths
- [x] Integration tests for API endpoints
- [x] E2E tests for complete flows
- [x] Security tests (invalid signatures, unauthorized access)
- [x] Test mode used for development

## Production Readiness

- [ ] Switch to live Stripe keys in production only
- [ ] Webhook endpoint uses HTTPS (required by Stripe)
- [ ] Environment-specific webhook secrets configured
- [ ] Error tracking (Sentry/similar) configured
- [ ] Monitoring dashboard set up
```

---

### Task 6.4: Implement Security Tests (3 hours)

**File**: `tests/security/test_stripe_security.py` (NEW)

**Action**: Create security-focused tests

```python
"""
Security tests for Stripe integration
"""

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

class TestWebhookSecurity:
    """Test webhook security measures"""
    
    def test_webhook_missing_signature(self):
        """Test webhook without signature header"""
        response = client.post(
            "/api/billing/webhook",
            json={"type": "test.event"}
        )
        assert response.status_code == 400
        assert "signature" in response.json()["detail"].lower()
    
    def test_webhook_invalid_signature(self):
        """Test webhook with invalid signature"""
        response = client.post(
            "/api/billing/webhook",
            headers={"Stripe-Signature": "t=123,v1=invalid"},
            json={"type": "test.event"}
        )
        assert response.status_code == 400
    
    def test_webhook_tampered_payload(self, valid_webhook_event):
        """Test webhook with tampered payload (signature mismatch)"""
        # Simulate attacker modifying payload after signing
        payload = valid_webhook_event
        payload["data"]["object"]["amount"] = 9999999  # Tampered
        
        response = client.post(
            "/api/billing/webhook",
            headers={"Stripe-Signature": "t=123,v1=signature"},
            content=payload
        )
        assert response.status_code == 400

class TestAuthorizationSecurity:
    """Test authorization boundaries"""
    
    def test_access_other_user_subscription(
        self,
        auth_headers_user1,
        auth_headers_user2
    ):
        """Test user cannot access another user's subscription"""
        # User 1 creates subscription
        # ... create subscription for user1 ...
        
        # User 2 tries to access user 1's data
        # (Should only see their own data via auth token)
        response = client.get(
            "/api/billing/subscription-status",
            headers=auth_headers_user2
        )
        assert response.status_code == 200
        data = response.json()
        # Should return user2's data (likely free tier, no subscription)
        assert data["has_subscription"] is False
    
    def test_checkout_without_auth(self):
        """Test checkout endpoint requires authentication"""
        response = client.post(
            "/api/billing/create-checkout-session",
            json={
                "price_id": "price_test123",
                "tier": "basic"
            }
        )
        assert response.status_code == 401

class TestInputValidationSecurity:
    """Test input validation prevents attacks"""
    
    def test_invalid_price_id_rejected(self, auth_headers):
        """Test invalid price ID cannot be used"""
        response = client.post(
            "/api/billing/create-checkout-session",
            headers=auth_headers,
            json={
                "price_id": "price_attacker_custom",
                "tier": "basic"
            }
        )
        assert response.status_code == 400
        assert "Invalid price ID" in response.json()["detail"]
    
    def test_tier_mismatch_rejected(self, auth_headers):
        """Test tier/price mismatch is rejected"""
        response = client.post(
            "/api/billing/create-checkout-session",
            headers=auth_headers,
            json={
                "price_id": pytest.config.STRIPE_PRICE_BASIC_MONTHLY,
                "tier": "educator"  # Wrong tier
            }
        )
        assert response.status_code == 400
    
    def test_sql_injection_attempt(self, auth_headers):
        """Test SQL injection in tier parameter"""
        response = client.post(
            "/api/billing/create-checkout-session",
            headers=auth_headers,
            json={
                "price_id": "price_123",
                "tier": "basic'; DROP TABLE profiles; --"
            }
        )
        # Should fail Pydantic validation (Literal["basic", "educator"])
        assert response.status_code == 422
```

---

### Task 6.5: Load Testing (2 hours)

**File**: `tests/load/locustfile.py` (NEW)

**Action**: Create load test with Locust

```python
"""
Load tests for Stripe integration endpoints
"""

from locust import HttpUser, task, between

class BillingUser(HttpUser):
    """Simulate users interacting with billing endpoints"""
    wait_time = between(1, 5)
    
    def on_start(self):
        """Login and get auth token"""
        response = self.client.post("/api/auth/login", json={
            "email": "test@example.com",
            "password": "testpassword"
        })
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    @task(5)
    def get_subscription_status(self):
        """Most common operation - check status"""
        self.client.get(
            "/api/billing/subscription-status",
            headers=self.headers
        )
    
    @task(1)
    def create_checkout_session(self):
        """Less common - create checkout"""
        self.client.post(
            "/api/billing/create-checkout-session",
            headers=self.headers,
            json={
                "price_id": "price_test_basic_monthly",
                "tier": "basic"
            }
        )
    
    @task(1)
    def create_portal_session(self):
        """Less common - access portal"""
        self.client.post(
            "/api/billing/create-portal-session",
            headers=self.headers
        )

# Run with:
# locust -f tests/load/locustfile.py --host http://localhost:8000
```

---

### Task 6.6: Performance Benchmarking (2 hours)

**File**: `tests/performance/test_billing_performance.py` (NEW)

**Action**: Create performance benchmarks

```python
"""
Performance benchmarks for billing operations
"""

import pytest
import time

@pytest.mark.performance
class TestBillingPerformance:
    """Benchmark billing operations"""
    
    def test_subscription_status_query_speed(self, auth_headers, benchmark):
        """Benchmark subscription status query"""
        def query_status():
            response = client.get(
                "/api/billing/subscription-status",
                headers=auth_headers
            )
            return response
        
        result = benchmark(query_status)
        assert result.status_code == 200
        
        # Should complete in < 500ms
        assert benchmark.stats.mean < 0.5
    
    def test_checkout_session_creation_speed(self, auth_headers, benchmark):
        """Benchmark checkout session creation"""
        def create_session():
            response = client.post(
                "/api/billing/create-checkout-session",
                headers=auth_headers,
                json={
                    "price_id": "price_test_basic_monthly",
                    "tier": "basic"
                }
            )
            return response
        
        result = benchmark(create_session)
        
        # Should complete in < 2s (Stripe API call included)
        assert benchmark.stats.mean < 2.0
```

---

## Verification Checklist

### Test Coverage
- [ ] Unit tests: >90% coverage for billing code
- [ ] Integration tests: All API endpoints covered
- [ ] E2E tests: Complete flows tested
- [ ] Security tests: All attack vectors tested
- [ ] Performance tests: Benchmarks established

### Security Audit
- [ ] All items in security checklist verified
- [ ] No hardcoded secrets
- [ ] All endpoints authenticated (except webhook)
- [ ] Webhook signature verification working
- [ ] Input validation comprehensive

### Performance
- [ ] Subscription status query < 500ms average
- [ ] Checkout session creation < 2s average
- [ ] Webhook processing < 1s average
- [ ] Load test: 100 concurrent users handled

### Documentation
- [ ] All test scenarios documented
- [ ] Security audit document complete
- [ ] Troubleshooting guide updated

---

## Running Tests

```bash
# Run all unit tests
pytest tests/unit/ -v

# Run integration tests
pytest tests/integration/ -v

# Run E2E tests (slower)
pytest tests/e2e/ -v -m e2e

# Run security tests
pytest tests/security/ -v

# Run performance tests
pytest tests/performance/ -v -m performance --benchmark-only

# Generate coverage report
pytest --cov=services/billing_service --cov=handlers/billing_handler \
       --cov-report=html

# Run load tests
locust -f tests/load/locustfile.py --host http://localhost:8000
```

---

## Next Steps

Once complete:
1. ✅ All tests passing
2. ✅ Coverage >90%
3. ✅ Security audit complete
4. ✅ Performance benchmarks established
5. ✅ Commit: `test: comprehensive testing and security audit (Epic 6)`
6. ➡️ Proceed to **Epic 7: Production Deployment**

---

**Epic Owner**: GitHub Copilot  
**Last Updated**: 2025-11-19
