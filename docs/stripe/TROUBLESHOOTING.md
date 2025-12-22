# Stripe Integration - Troubleshooting Guide

**Last Updated**: 2025-11-19

---

## Table of Contents

1. [Checkout Flow Issues](#checkout-flow-issues)
2. [Webhook Problems](#webhook-problems)
3. [Subscription Provisioning](#subscription-provisioning)
4. [Customer Portal Issues](#customer-portal-issues)
5. [Payment Failures](#payment-failures)
6. [Database Issues](#database-issues)
7. [Configuration Errors](#configuration-errors)
8. [API Errors](#api-errors)
9. [Testing Issues](#testing-issues)
10. [Common Error Messages](#common-error-messages)

---

## Checkout Flow Issues

### Issue: "Invalid price ID" Error

**Symptoms**:
```json
{
  "detail": "Invalid price ID: price_xxx"
}
```

**Causes**:
- Price ID not in allowed list in config
- Using test price ID in production or vice versa
- Typo in environment variable

**Solutions**:
1. Check `.env` file has correct price IDs:
   ```bash
   echo $STRIPE_PRICE_BASIC_MONTHLY
   ```
2. Verify price ID exists in Stripe Dashboard (Products → Prices)
3. Ensure using correct mode (test vs live)
4. Restart application after changing `.env`:
   ```bash
   # Railway automatically restarts on env var change
   # Local: Ctrl+C and restart
   ```

---

### Issue: "Already have an active subscription" (409 Conflict)

**Symptoms**:
```json
{
  "detail": "You already have an active subscription. Please cancel your current subscription first."
}
```

**Causes**:
- User has active subscription in database
- Previous subscription not canceled properly

**Solutions**:
1. Check current subscription:
   ```sql
   SELECT stripe_subscription_id, subscription_status 
   FROM profiles 
   WHERE id = 'user_id';
   ```
2. If subscription is invalid, clear it:
   ```sql
   UPDATE profiles SET 
     stripe_subscription_id = NULL,
     subscription_status = NULL
   WHERE id = 'user_id';
   ```
3. Have user access Customer Portal to cancel existing subscription first
4. Use sync endpoint to verify status: `/api/billing/sync-subscription`

---

### Issue: Checkout Session Link Not Working

**Symptoms**:
- User clicks checkout link, gets error
- "Session expired" message

**Causes**:
- Checkout sessions expire after 24 hours
- Session already completed
- Session ID invalid

**Solutions**:
1. Create new checkout session (sessions are single-use)
2. Verify session in Stripe Dashboard (Payments → Checkout Sessions)
3. Check session status:
   ```bash
   stripe checkout sessions retrieve cs_xxx
   ```

---

## Webhook Problems

### Issue: Webhooks Not Being Received

**Symptoms**:
- Subscription not provisioned after payment
- User tier not updated
- No webhook logs in Stripe Dashboard

**Diagnosis**:
1. Check Stripe Dashboard → Developers → Webhooks → Logs
2. Look for delivery attempts and responses
3. Check Railway logs for incoming requests:
   ```bash
   railway logs --filter "webhook"
   ```

**Solutions**:
1. **Verify webhook endpoint is accessible**:
   ```bash
   curl -I https://api.quizify.ca/api/billing/webhook
   # Should return 400 (missing signature), not 404
   ```
2. **Check HTTPS is enabled** (Stripe requires HTTPS)
3. **Verify webhook URL in Stripe Dashboard** is correct
4. **Check firewall/security groups** allow Stripe IPs
5. **Use Stripe CLI for local testing**:
   ```bash
   stripe listen --forward-to localhost:8000/api/billing/webhook
   ```

---

### Issue: Webhook Signature Verification Fails

**Symptoms**:
```
ERROR: Invalid webhook signature
```

**Causes**:
- Wrong webhook secret in environment variables
- Request body modified before verification
- Using test webhook secret with live events

**Solutions**:
1. **Verify webhook secret matches Stripe Dashboard**:
   ```bash
   # In Stripe Dashboard: Developers → Webhooks → <endpoint> → Signing secret
   # Compare with:
   echo $STRIPE_WEBHOOK_SECRET
   ```
2. **Ensure raw body used for verification**:
   ```python
   # Correct:
   body = await request.body()  # Raw bytes
   event = stripe.Webhook.construct_event(body, signature, secret)
   
   # Wrong:
   body = await request.json()  # Parsed JSON (signature fails)
   ```
3. **Use correct webhook secret for mode** (test vs live)
4. **Regenerate webhook secret** if compromised:
   - In Stripe Dashboard, click "Roll signing secret"
   - Update environment variable
   - Restart application

---

### Issue: Duplicate Webhook Processing

**Symptoms**:
- Same event processed multiple times
- Duplicate tier updates
- Duplicate emails sent

**Causes**:
- Idempotency check not working
- Redis connection failure
- Event ID collision (extremely rare)

**Solutions**:
1. **Verify Redis is running**:
   ```bash
   redis-cli ping
   # Should return: PONG
   ```
2. **Check idempotency logic**:
   ```python
   # Should check Redis before processing
   if await billing_service.is_event_processed(event.id):
       return {"status": "success", "message": "Event already processed"}
   ```
3. **Check Redis TTL** (should be 86400 = 24 hours):
   ```bash
   redis-cli TTL stripe:event:evt_xxx
   ```
4. **Manual cleanup** if duplicates occurred:
   ```sql
   -- Revert duplicate tier update if needed
   ```

---

## Subscription Provisioning

### Issue: Subscription Paid But Not Provisioned

**Symptoms**:
- Payment successful in Stripe Dashboard
- User still on free tier
- No tier update in database

**Diagnosis**:
1. Check if webhook was received:
   - Stripe Dashboard → Webhooks → Logs
2. Check webhook processing logs:
   ```bash
   railway logs --filter "invoice.paid"
   ```
3. Verify subscription in database:
   ```sql
   SELECT * FROM user_tier_info WHERE email = 'user@example.com';
   ```

**Solutions**:
1. **Manually trigger webhook re-delivery**:
   - In Stripe Dashboard → Webhooks → <endpoint> → Logs
   - Click failed event → "Resend"
2. **Use sync endpoint** to manually provision:
   ```bash
   curl -X POST https://api.quizify.ca/api/billing/sync-subscription \
     -H "Authorization: Bearer USER_TOKEN"
   ```
3. **Manual database update** (last resort):
   ```sql
   UPDATE profiles SET 
     account_tier = 'basic',
     stripe_subscription_id = 'sub_xxx',
     subscription_status = 'active',
     subscription_current_period_end = '2025-12-19'
   WHERE id = 'user_id';
   ```

---

### Issue: Wrong Tier Provisioned

**Symptoms**:
- User paid for Educator but got Basic
- Quota limit incorrect

**Causes**:
- Metadata mismatch in checkout session
- Wrong tier parameter passed
- Database update used wrong tier

**Solutions**:
1. **Check subscription metadata in Stripe**:
   ```bash
   stripe subscriptions retrieve sub_xxx
   # Look at metadata.tier
   ```
2. **Verify correct tier provisioned**:
   ```sql
   SELECT account_tier, stripe_subscription_id FROM profiles WHERE id = 'user_id';
   ```
3. **Correct tier manually**:
   ```sql
   UPDATE profiles SET account_tier = 'educator' WHERE id = 'user_id';
   ```
4. **Refund and re-checkout** if payment amount wrong

---

## Customer Portal Issues

### Issue: "No subscription found" When Accessing Portal

**Symptoms**:
```json
{
  "detail": "No subscription found. You must subscribe before managing your subscription."
}
```

**Causes**:
- User never completed checkout
- `stripe_customer_id` not stored in database
- Subscription canceled and cleared

**Solutions**:
1. **Verify customer ID exists**:
   ```sql
   SELECT stripe_customer_id FROM profiles WHERE id = 'user_id';
   ```
2. **If NULL, user must subscribe first** (no portal access)
3. **If customer exists in Stripe but not DB**, sync:
   ```sql
   UPDATE profiles SET stripe_customer_id = 'cus_xxx' WHERE id = 'user_id';
   ```

---

### Issue: Portal Shows Wrong Subscription

**Symptoms**:
- Portal shows different plan than database
- Portal shows canceled subscription as active

**Causes**:
- Database out of sync with Stripe
- Webhook processing failed

**Solutions**:
1. **Use sync endpoint** to refresh from Stripe:
   ```bash
   curl -X POST /api/billing/sync-subscription \
     -H "Authorization: Bearer USER_TOKEN"
   ```
2. **Verify in Stripe Dashboard**:
   - Go to Customers → <customer> → Subscriptions
   - Compare with database

---

## Payment Failures

### Issue: Payment Failed, User Locked Out Immediately

**Symptoms**:
- Payment fails
- User cannot create quizzes
- No grace period

**Causes**:
- Grace period not set in webhook handler
- Grace period already expired
- Status set to "canceled" instead of "past_due"

**Solutions**:
1. **Check subscription status**:
   ```sql
   SELECT subscription_status, subscription_grace_period_end 
   FROM profiles WHERE id = 'user_id';
   ```
2. **Manually set grace period** (7 days):
   ```sql
   UPDATE profiles SET 
     subscription_status = 'past_due',
     subscription_grace_period_end = NOW() + INTERVAL '7 days'
   WHERE id = 'user_id';
   ```
3. **Verify webhook handler** sets grace period:
   ```python
   await billing_service.handle_failed_payment(user_id, grace_days=7)
   ```

---

### Issue: Card Declined During Checkout

**Symptoms**:
- User reports payment won't go through
- Error: "Your card was declined"

**Causes**:
- Insufficient funds
- Card expired
- Card restricted by issuer
- Test card used incorrectly

**Solutions**:
1. **For test mode**, use correct test cards:
   - Success: `4242 4242 4242 4242`
   - Decline: `4000 0000 0000 0002`
2. **For production**, have user:
   - Verify card details
   - Try different card
   - Contact card issuer
3. **Check Stripe Dashboard** for decline reason:
   - Payments → Failed → <payment> → Decline code

---

## Database Issues

### Issue: Missing Stripe Columns

**Symptoms**:
```
ERROR: column "stripe_customer_id" does not exist
```

**Causes**:
- Migration 014 not applied
- Wrong database environment

**Solutions**:
1. **Apply migration**:
   ```bash
   psql -h <supabase-host> -U postgres -d postgres \
     -f migrations/014_add_stripe_integration.sql
   ```
2. **Verify columns exist**:
   ```sql
   \d profiles
   -- Should show: stripe_customer_id, stripe_subscription_id, etc.
   ```

---

### Issue: RLS Policy Blocking Updates

**Symptoms**:
- Webhook cannot update profiles
- Error: "new row violates row-level security policy"

**Causes**:
- RLS policy too restrictive
- Service role not used for webhook updates

**Solutions**:
1. **Verify service role client used**:
   ```python
   # Webhooks should use:
   supabase = get_supabase()  # Service role (bypasses RLS)
   
   # Not:
   supabase = get_authed_supabase_client(token)  # User-authenticated
   ```
2. **Check RLS policy**:
   ```sql
   SELECT * FROM pg_policies WHERE tablename = 'profiles' AND policyname LIKE '%Stripe%';
   ```
3. **Ensure policy allows service_role**:
   ```sql
   CREATE POLICY "Service role can update Stripe data"
       ON public.profiles FOR UPDATE
       USING (auth.role() = 'service_role');
   ```

---

## Configuration Errors

### Issue: "STRIPE_SECRET_KEY not configured"

**Symptoms**:
- Application won't start
- Warning in logs

**Causes**:
- Environment variable not set
- Wrong variable name
- Railway environment not applied

**Solutions**:
1. **Check environment variable**:
   ```bash
   # Local:
   grep STRIPE_SECRET_KEY .env
   
   # Railway:
   railway variables
   ```
2. **Set variable**:
   ```bash
   # Railway:
   railway variables set STRIPE_SECRET_KEY=sk_xxx
   ```
3. **Restart application** after setting

---

### Issue: Using Test Keys in Production

**Symptoms**:
- Payments work but don't appear in live Dashboard
- Test data mixed with live data

**Causes**:
- Test keys (`sk_test_`) used in production
- Wrong environment variables

**Solutions**:
1. **Verify key prefix**:
   - Test: `sk_test_`, `pk_test_`
   - Live: `sk_live_`, `pk_live_`
2. **Update to live keys** in production Railway variables
3. **Restart application**
4. **Update webhook endpoint** in Stripe Dashboard (test vs live)

---

## API Errors

### Issue: 500 Internal Server Error

**Symptoms**:
- Generic error response
- No detail provided

**Diagnosis**:
1. Check Railway logs:
   ```bash
   railway logs --tail 100
   ```
2. Look for stack traces

**Common Causes**:
- Stripe API key invalid
- Database connection failed
- Redis unavailable
- Unhandled exception

**Solutions**:
- Check logs for specific error
- Verify all services running (Supabase, Redis)
- Check environment variables
- Review recent code changes

---

### Issue: 401 Unauthorized

**Symptoms**:
```json
{
  "detail": "Not authenticated"
}
```

**Causes**:
- Missing `Authorization` header
- Expired access token
- Invalid token

**Solutions**:
1. **Login again** to get fresh token
2. **Check token expiry** (1 hour by default)
3. **Use refresh token** to get new access token
4. **Verify header format**:
   ```
   Authorization: Bearer eyJhbGc...
   ```

---

## Testing Issues

### Issue: Tests Failing with "Stripe Error"

**Symptoms**:
- Unit tests fail with Stripe API errors
- Error: "No such customer: cus_xxx"

**Causes**:
- Mocking not set up correctly
- Test using real Stripe API instead of mocks
- Missing test fixtures

**Solutions**:
1. **Ensure Stripe calls are mocked**:
   ```python
   @patch("stripe.Customer.create")
   def test_create_customer(mock_create):
       mock_create.return_value = MagicMock(id="cus_test123")
       # ... test code ...
   ```
2. **Use test fixtures**:
   ```python
   @pytest.fixture
   def mock_stripe():
       with patch("stripe.api_key"):
           yield
   ```
3. **Don't make real API calls in unit tests**

---

### Issue: Webhook Tests Failing on Signature

**Symptoms**:
- Test webhook returns 400
- Error: "Invalid signature"

**Causes**:
- Test not generating valid signature
- Signature verification not mocked

**Solutions**:
1. **Use Stripe test helpers**:
   ```python
   import stripe
   
   payload = json.dumps({"type": "test.event"})
   signature = stripe.WebhookSignature._compute_signature(
       payload, webhook_secret
   )
   ```
2. **Or mock signature verification**:
   ```python
   @patch("stripe.Webhook.construct_event")
   def test_webhook(mock_construct):
       mock_construct.return_value = mock_event
       # ... test code ...
   ```

---

## Common Error Messages

### "Price does not match tier"

**Meaning**: Price ID is for different tier than requested

**Fix**: Use correct price ID for tier, or update tier parameter

---

### "Session does not belong to this user"

**Meaning**: User trying to verify someone else's checkout session

**Fix**: Security check working correctly, ensure using correct session ID

---

### "Subscription not found, cleared from database"

**Meaning**: Subscription deleted in Stripe but still referenced in DB

**Fix**: Normal - sync endpoint automatically clears invalid references

---

### "Event already processed (idempotency check)"

**Meaning**: Webhook event received twice, second attempt skipped

**Fix**: Working as intended, prevents duplicate processing

---

## Getting Help

If issue not covered in this guide:

1. **Check Stripe Documentation**: https://stripe.com/docs
2. **Stripe Support**: https://support.stripe.com
3. **Check GitHub Issues**: Search for similar problems
4. **Review Logs**: Railway logs often contain detailed error info
5. **Contact Team**: Reach out to team lead or on-call engineer

---

## Debug Mode

Enable verbose logging for troubleshooting:

```python
# In services/logger.py
import logging

# Set to DEBUG temporarily
logging.basicConfig(level=logging.DEBUG)

# Or specific loggers:
logging.getLogger("stripe").setLevel(logging.DEBUG)
```

**Remember to revert to INFO in production!**

---

**Last Updated**: 2025-11-19  
**Maintained By**: GitHub Copilot
