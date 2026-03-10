# Epic 7: Production Deployment & Monitoring (Days 13-14)

**Status**: Not Started  
**Duration**: 2 days  
**Priority**: Critical  
**Dependencies**: All previous epics (1-6)

---

## Overview

Prepare and execute production deployment of Stripe integration with monitoring, alerting, and operational procedures.

---

## Tasks Breakdown

### Task 7.1: Production Environment Setup (2 hours)

**Platform**: Stripe Dashboard + Railway

**Actions**:

#### 1. Switch to Live Mode in Stripe Dashboard

1. **Navigate to Dashboard** (https://dashboard.stripe.com)
2. **Toggle to Live Mode** (top-right switch)
3. **Get Live API Keys**:
   - Go to: Developers → API keys
   - Copy **Publishable key** (starts with `pk_live_`)
   - Reveal and copy **Secret key** (starts with `sk_live_`)
   - Store securely (never commit to git)

#### 2. Create Live Products

1. **Go to Products** → Add Product
2. **Create Quizify Basic (Live)**:
   - Name: `Quizify Basic`
   - Description: `100 quizzes per month - Perfect for individual users`
   - **Monthly Price**: $9.99 USD → Copy price ID
   - **Annual Price**: $99.99 USD → Copy price ID

3. **Create Quizify Educator (Live)**:
   - Name: `Quizify Educator`
   - Description: `500 quizzes per month - Designed for teachers and trainers`
   - **Monthly Price**: $19.99 USD → Copy price ID
   - **Annual Price**: $199.99 USD → Copy price ID

#### 3. Configure Live Webhook

1. **Go to Webhooks** (Developers → Webhooks)
2. **Add Endpoint**:
   - **Endpoint URL**: `https://api.quizify.ca/api/billing/webhook`
   - **Description**: `Quizify Production Webhook`
   - **Events to send**:
     - `checkout.session.completed`
     - `invoice.paid`
     - `invoice.payment_failed`
     - `customer.subscription.updated`
     - `customer.subscription.deleted`
     - `customer.updated`
     - `customer.subscription.paused`
     - `customer.subscription.resumed`
   - **API version**: Latest (e.g., 2024-10-28)
3. **Save and Copy Webhook Secret** (starts with `whsec_`)

#### 4. Configure Customer Portal (Live)

1. **Go to Customer Portal** (Settings → Billing → Customer portal)
2. **Activate Live Link**
3. **Configure Settings**:
   - Business name: `Quizify`
   - Support email: `support@quizify.ca`
   - Privacy policy: `https://quizify.ca/privacy`
   - Terms of service: `https://quizify.ca/terms`
   - Features: Enable all (invoice history, update payment, cancel, update plan)
   - Branding: Upload logo, set colors

#### 5. Set Production Environment Variables (Railway)

```bash
# In Railway dashboard for production project:

# Stripe Live Keys
STRIPE_SECRET_KEY=sk_live_YOUR_LIVE_SECRET_KEY
STRIPE_PUBLISHABLE_KEY=pk_live_YOUR_LIVE_PUBLISHABLE_KEY
STRIPE_WEBHOOK_SECRET=whsec_YOUR_LIVE_WEBHOOK_SECRET

# Stripe Live Price IDs
STRIPE_PRICE_BASIC_MONTHLY=price_live_YOUR_BASIC_MONTHLY_ID
STRIPE_PRICE_BASIC_ANNUAL=price_live_YOUR_BASIC_ANNUAL_ID
STRIPE_PRICE_EDUCATOR_MONTHLY=price_live_YOUR_EDUCATOR_MONTHLY_ID
STRIPE_PRICE_EDUCATOR_ANNUAL=price_live_YOUR_EDUCATOR_ANNUAL_ID

# Frontend URL (Production)
FRONTEND_URL=https://app.quizify.ca
```

---

### Task 7.2: Pre-Deployment Checklist (1 hour)

**File**: `docs/stripe/DEPLOYMENT_CHECKLIST.md` (NEW)

**Action**: Create deployment checklist

```markdown
# Stripe Integration - Production Deployment Checklist

## Pre-Deployment

### Code Readiness
- [ ] All tests passing (unit, integration, E2E, security)
- [ ] Code coverage >90%
- [ ] Security audit completed
- [ ] No hardcoded secrets or test keys
- [ ] Environment variables documented in .env.example
- [ ] Database migrations tested in staging
- [ ] Performance benchmarks met

### Stripe Configuration
- [ ] Live mode enabled in Stripe Dashboard
- [ ] Live API keys generated and stored securely
- [ ] Live products created with correct pricing
- [ ] Live webhook endpoint configured
- [ ] Webhook events selected (all 8 events)
- [ ] Webhook secret generated
- [ ] Customer Portal configured for live mode
- [ ] Tax settings configured (if applicable)

### Environment Variables
- [ ] Production environment variables set in Railway
- [ ] All 8 Stripe variables configured
- [ ] FRONTEND_URL points to production frontend
- [ ] BACKEND_CORS_ORIGIN includes production frontend
- [ ] Webhook secret matches Stripe Dashboard
- [ ] Price IDs match live products

### Database
- [ ] Migration 014 (Stripe integration) applied
- [ ] Migration 015 (user_tier_info view) applied
- [ ] RLS policies verified for Stripe fields
- [ ] Indexes created for performance
- [ ] Backup strategy in place

### Infrastructure
- [ ] Railway production deployment ready
- [ ] HTTPS enabled (required for webhooks)
- [ ] Domain configured (api.quizify.ca)
- [ ] SSL certificate valid
- [ ] Redis running and accessible

## Deployment Steps

### Step 1: Database Migration
- [ ] Run database migrations in production:
  ```bash
  psql -h <prod-supabase-host> -U postgres -d postgres
  \i migrations/014_add_stripe_integration.sql
  \i migrations/015_update_user_tier_info_with_stripe.sql
  ```
- [ ] Verify columns added:
  ```sql
  SELECT column_name FROM information_schema.columns 
  WHERE table_name = 'profiles' AND column_name LIKE 'stripe%';
  ```

### Step 2: Deploy Code
- [ ] Merge feature branch to `deploy/production`
- [ ] Push to GitHub: `git push origin deploy/production`
- [ ] Railway auto-deploys (or trigger manual deploy)
- [ ] Wait for deployment to complete
- [ ] Check deployment logs for errors

### Step 3: Verify Deployment
- [ ] Check health endpoint: `https://api.quizify.ca/health`
- [ ] Verify OpenAPI docs accessible: `https://api.quizify.ca/docs`
- [ ] Check billing endpoints exist in docs
- [ ] Test authentication still works

### Step 4: Test Stripe Integration
- [ ] Test checkout session creation (live mode)
- [ ] Complete test purchase with live card (refund after)
- [ ] Verify webhook received (check Stripe Dashboard logs)
- [ ] Verify subscription provisioned in database
- [ ] Test customer portal access
- [ ] Test subscription status query

## Post-Deployment

### Monitoring Setup
- [ ] Error tracking configured (Sentry/similar)
- [ ] Log aggregation enabled
- [ ] Stripe webhook monitoring dashboard
- [ ] Uptime monitoring for webhook endpoint
- [ ] Alert on repeated webhook failures
- [ ] Alert on Stripe API errors

### Documentation
- [ ] Update README with Stripe integration details
- [ ] Document operational procedures
- [ ] Share Stripe Dashboard access with team
- [ ] Document rollback procedure
- [ ] Update API documentation

### Communication
- [ ] Notify stakeholders of deployment
- [ ] Announce new billing feature to users
- [ ] Update pricing page on website
- [ ] Prepare customer support FAQs
- [ ] Train support team on billing issues

## Rollback Plan

If critical issues discovered:
- [ ] Disable webhook in Stripe Dashboard (temporarily)
- [ ] Revert code deployment to previous version
- [ ] Communicate status to users
- [ ] Investigate and fix issues
- [ ] Re-deploy when ready
- [ ] Re-enable webhook

## Success Criteria

- [ ] First successful live checkout completed
- [ ] Webhook events processing correctly
- [ ] No errors in logs for 24 hours
- [ ] Customer Portal working correctly
- [ ] Subscription state syncing correctly
- [ ] Performance meets benchmarks (<2s checkout, <500ms status)
```

---

### Task 7.3: Monitoring & Alerting Setup (3 hours)

**File**: `services/monitoring.py` (NEW)

**Action**: Add monitoring and alerting

```python
"""
Monitoring and alerting for Stripe integration
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime
from config import config
from services.logger import app_logger as logger

# ============================================================================
# Metrics Tracking
# ============================================================================

class StripeMetrics:
    """Track Stripe integration metrics"""
    
    # In-memory counters (consider using Prometheus/StatsD in production)
    checkout_sessions_created = 0
    webhooks_received = 0
    webhooks_processed = 0
    webhooks_failed = 0
    subscriptions_provisioned = 0
    payment_failures = 0
    
    @classmethod
    def increment_checkout_sessions(cls):
        cls.checkout_sessions_created += 1
        logger.info(f"Checkout sessions created: {cls.checkout_sessions_created}")
    
    @classmethod
    def increment_webhooks_received(cls, event_type: str):
        cls.webhooks_received += 1
        logger.info(
            f"Webhooks received: {cls.webhooks_received} (type={event_type})"
        )
    
    @classmethod
    def increment_webhooks_processed(cls, event_type: str):
        cls.webhooks_processed += 1
        logger.info(
            f"Webhooks processed: {cls.webhooks_processed} (type={event_type})"
        )
    
    @classmethod
    def increment_webhooks_failed(cls, event_type: str, error: str):
        cls.webhooks_failed += 1
        logger.error(
            f"Webhook processing failed: {cls.webhooks_failed} "
            f"(type={event_type}, error={error})"
        )
        # TODO: Send alert if failures > threshold
    
    @classmethod
    def increment_subscriptions_provisioned(cls, tier: str):
        cls.subscriptions_provisioned += 1
        logger.info(
            f"Subscriptions provisioned: {cls.subscriptions_provisioned} (tier={tier})"
        )
    
    @classmethod
    def increment_payment_failures(cls, user_id: str):
        cls.payment_failures += 1
        logger.warning(
            f"Payment failures: {cls.payment_failures} (user={user_id[:8]})"
        )
        # TODO: Send alert if failures spike
    
    @classmethod
    def get_metrics(cls) -> Dict[str, int]:
        """Get current metrics snapshot"""
        return {
            "checkout_sessions_created": cls.checkout_sessions_created,
            "webhooks_received": cls.webhooks_received,
            "webhooks_processed": cls.webhooks_processed,
            "webhooks_failed": cls.webhooks_failed,
            "subscriptions_provisioned": cls.subscriptions_provisioned,
            "payment_failures": cls.payment_failures,
            "webhook_success_rate": (
                cls.webhooks_processed / cls.webhooks_received * 100
                if cls.webhooks_received > 0 else 100
            )
        }

# ============================================================================
# Health Checks
# ============================================================================

async def check_stripe_health() -> Dict[str, Any]:
    """
    Check Stripe integration health
    
    Returns:
        Dict with health status
    """
    import stripe
    
    health = {
        "stripe_configured": bool(config.STRIPE_SECRET_KEY),
        "webhook_secret_configured": bool(config.STRIPE_WEBHOOK_SECRET),
        "price_ids_configured": len([
            p for p in config.get_stripe_price_ids().values() if p
        ]) == 4,
        "stripe_api_reachable": False
    }
    
    # Test Stripe API connectivity
    if config.STRIPE_SECRET_KEY:
        try:
            stripe.api_key = config.STRIPE_SECRET_KEY
            # Lightweight API call to test connectivity
            stripe.Balance.retrieve()
            health["stripe_api_reachable"] = True
        except Exception as e:
            logger.error(f"Stripe API health check failed: {e}")
            health["stripe_api_error"] = str(e)
    
    health["overall_healthy"] = all([
        health["stripe_configured"],
        health["webhook_secret_configured"],
        health["price_ids_configured"],
        health["stripe_api_reachable"]
    ])
    
    return health

# ============================================================================
# Alerting (Placeholder - integrate with your alerting service)
# ============================================================================

async def send_alert(
    severity: str,
    title: str,
    message: str,
    context: Optional[Dict] = None
):
    """
    Send alert to monitoring service
    
    Args:
        severity: "info", "warning", "error", "critical"
        title: Alert title
        message: Alert message
        context: Additional context data
    """
    # TODO: Integrate with Sentry, PagerDuty, Slack, etc.
    logger.log(
        logging.ERROR if severity in ["error", "critical"] else logging.WARNING,
        f"ALERT [{severity.upper()}]: {title} - {message}",
        extra={"context": context}
    )
    
    # Example: Send to Slack
    # if config.SLACK_WEBHOOK_URL:
    #     await send_slack_alert(severity, title, message, context)
```

---

### Task 7.4: Add Monitoring Endpoints (1 hour)

**File**: `api/billing_routes.py`

**Action**: Add monitoring endpoints

```python
from services.monitoring import StripeMetrics, check_stripe_health

@router.get(
    "/metrics",
    summary="Get Stripe Integration Metrics",
    tags=["billing", "monitoring"],
    include_in_schema=False  # Hide from public docs
)
async def get_billing_metrics():
    """
    Get Stripe integration metrics
    
    **Internal Use Only** (Consider adding admin authentication)
    
    Returns metrics for monitoring dashboard
    """
    return StripeMetrics.get_metrics()

@router.get(
    "/health",
    summary="Stripe Integration Health Check",
    tags=["billing", "monitoring"]
)
async def billing_health_check():
    """
    Check health of Stripe integration
    
    **Use for monitoring/alerting**
    
    Returns:
    - Configuration status
    - API connectivity
    - Overall health status
    """
    return await check_stripe_health()
```

---

### Task 7.5: Integrate Monitoring Calls (1 hour)

**File**: Update existing billing code

**Action**: Add monitoring calls throughout billing flow

```python
# In services/billing_service.py

async def create_checkout_session(...):
    # ... existing code ...
    
    # Track metric
    StripeMetrics.increment_checkout_sessions()
    
    # ... existing code ...

# In handlers/billing_handler.py

async def handle_invoice_paid(event):
    # ... existing code ...
    
    # Track provisioning
    StripeMetrics.increment_subscriptions_provisioned(tier)
    
    # ... existing code ...

async def handle_invoice_payment_failed(event):
    # ... existing code ...
    
    # Track failure
    StripeMetrics.increment_payment_failures(user_id)
    
    # Send alert for payment failure
    await send_alert(
        severity="warning",
        title="Subscription Payment Failed",
        message=f"Payment failed for user {user_id[:8]}",
        context={"user_id": user_id, "invoice_id": invoice.id}
    )
    
    # ... existing code ...

# In api/billing_routes.py (webhook endpoint)

@router.post("/webhook", ...)
async def stripe_webhook(request: Request):
    # ... signature verification ...
    
    # Track webhook received
    StripeMetrics.increment_webhooks_received(event.type)
    
    # ... idempotency check ...
    
    # Process event
    try:
        await handler(event)
        StripeMetrics.increment_webhooks_processed(event.type)
    except Exception as e:
        StripeMetrics.increment_webhooks_failed(event.type, str(e))
        raise
```

---

### Task 7.6: Operational Runbook (2 hours)

**File**: `docs/stripe/OPERATIONS_RUNBOOK.md` (NEW)

**Action**: Create operations guide

```markdown
# Stripe Integration - Operations Runbook

## Common Operations

### 1. Check Subscription Status for User

```bash
# Get user ID from email
psql -h <supabase-host> -U postgres -d postgres \
  -c "SELECT id, email, account_tier FROM profiles WHERE email = 'user@example.com';"

# Query subscription details
psql -h <supabase-host> -U postgres -d postgres \
  -c "SELECT * FROM user_tier_info WHERE email = 'user@example.com';"

# Check in Stripe Dashboard:
# 1. Go to Customers
# 2. Search by email
# 3. View subscription details
```

### 2. Manually Provision Subscription

```bash
# Use sync endpoint
curl -X POST https://api.quizify.ca/api/billing/sync-subscription \
  -H "Authorization: Bearer USER_ACCESS_TOKEN"

# Or directly in database (service role)
psql -h <supabase-host> -U postgres -d postgres \
  -c "UPDATE profiles SET account_tier = 'basic', 
      stripe_subscription_id = 'sub_xxx', 
      subscription_status = 'active', 
      subscription_current_period_end = '2025-12-19' 
      WHERE id = 'user_id';"
```

### 3. Refund Subscription

```bash
# Find payment intent in Stripe Dashboard:
# Customers → <customer> → Payments

# Refund via Stripe CLI:
stripe refunds create --payment-intent=pi_xxx

# Or via Dashboard:
# Click payment → Refund
```

### 4. Cancel Subscription Manually

```bash
# In Stripe Dashboard:
# Customers → <customer> → Subscriptions → Cancel subscription

# Webhook will automatically downgrade user to free tier

# Or via CLI:
stripe subscriptions cancel sub_xxx
```

### 5. Check Webhook Logs

```bash
# In Stripe Dashboard:
# Developers → Webhooks → <webhook endpoint> → Logs

# Check Railway logs:
railway logs --filter "webhook"

# Check for failed webhooks:
railway logs --filter "webhook.*failed"
```

## Troubleshooting

### Issue: Webhook Not Processing

**Symptoms**: 
- Subscription not provisioned after payment
- User still on free tier after checkout

**Diagnosis**:
1. Check Stripe Dashboard → Webhooks → Logs
2. Look for failed deliveries
3. Check Railway logs for errors

**Solutions**:
- Verify webhook endpoint is accessible (HTTPS required)
- Check webhook secret matches environment variable
- Manually trigger webhook re-delivery in Dashboard
- Use sync endpoint to manually sync subscription

### Issue: Payment Failed, User Downgraded Immediately

**Symptoms**:
- User reports lost access after payment failure
- Subscription status shows "canceled" instead of "past_due"

**Diagnosis**:
1. Check `subscription_status` in database
2. Check `subscription_grace_period_end`
3. Review webhook logs for `invoice.payment_failed` event

**Solutions**:
- Verify grace period is set (7 days)
- Check webhook handler for `handle_failed_payment` is working
- Manually set grace period if needed:
  ```sql
  UPDATE profiles SET 
    subscription_status = 'past_due',
    subscription_grace_period_end = NOW() + INTERVAL '7 days'
  WHERE id = 'user_id';
  ```

### Issue: Checkout Session Expired

**Symptoms**:
- User reports checkout link doesn't work
- Error: "Session expired"

**Diagnosis**:
- Checkout sessions expire after 24 hours

**Solutions**:
- Have user create new checkout session
- Sessions are single-use and time-limited by design

### Issue: Duplicate Subscription

**Symptoms**:
- User charged twice
- Multiple active subscriptions in Stripe

**Diagnosis**:
1. Check Stripe Dashboard → Customer → Subscriptions
2. Verify database has only one `stripe_subscription_id`

**Solutions**:
- Cancel duplicate subscription in Stripe Dashboard
- Refund duplicate payment
- API should prevent this (409 Conflict), investigate if occurred

## Monitoring

### Key Metrics to Watch

1. **Webhook Success Rate**: Should be >99%
2. **Checkout Conversion**: Track sessions created vs completed
3. **Payment Failure Rate**: Normal: 5-10%, alert if >15%
4. **Provisioning Latency**: Should be <5 seconds from payment to provisioning
5. **API Response Times**: 
   - Checkout: <2s
   - Status: <500ms
   - Portal: <1s

### Alerts to Configure

- [ ] Webhook failure rate >5% in 1 hour
- [ ] Payment failure spike (>20% in 1 hour)
- [ ] Stripe API errors (any 5xx)
- [ ] Provisioning failures (webhook processed but tier not updated)
- [ ] Checkout session creation failures

### Health Check URLs

```bash
# Overall API health
curl https://api.quizify.ca/health

# Stripe integration health
curl https://api.quizify.ca/api/billing/health

# Metrics
curl https://api.quizify.ca/api/billing/metrics
```

## Emergency Contacts

- **Stripe Support**: https://support.stripe.com
- **Stripe Dashboard**: https://dashboard.stripe.com
- **Railway Dashboard**: https://railway.app
- **Team Lead**: [Name] - [Email]
- **On-Call Engineer**: [Name] - [Phone]

## Escalation Path

1. Check runbook for known issues
2. Check Stripe Dashboard for webhook/payment status
3. Check Railway logs for errors
4. Contact team lead if issue persists >30 min
5. Contact Stripe Support for API issues
6. Escalate to on-call engineer for critical production issues
```

---

### Task 7.7: Deploy to Production (1 hour)

**Action**: Execute deployment

```bash
# 1. Final pre-deployment verification
pytest tests/ -v --cov
ruff check .

# 2. Merge to production branch
git checkout deploy/production
git merge --no-ff feat/stripe-integration
git push origin deploy/production

# 3. Railway auto-deploys
# Monitor deployment in Railway dashboard

# 4. Verify deployment
curl https://api.quizify.ca/health
curl https://api.quizify.ca/api/billing/health

# 5. Test with live Stripe (small amount, refund after)
# - Create checkout session
# - Complete payment with real card
# - Verify webhook received
# - Verify provisioning worked
# - Access customer portal
# - Refund payment
```

---

### Task 7.8: Post-Deployment Monitoring (4 hours)

**Action**: Monitor production for first 24 hours

**Checklist**:
- [ ] Monitor Railway logs continuously
- [ ] Watch Stripe webhook logs
- [ ] Check for any error spikes
- [ ] Verify first real user checkout
- [ ] Monitor performance metrics
- [ ] Check database for correct provisioning
- [ ] Verify alerting is working

---

## Verification Checklist

### Pre-Deployment
- [ ] All environment variables set
- [ ] Live products created in Stripe
- [ ] Live webhook configured
- [ ] Customer Portal configured
- [ ] Database migrations applied
- [ ] All tests passing

### Deployment
- [ ] Code deployed successfully
- [ ] No errors in deployment logs
- [ ] Health checks passing
- [ ] API endpoints accessible

### Post-Deployment
- [ ] First test checkout successful
- [ ] Webhook processing correctly
- [ ] Subscription provisioned correctly
- [ ] Customer Portal accessible
- [ ] Monitoring dashboards active
- [ ] Alerts configured

---

## Success Criteria

- [ ] Zero critical errors in first 24 hours
- [ ] First successful customer checkout completed
- [ ] Webhook success rate >99%
- [ ] Performance meets benchmarks
- [ ] Team trained on operations
- [ ] Documentation complete
- [ ] Rollback plan tested

---

## Next Steps

Once production deployment successful:
1. ✅ Monitor for 24 hours
2. ✅ Document any issues encountered
3. ✅ Optimize based on real usage patterns
4. ✅ Collect user feedback
5. ✅ Plan future enhancements (annual discounts, coupons, etc.)

---

**Epic Owner**: GitHub Copilot  
**Last Updated**: 2025-11-19  
**Status**: Ready for Production Deployment
