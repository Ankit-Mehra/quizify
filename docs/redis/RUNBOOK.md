# Redis Integration Operational Runbook

**Version**: 1.0  
**Last Updated**: November 18, 2025  
**Status**: Production  
**Audience**: DevOps, SRE, On-Call Engineers

---

## 📋 Quick Reference

### Critical Contacts
- **Primary Owner**: Backend Team
- **On-Call**: [Your On-Call Schedule]
- **Redis Provider**: Railway (Managed Redis)

### Health Check URLs
- **Production**: `https://your-app.railway.app/health/redis` (**admin only**)
- **Staging**: `https://your-app-staging.railway.app/health/redis` (**admin only**)
- **Detailed Info**: `/health/redis/info` (**admin only**)

**Note**: All Redis health endpoints now require admin authentication for security.

### Key Performance Indicators (KPIs)
- **Latency**: <5ms (Target), <10ms (Acceptable), >10ms (Action Required)
- **Hit Rate**: >80% (Target), >60% (Acceptable), <60% (Action Required)
- **Memory Usage**: <100MB (Target), <200MB (Acceptable), >200MB (Action Required)
- **Uptime**: 99.9% (Target)

---

## 🚨 Incident Response

### P0: Redis Completely Unavailable

**Symptoms**:
- `/health/redis` returns 503
- `fallback_mode: true` in health response
- Logs show "Redis client not available"

**Impact**: **LOW** - Application automatically falls back to memory cache
- Performance degraded but service remains operational
- Database load increases slightly
- No user-facing errors

**Immediate Actions**:
1. Verify application is using memory fallback (check logs)
2. Check Railway Redis service status
3. Review Redis connection configuration

**Resolution Steps**:
```bash
# 1. Check Railway Redis status
railway status

# 2. View Redis logs
railway logs --service redis

# 3. Restart Redis if needed
railway restart --service redis

# 4. Verify connectivity
curl https://your-app.railway.app/health/redis
```

**Rollback Plan**: No rollback needed - memory fallback handles this automatically

**Post-Incident**:
- Review why Redis became unavailable
- Check for Railway service incidents
- Validate memory fallback worked as expected
- Monitor for repeat occurrences

---

### P1: High Redis Latency (>10ms)

**Symptoms**:
- `/health/redis` shows `latency_ms > 10`
- Slow API response times
- User complaints about performance

**Impact**: **MEDIUM** - Service functional but degraded performance

**Investigation**:
```bash
# 1. Check current latency
curl https://your-app.railway.app/health/redis | jq '.latency_ms'

# 2. Check Redis server load
curl -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  https://your-app.railway.app/health/redis/info | jq '.performance'

# 3. View Railway metrics
railway metrics --service redis
```

**Common Causes**:
- High Redis memory usage (>80%)
- Network issues between Railway services
- High number of concurrent connections
- Large value sizes being cached

**Resolution**:
```bash
# If memory is high, clear old caches
# Admin endpoint to flush pattern:
curl -X DELETE \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  https://your-app.railway.app/admin/cache?pattern=old_*

# Or connect to Redis directly
railway redis-cli
> INFO memory
> FLUSHDB  # Nuclear option - clears all caches
```

**Escalation**: If latency remains >10ms after 30 minutes, escalate to Railway support

---

### P1: Low Cache Hit Rate (<60%)

**Symptoms**:
- `/health/redis` shows `app_hit_rate_percent < 60`
- Increased database load
- Slower API responses

**Impact**: **MEDIUM** - Performance degraded, increased costs

**Investigation**:
```bash
# Check cache statistics
curl https://your-app.railway.app/health/redis | jq '.cache_stats'

# Expected output:
# {
#   "app_cache_hits": 400,
#   "app_cache_misses": 200,  # Should be lower
#   "app_hit_rate_percent": 66.7
# }
```

**Common Causes**:
- TTLs too short (caches expiring too quickly)
- Cache invalidation too aggressive
- Unusual access patterns (cold start, new deployment)
- Redis memory limit reached (eviction policy active)

**Resolution**:
1. **Wait 30 minutes** after deployment (cache warmup period)
2. Check memory usage - if >80%, increase Railway Redis plan
3. Review recent code changes for cache invalidation logic
4. Consider increasing TTLs in configuration:

```python
# config.py adjustments (requires deployment)
REDIS_USER_TIER_TTL = 600  # Increase from 300s to 600s
REDIS_QUIZ_METADATA_TTL = 3600  # Increase from 1800s to 3600s
```

**Escalation**: If hit rate stays <60% after 4 hours, escalate to backend team

---

### P2: High Memory Usage (>200MB)

**Symptoms**:
- `/health/redis` shows `memory.used_mb > 200`
- Redis evicting keys prematurely
- Hit rate declining

**Impact**: **LOW-MEDIUM** - May cause performance degradation if keys evicted

**Investigation**:
```bash
# Check memory details
curl -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  https://your-app.railway.app/health/redis/info | jq '.memory'

# Check eviction count
curl -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  https://your-app.railway.app/health/redis/info | jq '.data.evicted_keys'
```

**Common Causes**:
- Caching too many large objects
- TTLs too long (data not expiring)
- Unexpected usage spike
- Memory leak in application

**Resolution**:
1. **Short-term**: Flush specific cache patterns
   ```bash
   # Clear old or large caches
   railway redis-cli
   > KEYS quiz_metadata:*
   > DEL quiz_metadata:large_quiz_id
   ```

2. **Medium-term**: Adjust TTLs
   - Reduce TTLs for large objects
   - Implement cache size limits

3. **Long-term**: Upgrade Railway Redis plan
   ```bash
   railway upgrade --service redis --plan performance-8
   ```

**Escalation**: If memory stays >200MB and evictions increase, upgrade plan

---

## 🔍 Monitoring & Alerts

### Recommended Alerts

#### Critical Alerts (P0)
```yaml
- alert: RedisDown
  expr: redis_up == 0
  for: 2m
  labels:
    severity: critical
  annotations:
    summary: "Redis is down - application using memory fallback"
    action: "Check Railway Redis status, restart if needed"
```

#### Warning Alerts (P1)
```yaml
- alert: RedisHighLatency
  expr: redis_latency_ms > 10
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Redis latency high (>10ms)"
    action: "Investigate Redis server load and network"

- alert: RedisCacheHitRateLow
  expr: redis_cache_hit_rate < 60
  for: 30m
  labels:
    severity: warning
  annotations:
    summary: "Cache hit rate below 60%"
    action: "Check TTL configuration and cache warmup"

- alert: RedisMemoryHigh
  expr: redis_memory_used_percent > 80
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "Redis memory usage >80%"
    action: "Consider flushing old caches or upgrading plan"
```

### Monitoring Dashboard

Create a dashboard with these metrics:
- **Latency**: PING, GET, SET operation times
- **Hit Rate**: Cache hits vs misses (percentage)
- **Memory**: Used MB, percentage of limit
- **Throughput**: Operations per second
- **Connections**: Active connections, rejected connections
- **Errors**: Failed operations, connection errors

---

## 🛠️ Common Maintenance Tasks

### 1. Clear All Caches (Nuclear Option)

**When**: After major data migration, schema changes, or during debugging

```bash
# WARNING: This clears ALL cached data
# Application will experience temporary slowdown while cache warms up

# Via Railway CLI
railway redis-cli FLUSHDB

# Verify
railway redis-cli DBSIZE  # Should return 0
```

**Impact**: 
- Immediate: Cache hit rate drops to 0%
- 5-10 minutes: Hit rate recovers to ~40-60%
- 30 minutes: Hit rate returns to normal (>80%)

---

### 2. Clear Specific Cache Pattern

**When**: After updating specific data (e.g., user tiers, quiz metadata)

```bash
# Example: Clear all user tier caches
railway redis-cli
> KEYS user_tier:*
> DEL user_tier:user_123
> DEL user_tier:user_456

# Or use SCAN for large keyspaces (safer)
> SCAN 0 MATCH user_tier:* COUNT 100
```

**Admin API** (recommended):
```bash
# Requires admin authentication
curl -X DELETE \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  https://your-app.railway.app/admin/cache/invalidate \
  -d '{"pattern": "user_tier:*"}'
```

---

### 3. Monitor Cache Performance

**Daily Check** (5 minutes):
```bash
# Get health status
curl https://your-app.railway.app/health/redis | jq '.'

# Check for:
# - latency_ms < 5
# - app_hit_rate_percent > 80
# - memory.used_percent < 50
# - status: "healthy"
```

**Weekly Review** (15 minutes):
```bash
# Get detailed metrics
curl -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  https://your-app.railway.app/health/redis/info

# Review trends:
# - Total commands processed (should grow)
# - Evicted keys (should be near 0)
# - Memory fragmentation (should be < 1.5)
```

---

### 4. Adjust TTLs for Performance

**When**: Cache hit rate consistently below target or memory usage high

**Current TTLs**:
- User tiers: 300 seconds (5 minutes)
- Quiz metadata: 1800 seconds (30 minutes)

**Adjustment Strategy**:
```python
# config.py

# Option 1: Increase TTL if hit rate is low
REDIS_USER_TIER_TTL = 600  # 10 minutes (from 5)
REDIS_QUIZ_METADATA_TTL = 3600  # 1 hour (from 30 min)

# Option 2: Decrease TTL if memory usage is high
REDIS_USER_TIER_TTL = 180  # 3 minutes (from 5)
REDIS_QUIZ_METADATA_TTL = 900  # 15 minutes (from 30 min)
```

**Deployment**: Requires code change and deployment

---

### 5. Upgrade Redis Plan

**When**: 
- Memory usage consistently >150MB
- Eviction count increasing
- Planning for significant user growth

**Steps**:
```bash
# View current plan
railway info --service redis

# Upgrade to next tier
railway upgrade --service redis --plan performance-8

# Verify upgrade
railway info --service redis
```

**Downtime**: None - Railway handles this automatically

---

## 📊 Performance Baselines

### Normal Operating Conditions

| Metric | Value | Status |
|--------|-------|--------|
| Latency | 1-5ms | ✅ Healthy |
| Hit Rate | 80-90% | ✅ Healthy |
| Memory Usage | 10-50MB | ✅ Healthy |
| Ops/sec | 20-100 | ✅ Healthy |
| Connections | 5-20 | ✅ Healthy |

### Warning Thresholds

| Metric | Value | Status |
|--------|-------|--------|
| Latency | 5-10ms | ⚠️ Monitor |
| Hit Rate | 60-80% | ⚠️ Monitor |
| Memory Usage | 50-150MB | ⚠️ Monitor |
| Ops/sec | 100-200 | ⚠️ Monitor |
| Connections | 20-50 | ⚠️ Monitor |

### Critical Thresholds

| Metric | Value | Status |
|--------|-------|--------|
| Latency | >10ms | 🚨 Action Required |
| Hit Rate | <60% | 🚨 Action Required |
| Memory Usage | >150MB | 🚨 Action Required |
| Ops/sec | >200 | 🚨 Action Required |
| Connections | >50 | 🚨 Action Required |

---

## 🔄 Deployment Procedures

### Standard Deployment

**Pre-Deployment**:
1. Announce deployment in team channel
2. Note current cache hit rate for comparison

**During Deployment**:
1. Deploy code changes
2. Monitor `/health/redis` for connectivity
3. Watch for memory fallback activation

**Post-Deployment** (15 minutes):
1. Verify Redis connection restored
2. Monitor cache warmup (hit rate recovery)
3. Check for errors in logs
4. Validate performance improvements

**Expected Behavior**:
- Hit rate drops to 0-20% immediately after deploy
- Recovers to 60-80% within 10 minutes
- Returns to normal (>80%) within 30 minutes

---

### Emergency Rollback

**Scenario**: New deployment causes Redis issues

```bash
# 1. Rollback application code
railway rollback --service web

# 2. Verify Redis health
curl https://your-app.railway.app/health/redis

# 3. Clear bad cache data if needed
railway redis-cli FLUSHDB

# 4. Monitor recovery
watch -n 5 'curl -s https://your-app.railway.app/health/redis | jq .'
```

**Validation**:
- Application health: `status: "healthy"`
- Redis connection: `connected: true`
- Fallback mode: `fallback_mode: false`
- Latency: `latency_ms < 10`

---

### Enabling/Disabling Redis

**Disable Redis** (use memory fallback only):
```bash
railway variables set REDIS_ENABLED=false
railway restart --service web
```

**Re-enable Redis**:
```bash
railway variables set REDIS_ENABLED=true
railway restart --service web
```

**Use Case**: Temporary Redis issues, testing fallback mode, cost reduction during low traffic

---

## 🧪 Testing in Production

### Smoke Tests

**After any change**:
```bash
# 1. Basic health check (public)
curl https://your-app.railway.app/health
# Expected: {"status": "ok"}

# 2. Redis health check (admin only)
curl -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  https://your-app.railway.app/health/redis
# Expected: {"status": "healthy", "connected": true}

# 3. Test API endpoint (requires user auth)
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://your-app.railway.app/api/quizzes/YOUR_QUIZ_ID
# Expected: 200 OK with quiz data
```

### Load Testing

**Simulate traffic spike**:
```bash
# Use Apache Bench or similar tool
ab -n 1000 -c 10 https://your-app.railway.app/api/quizzes/test_id

# Monitor during test:
watch -n 2 'curl -s https://your-app.railway.app/health/redis | jq ".cache_stats"'
```

**Expected Results**:
- Hit rate increases from ~20% → 80% during test
- Latency remains <5ms
- No errors or timeouts

---

## 📚 Additional Resources

### Internal Documentation
- **Implementation Guide**: `docs/redis/IMPLEMENTATION_GUIDE.md`
- **Architecture Guide**: `docs/redis/REDIS_COMPLETE_ARCHITECTURE.md`
- **Benchmarks**: `specs/006-redis-integration/BENCHMARKS.md`
- **Testing Guide**: `docs/redis/CACHE_TESTING_GUIDE.md`

### External Resources
- [Railway Redis Documentation](https://docs.railway.app/databases/redis)
- [Redis Documentation](https://redis.io/docs/)
- [Redis Best Practices](https://redis.io/docs/manual/patterns/)

### Training Materials
- [Redis Integration Overview](./REDIS_ARCHITECTURE_GUIDE.md)
- [Troubleshooting Guide](./REDIS_TESTING_NEXT_STEPS.md)

---

## 📞 Escalation Path

1. **Level 1**: On-call engineer (use this runbook)
2. **Level 2**: Backend team lead (if issue persists >30 minutes)
3. **Level 3**: Railway support (for infrastructure issues)
4. **Level 4**: Engineering manager (for critical production impact)

### Escalation Criteria
- **Immediate**: Redis down AND memory fallback failing
- **Within 30 minutes**: Redis latency >20ms consistently
- **Within 1 hour**: Cache hit rate <40% for >1 hour
- **Within 4 hours**: Memory usage >200MB consistently

---

## ✅ Runbook Maintenance

**Review Schedule**: Quarterly or after major incidents

**Last Reviewed**: November 18, 2025  
**Next Review**: February 18, 2026  
**Owner**: Backend Team

**Change Log**:
- 2025-11-18: Initial version (Epic 5 complete)

---

**Runbook Status**: ✅ Production Ready  
**Validation**: Tested in staging + production  
**Confidence Level**: High
