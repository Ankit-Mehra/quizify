# Epic: Google Forms Export Feature

**Epic ID**: QUIZ-002  
**Created**: 2025-11-27  
**Status**: 🟡 In Progress  
**Branch**: `feature/google-forms-export`  
**Priority**: High  

---

## 📋 Overview

Enable users to export quizzes directly to Google Forms, creating a fully functional Google Form with quiz mode enabled, questions, and auto-grading configured.

### Business Value
- Users can distribute quizzes via Google Forms ecosystem
- Leverages Google's infrastructure for quiz taking and grading
- Integrates with Google Classroom and Google Workspace
- Pro-exclusive feature (drives upgrades from Free and Premium tiers)

### Success Criteria
- [ ] Pro tier users can export any quiz to Google Forms
- [ ] Exported form has quiz mode enabled with auto-grading
- [ ] MCQ and True/False questions are properly mapped
- [ ] Users receive a shareable Google Forms URL
- [ ] OAuth flow allows users to connect their Google account

---

## 🏗️ Architecture

### OAuth2 Flow
```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  Client  │────▶│  Backend │────▶│  Google  │────▶│  Backend │
│          │     │          │     │  OAuth   │     │  (token) │
└──────────┘     └──────────┘     └──────────┘     └──────────┘
     │                                                   │
     │           ┌──────────────────────────────────────┘
     │           ▼
     │    ┌──────────┐     ┌──────────┐
     └───▶│  Export  │────▶│  Google  │
          │  Request │     │Forms API │
          └──────────┘     └──────────┘
```

### Component Diagram
```
┌─────────────────────────────────────────────────────────────┐
│                     Export System                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  schemas/export.py                                           │
│  └── ExportFormat.GOOGLE_FORMS (new)                        │
│                                                              │
│  services/exporters/                                         │
│  ├── google_forms_exporter.py (new)                         │
│  ├── tier_validator.py (update PRO_ONLY_FORMATS)            │
│  └── __init__.py (register exporter)                        │
│                                                              │
│  services/google_auth_service.py (new)                      │
│  └── OAuth2 token management                                │
│                                                              │
│  api/auth_routes.py (update)                                │
│  └── /auth/google/connect, /callback, /disconnect           │
│                                                              │
│  migrations/019_add_google_oauth_tokens.sql (new)           │
│  └── Add google_refresh_token to profiles                   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 📦 Phases

### Phase 1: Foundation
**Status**: ✅ Complete  
**Target**: Add format enum and exporter skeleton

| Task ID | Description | Status | Assignee |
|---------|-------------|--------|----------|
| P1-001 | Add `GOOGLE_FORMS` to `ExportFormat` enum | ✅ | Copilot |
| P1-002 | Add `GOOGLE_FORMS` to `PRO_ONLY_FORMATS` | ✅ | Copilot |
| P1-003 | Create `google_forms_exporter.py` skeleton | ✅ | Copilot |
| P1-004 | Register exporter in factory | ✅ | Copilot |
| P1-005 | Add Google API dependencies to requirements.txt | ✅ | Copilot |

### Phase 2: OAuth Integration  
**Status**: ✅ Complete  
**Target**: Enable users to connect Google accounts

| Task ID | Description | Status | Assignee |
|---------|-------------|--------|----------|
| P2-001 | Create migration for google tokens in profiles | ✅ | Copilot |
| P2-002 | Create `google_auth_service.py` | ✅ | Copilot |
| P2-003 | Add `/auth/google/connect` endpoint | ✅ | Copilot |
| P2-004 | Add `/auth/google/callback` endpoint | ✅ | Copilot |
| P2-005 | Add `/auth/google/disconnect` endpoint | ✅ | Copilot |
| P2-006 | Add `/auth/google/status` endpoint | ✅ | Copilot |
| P2-007 | Handle token refresh logic | ✅ | Copilot |

### Phase 3: Forms Export Implementation
**Status**: ✅ Complete  
**Target**: Full export functionality

| Task ID | Description | Status | Assignee |
|---------|-------------|--------|----------|
| P3-001 | Implement form creation via Forms API | ✅ | Copilot |
| P3-002 | Enable quiz mode via batchUpdate | ✅ | Copilot |
| P3-003 | Map MCQ questions to choiceQuestion | ✅ | Copilot |
| P3-004 | Map True/False to choiceQuestion | ✅ | Copilot |
| P3-005 | Handle fill_blank as textQuestion | ✅ | Copilot |
| P3-006 | Configure grading with correctAnswers | ✅ | Copilot |
| P3-007 | Set point values for questions | ✅ | Copilot |
| P3-008 | Handle matching questions (skip or convert) | ✅ | Copilot |
| P3-009 | Return form URL in ExportResult | ✅ | Copilot |

### Phase 4: Testing & Documentation
**Status**: 🟡 In Progress  
**Target**: Comprehensive test coverage

| Task ID | Description | Status | Assignee |
|---------|-------------|--------|----------|
| P4-001 | Unit tests for GoogleFormsExporter | ✅ | Copilot |
| P4-002 | Unit tests for google_auth_service | ✅ | Copilot |
| P4-003 | Integration tests with mocked Google API | ⬜ | - |
| P4-004 | Contract tests for new endpoints | ⬜ | - |
| P4-005 | Update API documentation | ⬜ | - |
| P4-006 | Add usage guide to docs/ | ⬜ | - |

### Phase 5: PR & Review
**Status**: 🔴 Not Started  
**Target**: Code review and merge

| Task ID | Description | Status | Assignee |
|---------|-------------|--------|----------|
| P5-001 | Create PR to deploy/staging | ⬜ | - |
| P5-002 | Request Copilot review | ⬜ | - |
| P5-003 | Address review feedback (3 iterations min) | ⬜ | - |
| P5-004 | Merge to staging | ⬜ | - |
| P5-005 | Verify on staging environment | ⬜ | - |

---

## 🔧 Technical Specifications

### Dependencies
```
google-api-python-client>=2.100.0
google-auth-httplib2>=0.2.0
google-auth-oauthlib>=1.1.0
```

### Environment Variables
```bash
# Google OAuth2 Configuration
GOOGLE_CLIENT_ID=<from-google-cloud-console>
GOOGLE_CLIENT_SECRET=<from-google-cloud-console>
GOOGLE_REDIRECT_URI=https://quizify.app/api/auth/google/callback

# For local development
GOOGLE_REDIRECT_URI=http://localhost:8000/api/auth/google/callback
```

### Database Schema Changes
```sql
-- Migration: 019_add_google_oauth_tokens.sql
ALTER TABLE profiles 
ADD COLUMN google_refresh_token TEXT,
ADD COLUMN google_token_expires_at TIMESTAMPTZ,
ADD COLUMN google_connected_at TIMESTAMPTZ;

-- Index for quick lookup
CREATE INDEX idx_profiles_google_connected 
ON profiles(id) WHERE google_refresh_token IS NOT NULL;
```

### Google Forms API Mapping

| Quizify Type | Google Forms Type | API Field |
|-------------|-------------------|-----------|
| `multiple_choice` | RADIO | `choiceQuestion.type: "RADIO"` |
| `true_false` | RADIO | `choiceQuestion.type: "RADIO"` with True/False options |
| `fill_blank` | Short Answer | `textQuestion.paragraph: false` |
| `matching` | ⚠️ Not Supported | Skip with warning or convert to MCQ |

### API Request/Response

#### Export to Google Forms Request
```http
POST /api/quiz/{quiz_id}/export
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "format": "google_forms",
  "include_answer_key": true,
  "include_explanations": false
}
```

#### Success Response
```json
{
  "form_url": "https://docs.google.com/forms/d/e/1FAIpQLSc.../viewform",
  "edit_url": "https://docs.google.com/forms/d/1abc.../edit",
  "form_id": "1abc..."
}
```

#### OAuth Required Response (403)
```json
{
  "error": "google_auth_required",
  "message": "Please connect your Google account to export to Google Forms",
  "auth_url": "/api/auth/google/connect",
  "current_tier": "pro"
}
```

---

## ⚠️ Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Google API rate limits | Medium | Low | Implement exponential backoff |
| OAuth token expiry | Low | Medium | Auto-refresh before export |
| Matching questions unsupported | Low | High | Skip with user notification |
| Google API changes | Medium | Low | Pin API version, monitor deprecations |
| Token storage security | High | Low | Encrypt refresh tokens at rest |

---

## 📝 Notes

### Google Cloud Console Setup Required
1. Create project in Google Cloud Console
2. Enable Google Forms API
3. Configure OAuth consent screen
4. Create OAuth 2.0 credentials (Web application)
5. Add authorized redirect URIs

### Scopes Required
- `https://www.googleapis.com/auth/forms.body` - Create and modify forms

### Rate Limits (Google Forms API)
- Read requests: 300 per minute per user
- Write requests: 60 per minute per user

---

## 📚 References

- [Google Forms API Documentation](https://developers.google.com/forms/api/guides)
- [Google Forms API Reference](https://developers.google.com/forms/api/reference/rest)
- [Python Quickstart](https://developers.google.com/forms/api/quickstart/python)
- [OAuth 2.0 for Web Apps](https://developers.google.com/identity/protocols/oauth2/web-server)

---

## 📅 Changelog

| Date | Change | Author |
|------|--------|--------|
| 2025-11-27 | Epic created | - |
| 2025-11-27 | Phase 1-3 implemented: enum, exporter, OAuth service, endpoints, migration | Copilot |
| 2025-11-27 | Phase 4 started: 36 unit tests added and passing | Copilot |
| 2025-11-27 | **Tier policy update**: Google Forms is Pro-only (QTI, Moodle XML, Google Forms all require Pro) | Copilot |

