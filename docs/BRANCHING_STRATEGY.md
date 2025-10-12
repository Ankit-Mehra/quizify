# Branching Strategy & Workflow

## Current Situation
- **Current branch**: `copilot/add-quota-validation-to-quiz-endpoints` (branched from `deploy/production`)
- **Problem**: Tests and docs in `development`, but working from `deploy/production` base
- **Goal**: Development with all docs/tests, deployment without baggage

## Recommended Git Workflow

### Branch Structure
```
development (main development branch)
    ↓
    ├── feature branches (with tests + docs)
    ↓
deploy/production (lean, production-ready)
    ↓
    └── deployed to Railway/production
```

### Branch Purposes

#### `development` branch
- **Source of truth** for all development
- Contains: tests, docs, specs, migrations, all code
- All feature branches branch FROM here
- All PRs merge TO here
- Never deployed directly

#### `deploy/production` branch  
- **Production-only** branch
- Contains: only production code (no tests, minimal docs)
- Updated via cherry-pick or selective merge from `development`
- Deployed to Railway
- Protected branch

#### Feature branches
- Branch from: `development`
- Naming: `feature/admin-panel`, `copilot/quota-validation`
- Include: tests, docs, code changes
- Merge to: `development` via PR

---

## Solution: Rebase Your Current Work

### Option 1: Rebase onto `development` (RECOMMENDED)

```bash
# 1. Fetch latest changes
git fetch origin

# 2. Checkout development and update
git checkout development
git pull origin development

# 3. Create new feature branch from development
git checkout -b feature/quota-validation-complete

# 4. Cherry-pick your commits from current branch
git cherry-pick c2b138b..f32fa7d  # Range of commits from quota branch

# 5. Add new files
git add handlers/quiz_handlers.py tests/test_quota_integration.py
git add migrations/002_auto_create_profiles.sql migrations/003_official_supabase_trigger.sql
git commit -m "feat: complete quota enforcement with auto-profile creation"

# 6. Push new branch
git push origin feature/quota-validation-complete
```

### Option 2: Merge `development` into Current Branch (FASTER)

```bash
# 1. Stay on current branch
git checkout copilot/add-quota-validation-to-quiz-endpoints

# 2. Merge development branch to get tests/docs
git merge origin/development

# 3. Resolve conflicts if any
# 4. Now you have tests + docs + your quota work
```

---

## Going Forward: Proper Workflow

### 1. Starting New Feature
```bash
# Always branch from development
git checkout development
git pull origin development
git checkout -b feature/admin-panel

# Work with tests and docs available
# Write tests alongside code
# Update specs/docs as needed
```

### 2. Completing Feature
```bash
# Commit everything (code + tests + docs)
git add .
git commit -m "feat: admin panel for tier management"

# Push and create PR to development
git push origin feature/admin-panel
# Create PR: feature/admin-panel → development
```

### 3. Deploying to Production
```bash
# Option A: Cherry-pick specific commits (LEAN)
git checkout deploy/production
git pull origin deploy/production

# Pick only production code commits (exclude test/doc commits)
git cherry-pick <commit-hash>  # Just the code changes
git cherry-pick <migration-hash>  # Just production migrations

# Push to production
git push origin deploy/production

# Option B: Selective merge with exclusion
git checkout deploy/production
git merge development --no-commit
git reset HEAD tests/ docs/ *.md  # Exclude tests and docs
git checkout -- tests/ docs/ *.md
git commit -m "deploy: quota validation feature"
git push origin deploy/production
```

---

## .gitignore for Production Branch

Create `.gitignore` additions for `deploy/production` branch:

```gitignore
# Exclude from production deploys
tests/
pytest.ini
.pytest_cache/
htmlcov/
.coverage

# Keep only essential docs
!README.md
!CHANGELOG.md
*_PLAN.md
*_STATUS.md
*_PROGRESS.md
IMPLEMENTATION_*.md
TEST_*.md
BUG_*.md
MOCKING_*.md
```

---

## Automated Deployment Script

Create `scripts/deploy_to_production.sh`:

```bash
#!/bin/bash
set -e

echo "🚀 Deploying to production..."

# Ensure we're on development
git checkout development
git pull origin development

# Switch to production branch
git checkout deploy/production
git pull origin deploy/production

# Merge only specific directories
git checkout development -- api/ handlers/ services/ schemas/ middleware/
git checkout development -- main.py requirements.txt pyproject.toml
git checkout development -- migrations/*.sql  # Only .sql files

# Commit
git add api/ handlers/ services/ schemas/ middleware/ main.py requirements.txt pyproject.toml migrations/
git commit -m "deploy: sync from development ($(date +%Y-%m-%d))"

# Push
git push origin deploy/production

echo "✅ Deployed successfully!"
echo "🔗 Check Railway: https://railway.app"
```

---

## Your Immediate Action Plan

### Step 1: Fix Current Branch (Choose One)

**Quick Fix** (5 minutes):
```bash
git checkout copilot/add-quota-validation-to-quiz-endpoints
git merge origin/development
# Now you have tests + docs
```

**Proper Fix** (10 minutes):
```bash
git checkout development
git pull origin development
git checkout -b feature/quota-validation-with-admin-panel
git cherry-pick c4d2990 81c054a f32fa7d  # Your quota commits
# Add your new changes
git add handlers/ tests/ migrations/
git commit -m "feat: quota validation with admin panel"
git push origin feature/quota-validation-with-admin-panel
```

### Step 2: Implement Admin Panel (on proper branch)
- Work from `development` or merged branch
- Tests and docs available
- Commit everything together

### Step 3: Deploy to Production
- Use cherry-pick or deployment script
- Only code + migrations to `deploy/production`
- No tests, no extra docs

---

## Benefits of This Approach

✅ **Development**: All tests and docs always available
✅ **Production**: Lean, fast deployments, no baggage  
✅ **Traceability**: Clear history of what's deployed
✅ **Safety**: Can test fully before production deploy
✅ **Flexibility**: Can deploy subset of features

---

## Which Option Do You Prefer?

1. **Quick merge** (stay on current branch, merge development) → 5 mins
2. **Proper rebase** (new branch from development) → 10 mins
3. **Continue as-is** (I'll handle the workflow during admin panel work)

Let me know and I'll execute the chosen strategy!
