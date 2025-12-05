# 🚀 Quick Deployment Checklist

Use this checklist to deploy your Quizify API in under 30 minutes.

---

## ✅ Pre-Deployment Checklist

### 1. Code Preparation
- [x] `Procfile` exists (✅ created)
- [x] `runtime.txt` exists (✅ created)
- [x] `Dockerfile` exists (✅ created, optional)
- [ ] All secrets moved to `.env` (not hardcoded)
- [ ] `.env.example` up to date
- [ ] `requirements.txt` includes all dependencies
- [ ] Tests passing: `pytest tests/ -v`

### 2. Environment Variables Ready
- [ ] `SUPABASE_URL`
- [ ] `SUPABASE_KEY`
- [ ] `SUPABASE_STORAGE_NAME`
- [ ] `OPENAI_API_KEY`
- [ ] `GEMINI_API_KEY` (optional)
- [ ] `BACKEND_CORS_ORIGINS` (will update after frontend deployment)

### 3. Supabase Configuration
- [ ] Database tables created
- [ ] Row Level Security (RLS) policies enabled
- [ ] Storage bucket created and public access configured
- [ ] Auth providers enabled (email/password minimum)

---

## 🎯 Deployment: Railway (Recommended - 15 minutes)

### Step 1: Create Railway Account
1. Go to [railway.app](https://railway.app)
2. Sign up with GitHub
3. No credit card needed for free tier

### Step 2: Deploy from GitHub
1. Click **"New Project"**
2. Select **"Deploy from GitHub repo"**
3. Choose your `quizify` repository
4. Railway auto-detects Python and requirements.txt ✅

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

**🇨🇦 For Canadian Launch:**
- See `CANADA_DEPLOYMENT.md` for Canada-specific setup
- Use `us-east4` (Virginia) for Railway
- Use `us-east-1` (Virginia) for Supabase
- Best for Toronto/Montreal/Ontario/Quebec users (70% of Canada)

### Step 4: Deploy
1. Railway automatically builds and deploys
2. Wait 2-3 minutes for build to complete
3. Get your public URL: `https://quizify-production.up.railway.app`

### Step 5: Test Deployment
```bash
# Test health endpoint
curl https://YOUR-RAILWAY-URL.up.railway.app/api/test

# Expected response:
{"message": "API is working"}
```

### Step 6: View API Documentation
Open: `https://YOUR-RAILWAY-URL.up.railway.app/docs`

### Step 7: Update CORS for Frontend
Once frontend is deployed, update `BACKEND_CORS_ORIGINS`:
```json
["https://your-frontend.vercel.app"]
```

**✅ Backend Deployed!**

---

## 🎨 Next: Deploy Frontend (20 minutes)

### Option A: Vercel (Recommended for Next.js)

1. **Create Frontend Repo**
   ```bash
   npx create-next-app@latest quizify-frontend
   cd quizify-frontend
   ```

2. **Install Dependencies**
   ```bash
   npm install axios swr
   npm install --save-dev openapi-typescript
   ```

3. **Configure API Client**
   Create `.env.local`:
   ```bash
   NEXT_PUBLIC_API_URL=https://YOUR-RAILWAY-URL.up.railway.app
   ```

4. **Generate Types from OpenAPI**
   Add to `package.json`:
   ```json
   "scripts": {
     "generate-types": "openapi-typescript $NEXT_PUBLIC_API_URL/openapi.json -o src/types/api.ts",
     "dev": "npm run generate-types && next dev"
   }
   ```

5. **Deploy to Vercel**
   ```bash
   # Install Vercel CLI
   npm i -g vercel
   
   # Deploy
   vercel
   
   # Follow prompts
   # Get URL: https://quizify.vercel.app
   ```

6. **Update Backend CORS**
   In Railway, update `BACKEND_CORS_ORIGINS`:
   ```json
   ["https://quizify.vercel.app"]
   ```

**✅ Full Stack Deployed!**

---

## 🔍 Post-Deployment Verification

### Test All Endpoints

```bash
# Set your API URL
export API_URL="https://YOUR-RAILWAY-URL.up.railway.app"

# 1. Test health check
curl $API_URL/api/test

# 2. Test signup
curl -X POST $API_URL/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "testpass123",
    "name": "Test User"
  }'

# 3. Test login (save token)
curl -X POST $API_URL/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "testpass123"
  }'

# 4. Test authenticated endpoint (use token from login)
curl $API_URL/api/quiz/my-quizzes \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

### Check Logs

**Railway:**
1. Go to Railway dashboard
2. Select your project
3. Click **"Deployments"** → Latest deployment
4. View real-time logs

**Look for:**
- ✅ `"Application startup complete"`
- ✅ `"Uvicorn running on http://0.0.0.0:8000"`
- ❌ Any Python errors or import failures

---

## 🐛 Common Issues & Fixes

### Issue 1: Module Import Errors
```
Error: No module named 'fastapi'
```
**Fix:** Ensure `requirements.txt` is complete
```bash
pip freeze > requirements.txt
git add requirements.txt
git commit -m "Update dependencies"
git push
```

### Issue 2: CORS Errors in Browser
```
Access to fetch blocked by CORS policy
```
**Fix:** Update `BACKEND_CORS_ORIGINS` in Railway
```json
["https://your-frontend-domain.vercel.app"]
```

### Issue 3: Database Connection Failed
```
Error: Invalid Supabase credentials
```
**Fix:** Verify environment variables
1. Check Railway dashboard → Variables
2. Ensure `SUPABASE_URL` and `SUPABASE_KEY` are correct
3. Test connection in Supabase dashboard

### Issue 4: File Upload Fails
```
Error: Storage bucket not found
```
**Fix:** 
1. Go to Supabase dashboard → Storage
2. Create bucket named `user-files` (or match `SUPABASE_STORAGE_NAME`)
3. Set public access policies

### Issue 5: OpenAI API Errors
```
Error: Invalid OpenAI API key
```
**Fix:**
1. Verify `OPENAI_API_KEY` in Railway
2. Check OpenAI dashboard for valid key
3. Ensure billing is set up

### Issue 6: Cold Starts (Render only)
```
Request timeout after 30s
```
**Fix:** 
- Upgrade to paid tier ($7/month)
- Or switch to Railway (no cold starts on free tier)

---

## 📊 Monitoring Setup

### Railway Built-in Monitoring
1. Dashboard shows:
   - CPU usage
   - Memory usage
   - Request count
   - Error rate

2. Set up alerts:
   - Go to Settings → Notifications
   - Add Discord/Slack webhook

### External Monitoring (Optional)

**Option 1: UptimeRobot (Free)**
```
1. Go to uptimerobot.com
2. Add new monitor:
   - Type: HTTP(s)
   - URL: https://YOUR-API-URL.up.railway.app/api/test
   - Interval: 5 minutes
3. Get email alerts on downtime
```

**Option 2: Better Uptime**
- More features than UptimeRobot
- Status page included
- Free tier available

---

## 💰 Cost Tracking

### Free Tier Limits

**Railway:**
- $5 credit/month
- ~500 hours runtime
- Suitable for MVP

**Vercel:**
- 100GB bandwidth
- Unlimited deployments
- Suitable for small apps

**Supabase:**
- 500MB database
- 1GB file storage
- 50,000 monthly active users

**OpenAI:**
- Pay per use
- ~$0.002 per 1K tokens
- Estimate: $10-50/month for MVP

### When to Upgrade

**Backend (Railway):**
- Upgrade at $5/month credit exhausted
- Or when >100 requests/minute

**Database (Supabase):**
- Upgrade at 400MB database used
- Or when >40K monthly users

**Frontend (Vercel):**
- Upgrade at 100GB bandwidth
- Rarely needed for MVPs

---

## 🔐 Security Hardening

### Immediate (Must Do)
- [ ] All secrets in environment variables
- [ ] CORS restricted to frontend domain only
- [ ] HTTPS enabled (automatic on Railway/Vercel)
- [ ] Supabase RLS policies enabled

### Soon (Within First Month)
- [ ] Rate limiting implemented
- [ ] API key rotation schedule
- [ ] Error messages sanitized (no stack traces in production)
- [ ] File upload size limits enforced
- [ ] Input validation on all endpoints

### Later (Before Scaling)
- [ ] DDoS protection (Cloudflare)
- [ ] Secrets rotation automated
- [ ] Security audit
- [ ] Penetration testing

---

## 📈 Next Steps After Deployment

### Week 1: Monitoring
- [ ] Check logs daily
- [ ] Monitor error rates
- [ ] Track API response times
- [ ] Test all user flows

### Week 2: Optimization
- [ ] Add database indexes
- [ ] Implement caching (Redis optional)
- [ ] Optimize slow queries
- [ ] Add request logging

### Month 1: Growth
- [ ] Set up analytics
- [ ] Track user metrics
- [ ] Plan scaling strategy
- [ ] Budget for API costs

---

## 🆘 Getting Help

### Platform Support
- **Railway**: [docs.railway.app](https://docs.railway.app)
- **Vercel**: [vercel.com/docs](https://vercel.com/docs)
- **Supabase**: [supabase.com/docs](https://supabase.com/docs)

### Community
- **Railway Discord**: [discord.gg/railway](https://discord.gg/railway)
- **Supabase Discord**: [discord.supabase.com](https://discord.supabase.com)

### Debugging
```bash
# View Railway logs
railway logs

# Tail logs in real-time
railway logs --tail

# Check deployment status
railway status
```

---

## ✅ Deployment Complete!

Congratulations! Your Quizify API is now live.

**Your URLs:**
- Backend API: `https://YOUR-APP.up.railway.app`
- API Docs: `https://YOUR-APP.up.railway.app/docs`
- Frontend: `https://YOUR-APP.vercel.app`

**Next:** Start building your frontend or share your API with users! 🎉

---

## 📝 Deployment Summary Template

Copy this and fill in your details:

```
# Quizify Deployment Details

## Backend (Railway)
- URL: https://_____.up.railway.app
- Deployed: YYYY-MM-DD
- Version: v0.1.0

## Frontend (Vercel)
- URL: https://_____.vercel.app
- Deployed: YYYY-MM-DD
- Version: v0.1.0

## Services
- Database: Supabase (Free tier)
- Storage: Supabase Storage
- AI: OpenAI GPT-4
- Frontend: Vercel (Free tier)

## Costs (Monthly)
- Railway: $0-5
- Vercel: $0 (free tier - 100GB bandwidth)
- Supabase: $0
- OpenAI: $10-50
- Total: ~$10-55/month

## Credentials
- Store in password manager
- Never commit to Git
- Rotate every 90 days
```

---

**Last Updated:** 2025-10-05
