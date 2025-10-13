# Housekeeping Plan: Branch Strategy Cleanup

## Current Situation Analysis

### Your Branch Structure
```
deploy/production (c2b138b)
    ↓ (you branched from here)
    copilot/add-quota-validation-to-quiz-endpoints (current) ← YOU ARE HERE
    
development (578a260) ← Has all tests/specs/docs
```

### What You're Missing (in development, not in current branch)
✅ **Tests**: 
- `tests/contract/` - 10 contract tests (auth, files, quiz, submission)
- `tests/integration/` - Integration test setup
- `tests/conftest.py` - Pytest configuration with fixtures
- `tests/__init__.py` - Test package setup

✅ **Specs/Documentation**:
- `specs/001-comprehensive-quiz-generation/` - Full API specs
- `specs/001-comprehensive-quiz-generation/contracts/` - API contract definitions
- `analysis/` - Deployment analysis, cost breakdown, latency analysis
- `DEPLOYMENT.md`, `API_CONTRACT_ALIGNMENT_REPORT.md`

✅ **Development Tools**:
- `.github/copilot-instructions.md` - Copilot setup
- `.github/prompts/` - AI prompts for development
- `.specify/` - Specification framework
- `scripts/add_account_tier.py` - Utility script

✅ **Configuration**:
- `.python-version` - Python version pinning
- `pytest.ini` - Test configuration
- `.github/workflows/development_chopal.yml` - CI/CD

### What You Have (not in development)
🆕 Your quota validation work:
- Modified `handlers/quiz_handlers.py` (quota validation)
- Modified `tests/test_quota_integration.py` (13 new tests)
- New migrations (002, 003)
- Planning docs (TIER_MANAGEMENT_PLAN.md, etc.)

---

## Recommended Solution: Quick Merge Strategy

### ✅ RECOMMENDED: Option 1 - Merge Development (5 minutes)

**Why this is best:**
- ✅ Fastest solution (one command)
- ✅ Get all tests and specs immediately
- ✅ Keep your current work intact
- ✅ Can start admin panel work right away
- ✅ No risk of losing uncommitted changes

**Execution:**
```bash
# Step 1: Ensure current changes are safe
git stash  # Temporarily save uncommitted changes

# Step 2: Merge development branch
git merge origin/development

# Step 3: Restore your changes
git stash pop

# Step 4: Resolve any conflicts (likely none or minimal)
# If conflicts, just keep your versions of quiz_handlers.py and tests

# Done! Now you have:
# - All tests from development
# - All specs from development  
# - Your quota validation work
# - Ready to implement admin panel
```

**What happens:**
```
Before merge:
  deploy/production ← your base
      ↓
      copilot/quota-validation ← YOU (quota work only)
  
  development ← tests/specs (separate)

After merge:
  deploy/production
      ↓
      copilot/quota-validation ← YOU
          ↓ merged from
          development ← NOW YOU HAVE EVERYTHING!
```

---

### Alternative: Option 2 - Rebase onto Development (10 minutes)

**When to use:** If you want a cleaner git history

```bash
# Create new branch from development
git checkout development
git pull origin development
git checkout -b feature/quota-validation-complete

# Cherry-pick your quota commits
git cherry-pick c4d2990  # Add quota validation commit
git cherry-pick 81c054a  # Add comprehensive tests commit  
git cherry-pick f32fa7d  # Add test documentation commit

# Add uncommitted changes
git stash pop  # If you stashed earlier
git add handlers/ tests/ migrations/
git commit -m "feat: complete quota enforcement with admin panel ready"

# Push new branch
git push origin feature/quota-validation-complete

# Delete old branch
git branch -D copilot/add-quota-validation-to-quiz-endpoints
git push origin --delete copilot/add-quota-validation-to-quiz-endpoints
```

---

## Deploy Branch Strategy (For Future)

### Keep deploy/production Lean

Create `deploy-to-production.sh` script:

```bash
#!/bin/bash
# Deploy only production code, exclude tests/docs

set -e

echo "🚀 Preparing production deployment..."

# Checkout production branch
git checkout deploy/production
git pull origin deploy/production

# Merge only production files from development
echo "📦 Syncing production code..."

# Copy only production directories
git checkout development -- api/
git checkout development -- handlers/
git checkout development -- services/
git checkout development -- schemas/
git checkout development -- middleware/
git checkout development -- dependencies/

# Copy production files
git checkout development -- main.py
git checkout development -- requirements.txt
git checkout development -- pyproject.toml
git checkout development -- Dockerfile
git checkout development -- README.md

# Copy production migrations only (*.sql files)
git checkout development -- migrations/*.sql

# DO NOT copy:
# - tests/
# - specs/
# - analysis/
# - *_PLAN.md, *_STATUS.md, etc.

echo "✅ Staging production-ready files..."
git add api/ handlers/ services/ schemas/ middleware/ dependencies/
git add main.py requirements.txt pyproject.toml Dockerfile README.md
git add migrations/*.sql

echo "📝 Creating deploy commit..."
git commit -m "deploy: sync from development ($(date +%Y-%m-%d))"

echo "🚀 Pushing to production..."
git push origin deploy/production

echo ""
echo "✅ Deployment complete!"
echo "🔗 Check Railway dashboard"
echo ""
echo "Deployed files:"
git diff HEAD~1 --name-only
```

### .gitignore for Deploy Branch

Add to `.gitignore` on `deploy/production` branch only:

```gitignore
# Development-only files (exclude from production)
tests/
specs/
analysis/
.specify/
.github/prompts/
.github/copilot-instructions.md
scripts/add_account_tier.py

# Documentation (keep only README)
*_PLAN.md
*_STATUS.md
*_PROGRESS.md
*_REPORT.md
*_SUMMARY.md
*_ANALYSIS.md
IMPLEMENTATION_*.md
TEST_*.md
BUG_*.md
MOCKING_*.md
DEPLOYMENT.md
API_CONTRACT_*.md
GITHUB_ISSUES.md

# Test artifacts
pytest.ini
.pytest_cache/
htmlcov/
.coverage
*.coverage.*
```

---

## Workflow Going Forward

### Development Workflow
```bash
# 1. Start new feature
git checkout development
git pull origin development
git checkout -b feature/admin-panel

# 2. Develop with tests
# - Write code in handlers/
# - Write tests in tests/
# - Update specs in specs/
# - Run: pytest tests/

# 3. Commit everything
git add handlers/ tests/ specs/
git commit -m "feat: admin panel for tier management"

# 4. Push and PR
git push origin feature/admin-panel
# Create PR: feature/admin-panel → development

# 5. Merge to development
# Tests run in CI, then merge
```

### Deployment Workflow
```bash
# After feature merged to development

# Option A: Manual selective deploy
git checkout deploy/production
git checkout development -- api/ handlers/ services/
git checkout development -- main.py requirements.txt
git add . && git commit -m "deploy: admin panel"
git push origin deploy/production

# Option B: Automated script
./scripts/deploy-to-production.sh
```

---

## Immediate Action Items

### Right Now (Before Admin Panel)

1. **Execute merge** (1 minute):
   ```bash
   git stash
   git merge origin/development
   git stash pop
   ```

2. **Verify you have everything** (30 seconds):
   ```bash
   ls tests/contract/     # Should see 10 test files
   ls specs/              # Should see spec directories
   pytest --collect-only  # Should see ~30+ tests
   ```

3. **Commit current work** (1 minute):
   ```bash
   git add handlers/quiz_handlers.py
   git add tests/test_quota_integration.py
   git add migrations/002_auto_create_profiles.sql
   git add migrations/003_official_supabase_trigger.sql
   git commit -m "feat: complete quota enforcement with auto-profile creation

   - Add quota validation to all 3 quiz endpoints
   - Create 13 integration tests (all passing)
   - Implement database trigger for auto-profile creation
   - Add tier-specific error messages"
   ```

4. **Create deployment script** (2 minutes):
   ```bash
   mkdir -p scripts
   # I'll create the deploy script for you
   chmod +x scripts/deploy-to-production.sh
   ```

5. **Push updated branch** (30 seconds):
   ```bash
   git push origin copilot/add-quota-validation-to-quiz-endpoints
   ```

### After Admin Panel Complete

1. **Test with full test suite**:
   ```bash
   pytest tests/ -v  # All tests including contract tests
   ```

2. **Deploy to production** (lean):
   ```bash
   ./scripts/deploy-to-production.sh
   ```

---

## Benefits Summary

✅ **Development**: Full test suite + specs always available
✅ **Production**: Only code + migrations deployed (fast, lean)
✅ **Workflow**: Clear separation of concerns
✅ **Safety**: Test everything before production deploy
✅ **Efficiency**: Automated deployment script

---

## Your Decision

**Which option do you prefer?**

1. ✅ **Merge development now** (RECOMMENDED)
   - Fastest (5 mins)
   - Get tests/specs immediately
   - Start admin panel work

2. **Rebase onto development**
   - Cleaner history (10 mins)
   - More git commands
   - Same end result

3. **Continue as-is**
   - No immediate change
   - I'll adapt during admin work

**Say "merge now" and I'll execute Option 1 immediately!**
