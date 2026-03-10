# Webhook Testing Guide

This guide explains how to test Stripe webhooks locally using the Stripe CLI.

## Prerequisites

1. Install Stripe CLI: https://docs.stripe.com/stripe-cli
2. Login to Stripe: `stripe login`
3. Server running on `http://localhost:8000`

## Setup Webhook Forwarding

### Step 1: Start Webhook Listener

In a new terminal, run:

```bash
stripe listen --forward-to localhost:8000/api/billing/webhook
```

This command will:
- Display your webhook signing secret (starts with `whsec_`)
- Forward all Stripe events to your local endpoint
- Show real-time event logs

### Step 2: Update Environment Variable

Copy the webhook signing secret from the Stripe CLI output and add it to your `.env` file:

```env
STRIPE_WEBHOOK_SECRET=whsec_YOUR_SECRET_HERE
```

### Step 3: Restart Server

Restart your FastAPI server to load the new webhook secret:

```bash
# Kill server
pkill -f uvicorn

# Restart
source .venv/bin/activate && uvicorn main:app --reload --port 8000
```

## Testing Webhook Events

### Test Checkout Completion

Trigger a `checkout.session.completed` event:

```bash
stripe trigger checkout.session.completed
```

**Expected Behavior:**
- Webhook endpoint receives event
- User subscription is provisioned
- Database updated with subscription details
- Logs show: "Checkout completed for user..."

### Test Subscription Created

Trigger a `customer.subscription.created` event:

```bash
stripe trigger customer.subscription.created
```

**Expected Behavior:**
- Subscription provisioned in database
- User tier upgraded
- Cache invalidated

### Test Invoice Paid

Trigger an `invoice.paid` event (successful recurring payment):

```bash
stripe trigger invoice.paid
```

**Expected Behavior:**
- Subscription status updated to "active"
- Database reflects successful payment
- Logs show: "Invoice paid: inv_..."

### Test Invoice Payment Failed

Trigger an `invoice.payment_failed` event:

```bash
stripe trigger invoice.payment_failed
```

**Expected Behavior:**
- Subscription status updated to "past_due"
- Database updated
- Logs show: "Invoice payment failed: inv_..."

### Test Subscription Canceled

Trigger a `customer.subscription.deleted` event:

```bash
stripe trigger customer.subscription.deleted
```

**Expected Behavior:**
- Subscription status set to "canceled"
- `subscription_canceled_at` timestamp recorded
- User tier unchanged (grace period)
- Logs show: "Subscription deleted: sub_..."

## Manual Testing with Real Checkout

### Step 1: Create Checkout Session

```bash
curl -X POST http://localhost:8000/api/billing/create-checkout-session \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"tier": "basic"}'
```

### Step 2: Complete Payment

1. Open the `checkout_url` from response in browser
2. Use test card: `4242 4242 4242 4242`
3. Enter any future expiration date, any CVC
4. Complete payment

### Step 3: Verify Webhook Received

Check Stripe CLI output for:
```
--> checkout.session.completed [evt_xxx]
```

Check server logs for:
```
INFO: Checkout completed for user [user_id], subscription [sub_id]
INFO: Synchronously provisioned subscription for user [user_id]
```

### Step 4: Verify Database

Query the database to confirm:

```sql
SELECT 
  account_tier,
  subscription_status,
  stripe_subscription_id,
  current_period_start,
  current_period_end
FROM profiles
WHERE id = 'USER_ID';
```

## Verifying Webhook Signature

The webhook endpoint verifies signatures using:

```python
event = stripe.Webhook.construct_event(
    payload, sig_header, config.STRIPE_WEBHOOK_SECRET
)
```

**Test Invalid Signature:**

```bash
curl -X POST http://localhost:8000/api/billing/webhook \
  -H "Content-Type: application/json" \
  -H "Stripe-Signature: invalid" \
  -d '{"type":"test","data":{}}'
```

**Expected Response:** `400 Bad Request - Invalid signature`

## Monitoring Webhooks

### View Webhook Logs

1. Go to Stripe Dashboard: https://dashboard.stripe.com/test/webhooks
2. Click on your endpoint
3. View event logs and delivery attempts

### Check Server Logs

```bash
# Follow server logs
tail -f logs/app.log

# Or watch for webhook events
tail -f logs/app.log | grep "webhook"
```

### Debug Failed Webhooks

If webhook fails:

1. Check Stripe CLI output for error details
2. Check server logs for exception traces
3. Verify `STRIPE_WEBHOOK_SECRET` is correct
4. Verify database connection
5. Check RLS policies allow service role updates

## Common Issues

### Issue: "Webhook secret not configured"

**Solution:** Set `STRIPE_WEBHOOK_SECRET` in `.env` and restart server

### Issue: "Invalid signature"

**Solution:** 
1. Verify webhook secret matches Stripe CLI output
2. Restart server after updating `.env`
3. Ensure no proxy modifying request headers

### Issue: "No user_id in subscription metadata"

**Solution:** When creating checkout sessions, ensure metadata includes `user_id`:

```python
metadata={
    "user_id": user_id,
    "tier": tier
}
```

### Issue: Webhook timing out

**Solution:**
- Check database connectivity
- Verify Supabase service role key is valid
- Check for long-running queries
- Ensure cache invalidation doesn't block

## Production Webhook Setup

### Step 1: Deploy to Production

Ensure your production server is accessible at `https://your-domain.com`

### Step 2: Register Webhook Endpoint

1. Go to Stripe Dashboard: https://dashboard.stripe.com/webhooks
2. Click "Add endpoint"
3. Enter URL: `https://your-domain.com/api/billing/webhook`
4. Select events to listen for:
   - `checkout.session.completed`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.paid`
   - `invoice.payment_failed`

### Step 3: Update Production Environment

Copy the webhook signing secret from dashboard and set in production:

```env
STRIPE_WEBHOOK_SECRET=whsec_PRODUCTION_SECRET_HERE
```

### Step 4: Test Production Webhooks

Use Stripe Dashboard to send test events to production endpoint.

## Best Practices

1. **Always verify signatures** - Never process unsigned webhook events
2. **Handle idempotency** - Store event IDs to prevent duplicate processing
3. **Log everything** - Comprehensive logging helps debug webhook issues
4. **Monitor failures** - Set up alerts for webhook delivery failures
5. **Test thoroughly** - Test all event types before production deployment
6. **Use metadata** - Include user_id in all Stripe objects for easy mapping

## References

- [Stripe CLI Documentation](https://docs.stripe.com/stripe-cli)
- [Stripe Webhook Testing](https://docs.stripe.com/webhooks/test)
- [Stripe Subscription Webhooks](https://docs.stripe.com/billing/subscriptions/webhooks)
- [Webhook Best Practices](https://docs.stripe.com/webhooks/best-practices)
