# Railway Cron Job Setup Guide

**Date**: December 16, 2025  
**Purpose**: Configure Railway to automatically reset free user credits monthly

---

## 📋 Overview

The cron job calls the `/api/cron/reset-monthly-credits` endpoint daily to reset expired free credit allowances. Pro users are handled separately via Stripe webhooks.

## 🔑 Step 1: Set Environment Variable

1. **Go to Railway Dashboard** → Your Project → Variables
2. **Add new variable**:
   ```
   Variable Name: CRON_API_KEY
   Value: _Cf1Xmf640BkbWxJxVX-GqKoc9MAinGzwinGolptjSQ
   ```
3. **Click "Add"** and redeploy your service

⚠️ **IMPORTANT**: Keep this key secret! Anyone with this key can trigger credit resets.

---

## 🤖 Step 2: Create Cron Job in Railway

### Option A: Railway Dashboard (Recommended)

1. **Go to Railway Dashboard** → Your Project
2. **Click "New"** → **"Cron Job"**
3. **Configure the cron job**:

   **Name**: `daily-credit-reset`
   
   **Schedule**: `0 0 * * *`
   - Translation: Run daily at midnight UTC (12:00 AM UTC)
   - [Cron expression helper](https://crontab.guru/#0_0_*_*_*)
   
   **Command**:
   ```bash
   curl -X POST ${{RAILWAY_PUBLIC_DOMAIN}}/api/cron/reset-monthly-credits -H "X-Cron-API-Key: ${{CRON_API_KEY}}" -f
   ```
   
   Or if you need the full URL:
   ```bash
   curl -X POST https://quizify-production.up.railway.app/api/cron/reset-monthly-credits -H "X-Cron-API-Key: ${{CRON_API_KEY}}" -f
   ```

4. **Click "Create"**

### Option B: Railway CLI (Alternative)

If Railway doesn't have UI-based cron jobs, use Railway CLI:

```bash
# Install Railway CLI
npm i -g @railway/cli

# Login to Railway
railway login

# Link to your project
railway link

# Add cron job (if Railway supports it via CLI)
railway run "curl -X POST https://quizify-production.up.railway.app/api/cron/reset-monthly-credits -H 'X-Cron-API-Key: ${CRON_API_KEY}' -f"
```

---

## 🧪 Step 3: Test the Cron Job

### Manual Test (Before Scheduling)

Test the endpoint manually to ensure it works:

```bash
# Replace with your actual Railway URL
curl -X POST https://quizify-production.up.railway.app/api/cron/reset-monthly-credits \
  -H "X-Cron-API-Key: _Cf1Xmf640BkbWxJxVX-GqKoc9MAinGzwinGolptjSQ" \
  -v

# Expected response:
# {
#   "status": "success",
#   "reset_count": 0,
#   "error_count": 0,
#   "errors": []
# }
```

### Check Logs

After the test:
1. Go to **Railway Dashboard** → Your Service → **Logs**
2. Search for: `"Monthly credit reset"`
3. Verify you see: `"Monthly credit reset complete: X users, 0 errors"`

---

## 🔍 Step 4: Verify It's Running

### Check Cron Job Status

1. **Railway Dashboard** → Your Project → **Cron Jobs**
2. Look for `daily-credit-reset`
3. Check:
   - ✅ **Status**: Active
   - ✅ **Last Run**: Shows recent execution
   - ✅ **Next Run**: Shows next scheduled time

### Monitor First Execution

Wait for the next midnight UTC (or trigger manually if Railway allows):
1. Check **Logs** at execution time
2. Look for:
   ```
   INFO: Starting monthly credit reset cron job
   INFO: Monthly credit reset complete: X users, 0 errors
   ```

### Database Verification

After first run, check Supabase:

```sql
-- Check profiles table for recent period updates
SELECT 
    id,
    billing_plan,
    free_credit_units_remaining,
    free_credit_units_monthly,
    current_period_start,
    current_period_end,
    subscription_status
FROM profiles
WHERE billing_plan = 'free'
ORDER BY current_period_start DESC
LIMIT 10;

-- Expected: current_period_start/end should be at month boundaries
-- free_credit_units_remaining should equal free_credit_units_monthly
```

---

## 📊 What the Cron Job Does

1. **Finds Expired Users**:
   - `current_period_end < now()` OR `current_period_end IS NULL`

2. **Filters to FREE Users**:
   - `billing_plan = 'free'` OR
   - `billing_plan = 'pro'` but `subscription_status NOT IN ('active', 'trialing')`

3. **Resets Credits**:
   - `free_credit_units_remaining = free_credit_units_monthly` (default: 6 units = 3 credits)

4. **Updates Period**:
   - `current_period_start = first day of current month`
   - `current_period_end = first day of next month`

5. **Logs Results**:
   - Count of users reset
   - Count of errors
   - First 10 errors (for debugging)

---

## 🛡️ Security Features

- ✅ **API Key Authentication**: Prevents unauthorized access
- ✅ **Constant-time Comparison**: Prevents timing attacks
- ✅ **Production Enforcement**: Blocks requests without key in production
- ✅ **Audit Logging**: All attempts logged with results
- ✅ **Read-only for Pro Users**: Skips users with active subscriptions (Stripe manages their resets)

---

## 🚨 Troubleshooting

### Issue: "Invalid API key"

**Cause**: Mismatch between environment variable and header

**Fix**:
1. Verify `CRON_API_KEY` in Railway environment variables
2. Ensure curl command uses same key: `${{CRON_API_KEY}}`
3. Check for whitespace/newlines in key

### Issue: "Cron endpoint not configured"

**Cause**: `CRON_API_KEY` not set in production

**Fix**:
1. Add `CRON_API_KEY` to Railway environment variables
2. Redeploy the service
3. Test again

### Issue: No users being reset

**Possible Causes**:
1. All users have future `current_period_end` dates
2. All users are Pro with active subscriptions
3. Database query failing silently

**Debugging**:
```sql
-- Check which users should be reset
SELECT 
    id,
    billing_plan,
    subscription_status,
    current_period_end,
    NOW() as current_time,
    current_period_end < NOW() as should_reset
FROM profiles
WHERE billing_plan = 'free'
   OR (billing_plan = 'pro' AND subscription_status NOT IN ('active', 'trialing'))
ORDER BY current_period_end;
```

### Issue: Cron job not running

**Check**:
1. Railway Dashboard → Cron Jobs → Status
2. Verify schedule expression: `0 0 * * *`
3. Check Railway service logs for errors
4. Ensure service is deployed and running

---

## 📝 Maintenance

### Checking Cron Job Health

**Monthly**:
- Review Railway logs for any errors
- Verify reset counts are reasonable
- Check for any users stuck with `period_end < now()` for multiple days

**Query to Check Stuck Users**:
```sql
SELECT 
    id,
    billing_plan,
    free_credit_units_remaining,
    current_period_end,
    NOW() - current_period_end as days_overdue
FROM profiles
WHERE current_period_end < NOW() - INTERVAL '2 days'
  AND billing_plan = 'free';
```

### Updating the Schedule

If you need to change when the cron runs:
1. Railway Dashboard → Cron Jobs → `daily-credit-reset`
2. Edit schedule (common options):
   - `0 0 * * *` - Daily at midnight UTC
   - `0 1 * * *` - Daily at 1 AM UTC
   - `0 */6 * * *` - Every 6 hours
   - `0 0 1 * *` - First day of month (for testing)

### Manual Trigger (Emergency Reset)

If you need to manually reset credits outside the schedule:

```bash
# Use the same curl command
curl -X POST https://quizify-production.up.railway.app/api/cron/reset-monthly-credits \
  -H "X-Cron-API-Key: _Cf1Xmf640BkbWxJxVX-GqKoc9MAinGzwinGolptjSQ" \
  -f

# Or via Railway CLI
railway run "curl -X POST https://quizify-production.up.railway.app/api/cron/reset-monthly-credits -H 'X-Cron-API-Key: ${CRON_API_KEY}' -f"
```

---

## 🔗 Related Documentation

- [Billing User Journeys](./BILLING_USER_JOURNEYS.md#monthly-reset-flow)
- [Hybrid Pricing Epics](./HYBRID_PRICING_EPICS.md#epic-4-monthly-reset-job)
- [Environment Variables Guide](./ENV_VARIABLES_GUIDE.md#cron-configuration)
- [Cron Routes Implementation](../api/cron_routes.py)

---

## ✅ Setup Complete Checklist

- [ ] `CRON_API_KEY` added to Railway environment variables
- [ ] Service redeployed with new environment variable
- [ ] Cron job created with schedule `0 0 * * *`
- [ ] Cron job command uses correct URL and API key
- [ ] Manual test successful (returns `status: success`)
- [ ] Logs show successful execution
- [ ] First scheduled run verified
- [ ] Database shows correct period updates
- [ ] Monitoring/alerting configured (optional)

---

**Questions or Issues?**
- Check Railway logs: Dashboard → Service → Logs
- Check API logs for `"Monthly credit reset"`
- Verify environment variables: Dashboard → Variables
- Test manually with curl command above
