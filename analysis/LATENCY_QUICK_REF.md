# Latency Quick Reference Card

## 🎯 TL;DR

**Your app with proper setup:**
- Authentication: **~120ms**
- Get quizzes: **~95ms** 
- Quiz generation: **~12s** (GPT-4) or **~3.5s** (GPT-3.5)
- File upload: **~1.2s**

**Critical for performance:** Railway and Supabase MUST be in the same region!

---

## 🌍 Regional Latency at a Glance

### Same Region (✅ Optimal)
```
User → Vercel Edge: 20ms
Vercel → Railway: 15ms
Railway → Supabase: 10ms ⚡ KEY!
Railway → OpenAI: 80ms
─────────────────────────
Total (non-AI ops): ~125ms ✅✅✅
```

### Cross-Region (❌ Poor)
```
User → Vercel Edge: 20ms
Vercel → Railway: 15ms
Railway → Supabase: 150ms ⚠️ SLOW!
Railway → OpenAI: 80ms
─────────────────────────
Total (non-AI ops): ~265ms ⚠️
```

### Impact: **2x slower!**

---

## 📍 Region Pairing Guide

| Your Users Mostly In | Railway Region | Supabase Region |
|---------------------|---------------|----------------|
| �🇦 Canada (ON/QC) | `us-east4` | `us-east-1` ✅ ⭐ |
| 🇨🇦 Canada (BC/AB) | `us-west1` | `us-west-1` ✅ |
| �🇺🇸 USA (General) | `us-west1` | `us-west-1` ✅ |
| 🇺🇸 West Coast | `us-west1` | `us-west-1` ✅ |
| 🇺🇸 East Coast | `us-east4` | `us-east-1` ✅ |
| 🇪🇺 Europe | `europe-west1` | `eu-central-1` ✅ |
| 🌏 Asia | `asia-southeast1` | `ap-southeast-1` ✅ |

**Golden Rule:** Railway region number MUST match Supabase region number!

**🇨🇦 Canadian Launch?** See `CANADA_DEPLOYMENT.md` for detailed guide!

---

## ⚡ 3 Quick Wins (30 Minutes Total)

### 1. Same Region (5 minutes)
```bash
# In Railway Dashboard:
Settings → Region → Select us-west1 (if Supabase is us-west-1)
```
**Impact:** Database queries **10x faster** (150ms → 10ms)

### 2. Database Indexes (10 minutes)
```sql
-- Run in Supabase SQL Editor:
CREATE INDEX idx_quizzes_user_created ON quizzes(created_by, created_at DESC);
CREATE INDEX idx_questions_quiz ON questions(quiz_id);
CREATE INDEX idx_user_files_user ON user_files(user_id, uploaded_at DESC);
```
**Impact:** Queries **5x faster** (100ms → 15ms)

### 3. Connection Pooling (15 minutes)
```bash
# In Supabase Dashboard:
Database → Connection Pooling → Enable "Transaction" mode
# Update SUPABASE_URL in Railway to use port 6543
```
**Impact:** **50% faster** connection overhead (50ms → 10ms)

---

## 🚀 Performance by Operation

| Operation | Latency | Bottleneck | Quick Fix |
|-----------|---------|-----------|-----------|
| **Login** | 120ms | Supabase auth | ✅ Already optimal |
| **Get Quizzes** | 95ms | DB query | Add indexes ↑ |
| **File Upload** | 1.2s | Network transfer | Use presigned URLs |
| **Quiz Gen (GPT-4)** | 12s | OpenAI processing | Switch to GPT-3.5 ↓ |
| **Quiz Gen (GPT-3.5)** | 3.5s | OpenAI processing | Enable streaming |

---

## 🎨 Architecture Diagram

```
┌─────────┐
│  User   │ San Francisco user
└────┬────┘
     │ 15ms (to nearest edge)
     ▼
┌─────────────┐
│Vercel Edge  │ Global CDN
│  (Static)   │
└─────┬───────┘
      │ 10ms (same region)
      ▼
┌──────────────┐
│Railway       │ us-west1 (Oregon) ⚡
│(FastAPI)     │
└──┬───────┬───┘
   │       │
   │ 8ms   │ 80ms
   ▼       ▼
┌─────┐ ┌──────┐
│Supa │ │OpenAI│
│base │ │ API  │
└─────┘ └──────┘
us-west-1  ✅ Same region = FAST!
```

---

## 📊 Latency Breakdown by Scenario

### Scenario A: Login (120ms total)
```
User types credentials
  → Vercel Edge: 15ms
  → Railway API: 10ms
  → Supabase Auth: 80ms (JWT verification + DB lookup)
  → Response back: 15ms
= 120ms ✅
```

### Scenario B: View Quizzes (95ms total)
```
User clicks "My Quizzes"
  → Vercel Edge: 15ms
  → Railway API: 10ms
  → Supabase DB Query: 55ms (with indexes: 12ms ✅)
  → Response back: 15ms
= 95ms ✅ (or 37ms with indexes!)
```

### Scenario C: Generate Quiz (12,000ms total)
```
User submits content
  → Vercel Edge: 15ms
  → Railway API: 10ms
  → OpenAI GPT-4: 11,800ms ⚠️ SLOW!
  → Save to DB: 50ms
  → Response back: 125ms
= 12,000ms (12 seconds)

With GPT-3.5: 3,500ms (3.5 seconds) ✅✅
With Streaming: 2,000ms to first question ✅✅✅
```

---

## 🔥 Common Mistakes & Fixes

### ❌ Mistake 1: Wrong Region Pairing
```
Railway: us-west1
Supabase: eu-central-1
= 150ms+ database latency ❌
```
**Fix:** Move both to same region
**Time:** 5 minutes (redeploy)

### ❌ Mistake 2: No Database Indexes
```
Query: SELECT * FROM quizzes WHERE created_by = '...'
Time: 100ms+ ❌
```
**Fix:** Add index on `created_by`
**Time:** 10 minutes (run SQL)

### ❌ Mistake 3: Direct Database Connections
```
Connection overhead: 50ms per request ❌
```
**Fix:** Enable Supabase connection pooling
**Time:** 15 minutes (config change)

### ❌ Mistake 4: Using GPT-4 for Everything
```
Generation time: 12-15 seconds ❌
```
**Fix:** Switch to GPT-3.5-turbo
**Time:** 1 hour (code change)
**Bonus:** Also cheaper! ($0.002 vs $0.03 per 1K tokens)

---

## 📈 Performance Goals

### MVP (Your Target)
- ✅ Login: <200ms
- ✅ Get Quizzes: <150ms
- ✅ File Upload: <2s
- ✅ Quiz Gen: <15s

### Optimized (Month 2)
- ✅ Login: <100ms (with caching)
- ✅ Get Quizzes: <50ms (with caching)
- ✅ File Upload: <1s (presigned URLs)
- ✅ Quiz Gen: <5s (GPT-3.5) or 2s perceived (streaming)

### Production (Month 6)
- ✅ All operations: <100ms (multi-region)
- ✅ Quiz Gen: <3s globally (streaming + edge)

---

## 🛠️ Monitoring Latency

### Check in Railway Logs
```bash
railway logs --tail

# Look for:
[INFO] GET /api/quiz/my-quizzes - 0.095s ✅
[WARN] POST /api/quiz/generate - 12.5s ⚠️
[ERROR] GET /api/auth/login - 2.5s ❌ (investigate!)
```

### Add to Every Response
```bash
# Check response headers:
curl -I https://your-api.up.railway.app/api/test

# Look for:
X-Process-Time: 0.123  # 123ms
```

### Set Up Alerts
```bash
# In Railway dashboard:
Settings → Notifications
- Alert when response time > 1s
- Alert when error rate > 5%
```

---

## 💰 Cost vs Performance

| Configuration | Cost/Month | Latency (US) | Latency (EU) |
|--------------|-----------|-------------|-------------|
| **Single Region** | $5-35 | 100ms ✅ | 300ms ⚠️ |
| **+ Optimization** | $35-45 | 50ms ✅✅ | 250ms ✅ |
| **Multi-Region** | $75-150 | 100ms ✅ | 100ms ✅ |

**Recommendation for MVP:** Single Region + Optimization = Best value

---

## 🎯 Action Checklist

### Before Launch (30 min)
- [ ] Deploy Railway in same region as Supabase
- [ ] Add database indexes (run SQL)
- [ ] Enable connection pooling
- [ ] Test latency with `curl -w "\nTime: %{time_total}s\n"`

### Week 1 After Launch
- [ ] Monitor Railway logs for slow requests
- [ ] Check p95/p99 latencies
- [ ] Identify bottlenecks

### Month 1
- [ ] Switch to GPT-3.5-turbo (if quality acceptable)
- [ ] Add response caching for quiz lists
- [ ] Implement pagination

### Month 2+
- [ ] Implement streaming quiz generation
- [ ] Add Redis caching layer
- [ ] Consider multi-region (if international users)

---

## 📞 When to Worry

### 🟢 Green: Everything Normal
- p95 latency under targets
- No user complaints
- Railway logs show <1s for most requests

### 🟡 Yellow: Monitor Closely
- p95 occasionally over target
- Some user complaints about "slow"
- Railway logs show 1-2s for some requests

### 🔴 Red: Action Required
- p95 consistently over target
- Multiple user complaints
- Railway logs show >2s frequently
- Timeouts occurring

**Action:** Check `LATENCY_ANALYSIS.md` for debugging guide

---

## 📚 Full Documentation

- **Detailed Analysis:** `LATENCY_ANALYSIS.md` (20+ pages)
- **Deployment Guide:** `DEPLOYMENT.md`
- **Monorepo Analysis:** `MONOREPO_ANALYSIS.md`
- **Quick Start:** `DEPLOYMENT_CHECKLIST.md`

---

**Remember:** The #1 performance killer is **wrong region pairing**! 
Railway + Supabase in same region = 10ms
Railway + Supabase in different regions = 150ms+

**Get the region right, everything else is optimization!** 🚀

---

**Last Updated:** 2025-10-05
