# Web URL Quiz Generation - Postman Testing Guide

## Overview

This guide covers testing the **Web URL Quiz Generation** feature (Issue #4) using the comprehensive Postman collection.

**Feature:** Generate quizzes from web page URLs using Playwright browser automation and Trafilatura content extraction.

**Collection File:** `Quizify_Web_URL_Quiz_Generation.postman_collection.json`

---

## 🚀 Quick Start

### 1. Import Collection

1. Open Postman
2. Click **Import** button
3. Select `Quizify_Web_URL_Quiz_Generation.postman_collection.json`
4. Collection will appear in your workspace

### 2. Configure Environment Variables

Set these variables in Postman (Environment or Collection variables):

| Variable | Description | Example | Required |
|----------|-------------|---------|----------|
| `base_url` | API base URL | `http://localhost:8000` or `https://api.quizify.app` | ✅ Yes |
| `auth_token` | JWT authentication token | `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...` | ✅ Yes |
| `user_tier` | User's tier (for reference) | `basic` or `educator` | Optional |
| `user_id` | User ID (auto-populated) | `uuid` | Auto-set |
| `url_quiz_id` | Created quiz ID (auto-populated) | `uuid` | Auto-set |

### 3. Get Your Auth Token

**Option A: Using existing endpoints**
```bash
# Login to get token
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "your@email.com", "password": "yourpassword"}'
```

**Option B: Use the Auth collection**
- Import `Quizify_Auth_API.postman_collection.json`
- Run login request
- Copy token from response

### 4. Run Tests

**Recommended Order:**
1. **Setup** folder first (health check, verify auth, get tier info)
2. **Success Scenarios** (if you're basic/educator tier)
3. **SSRF Protection Tests** (should all return 400)
4. **Error Handling Tests**
5. **Cleanup** (delete test quizzes)

---

## 📋 Test Scenarios Included

### Setup (3 requests)
- ✅ Health Check - Verify API is running
- ✅ Verify Authentication - Check JWT token is valid
- ✅ Get User Tier Info - Check tier and quota

### 1. Success Scenarios - Basic Tier (4 requests)
- ✅ Generate Quiz from Wikipedia URL
- ✅ Generate Quiz from Blog Post
- ✅ Generate Quiz from News Article
- ✅ Verify Quiz Saved in Database

### 2. Success Scenarios - Educator Tier (1 request)
- ✅ Generate Quiz (Educator Tier)

### 3. Tier Enforcement (1 request)
- ❌ Free Tier User Rejected (403)

### 4. Quota Enforcement (1 request)
- ❌ Quota Exceeded (403)

### 5. SSRF Protection Tests (6 requests)
- ❌ Reject Localhost URL
- ❌ Reject 127.0.0.1 URL
- ❌ Reject Private IP 192.168.x.x
- ❌ Reject Private IP 10.x.x.x
- ❌ Reject Private IP 172.16.x.x
- ❌ Reject File Protocol

### 6. URL Validation Tests (3 requests)
- ❌ Invalid URL Format
- ❌ Missing Required Fields
- ❌ Invalid Question Count

### 7. Error Handling Tests (2 requests)
- ❌ URL Not Found (404)
- ❌ Insufficient Content (422)

### 8. Performance Tests (2 requests)
- ⏱️ Timeout Test (< 35s)
- ⏱️ Content Truncation Test (500KB max)

### 9. Cleanup (2 requests)
- ✅ List My Quizzes
- ✅ Delete Test Quiz

**Total: 25 test requests**

---

## 🎯 Test Coverage

| Category | Coverage |
|----------|----------|
| **Tier Enforcement** | Free tier rejection with upgrade message |
| **Quota Enforcement** | Basic/educator tier quota limits |
| **SSRF Protection** | Localhost, 127.0.0.1, 192.168.x.x, 10.x.x.x, 172.16.x.x, file:// |
| **URL Validation** | Invalid format, missing fields, invalid protocols |
| **Content Extraction** | Playwright + Trafilatura, min 100 chars, max 500KB |
| **Timeout Handling** | 30-second timeout with proper error messages |
| **Error Responses** | 400, 403, 404, 408, 422, 500 |
| **Database Storage** | content_source_type='url', content_source_reference |

---

## 🔐 Testing Different User Tiers

### Testing as Free Tier User
1. Use auth token for a **free tier** user
2. Run folder **"3. Tier Enforcement"**
3. **Expected:** 403 Forbidden with upgrade message

```json
{
  "detail": {
    "detail": "URL-based quiz generation is a premium feature...",
    "user_tier": "free",
    "required_tier": "basic",
    "upgrade_url": "/api/admin/users/{user_id}/tier"
  }
}
```

### Testing as Basic Tier User
1. Use auth token for a **basic tier** user
2. Run folders **"1. Success Scenarios - Basic Tier"**
3. **Expected:** 201 Created with quiz_id

### Testing as Educator Tier User
1. Use auth token for an **educator tier** user
2. Run folders **"2. Success Scenarios - Educator Tier"**
3. **Expected:** 201 Created with quiz_id

---

## 🛡️ SSRF Protection Testing

The collection includes extensive SSRF (Server-Side Request Forgery) protection tests:

### What is SSRF?
SSRF attacks trick the server into making requests to internal/private resources.

### Protection Implemented
All these URLs should be **REJECTED with 400 Bad Request**:

```
✗ http://localhost:8000/api/test
✗ http://127.0.0.1:8000/api/test
✗ http://192.168.1.1/admin
✗ http://10.0.0.1/internal
✗ http://172.16.0.1/internal
✗ file:///etc/passwd
```

### Testing SSRF Protection
Run folder **"5. SSRF Protection Tests"**

**Expected Results:**
- All requests return **400 Bad Request**
- Error messages mention "localhost" or "private IP"
- No internal resources are accessed

---

## ⚠️ Common Issues & Solutions

### Issue: 401 Unauthorized
**Problem:** Invalid or expired auth token  
**Solution:** Get a fresh token using login endpoint

### Issue: 403 Forbidden (Tier)
**Problem:** User is free tier  
**Solution:** Upgrade user to basic/educator or use different token

### Issue: 403 Forbidden (Quota)
**Problem:** User has reached quota limit  
**Solution:** Delete some quizzes or use different user

### Issue: 408 Request Timeout
**Problem:** Page takes > 30 seconds to load  
**Solution:** Try a different URL or verify network connectivity

### Issue: 422 Insufficient Content
**Problem:** Page has < 100 characters of content  
**Solution:** Try a URL with more substantial content

### Issue: Tests fail with connection errors
**Problem:** API server not running  
**Solution:** Start the API server: `uvicorn main:app --reload`

---

## 📊 Expected Response Times

| Scenario | Expected Time |
|----------|---------------|
| Small page (< 50KB) | 5-10 seconds |
| Medium page (50-200KB) | 10-20 seconds |
| Large page (200-500KB) | 20-30 seconds |
| Timeout | 30 seconds (then 408 error) |

---

## 🧪 Sample Test URLs

### Good URLs for Testing (Should Work)
```
✅ https://en.wikipedia.org/wiki/Machine_learning
✅ https://www.python.org/about/gettingstarted/
✅ https://en.wikipedia.org/wiki/Artificial_intelligence
✅ https://en.wikipedia.org/wiki/Python_(programming_language)
✅ https://developer.mozilla.org/en-US/docs/Web/JavaScript
```

### URLs That Will Fail (For Testing Error Handling)
```
❌ https://en.wikipedia.org/wiki/ThisPageDoesNotExist123456 (404)
❌ https://example.com (Insufficient content - 422)
❌ http://localhost:8000 (SSRF protection - 400)
❌ http://192.168.1.1 (Private IP - 400)
```

---

## 📝 Automated Test Scripts

Each request includes Postman test scripts that automatically verify:
- ✅ Status codes (201, 400, 403, 422, etc.)
- ✅ Response structure (has quiz_id, title, etc.)
- ✅ Error messages (mentions "premium", "quota", "localhost", etc.)
- ✅ Response times (< 35 seconds)
- ✅ Tier enforcement
- ✅ SSRF protection

### View Test Results
1. Run a request
2. Click **Test Results** tab
3. See pass/fail for each assertion
4. Console logs show additional details

---

## 🎬 Running the Full Test Suite

### Option 1: Run Entire Collection
1. Click on collection name
2. Click **Run** button
3. Select all folders
4. Click **Run Quizify - Web URL Quiz Generation**
5. Review results in **Run Summary**

### Option 2: Run Specific Folder
1. Expand collection
2. Right-click folder (e.g., "SSRF Protection Tests")
3. Click **Run folder**
4. Review results

### Option 3: Command Line (Newman)
```bash
# Install Newman
npm install -g newman

# Run collection
newman run Quizify_Web_URL_Quiz_Generation.postman_collection.json \
  --environment your-environment.json \
  --reporters cli,json \
  --reporter-json-export results.json
```

---

## 🔍 Debugging Failed Tests

### Enable Postman Console
1. Click **View** → **Show Postman Console**
2. Run your request
3. See detailed request/response data

### Check Request Details
- **Headers:** Verify Authorization header is set
- **Body:** Ensure JSON is valid
- **URL:** Check base_url variable is correct

### Check Response
- **Status:** Expected vs. actual status code
- **Body:** Error messages provide clues
- **Time:** Timeout if > 30 seconds

---

## 📚 Related Documentation

- **Implementation:** `services/web_scraping_service.py`
- **Handler:** `handlers/quiz_handlers.py` (lines 412-489)
- **Route:** `api/quiz_routes.py`
- **Tests:** `tests/test_web_scraping_service.py`, `tests/test_url_quiz_generation.py`
- **Contract:** `specs/001-comprehensive-quiz-generation/contracts/generate-quiz-from-url.md`
- **Issue:** `docs/GITHUB_ISSUES.md` (Issue #4)

---

## 🚨 Security Notes

### Why SSRF Protection Matters
Without SSRF protection, attackers could:
- Access internal services (databases, admin panels)
- Read local files
- Port scan internal networks
- Access cloud metadata endpoints

### Protection Implemented
✅ Blocks localhost (127.0.0.1, 0.0.0.0, localhost)  
✅ Blocks private IPs (10.x, 192.168.x, 172.16-31.x)  
✅ Blocks link-local (169.254.x.x)  
✅ Only allows HTTP/HTTPS protocols  
✅ Validates URLs before scraping  

---

## 📧 Support

If tests fail unexpectedly:
1. Check API logs: `logs/app.log`
2. Verify Playwright is installed: `playwright --version`
3. Check browser binaries: `playwright install chromium`
4. Verify dependencies: `pip list | grep -E "(playwright|trafilatura)"`

---

**Last Updated:** October 13, 2025  
**Feature Status:** ✅ Fully Implemented and Tested (26 tests passing)  
**Collection Version:** 1.0.0
