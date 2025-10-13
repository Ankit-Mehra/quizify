# Deployment Guide - Production Branch

## Overview
This `deploy/production` branch is specifically configured for production deployment.

## Key Differences from Development
- Uses `.dockerignore` to exclude development files from container
- Contains only production-ready code
- All tests passing (45/45 tests, 66% coverage)

## Excluded from Production Container
The following are automatically excluded via `.dockerignore`:
- Test files (`tests/`, `.coverage`, `htmlcov/`)
- Development files (`.vscode/`, logs, `*.md` except README)
- Python cache (`__pycache__/`, `*.pyc`)
- Lock files (`uv.lock`)
- CI/CD configs
- Status tracking files

## Environment Variables Required
Set these in your deployment platform:
```
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
OPENAI_API_KEY=your_openai_key
TESTING=false  # CRITICAL: Must be false in production for security
```

## Security Features
- **Access Token Protection**: In production (`TESTING=false`), access tokens are ONLY sent via HttpOnly cookies, never in response body
- **Fail-Fast Configuration**: App crashes at startup if required environment variables are missing
- **No Test Dependencies**: Test libraries excluded from production image

## Deployment Steps

### 1. Docker Build
```bash
docker build -t quizify-prod .
```

### 2. Test Locally
```bash
docker run -p 8000:8000 \
  -e SUPABASE_URL=xxx \
  -e SUPABASE_KEY=xxx \
  -e OPENAI_API_KEY=xxx \
  -e TESTING=false \
  quizify-prod
```

### 3. Deploy to Platform
Choose your platform:

#### Railway
```bash
railway up
```

#### Render
- Connect this branch in Render dashboard
- Set environment variables
- Deploy

#### Heroku
```bash
git push heroku deploy/production:main
```

#### AWS/GCP/Azure
Follow platform-specific Docker deployment instructions

## Monitoring
- Check startup logs for config validation
- Monitor `/api/health` endpoint
- Set up error tracking (Sentry recommended)

## Rollback
If issues occur:
```bash
git checkout development
# Fix issues
git checkout deploy/production
git merge development
git push origin deploy/production --force
```

## Last Deployed
Branch created: October 7, 2025
Last merge from development: October 7, 2025

## Contact
For deployment issues, contact: [Your team contact]
