# Web URL Quiz Generation - Quick Reference Card

## 🎯 Endpoint

```http
POST /api/quiz/generate/url
```

**Status:** 201 Created (success)  
**Auth:** Bearer token required  
**Tier:** Basic or Educator only (Free tier blocked)

---

## 📥 Request

### Headers
```
Authorization: Bearer <your_jwt_token>
Content-Type: application/json
```

### Body
```json
{
  "url": "https://en.wikipedia.org/wiki/Machine_learning",
  "title": "Machine Learning Quiz",
  "num_questions": 10,
  "question_type": ["multiple_choice", "true_false"]
}
```

### Field Validation
| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `url` | HttpUrl | Yes | HTTP/HTTPS only, no private IPs |
| `title` | string | Yes | 1-200 characters |
| `num_questions` | int | Yes | 1-50 |
| `question_type` | array | Yes | ["multiple_choice", "true_false", "mixed"] |

---

## 📤 Response

### Success (201)
```json
{
  "quiz_id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "Machine Learning Quiz",
  "message": "Quiz generated successfully from URL",
  "source_url": "https://en.wikipedia.org/wiki/Machine_learning"
}
```

### Free Tier Rejected (403)
```json
{
  "detail": {
    "detail": "URL-based quiz generation is a premium feature. Upgrade to basic or educator tier.",
    "user_tier": "free",
    "required_tier": "basic",
    "upgrade_url": "/api/admin/users/{user_id}/tier"
  }
}
```

### Quota Exceeded (403)
```json
{
  "detail": {
    "detail": "Quiz quota exceeded for basic tier (20/20). Upgrade to educator tier for more quizzes.",
    "current_count": 20,
    "quota_limit": 20,
    "user_tier": "basic"
  }
}
```

### SSRF Protection (400)
```json
{
  "detail": "Cannot scrape localhost URLs."
}
```

### Invalid URL (400)
```json
{
  "detail": "Invalid URL protocol. Only HTTP and HTTPS are allowed."
}
```

### Timeout (408)
```json
{
  "detail": "Request timeout. The page took longer than 30 seconds to load."
}
```

### Insufficient Content (422)
```json
{
  "detail": "Extracted content too short (minimum 100 characters)."
}
```

---

## 🛡️ SSRF Protection

### ❌ Blocked URLs
```
http://localhost:8000
http://127.0.0.1:8000
http://0.0.0.0:8000
http://192.168.1.1
http://10.0.0.1
http://172.16.0.1
file:///etc/passwd
ftp://example.com
```

### ✅ Allowed URLs
```
https://en.wikipedia.org/wiki/...
https://www.python.org/...
https://developer.mozilla.org/...
http://example.com (public domain)
```

---

## 🔢 Status Codes

| Code | Meaning | Reason |
|------|---------|--------|
| 201 | Created | Quiz generated successfully |
| 400 | Bad Request | Invalid URL, SSRF protection triggered |
| 401 | Unauthorized | Missing or invalid auth token |
| 403 | Forbidden | Free tier user or quota exceeded |
| 404 | Not Found | URL returned 404 |
| 408 | Request Timeout | Page load took > 30 seconds |
| 422 | Unprocessable Entity | Invalid fields or insufficient content |
| 500 | Internal Server Error | Server error during scraping |

---

## ⚡ Features

### Web Scraping
- **Playwright:** Browser automation for JavaScript-rendered content
- **Trafilatura:** Intelligent extraction (removes nav, ads, footers)
- **Timeout:** 30 seconds maximum
- **Content:** Min 100 chars, max 500KB (auto-truncates)
- **User Agent:** Custom bot identifier

### Tier System
| Tier | Access | Quota |
|------|--------|-------|
| Free | ❌ Blocked | - |
| Basic | ✅ Allowed | 20 quizzes/month |
| Educator | ✅ Allowed | Unlimited |

### Database Storage
- `content_source_type`: "url"
- `content_source_reference`: Original URL
- `scrape_timestamp`: When scraped
- `content_length`: Extracted text length
- `word_count`: Number of words

---

## 🧪 Postman Variables

```javascript
// Set in Collection/Environment
base_url: "http://localhost:8000"
auth_token: "eyJhbGci..."

// Auto-set by tests
user_id: "uuid"
user_tier: "basic"
url_quiz_id: "uuid"
current_quiz_count: 5
quota_limit: 20
```

---

## 🎬 Quick Test Commands

### Using cURL
```bash
# Success case
curl -X POST http://localhost:8000/api/quiz/generate/url \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://en.wikipedia.org/wiki/Python",
    "title": "Python Quiz",
    "num_questions": 5,
    "question_type": ["multiple_choice"]
  }'

# SSRF test (should fail)
curl -X POST http://localhost:8000/api/quiz/generate/url \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "http://localhost:8000/api/test",
    "title": "Test",
    "num_questions": 5,
    "question_type": ["multiple_choice"]
  }'
```

### Using httpie
```bash
# Success case
http POST http://localhost:8000/api/quiz/generate/url \
  Authorization:"Bearer YOUR_TOKEN" \
  url="https://en.wikipedia.org/wiki/Python" \
  title="Python Quiz" \
  num_questions:=5 \
  question_type:='["multiple_choice"]'
```

---

## 📊 Performance

| Metric | Value |
|--------|-------|
| Max timeout | 30 seconds |
| Min content | 100 characters |
| Max content | 500KB (512,000 bytes) |
| Typical response | 5-20 seconds |
| Browser | Chromium (headless) |

---

## 🐛 Troubleshooting

### 401 Unauthorized
→ Check auth token is valid and not expired

### 403 Free Tier
→ Upgrade user to basic/educator tier

### 403 Quota
→ User has reached monthly limit

### 400 SSRF
→ URL is localhost or private IP (by design)

### 408 Timeout
→ Page took > 30s to load, try different URL

### 422 Content
→ Page has < 100 chars, try URL with more content

### 500 Error
→ Check server logs: `logs/app.log`

---

## 📚 Test Files

| File | Purpose |
|------|---------|
| `Quizify_Web_URL_Quiz_Generation.postman_collection.json` | Complete test suite (25 tests) |
| `README_WEB_URL_TESTING.md` | Full testing guide |
| `WEB_URL_QUICK_REFERENCE.md` | This file |

---

## ✅ Pre-flight Checklist

Before testing:
- [ ] API server running (`uvicorn main:app --reload`)
- [ ] Playwright installed (`playwright --version`)
- [ ] Browser binaries installed (`playwright install chromium`)
- [ ] Valid auth token obtained
- [ ] User is basic/educator tier (for success tests)
- [ ] Postman collection imported
- [ ] Environment variables configured

---

## 🔗 URLs for Testing

### Good Test URLs
```
✅ https://en.wikipedia.org/wiki/Machine_learning
✅ https://en.wikipedia.org/wiki/Python_(programming_language)
✅ https://www.python.org/about/gettingstarted/
✅ https://developer.mozilla.org/en-US/docs/Web/JavaScript
```

### Bad Test URLs (For Error Testing)
```
❌ http://localhost:8000 (SSRF - 400)
❌ http://192.168.1.1 (Private IP - 400)
❌ https://example.com (Minimal content - 422)
❌ https://en.wikipedia.org/wiki/NonExistent123 (404)
```

---

**Version:** 1.0.0  
**Last Updated:** October 13, 2025  
**Feature:** Issue #4 - Web URL Quiz Generation  
**Status:** ✅ Fully Implemented (26 tests passing)
