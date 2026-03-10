# Quizify Redis Health Check - Postman Collection

## Overview
Comprehensive Postman collection for testing Redis connectivity and health monitoring endpoints introduced in **Epic 1: Core Redis Infrastructure**.

## Files
- `Quizify_Redis_Health_Check.postman_collection.json` - Test collection
- `Redis_Testing.postman_environment.json` - Environment variables

## Quick Start

### 1. Import into Postman
```bash
# Import both files:
# - Quizify_Redis_Health_Check.postman_collection.json
# - Redis_Testing.postman_environment.json
```

### 2. Configure Environment Variables
Edit `Redis_Testing` environment in Postman:

```
BASE_URL = http://localhost:8000              # Local development
STAGING_URL = https://your-staging.railway.app    # Railway staging
PRODUCTION_URL = https://your-app.railway.app     # Railway production
```

### 3. Run Tests

**Option A: Individual Requests**
1. Select "Redis Testing" environment
2. Navigate to any request
3. Click "Send"
4. Check test results in "Test Results" tab

**Option B: Collection Runner (Recommended)**
1. Click "Collections" → "Quizify Redis Health Check"
2. Click "Run" button
3. Select environment: "Redis Testing"
4. Click "Run Quizify Redis Health Check"
5. View test results for all requests

---

## Test Categories

### 1. Health Checks
Basic connectivity tests for application and Redis.

#### Basic Health Check
- **Endpoint:** `GET /health`
- **Purpose:** Verify application is running
- **Expected:** `200 OK` with `{"status": "ok"}`

#### Redis Health Check (Success)
- **Endpoint:** `GET /health/redis`
- **Purpose:** Verify Redis connection established
- **Expected:** `200 OK` with `{"connected": true, "latency_ms": X.XX}`
- **Tests:**
  - Status code is 200
  - Redis is connected
  - Latency < 100ms
  - No error field present

#### Redis Health Check (Expect Failure)
- **Endpoint:** `GET /health/redis`
- **Purpose:** Test fallback when Redis unavailable
- **Expected:** `503 Service Unavailable` with error message
- **When to use:**
  - Testing with `REDIS_ENABLED=false`
  - After pausing Redis service in Railway
  - Verifying graceful degradation

---

### 2. Performance Tests
Benchmarking and load testing for Redis.

#### Redis Latency Benchmark
- **Purpose:** Measure and classify Redis latency
- **Performance Tiers:**
  - **Excellent:** < 5ms (Railway internal network)
  - **Good:** < 10ms (acceptable for production)
  - **Acceptable:** < 50ms (may indicate network issues)
  - **Slow:** ≥ 50ms (investigate connection problems)
- **Features:**
  - Tracks latency over time (last 10 measurements)
  - Calculates average latency
  - Stores results in environment variables

#### Concurrent Health Checks
- **Purpose:** Test Redis under concurrent load
- **How to run:**
  1. Open Collection Runner
  2. Set Iterations: 10-50
  3. Set Delay: 0ms
  4. Run collection
- **What to observe:**
  - 100% success rate
  - Stable latency across requests
  - No connection pool exhaustion
  - Validates connection pool configuration (20 connections)

---

### 3. Environment Tests
Test Redis health across different environments.

#### Local Redis Health
- **URL:** `http://localhost:8000/health/redis`
- **Prerequisites:**
  - Docker Compose running: `docker-compose up -d`
  - App running: `uvicorn main:app --reload`
- **Expected:** Very low latency (< 5ms)

#### Staging Redis Health
- **URL:** `{{STAGING_URL}}/health/redis`
- **Prerequisites:**
  - Staging deployment in Railway
  - Redis service provisioned
- **Expected:** Railway internal network latency (1-5ms)

#### Production Redis Health
- **URL:** `{{PRODUCTION_URL}}/health/redis`
- **Prerequisites:**
  - Production deployment active
  - Redis service running
- **Expected:** Excellent latency (< 10ms)
- **⚠️ Note:** Run sparingly. Use Railway monitoring for continuous checks.

---

### 4. Epic 1 Verification Suite
Complete verification workflow for Epic 1 deployment.

**Run in sequence:**
1. **Verify App Is Running** - `GET /health`
2. **Verify Redis Connection** - `GET /health/redis`
3. **Verify Redis Performance** - Check latency < 100ms

**Success Criteria:**
- ✅ All 3 steps pass
- ✅ Redis connected with acceptable latency
- ✅ No errors in any response

**How to run:**
1. Set `BASE_URL` to target environment
2. Run folder "Epic 1 Verification Suite" in Collection Runner
3. All tests should pass with green checkmarks

---

## Environment Setup Examples

### Local Development
```json
{
  "BASE_URL": "http://localhost:8000",
  "STAGING_URL": "",
  "PRODUCTION_URL": ""
}
```

### Testing All Environments
```json
{
  "BASE_URL": "http://localhost:8000",
  "STAGING_URL": "https://quizify-staging.railway.app",
  "PRODUCTION_URL": "https://api.quizify.ca"
}
```

---

## Usage Scenarios

### Scenario 1: Local Development Verification
**Goal:** Verify Redis working locally before deployment
```
1. Start Redis: docker-compose up -d
2. Start app: uvicorn main:app --reload
3. Set BASE_URL to http://localhost:8000
4. Run "Epic 1 Verification Suite"
5. All tests should pass
```

### Scenario 2: Production Deployment Verification
**Goal:** Verify Epic 1 working in Railway production
```
1. Deploy redis-integration branch to Railway
2. Add Redis service in Railway dashboard
3. Set PRODUCTION_URL in Postman environment
4. Run "Production Redis Health" request
5. Verify 200 OK with low latency
```

### Scenario 3: Performance Benchmarking
**Goal:** Measure Redis latency over time
```
1. Select "Redis Latency Benchmark" request
2. Open Collection Runner
3. Set Iterations: 20
4. Set Delay: 100ms (to avoid rate limiting)
5. Run collection
6. View average latency in console output
```

### Scenario 4: Fallback Testing
**Goal:** Verify app survives Redis unavailability
```
1. Pause Redis service in Railway
2. Redeploy application
3. Run "Basic Health Check" - should pass (200 OK)
4. Run "Redis Health Check (Expect Failure)" - should pass (503)
5. Resume Redis service
6. Redeploy application
7. Run "Redis Health Check (Success)" - should pass (200 OK)
```

---

## Test Assertions

### All tests include:
- ✅ HTTP status code validation
- ✅ Response structure validation
- ✅ Response time thresholds
- ✅ Data type validation
- ✅ Business logic validation

### Example Test Output
```javascript
✅ Status code is 200
✅ Response has correct structure
✅ Redis is connected
✅ Latency is within acceptable range
✅ No error field present
✅ Response time is acceptable

Redis Latency: 1.23ms
✅ EXCELLENT: Redis latency 1.23ms (< 5ms)
Average latency (last 10 requests): 1.45ms
```

---

## Troubleshooting

### Issue: All requests fail with "Could not send request"
**Solution:**
- Verify app is running (check Railway dashboard or local terminal)
- Check BASE_URL is correct
- Verify network connectivity

### Issue: Redis health check returns 503
**Solution:**
- Check Redis service is running in Railway
- Verify `REDIS_URL` environment variable exists
- Check Railway logs for Redis connection errors
- Try setting `REDIS_ENABLED=true` explicitly

### Issue: High latency (> 50ms)
**Solution:**
- Verify Redis and app are in same Railway project
- Check Railway service region matches
- Verify using Railway internal network (redis.railway.internal)
- Check Redis service metrics for CPU/memory issues

### Issue: Tests pass locally but fail in production
**Solution:**
- Verify PRODUCTION_URL environment variable is correct
- Check Railway Redis service is provisioned
- Review Railway deployment logs
- Verify no Railway firewall blocking internal traffic

---

## Integration with CI/CD

### Newman (Postman CLI)
```bash
# Install Newman
npm install -g newman

# Run collection
newman run Quizify_Redis_Health_Check.postman_collection.json \
  -e Redis_Testing.postman_environment.json \
  --env-var "BASE_URL=https://your-app.railway.app"

# Run with JSON output
newman run Quizify_Redis_Health_Check.postman_collection.json \
  -e Redis_Testing.postman_environment.json \
  --reporters cli,json \
  --reporter-json-export results.json
```

### GitHub Actions Example
```yaml
name: Redis Health Check
on: [deployment_status]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Install Newman
        run: npm install -g newman
      - name: Run Redis Health Tests
        run: |
          newman run postman/Quizify_Redis_Health_Check.postman_collection.json \
            -e postman/Redis_Testing.postman_environment.json \
            --env-var "PRODUCTION_URL=${{ secrets.PRODUCTION_URL }}"
```

---

## Monitoring Recommendations

### Development
- Run health checks after code changes
- Monitor latency trends during development
- Test fallback scenarios regularly

### Staging
- Run full test suite before production deploy
- Benchmark performance weekly
- Test concurrent load scenarios

### Production
- Use Railway built-in monitoring (don't spam health endpoint)
- Set up alerts for Redis connection failures
- Run verification suite only after deployments
- Monitor latency trends via Railway metrics

---

## Related Documentation
- [Epic 1 Production Verification Guide](../docs/redis/EPIC_1_PRODUCTION_VERIFICATION.md)
- [Epic 1 Implementation Guide](../docs/redis/IMPLEMENTATION_GUIDE.md)
- [Redis Configuration Guide](../docs/redis/EPIC_1_COMPLETE.md)

---

## Support
For issues or questions:
1. Check [EPIC_1_PRODUCTION_VERIFICATION.md](../docs/redis/EPIC_1_PRODUCTION_VERIFICATION.md)
2. Review Railway logs
3. Run local tests with `docker-compose up -d`
4. Verify environment variables in Railway dashboard
