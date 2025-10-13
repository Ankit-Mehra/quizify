# Railway Deployment Quick Reference

**Last Updated**: 2025-10-12  
**Platform**: Railway.app  
**Deployment Method**: Docker (automatic)

---

## 🎯 TL;DR

✅ **Specs/tests stay in all Git branches**  
✅ **`.dockerignore` excludes them from Railway containers**  
✅ **No manual deletion needed**  
✅ **Already configured and working**

---

## 📦 What Railway Deploys

### ✅ Included in Production Container
- `main.py` - FastAPI application
- `api/` - Route handlers
- `handlers/` - Business logic
- `services/` - Core services
- `schemas/` - Pydantic models
- `dependencies/` - Auth & middleware
- `middleware/` - Request middleware
- `migrations/` - Database migrations
- `requirements.txt` - Python dependencies
- `config.py` - Configuration
- `.env.example` - Environment template
- `README.md` - Production reference

### ❌ Excluded from Production Container
- `specs/` - Specification documents (~50MB)
- `tests/` - Test files (~30MB)
- `docs/` - Documentation (~20MB)
- `scripts/` - Development scripts (~5MB)
- `postman/` - API collections (~10MB)
- `.github/` - CI/CD workflows (~5MB)
- `htmlcov/` - Coverage reports (~10MB)
- `__pycache__/` - Python cache (~5MB)
- `.venv/` - Virtual environment (~200MB)
- All `.md` status files (~5MB)

**Total excluded**: ~340MB  
**Production image**: ~150MB (vs ~490MB without .dockerignore)

---

## 🚀 Deployment Flow

```
┌─────────────────────────────────────────────────────────────┐
│  Developer Pushes to deploy/production                      │
│  git push origin deploy/production                          │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│  Railway Detects Push                                       │
│  - Webhook triggered                                        │
│  - Clone repository                                         │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│  Railway Builds Docker Image                                │
│  1. Read Dockerfile                                         │
│  2. Read .dockerignore                                      │
│  3. COPY . . (with .dockerignore filters)                   │
│  4. pip install -r requirements.txt                         │
│  5. Create image (excludes specs/tests/docs)                │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│  Railway Deploys Container                                  │
│  - Start: hypercorn main:app --bind 0.0.0.0:$PORT           │
│  - Health check: GET /api/test                              │
│  - If healthy: Route traffic to new container               │
│  - If unhealthy: Rollback to previous deployment            │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔍 How to Verify It's Working

### Check 1: Local Docker Build
```bash
# Build same way Railway does
docker build -t quizify-test .

# Verify specs excluded
docker run --rm quizify-test ls specs/
# Expected: ls: specs/: No such file or directory ✅

# Verify production files included
docker run --rm quizify-test ls api/
# Expected: auth_routes.py  file_routes.py  quiz_routes.py ... ✅
```

### Check 2: Railway Build Logs
```
Railway Dashboard → Project → Deployments → Latest → Logs

Look for:
#5 [internal] load build context
#5 transferring context: 2.3MB done

✅ If < 5MB: .dockerignore working correctly
❌ If > 50MB: .dockerignore not being read
```

### Check 3: Container Shell (Advanced)
```
Railway Dashboard → Project → Deployments → Latest → Shell

# In Railway shell:
ls specs/
# Expected: ls: cannot access 'specs/': No such file or directory ✅

ls api/
# Expected: auth_routes.py  file_routes.py  quiz_routes.py ... ✅
```

---

## 🛠️ Common Tasks

### Update What's Excluded

```bash
# 1. Edit .dockerignore
echo "new-dev-folder/" >> .dockerignore

# 2. Commit and push
git add .dockerignore
git commit -m "Exclude new-dev-folder from production"
git push origin development

# 3. Merge to deploy branch when ready
git checkout deploy/production
git merge development
git push origin deploy/production

# 4. Railway auto-deploys with new exclusions
```

### Test Before Deploying

```bash
# Always test Docker build locally first
docker build -t quizify-test .

# Check image size
docker images quizify-test
# Should be ~150MB

# Run container locally
docker run -p 8000:8000 --env-file .env quizify-test

# Test endpoints
curl http://localhost:8000/api/test
```

### Force Rebuild on Railway

```
Railway Dashboard → Project → Deployments → Click "Redeploy"
```

### Check Railway Environment Variables

```
Railway Dashboard → Project → Settings → Variables

Required:
- SUPABASE_URL
- SUPABASE_KEY
- OPENAI_API_KEY
- PORT (auto-set by Railway)
- BACKEND_CORS_ORIGINS (JSON array)
```

---

## ⚠️ Important Notes

1. **Never manually delete specs from Git branches**
   - Specs stay in `development` branch
   - `.dockerignore` handles exclusion automatically

2. **Always test Docker builds locally**
   - Catches .dockerignore issues before Railway deployment
   - `docker build -t test .` should complete in < 1 minute

3. **Railway watches specific branch**
   - Configure in Railway Dashboard → Settings → Deploy
   - Usually set to `deploy/production` or `main`

4. **Environment variables**
   - Set in Railway Dashboard, NOT in .env file
   - .env files excluded by .dockerignore

5. **Database migrations**
   - Run manually via Railway shell or deployment script
   - Migrations folder IS included in production

---

## 📋 Pre-Deployment Checklist

Before merging to `deploy/production`:

- [ ] All tests passing: `pytest tests/`
- [ ] Local Docker build succeeds: `docker build -t test .`
- [ ] Docker image size reasonable: `docker images test` (~150MB)
- [ ] Specs excluded from image: `docker run --rm test ls specs/` (should error)
- [ ] Production files included: `docker run --rm test ls api/` (should list files)
- [ ] Railway env variables up to date
- [ ] Database migrations ready (if any)
- [ ] CHANGELOG updated (if used)

---

## 🔗 Related Documentation

- [Full Deployment Strategy](./DEPLOYMENT_SPECS_STRATEGY.md)
- [Environment Variables Guide](./ENV_VARIABLES_GUIDE.md)
- [Branching Strategy](./BRANCHING_STRATEGY.md)
- [Railway Docs](https://docs.railway.app/)
- [Docker .dockerignore Reference](https://docs.docker.com/engine/reference/builder/#dockerignore-file)

---

## 🆘 Quick Fixes

### "Specs appearing in production"
```bash
# Check .dockerignore has specs/
grep "specs/" .dockerignore

# If missing, add it
echo "specs/" >> .dockerignore
git commit -am "Fix: Exclude specs from Docker"
git push origin deploy/production
```

### "Railway build too slow"
```bash
# Check build context size in logs
# Should be < 5MB

# If > 50MB, .dockerignore might not be working
# Verify .dockerignore is in repo root:
ls -la .dockerignore Dockerfile
# Both must be in same directory
```

### "Production files missing"
```bash
# Check file isn't excluded
grep "main.py" .dockerignore
# Should return nothing

# If excluded by mistake, remove from .dockerignore
```

---

**Maintained By**: Development Team  
**Status**: ✅ Active and Tested  
**Last Verified**: 2025-10-12
