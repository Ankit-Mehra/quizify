# Automated Credit Reset Setup Guide

**Date**: December 16, 2025  
**Purpose**: Configure automated daily credit resets for free users

---

## 📋 Overview

The cron job calls the `/api/cron/reset-monthly-credits` endpoint daily to reset expired free credit allowances. Pro users are handled separately via Stripe webhooks.

## ⚠️ Important: Railway Cron Limitation

**Railway's native cron feature only works for short-lived tasks that exit after completion.** Since Quizify is a long-running FastAPI web server that never exits, you must use an external cron service to hit the API endpoint.

## 🔑 Step 1: Set Environment Variable

1. **Go to Railway Dashboard** → Your Project → Variables
2. **Generate a secure API key**:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
3. **Add new variable**:
   ```
   Variable Name: CRON_API_KEY
   Value: <paste-your-generated-key-here>
   ```
4. **Click "Add"** and redeploy your service

⚠️ **IMPORTANT**: Keep this key secret! Anyone with this key can trigger credit resets.

---

## 🤖 Step 2: Choose a Cron Service

### Option A: cron-job.org (Recommended - Free)

1. **Create Account**: Go to [cron-job.org](https://cron-job.org) and sign up
2. **Create New Cron Job**:
   - **Title**: `Quizify Daily Credit Reset`
   - **URL**: `https://your-app.railway.app/api/cron/reset-monthly-credits`
   - **Schedule**: Every day at 00:00 UTC (midnight)
   - **Request Method**: POST
   - **Custom Headers**:
     ```
     X-Cron-API-Key: <your-generated-api-key-here>
     ```
   - **Notifications**: Enable email on failure (optional)
3. **Save and Activate**

### Option B: GitHub Actions (Free, Code-based)

1. **Create Workflow File**: `.github/workflows/monthly-credit-reset.yml`

```yaml
name: Monthly Credit Reset
on:
  schedule:
    - cron: '0 0 * * *'  # Daily at midnight UTC
  workflow_dispatch:  # Allow manual trigger

jobs:
  reset-credits:
    runs-on: ubuntu-latest
    steps:
      - name: Call credit reset endpoint
        run: |
          response=$(curl -X POST https://your-app.railway.app/api/cron/reset-monthly-credits \
            -H "X-Cron-API-Key: ${{ secrets.CRON_API_KEY }}" \
            -f -s -w "\n%{http_code}")
          
          http_code=$(echo "$response" | tail -n1)
          body=$(echo "$response" | head -n-1)
          
          echo "HTTP Status: $http_code"
          echo "Response: $body"
          
          if [ "$http_code" != "200" ]; then
            echo "Credit reset failed with status $http_code"
            exit 1
          fi
```

2. **Add Secret to GitHub**:
   - Go to your repository → Settings → Secrets and variables → Actions
   - Create new secret: `CRON_API_KEY` = `_Cf1Xmf640BkbWxJxVX-GqKoc9MAinGzwinGolptjSQ`

3. **Commit and Push**:
   ```bash
   git add .github/workflows/monthly-credit-reset.yml
   git commit -m "ci: add daily credit reset workflow"
   git push
   ```

### Option C: Supabase pg_cron (If Using Supabase)

Run this in your Supabase SQL Editor:

```sql
-- Enable pg_cron extension
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- Schedule the credit reset job
SELECT cron.schedule(
    'daily-credit-reset',
    '0 0 * * *',  -- Daily at midnight UTC
    $$
    SELECT net.http_post(
        url := 'https://your-app.railway.app/api/cron/reset-monthly-credits',
        headers := jsonb_build_object(
            'Content-Type', 'application/json',
            'X-Cron-API-Key', '<your-generated-api-key-here>'
        )
    );
    $$
);

-- Verify the job was created
SELECT * FROM cron.job;
```

### Option D: EasyCron (Free Tier Available)

1. **Sign up**: [easycron.com](https://www.easycron.com)
2. **Create Cron Job**:
   - URL: `https://your-app.railway.app/api/cron/reset-monthly-credits`
   - Schedule: Daily at 00:00
   - HTTP Method: POST
   - Custom Headers: `X-Cron-API-Key: <your-generated-api-key-here>`

---

## 🧪 Step 3: Test the Cron Job

### Manual Test (Before Scheduling)

Test the endpoint manually to ensure it works:

```bash
# Replace with your actual Railway URL and API key
curl -X POST https://your-app.railway.app/api/cron/reset-monthly-credits \
  -H "X-Cron-API-Key: <your-generated-api-key-here>" \
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
   - `free_credit_units_remaining = free_credit_units_monthly` (default: 6 units; **conversion:** 1 credit = 2 units, so 6 units = 3 credits)

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
# Use the same curl command (replace with your Railway URL and API key)
curl -X POST https://your-app.railway.app/api/cron/reset-monthly-credits \
  -H "X-Cron-API-Key: <your-generated-api-key-here>" \
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
