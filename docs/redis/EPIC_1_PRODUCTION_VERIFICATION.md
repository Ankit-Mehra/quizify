# Epic 1 Production Verification Guide

## Pre-Deployment Checklist

### 1. Railway Redis Service Setup
- [ ] **Add Redis service to Railway project**
  - Go to Railway dashboard → Add Service → Database → Redis
  - Railway automatically provisions: `REDIS_URL`, `REDISHOST`, `REDISPORT`, `REDIS_PASSWORD`
  - No additional configuration needed - Railway handles everything

### 2. Environment Variables (Already Set)
- [ ] Verify `REDIS_URL` is available in Railway environment
  - Should be auto-generated when Redis service is added
  - Format: `redis://default:PASSWORD@redis.railway.internal:6379`
- [ ] Optional variables (use defaults if not set):
  - `REDIS_ENABLED=true` (default)
  - `REDIS_MAX_CONNECTIONS=20` (default)
  - Other Redis settings have sensible defaults

### 3. Deploy to Production
```bash
# Option A: Merge to main (if Railway watches main branch)
git checkout main
git merge redis-integration
git push origin main

# Option B: Configure Railway to deploy redis-integration branch
# Railway Dashboard → Settings → Deploy Branch → redis-integration
```

---

## Post-Deployment Verification

### Step 1: Check Application Health (Critical)
```bash
# Basic health check - should return 200 OK
curl https://your-app.railway.app/health

# Expected response:
{
  "status": "ok",
  "timestamp": "2025-11-02T12:34:56.789Z"
}
```

### Step 2: Check Redis Connectivity (Critical)
```bash
# Redis-specific health check
curl https://your-app.railway.app/health/redis

# Expected response if Redis connected:
{
  "connected": true,
  "latency_ms": 1.23
}

# Expected response if Redis unavailable (fallback mode):
{
  "connected": false,
  "error": "Redis client not initialized"
}
```

**Status Code Verification:**
- `200 OK` = Redis connected and healthy ✅
- `503 Service Unavailable` = Redis unavailable, app using memory fallback ⚠️

### Step 3: Verify Application Logs (Important)
Check Railway logs for startup messages:

```bash
# In Railway Dashboard → Deployments → View Logs

# Look for these messages:

✅ Success Case:
"Starting Redis client initialization..."
"Redis client initialized successfully"
"Redis health check: Connected=True, Latency=X.XXms"

❌ Fallback Case:
"Starting Redis client initialization..."
"Redis connection failed: [error message]"
"Application will run in memory-only mode"
```

### Step 4: Test Fallback Behavior (Optional)
To verify graceful degradation:

1. **Temporarily disable Redis** in Railway:
   - Railway Dashboard → Redis Service → Settings → Pause Service
   
2. **Redeploy your application**
   - Should start successfully (not crash)
   - `/health` should return `200 OK`
   - `/health/redis` should return `503` with error message
   
3. **Re-enable Redis**:
   - Railway Dashboard → Redis Service → Resume Service
   - Redeploy application
   - Should reconnect automatically

---

## Verification Checklist

### Critical Checks (Must Pass)
- [ ] App starts successfully (Railway shows "Active")
- [ ] `/health` endpoint returns `200 OK`
- [ ] `/health/redis` returns `200 OK` with latency info
- [ ] No error logs related to Redis initialization
- [ ] Application can serve existing requests (quiz generation, etc.)

### Performance Checks (Nice to Have)
- [ ] Redis latency < 10ms (typical Railway internal network)
- [ ] No connection timeout errors in logs
- [ ] Application startup time < 30 seconds

### Fallback Checks (Safety Net)
- [ ] App survives Redis service pause/restart
- [ ] Graceful error messages (no stack traces to users)
- [ ] Automatic reconnection when Redis comes back

---

## Troubleshooting

### Issue: App won't start after deployment

**Symptoms:**
- Railway shows "Crashed" or "Build Failed"
- Logs show Redis connection errors

**Solutions:**
1. Check if Redis service is running in Railway
2. Verify `REDIS_URL` variable exists
3. Check for typos in environment variable names
4. Set `REDIS_ENABLED=false` temporarily to bypass Redis

### Issue: `/health/redis` returns 503

**Symptoms:**
- App is running but Redis health check fails
- Logs show connection timeout or refused errors

**Solutions:**
1. Verify Redis service is in same Railway project
2. Check Redis service is not paused
3. Verify `REDIS_URL` points to internal Railway network
4. Check Railway network connectivity (rare issue)

### Issue: High Redis latency (>50ms)

**Symptoms:**
- `/health/redis` shows latency > 50ms
- Slower than expected response times

**Solutions:**
1. Check if Redis and app are in same Railway region
2. Verify Railway internal network is being used (redis.railway.internal)
3. Check Redis service metrics for CPU/memory issues
4. Consider upgrading Redis service plan if overloaded

---

## Success Metrics

### Epic 1 is successful when:
1. ✅ Application deploys without Redis-related crashes
2. ✅ Redis connectivity confirmed via health check
3. ✅ Latency measurements available and reasonable (<10ms)
4. ✅ Application survives Redis service interruptions (fallback works)
5. ✅ No degradation of existing features (quiz generation, etc.)

### What Epic 1 does NOT include yet:
- ❌ No browser slot management yet (Epic 2)
- ❌ No quota caching yet (Epic 3)
- ❌ No session management yet (Epic 4)
- ❌ No horizontal scaling yet (requires Epics 2-4)

**Current State:** Single-instance deployment with Redis infrastructure ready for future features.

---

## Quick Reference Commands

```bash
# Check app health
curl https://your-app.railway.app/health

# Check Redis health
curl https://your-app.railway.app/health/redis

# View Railway logs
railway logs --project your-project-id

# Check Redis service status
railway status --service redis
```

---

## Next Steps After Verification

Once Epic 1 is verified in production:

1. **Monitor for 24-48 hours**
   - Watch error rates in Railway metrics
   - Check Redis connection stability
   - Verify no unexpected issues

2. **Begin Epic 2 (Browser Slot Management)**
   - Implement distributed browser slot coordination
   - Replace in-memory tracking with Redis
   - Enable multi-instance support

3. **Consider staging environment**
   - Test Epic 2-4 in staging before production
   - Reduce production risk for more complex features

---

## Emergency Rollback

If Epic 1 causes production issues:

```bash
# Quick rollback to previous version
git revert HEAD
git push origin main

# Or in Railway Dashboard:
# Deployments → Previous Deployment → Redeploy
```

Redis infrastructure can be left running - it won't cause issues even if code is rolled back.
