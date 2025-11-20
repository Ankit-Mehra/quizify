# Quizify API Deployment Guide

## Quick Start: Railway Deployment (Recommended)

### Prerequisites
- GitHub account
- Railway account (free tier available)
- Supabase project configured

### Step 1: Prepare Environment Variables

Create these in Railway dashboard after deployment:

```bash
SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_anon_key
SUPABASE_STORAGE_NAME=your_storage_bucket_name
OPENAI_API_KEY=your_openai_api_key
GEMINI_API_KEY=your_gemini_api_key  # Optional
BACKEND_CORS_ORIGINS=["https://your-frontend-domain.vercel.app"]
```

### Step 2: Deploy to Railway

1. **Go to Railway Dashboard**
   - Visit [railway.app](https://railway.app)
   - Click "New Project"
   - Select "Deploy from GitHub repo"

2. **Connect Repository**
   - Select your `quizify` backend repository
   - Railway will auto-detect Python and requirements.txt

3. **⚠️ CRITICAL: Select Region**
   - **MUST match your Supabase region** for optimal latency
   - Click Settings → Region
   - Options:
     - `us-west1` (Oregon) - if Supabase is `us-west-1` ✅ Recommended
     - `us-east4` (Virginia) - if Supabase is `us-east-1`
     - `europe-west1` (Belgium) - if Supabase is `eu-central-1`
   - **Impact**: Same region = 10ms latency, different region = 150ms+ ❌

4. **Configure Service**
   - Railway will automatically use the `Procfile`
   - Set Python version in dashboard: `3.12`
   - Add environment variables from Step 1

5. **Deploy**
   - Railway will build and deploy automatically
   - Get your deployment URL: `https://quizify-production.up.railway.app`

6. **Update CORS**
   - Update `BACKEND_CORS_ORIGINS` to include your frontend URL
   - Redeploy if needed

### Step 3: Test Deployment

```bash
# Test health endpoint
curl https://your-railway-url.up.railway.app/api/test

# View API docs
open https://your-railway-url.up.railway.app/docs
```

---

## Alternative: Render.com Deployment

### Create `render.yaml`

```yaml
services:
  - type: web
    name: quizify-api
    env: python
    region: oregon
    plan: free
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn main:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /api/test
    envVars:
      - key: PYTHON_VERSION
        value: 3.12.0
      - key: SUPABASE_URL
        sync: false
      - key: SUPABASE_KEY
        sync: false
      - key: OPENAI_API_KEY
        sync: false
      - key: BACKEND_CORS_ORIGINS
        value: '["https://your-frontend.vercel.app"]'
```

1. Push code to GitHub
2. Connect repo to Render dashboard
3. Add environment variables
4. Deploy!

**Note:** Free tier has cold starts (30s delay after inactivity).

---

## Alternative: Fly.io Deployment (Advanced)

### Prerequisites
```bash
# Install flyctl
brew install flyctl

# Login
flyctl auth login
```

### Setup
```bash
# Initialize fly app
flyctl launch

# Set secrets
flyctl secrets set SUPABASE_URL="your_url"
flyctl secrets set SUPABASE_KEY="your_key"
flyctl secrets set OPENAI_API_KEY="your_key"

# Deploy
flyctl deploy

# View logs
flyctl logs
```

Fly will use the `Dockerfile` in this repository.

---

## Environment Variables Reference

### Required
- `SUPABASE_URL` - Your Supabase project URL
- `SUPABASE_KEY` - Your Supabase anon/service key
- `SUPABASE_STORAGE_NAME` - Storage bucket name (e.g., "user-files")
- `OPENAI_API_KEY` - OpenAI API key for quiz generation

### ⚡ Performance Critical
- **Railway Region** - MUST match Supabase region (check Settings → Region)
- **Database Indexes** - Run migration SQL after first deployment (see Performance section)
- **Connection Pooling** - Enable in Supabase dashboard (Database → Connection Pooling)

### Optional
- `GEMINI_API_KEY` - Google Gemini API key (alternative to OpenAI)
- `BACKEND_CORS_ORIGINS` - JSON array of allowed origins (default: localhost)

### Auto-Set by Platform
- `PORT` - Set automatically by Railway/Render/Fly
- `TESTING` - Keep as "false" in production

---

## CI/CD Setup (Optional)

### GitHub Actions for Railway

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to Railway

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Install Railway CLI
        run: npm install -g @railway/cli
      
      - name: Deploy to Railway
        run: railway up
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}
```

---

## Monitoring & Logs

### Railway
- View logs in Railway dashboard
- Set up log alerts for errors
- Monitor resource usage

### Health Check Endpoint
```bash
# Check if API is running
curl https://your-api-url.com/api/test

# Check API documentation
open https://your-api-url.com/docs
```

---

## Performance Optimization (Critical!)

### Immediate Actions (Before Launch)

#### 1. Verify Region Co-Location ✅
```bash
# Check Railway region matches Supabase
# Railway: Settings → Region (should be us-west1 if Supabase is us-west-1)
# Impact: 10ms vs 150ms+ database latency
```

#### 2. Add Database Indexes ✅
```sql
-- Run in Supabase SQL Editor
CREATE INDEX IF NOT EXISTS idx_quizzes_user_created 
ON quizzes(created_by, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_questions_quiz 
ON questions(quiz_id);

CREATE INDEX IF NOT EXISTS idx_user_files_user 
ON user_files(user_id, uploaded_at DESC);

CREATE INDEX IF NOT EXISTS idx_submissions_user 
ON submissions(user_id, submitted_at DESC);

-- Impact: 50-100ms → 5-15ms query time
```

#### 3. Enable Connection Pooling ✅
```bash
# In Supabase Dashboard:
# 1. Go to Database → Connection Pooling
# 2. Enable "Transaction" mode
# 3. Copy pooler connection string (port 6543)
# 4. Update SUPABASE_URL in Railway to use port 6543

# Impact: 20-50ms → 5-10ms connection overhead
```

#### 4. Add Performance Monitoring
```python
# Already configured in middleware/auto_refresh.py
# Logs request times automatically
# Check Railway logs for slow requests (>1s)
```

### Expected Latency After Optimization

| Operation | Before | After | Improvement |
|-----------|--------|-------|-------------|
| Login | 250ms | 120ms | 52% faster ✅ |
| Get Quizzes | 180ms | 95ms | 47% faster ✅ |
| Quiz Gen (GPT-4) | 18s | 12s | 33% faster ✅ |
| Quiz Gen (GPT-3.5) | - | 3.5s | 71% faster ✅✅ |

See `LATENCY_ANALYSIS.md` for detailed breakdown.

---

## Scaling Considerations

### Current Architecture
- Stateless API (can scale horizontally)
- External database (Supabase)
- External file storage (Supabase Storage)
- AI services (OpenAI/Gemini) scale automatically

### When to Scale
- **Railway**: Automatically scales within plan limits
- **Free tier**: 500-750 hours/month (sufficient for MVP)
- **Upgrade when**: >1000 daily active users

### Advanced Optimization (Month 2+)
1. Add Redis for caching (Upstash: $5/month)
2. Implement streaming quiz generation (perceived latency: 15s → 2s)
3. Switch to GPT-3.5-turbo for 70% faster generation
4. Enable Supabase read replicas (Pro plan)

---

## Cost Estimates

### MVP (First 6 Months)

**Backend:**
- **Railway**: $0-10/month (500 hours free, then usage-based)
- **Supabase**: $0-25/month (free tier → Pro plan)
- **OpenAI API**: $10-50/month (usage-based, ~$0.002 per 1K tokens for GPT-3.5)

**Frontend:**
- **Vercel**: $0/month (Hobby plan - 100GB bandwidth, unlimited deployments)

**Total**: ~$10-85/month

### Growth Phase (1,000-5,000 users)

**Backend:**
- **Railway**: $20-50/month (increased usage)
- **Supabase**: $25-100/month (Pro plan with more storage/bandwidth)
- **OpenAI API**: $100-500/month (higher quiz generation volume)

**Frontend:**
- **Vercel**: $0-20/month (Hobby plan usually sufficient, Pro $20/month if needed)

**Total**: ~$145-670/month

### Scale Phase (10,000+ users)

**Backend:**
- **Railway**: $50-150/month (or migrate to dedicated infrastructure)
- **Supabase**: $100-500/month (Pro/Team plan with read replicas)
- **OpenAI API**: $500-2,000/month (high volume)
- **Redis Cache**: $5-20/month (Upstash or similar)

**Frontend:**
- **Vercel**: $20/month (Pro plan - 1TB bandwidth)

**Total**: ~$675-2,690/month

### Cost Breakdown by Service

| Service | Free Tier | Paid Tier | What You Get |
|---------|-----------|-----------|--------------|
| **Railway** | $5 credit/month | $0.000463/GB-hour | Auto-deploy, logs, metrics |
| **Supabase** | 500MB DB, 1GB storage | $25/month (Pro) | 8GB DB, 100GB storage, daily backups |
| **Vercel** | 100GB bandwidth | $20/month (Pro) | 1TB bandwidth, priority support |
| **OpenAI GPT-3.5** | Pay-per-use | $0.002/1K tokens | Fast generation (3-5s) |
| **OpenAI GPT-4** | Pay-per-use | $0.03/1K tokens | High quality (12-15s) |

### Cost Optimization Tips

1. **Start with GPT-3.5-turbo** - 15x cheaper than GPT-4, 70% faster
2. **Use Vercel free tier** - 100GB is plenty for MVP (text/JSON responses only)
3. **Cache responses** - Reduce database queries and API calls
4. **Monitor usage** - Set up billing alerts in each service
5. **Optimize prompts** - Shorter prompts = lower OpenAI costs

---

## Troubleshooting

### Common Issues

**1. Module Import Errors**
```bash
# Ensure all dependencies in requirements.txt
# Check Python version matches (3.12)
```

**2. CORS Errors**
```bash
# Update BACKEND_CORS_ORIGINS to include frontend URL
# Format: ["https://frontend.vercel.app"]
```

**3. Database Connection Errors**
```bash
# Verify SUPABASE_URL and SUPABASE_KEY
# Check Supabase project status
```

**4. File Upload Failures**
```bash
# Verify SUPABASE_STORAGE_NAME matches bucket name
# Check storage permissions in Supabase dashboard
```

**5. Cold Starts (Render free tier)**
```bash
# Implement keep-alive pinger
# Upgrade to paid tier
# Switch to Railway
```

---

## Security Checklist

- [ ] All secrets in environment variables (not in code)
- [ ] CORS configured for production frontend only
- [ ] Supabase Row Level Security (RLS) enabled
- [ ] API rate limiting implemented
- [ ] HTTPS enabled (automatic on Railway/Render/Fly)
- [ ] File upload size limits enforced (10MB)
- [ ] Input validation on all endpoints
- [ ] JWT token expiration configured

---

## Next Steps After Deployment

1. **Test all endpoints** using production URL
2. **Update frontend** with new API URL
3. **Set up monitoring** (Railway dashboard or external)
4. **Configure custom domain** (optional)
5. **Enable automatic deployments** from main branch
6. **Set up staging environment** (optional)

---

## Support

- Railway: [docs.railway.app](https://docs.railway.app)
- Render: [render.com/docs](https://render.com/docs)
- Fly.io: [fly.io/docs](https://fly.io/docs)
- Supabase: [supabase.com/docs](https://supabase.com/docs)
