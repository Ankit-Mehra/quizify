# Deployment Strategy: Keeping Specs in Dev, Excluding from Production

**Last Updated**: 2025-10-12  
**Status**: ✅ Implemented  
**Method**: `.dockerignore` for Railway + `.gitattributes` for archive deployments  
**Deployment Platform**: Railway (Docker-based)

---

## 🎯 Problem Statement

**Goal**: Keep specification documents, tests, and development files in the `development` branch, but automatically exclude them from production deployments.

**Requirements**:
- ✅ Specs stay in development and feature branches
- ✅ No manual deletion of files before deployment
- ✅ Automated, foolproof exclusion
- ✅ Easy to maintain and understand
- ✅ Industry-standard approach

---

## ✅ Implemented Solution: Dual Strategy

Since you're deploying with **Railway (Docker-based)**, we use a **dual approach**:

### 1. `.dockerignore` (Primary - Used by Railway)

Railway clones your Git branch and builds a Docker image. The `.dockerignore` file tells Docker what to exclude from the build context.

**How It Works**:
1. Railway connects to your `deploy/production` branch
2. Runs `docker build` which reads `.dockerignore`
3. Excludes specs, tests, docs automatically
4. Only production files go into the Docker image

### 2. `.gitattributes` (Backup - For Manual Deployments)

If you ever need to deploy via `git archive` (VPS, manual deployments), this provides the same exclusions.

**How It Works**:
1. `.gitattributes` marks files with `export-ignore`
2. `git archive` command creates tarball, excluding marked files
3. Deploy tarball to server

### Railway-Specific Benefits

- ✅ **Automatic**: Railway reads `.dockerignore` natively
- ✅ **Smaller images**: Excludes 100+ MB of dev files
- ✅ **Faster builds**: Less data to copy
- ✅ **No manual steps**: Works on every deployment
- ✅ **Branch agnostic**: Same `.dockerignore` in all branches

---

## 📁 File Structure

```
quizify/
├── .gitattributes          # ← Controls what gets deployed
├── specs/                  # ← Kept in dev, excluded from production
│   ├── 001-comprehensive-quiz-generation/
│   │   ├── contracts/
│   │   ├── spec.md
│   │   ├── plan.md
│   │   └── tasks.md
│   └── _archive/
├── tests/                  # ← Kept in dev, excluded from production
├── docs/                   # ← Kept in dev, excluded from production
├── scripts/                # ← Kept in dev, excluded from production
├── main.py                 # ✅ Included in production
├── api/                    # ✅ Included in production
├── handlers/               # ✅ Included in production
├── services/               # ✅ Included in production
└── requirements.txt        # ✅ Included in production
```

---

## 🚀 Usage (Railway Deployment)

### Current Workflow (Automated)

Railway automatically handles everything:

```bash
# 1. Push to development branch
git push origin development

# 2. Railway watches deploy/production branch
# (You merge development → deploy/production when ready)

# 3. Railway automatically:
#    - Clones deploy/production branch
#    - Reads .dockerignore
#    - Builds Docker image (excludes specs/tests/docs)
#    - Deploys container

# That's it! No manual steps.
```

### What Railway Sees

```dockerfile
# In your Dockerfile, this line copies files:
COPY . .

# But .dockerignore filters what gets copied:
# ✅ Copies: main.py, api/, handlers/, services/, requirements.txt
# ❌ Skips: specs/, tests/, docs/, scripts/, __pycache__/
```

### Verify What's Excluded (Local Test)

```bash
# Build Docker image locally (same as Railway)
docker build -t quizify-test .

# Check image size (should be smaller without dev files)
docker images quizify-test

# List files in image
docker run --rm quizify-test ls -la

# Verify specs are NOT in image
docker run --rm quizify-test ls specs/
# Should error: "ls: cannot access 'specs/': No such file or directory"

# Verify production files ARE in image
docker run --rm quizify-test ls api/
# Should list: quiz_routes.py, auth_routes.py, etc.
```

### Railway Dashboard Verification

1. Go to Railway → Your Project → Deployments
2. Click on a deployment → Logs tab
3. Look for build output:
   ```
   #5 [internal] load build context
   #5 transferring context: 2.3MB (excludes applied)
   ```
4. The "excludes applied" confirms `.dockerignore` is working

---

## 🚀 Usage (Alternative: Git Archive for VPS)

If you ever need to deploy to a traditional server (not Railway):

### Create Production Archive

```bash
# Create archive from development branch
./scripts/create-production-archive.sh development

# Create archive from specific tag
./scripts/create-production-archive.sh v1.2.3
```

This creates: `deploy-archives/quizify-production-{branch}-{timestamp}.tar.gz`

### Deploy to VPS

```bash
# 1. Upload archive
scp deploy-archives/quizify-production-*.tar.gz user@server:/tmp/

# 2. Extract (automatically excludes dev files)
ssh user@server '
  cd /app &&
  tar -xzf /tmp/quizify-production-*.tar.gz --strip-components=1 &&
  pip install -r requirements.txt &&
  systemctl restart quizify
'
```

---

## 📝 What's Excluded

Your existing `.dockerignore` already excludes:

### Development Documentation ✅
- `specs/` - All specification documents
- `docs/` - All documentation (except README.md)
- `*.md` files (development status, planning, etc.)
- `analysis/` - Deployment analysis docs

### Testing ✅
- `tests/` - All test files
- `pytest.ini` - Test configuration
- `.pytest_cache/` - Test cache
- `htmlcov/` - Coverage reports
- `.coverage` - Coverage data

### Development Tools ✅
- `scripts/` - Development scripts
- `postman/` - API testing collections
- `.github/` - CI/CD workflows
- `.specify/` - Spec tools

### Build Artifacts ✅
- `__pycache__/` - Python cache
- `*.pyc`, `*.pyo` - Compiled Python
- `.venv/`, `venv/` - Virtual environments
- `uv.lock` - Lock files (uses requirements.txt)

### IDE Files ✅
- `.vscode/` - VS Code settings
- `.idea/` - PyCharm settings
- `.DS_Store` - macOS files
- `*.swp` - Vim swap files

### Git & Docker ✅
- `.git/` - Git history
- `.gitignore`, `.gitattributes`
- `Dockerfile`, `docker-compose*.yml`
- `.dockerignore` itself

**Total excluded**: ~150+ MB of development files  
**Result**: Smaller Docker images, faster Railway deployments

---

## 🔧 Maintenance

### Add New Exclusion (Railway)

Edit `.dockerignore`:
```bash
# Add new line
new-dev-folder/
new-status-report.md
```

Commit and push:
```bash
git add .dockerignore
git commit -m "Exclude new-dev-folder from Docker builds"
git push origin development
```

Next Railway deployment automatically respects the change.

### Test Exclusion Locally

```bash
# Build image locally
docker build -t quizify-test .

# Verify file is excluded
docker run --rm quizify-test ls new-dev-folder/
# Should error if exclusion works
```

### Remove Exclusion

Simply delete the line from `.dockerignore`:
```bash
# This folder will now be included in Docker image
# new-dev-folder/  ← commented out or deleted
```

### Check What Railway Will Deploy

```bash
# See exact files that will be copied
docker build --no-cache -t quizify-test . 2>&1 | grep "transferring context"

# Example output:
# #5 transferring context: 2.3MB (with exclusions)
```

---

## 🆚 Alternative Approaches (Why We Didn't Use Them)

### ❌ Option 1: Separate Deploy Branch with Manual Deletion
```
development branch: Has specs, tests, docs
deploy/production branch: Manually delete specs before Railway deployment
```

**Problems**:
- ❌ Manual deletion prone to errors
- ❌ Merge conflicts between branches
- ❌ Extra branch to maintain
- ❌ Easy to forget steps
- ❌ Railway still builds everything if no .dockerignore

### ❌ Option 2: Build Scripts Before Push
```
Run scripts to delete files before pushing to deploy branch
```

**Problems**:
- ❌ Manual step can be forgotten
- ❌ Hard to version control what's excluded
- ❌ Different behavior on different systems
- ❌ Requires discipline from all developers

### ❌ Option 3: Railway Build Commands
```
Use Railway's build command to delete files during deployment
```

**Problems**:
- ❌ Still copies files from Git (wastes time)
- ❌ Files counted toward build context size
- ❌ More complex build process
- ❌ Platform-specific (doesn't work on other Docker platforms)

### ✅ Why `.dockerignore` is Best for Railway

- ✅ **Native Docker**: Railway uses Docker, `.dockerignore` is standard
- ✅ **Automatic**: Docker handles it, no manual steps
- ✅ **Version controlled**: Changes tracked in Git
- ✅ **Universal**: Works on Railway, local, any Docker platform
- ✅ **Efficient**: Files never copied, faster builds
- ✅ **Standard**: Used by all major Docker projects

---

## 📋 Railway Deployment Workflow

### Complete Development → Production Flow

```bash
# ===== DEVELOPMENT PHASE =====
# 1. Create feature branch (includes specs)
git checkout development
git checkout -b feature/new-quiz-type

# 2. Write specs (kept in all branches)
mkdir -p specs/002-new-quiz-type
vim specs/002-new-quiz-type/spec.md

# 3. Write code
vim handlers/quiz_handlers.py

# 4. Write tests
vim tests/test_new_quiz_type.py

# 5. Commit everything (specs, code, tests)
git add specs/ handlers/ tests/
git commit -m "Add new quiz type feature"

# 6. Push and create PR to development
git push origin feature/new-quiz-type
# Create PR on GitHub: feature/new-quiz-type → development

# 7. Merge to development (keeps all specs/tests)
# After PR approval, merge on GitHub

# ===== DEPLOYMENT PHASE =====
# 8. Merge development → deploy/production
git checkout deploy/production
git merge development
git push origin deploy/production

# 9. Railway automatically:
#    - Detects push to deploy/production
#    - Clones repository
#    - Reads .dockerignore
#    - Builds Docker image (excludes specs/tests/docs)
#    - Deploys container

# 10. Verify deployment
# Check Railway logs for successful deployment
```

### What Railway Does Automatically

```
┌─────────────────────────────────────────┐
│  Railway Deployment Process             │
├─────────────────────────────────────────┤
│  1. Git Clone deploy/production         │
│     ├─ Downloads all files from branch  │
│     └─ Includes: code, specs, tests     │
│                                          │
│  2. Read .dockerignore                  │
│     ├─ Loads exclusion rules            │
│     └─ Prepares file filter             │
│                                          │
│  3. Build Docker Image                  │
│     ├─ COPY . . (with filters)          │
│     ├─ ✅ Copies: main.py, api/,       │
│     │            handlers/, services/   │
│     ├─ ❌ Skips: specs/, tests/, docs/ │
│     └─ Result: Lean production image    │
│                                          │
│  4. Deploy Container                    │
│     ├─ Runs: hypercorn main:app         │
│     └─ Container has NO specs/tests     │
└─────────────────────────────────────────┘
```

### Branch Strategy Summary

```
feature/xyz → [PR] → development → [PR] → deploy/production → Railway
                           │                        │
                           │                        └─ .dockerignore filters
                           │                           during Docker build
                           └─ Keeps all specs/tests
```

---

## 🧪 Testing the Setup

### Test 1: Verify Specs Exist in Development
```bash
# Switch to development branch
git checkout development

# Check specs exist
ls -la specs/001-comprehensive-quiz-generation/

# Should see:
# - contracts/
# - spec.md
# - plan.md
# - tasks.md
```

### Test 2: Build Docker Image Locally (Railway Simulation)
```bash
# Build exactly as Railway does
docker build -t quizify-test .

# Check image size (should be ~150MB smaller without specs)
docker images quizify-test

# Verify specs are NOT in image
docker run --rm quizify-test sh -c "ls specs/ 2>&1"
# Should output: "ls: specs/: No such file or directory"

# Verify production files ARE in image
docker run --rm quizify-test ls api/
# Should output: auth_routes.py, quiz_routes.py, etc.

# Verify tests are NOT in image
docker run --rm quizify-test sh -c "ls tests/ 2>&1"
# Should output: "ls: tests/: No such file or directory"
```

### Test 3: Check Build Context Size
```bash
# See how much data Docker copies (should be small)
docker build --no-cache -t quizify-test . 2>&1 | grep "transferring context"

# Example good output:
# #5 transferring context: 2.3MB done

# Example bad output (if .dockerignore not working):
# #5 transferring context: 150.7MB done
```

### Test 4: Verify .dockerignore is Working
```bash
# List what would be excluded
git ls-files | while read file; do
  if grep -q "^${file%/*}" .dockerignore 2>/dev/null; then
    echo "❌ Excluded: $file"
  fi
done | head -20

# Should see:
# ❌ Excluded: specs/001-comprehensive-quiz-generation/spec.md
# ❌ Excluded: tests/test_admin_api.py
# ❌ Excluded: docs/DEPLOYMENT.md
```

---

## 🔄 Migration Steps

### ✅ Already Complete

1. ✅ **Existing `.dockerignore`** - Already excludes specs, tests, docs
2. ✅ **Dockerfile configured** - Uses `COPY . .` with .dockerignore filtering
3. ✅ **Railway deployment** - Already using Docker builds

### ✅ Restored Specs (If Missing)

If specs were previously deleted from development branch:

```bash
# 1. Find commit where specs existed
git log --all --oneline --grep="spec" -- specs/

# 2. Restore specs from that commit
git checkout <commit-hash> -- specs/

# 3. Commit restoration
git add specs/
git commit -m "Restore specs to development branch"
git push origin development
```

### ✅ Create `.gitattributes` (Optional - For Archive Deployments)

Only needed if you plan to use `git archive` for non-Railway deployments:

```bash
# Create .gitattributes file
cat > .gitattributes << 'EOF'
# Exclude development files from git archive
specs/ export-ignore
tests/ export-ignore
docs/ export-ignore
scripts/ export-ignore
.github/ export-ignore
htmlcov/ export-ignore
__pycache__/ export-ignore
*.pyc export-ignore
.venv/ export-ignore
uv.lock export-ignore
EOF

# Commit
git add .gitattributes
git commit -m "Add export-ignore for git archive deployments"
git push origin development
```

### 📋 Next Steps (If Needed)

- [x] Verify `.dockerignore` exists and is comprehensive
- [x] Test Docker build locally
- [x] Verify Railway deployments work
- [ ] Document Railway environment variables
- [ ] Set up Railway deployment webhooks (if needed)
- [ ] Configure Railway health checks

---

## 📚 References

- [Git Attributes Documentation](https://git-scm.com/docs/gitattributes)
- [Git Archive Documentation](https://git-scm.com/docs/git-archive)
- [Pro Git Book - Export-Ignore](https://git-scm.com/book/en/v2/Customizing-Git-Git-Attributes)

---

## 🆘 Troubleshooting

### Problem: Specs still appearing in Railway container

**Check 1**: Verify .dockerignore exists and has `specs/`
```bash
grep "specs/" .dockerignore
# Should output: specs/
```

**Check 2**: Test locally
```bash
docker build -t test .
docker run --rm test ls specs/
# Should error if working correctly
```

**Check 3**: Rebuild Railway deployment
```
Railway Dashboard → Deployments → Click "Redeploy"
```

### Problem: Production files missing from container

**Check**: Ensure file is NOT in .dockerignore
```bash
grep "main.py" .dockerignore
# Should output nothing (file not excluded)
```

### Problem: Railway build failing

**Check 1**: Verify Dockerfile syntax
```bash
docker build -t test .
# Should complete without errors
```

**Check 2**: Check Railway logs
```
Railway Dashboard → Deployments → Click on failed deployment → Logs
```

### Problem: Docker image too large

**Check**: Build context size
```bash
docker build --no-cache -t test . 2>&1 | grep "transferring context"
# Should be < 5MB if .dockerignore working

# If > 50MB, .dockerignore may not be working
```

### Problem: .dockerignore not working

**Fix**: Ensure .dockerignore is in repo root (same level as Dockerfile)
```bash
# Check location
ls -la .dockerignore Dockerfile
# Both should be in same directory

# Rebuild without cache
docker build --no-cache -t test .
```

### Problem: Need to restore deleted specs

```bash
# Find when specs were deleted
git log --all --full-history -- specs/ | head -20

# Restore from before deletion
git checkout <commit-hash> -- specs/

# Commit restoration
git add specs/
git commit -m "Restore specs from commit <hash>"
```

---

**Maintained By**: Development Team  
**Last Updated**: 2025-10-12  
**Status**: ✅ Active and Tested
