# Environment Variables Guide - After Lazy Loading Refactor

## ✅ REQUIRED Environment Variables

These **MUST** be set for the application to work:

### 1. Supabase Configuration
```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_service_role_key
SUPABASE_STORAGE_NAME=your_storage_bucket_name
```
**Used by:** 
- `config.py` - Core configuration
- `dependencies/auth_dependencies.py` - JWT validation
- `middleware/auto_refresh.py` - Token refresh
- All handlers and DB services via `get_supabase()`

**Why required:** Without these, the app cannot connect to Supabase database

---

### 2. AI Service Configuration
```bash
OPENAI_API_KEY=sk-proj-...
```
**Used by:**
- `config.py`
- `services/ai_services/openai_service.py` - Quiz generation

**Why required:** Without this, quiz generation will fail

---

## 🔧 OPERATIONAL Mode Flags

These control HOW the application runs:

### 3. Testing Mode (Default: false)
```bash
TESTING=false  # or true for unit tests
```
**Used by:**
- `config.py` - Returns None for `get_supabase_client()` when true
- All test files via `TESTING=true pytest`

**When to use:**
- ✅ Set to `true` when running unit tests: `TESTING=true pytest`
- ✅ Set to `false` (or omit) in development/production

---

### 4. Development Mode (Default: false)
```bash
DEVELOPMENT_MODE=true  # or false for production
```
**Used by:**
- `config.py` - `is_development()` check
- `handlers/auth_handlers.py` - Returns token in response body when true

**When to use:**
- ✅ Set to `true` for local development and Postman testing
- ❌ Set to `false` in production (tokens only in HttpOnly cookies)

---

### 5. Documentation Endpoints (Default: false)
```bash
ENABLE_DOCS=true  # or false to hide /docs
```
**Used by:**
- `main.py` - Controls `/docs` and `/redoc` endpoints

**When to use:**
- ✅ Set to `true` in development
- ❌ Set to `false` in production (security)

---

## 🌐 CORS Configuration

### 6. Backend CORS Origins
```bash
BACKEND_CORS_ORIGINS=["http://localhost:3000","http://localhost:3001","http://localhost:8000","http://127.0.0.1:8000","https://yourdomain.com"]
```
**Used by:**
- `main.py` - FastAPI CORS middleware

**When to customize:**
- Add your frontend URLs
- Add Postman/API testing URLs (localhost:8000, 127.0.0.1:8000)
- Add production domain

---

## 🔒 OPTIONAL Admin Configuration

### 7. Admin User IDs (Optional)
```bash
ADMIN_USER_IDS=uuid-1,uuid-2,uuid-3
```
**Used by:**
- `handlers/admin_handlers.py` - Fallback admin check

**When to use:**
- ⚠️ Only if you haven't set `is_admin=true` in profiles table
- ⚠️ Fallback mechanism for quick admin access
- ✅ Better: Use database `profiles.is_admin` column instead

---

## 🌐 Web Scraping Configuration

### 8. Scraper User Agent (Optional)
```bash
SCRAPER_USER_AGENT=Mozilla/5.0 (compatible; QuizifyBot/1.0; +https://quizify.app/bot)
```
**Used by:**
- `services/web_scraping_service.py` - User agent for Playwright browser
- URL quiz generation feature

**Default value:** `Mozilla/5.0 (compatible; QuizifyBot/1.0; +https://quizify.app/bot)`

**When to customize:**
- ✅ When deploying to your own domain (change URL in user agent)
- ✅ When you want to identify your bot with a different name
- ✅ For compliance with website robots.txt policies

**Examples:**
```bash
# For your custom domain
SCRAPER_USER_AGENT=Mozilla/5.0 (compatible; MyQuizBot/1.0; +https://myschool.edu/bot)

# For development/staging environment
SCRAPER_USER_AGENT=Mozilla/5.0 (compatible; QuizifyBot-Dev/1.0; +https://dev.quizify.app/bot)
```

---

## ❌ REMOVED / NO LONGER NEEDED

### Variables from old architecture:
- ❌ None! The lazy loading refactor didn't remove any variables
- ✅ All existing variables are still used

---

## 📋 Minimal .env for Different Environments

### Local Development (.env)
```bash
# Core Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_service_role_key
SUPABASE_STORAGE_NAME=quiz-files

# AI
OPENAI_API_KEY=sk-proj-...

# Development Settings
DEVELOPMENT_MODE=true
ENABLE_DOCS=true
TESTING=false

# CORS - include Postman testing URLs
BACKEND_CORS_ORIGINS=["http://localhost:3000","http://localhost:3001","http://localhost:8000","http://127.0.0.1:8000"]
```

### Production (.env)
```bash
# Core Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_service_role_key
SUPABASE_STORAGE_NAME=quiz-files

# AI
OPENAI_API_KEY=sk-proj-...

# Production Settings (secure)
DEVELOPMENT_MODE=false
ENABLE_DOCS=false
TESTING=false

# CORS - only your production domains
BACKEND_CORS_ORIGINS=["https://yourdomain.com","https://www.yourdomain.com"]

# Optional: Admin fallback
ADMIN_USER_IDS=your-admin-uuid
```

### Unit Testing (command line)
```bash
TESTING=true pytest tests/
```
*Note: Test-specific variables are set in `tests/conftest.py`, not .env*

---

## 🎯 Answer to Your Question

**Do we need all those variables in .env now?**

**YES** - All the variables are still needed! ✅

The lazy loading refactor changed **HOW** the Supabase client is created (function call vs module-level), but it didn't change **WHAT** configuration is needed.

### What Changed:
- ❌ **NOT the environment variables** (still the same)
- ✅ **HOW we use them** (lazy loading via `get_supabase()`)

### Your current .env is correct:
```bash
# These are all still needed ✅
SUPABASE_URL=...              # ✅ Required for database connection
SUPABASE_KEY=...              # ✅ Required for authentication
OPENAI_API_KEY=...            # ✅ Required for quiz generation
BACKEND_CORS_ORIGINS=[...]    # ✅ Required for API access
TESTING=false                 # ✅ Required to control test mode
DEVELOPMENT_MODE=true         # ✅ Required for Postman testing
ENABLE_DOCS=true              # ✅ Required to show /docs
```

### Only missing:
```bash
SUPABASE_STORAGE_NAME=quiz-files  # ⚠️ Add this!
```

---

## 🚀 Quick Actions

1. **Add to your .env:**
   ```bash
   SUPABASE_STORAGE_NAME=quiz-files
   ```

2. **Keep everything else as-is** - it's all still needed! ✅

3. **When deploying to production:**
   - Set `DEVELOPMENT_MODE=false`
   - Set `ENABLE_DOCS=false`
   - Update `BACKEND_CORS_ORIGINS` with your real domain

That's it! The lazy loading refactor made your code cleaner but didn't reduce the number of required environment variables. 🎉
