# Frontend Implementation: Google Forms Export OAuth Flow

## Overview

> **Updated December 2025**: Google Forms export is now available to **all tiers** (Free, Basic, Pro). The OAuth flow remains the same - users still need to connect their Google account to export.

Google Forms export requires OAuth2 authentication. When a user clicks "Export to Google Forms", the backend will either:
1. Complete the export (if already connected)
2. Return an auth URL for OAuth (if not connected)

The frontend handles the OAuth redirect flow and retries the export after authorization.

---

## API Endpoint

```
POST /api/quizzes/{quiz_id}/export
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "format": "google_forms",
  "include_answer_key": true,
  "include_explanations": false
}
```

---

## Response Scenarios

### 1. User NOT Connected to Google (401)

```json
{
  "error": "google_connection_required",
  "message": "Please connect your Google account to export to Google Forms",
  "auth_url": "https://accounts.google.com/o/oauth2/v2/auth?client_id=...&redirect_uri=...&scope=...&state=...",
  "state": "timestamp:user-id:signature"
}
```

> **Security Note:**  
> The `state` parameter is an HMAC-signed token containing a timestamp and user identifier.  
> This protects against CSRF attacks and prevents tampering with the OAuth flow.  
> The backend validates this signature in the callback before processing the authorization.

**Frontend Action:**

```javascript
// 1. Store pending export in sessionStorage
sessionStorage.setItem('pendingGoogleExport', JSON.stringify({
  quizId: quizId,
  options: { 
    format: 'google_forms',
    include_answer_key: true 
  }
}));

// 2. Redirect user to Google consent screen
window.location.href = response.auth_url;
```

---

### 2. After OAuth Callback

After user authorizes on Google, they are redirected to:
```
{FRONTEND_URL}/settings?google_connected=true
```

**Frontend Action (on Settings page or App init):**

```javascript
// Check URL params and sessionStorage
const params = new URLSearchParams(window.location.search);
const googleConnected = params.get('google_connected');
const pending = sessionStorage.getItem('pendingGoogleExport');

if (googleConnected === 'true' && pending) {
  const { quizId, options } = JSON.parse(pending);
  sessionStorage.removeItem('pendingGoogleExport');
  
  // Clean up URL
  window.history.replaceState({}, '', '/settings');
  
  // Retry the export
  try {
    const result = await exportToGoogleForms(quizId, options);
    // Show success - open form in new tab
    window.open(result.form_url, '_blank');
  } catch (error) {
    showToast('Export failed. Please try again.', 'error');
  }
}

// Handle OAuth errors
const googleError = params.get('google_error');
if (googleError) {
  sessionStorage.removeItem('pendingGoogleExport');
  
  // NOTE (December 2025): tier_insufficient error is no longer used.
  // Google Forms export is available to all tiers.
  const errorMessages = {
    'access_denied': 'Google authorization was cancelled',
    'invalid_state': 'Authorization failed. Please try again.',
    'state_expired': 'Authorization link expired. Please try again.'
  };
  
  showToast(errorMessages[googleError] || 'Google connection failed', 'error');
}
```

---

### 3. Export SUCCESS (200)

```json
{
  "form_url": "https://docs.google.com/forms/d/e/xxx/viewform",
  "edit_url": "https://docs.google.com/forms/d/xxx/edit",
  "form_id": "1ABC123xyz..."
}
```

**Frontend Action:**

```javascript
// Option A: Open form in new tab
window.open(response.form_url, '_blank');

// Option B: Show success modal with options
showModal({
  title: 'Google Form Created!',
  content: 'Your quiz has been exported to Google Forms.',
  actions: [
    { label: 'View Form', onClick: () => window.open(response.form_url, '_blank') },
    { label: 'Edit Form', onClick: () => window.open(response.edit_url, '_blank') }
  ]
});
```

---

### 4. Tier Insufficient (DEPRECATED - December 2025)

> **Note**: This error is no longer returned. Google Forms export is now available to all tiers. This section is kept for historical reference only.

~~```json
{
  "detail": {
    "error": "tier_insufficient",
    "message": "Google Forms export requires a Pro subscription",
    "required_tier": "pro",
    "current_tier": "premium"
  }
}
```~~

---

### 5. Other Errors

| Status | Error | Message | Action |
|--------|-------|---------|--------|
| 500 | Export failed | `"Export failed: {reason}"` | Show error toast |
| 503 | Not configured | `"Google Forms export is not configured..."` | Show "Contact support" |
| 422 | Invalid format | `"Export format 'x' is not available"` | Show error toast |

---

## Complete Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                User clicks "Export to Google Forms"             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              POST /api/quizzes/{id}/export                      │
│              { "format": "google_forms" }                       │
└─────────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
          ▼                   ▼                   ▼
    ┌──────────┐        ┌──────────┐        ┌──────────┐
    │   403    │        │   401    │        │   200    │
    │  Tier    │        │  Google  │        │ Success  │
    │Insufficient│      │Connection│        │          │
    └──────────┘        │ Required │        └──────────┘
          │             └──────────┘              │
          ▼                   │                   ▼
    ┌──────────┐              │            ┌──────────┐
    │  Show    │              ▼            │  Open    │
    │ Upgrade  │        ┌──────────┐       │ Form URL │
    │  Modal   │        │  Save    │       │ in Tab   │
    └──────────┘        │ Pending  │       └──────────┘
                        │ Export   │
                        └──────────┘
                              │
                              ▼
                        ┌──────────┐
                        │ Redirect │
                        │to auth_url│
                        └──────────┘
                              │
                              ▼
                        ┌──────────┐
                        │  Google  │
                        │ Consent  │
                        │  Screen  │
                        └──────────┘
                              │
                    ┌─────────┴─────────┐
                    │                   │
                    ▼                   ▼
              ┌──────────┐        ┌──────────┐
              │ Approved │        │ Denied   │
              └──────────┘        └──────────┘
                    │                   │
                    ▼                   ▼
              ┌──────────┐        ┌──────────┐
              │ Callback │        │ Callback │
              │?google_  │        │?google_  │
              │connected │        │error=    │
              │=true     │        │access_   │
              └──────────┘        │denied    │
                    │             └──────────┘
                    ▼                   │
              ┌──────────┐              ▼
              │  Check   │        ┌──────────┐
              │ Session  │        │  Show    │
              │ Storage  │        │  Error   │
              └──────────┘        │  Toast   │
                    │             └──────────┘
                    ▼
              ┌──────────┐
              │  Retry   │
              │  Export  │
              └──────────┘
                    │
                    ▼
              ┌──────────┐
              │   200    │
              │ Success  │
              └──────────┘
                    │
                    ▼
              ┌──────────┐
              │  Open    │
              │ Form URL │
              └──────────┘
```

---

## Example React Implementation

```tsx
// hooks/useGoogleFormsExport.ts
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '@/lib/api';

interface ExportOptions {
  include_answer_key?: boolean;
  include_explanations?: boolean;
}

interface ExportResult {
  form_url: string;
  edit_url: string;
  form_id: string;
}

export function useGoogleFormsExport() {
  const [isExporting, setIsExporting] = useState(false);
  const navigate = useNavigate();

  const exportToGoogleForms = async (
    quizId: string, 
    options: ExportOptions = {}
  ): Promise<ExportResult | null> => {
    setIsExporting(true);
    
    try {
      const response = await api.post(`/quizzes/${quizId}/export`, {
        format: 'google_forms',
        ...options
      });
      
      return response.data;
      
    } catch (error: any) {
      const status = error.response?.status;
      const data = error.response?.data;
      
      if (status === 401 && data?.error === 'google_connection_required') {
        // Validate auth_url is a legitimate Google OAuth URL before redirecting
        // This prevents potential open redirect vulnerabilities
        if (typeof data.auth_url === 'string' && 
            data.auth_url.startsWith('https://accounts.google.com/o/oauth2')) {
          // Store pending export and redirect to Google OAuth
          sessionStorage.setItem('pendingGoogleExport', JSON.stringify({
            quizId,
            options: { format: 'google_forms', ...options }
          }));
          
          window.location.href = data.auth_url;
        } else {
          throw new Error('Invalid OAuth URL received from server');
        }
        return null;
      }
      
      if (status === 403 && data?.detail?.error === 'tier_insufficient') {
        // Show upgrade modal
        throw new Error('PRO_REQUIRED');
      }
      
      throw error;
      
    } finally {
      setIsExporting(false);
    }
  };

  return { exportToGoogleForms, isExporting };
}
```

```tsx
// hooks/useGoogleOAuthCallback.ts
import { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useGoogleFormsExport } from './useGoogleFormsExport';
import { toast } from '@/components/ui/toast';

export function useGoogleOAuthCallback() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { exportToGoogleForms } = useGoogleFormsExport();

  useEffect(() => {
    const googleConnected = searchParams.get('google_connected');
    const googleError = searchParams.get('google_error');
    
    // Handle successful connection
    if (googleConnected === 'true') {
      const pending = sessionStorage.getItem('pendingGoogleExport');
      
      if (pending) {
        const { quizId, options } = JSON.parse(pending);
        sessionStorage.removeItem('pendingGoogleExport');
        
        // Clean URL
        searchParams.delete('google_connected');
        setSearchParams(searchParams);
        
        // Retry export
        exportToGoogleForms(quizId, options)
          .then((result) => {
            if (result) {
              toast.success('Google Form created successfully!');
              window.open(result.form_url, '_blank');
            }
          })
          .catch(() => {
            toast.error('Export failed. Please try again.');
          });
      } else {
        toast.success('Google account connected!');
        searchParams.delete('google_connected');
        setSearchParams(searchParams);
      }
    }
    
    // Handle errors
    if (googleError) {
      sessionStorage.removeItem('pendingGoogleExport');
      
      const errorMessages: Record<string, string> = {
        'access_denied': 'Google authorization was cancelled',
        'tier_insufficient': 'Google Forms export requires a Pro subscription',
        'invalid_state': 'Authorization failed. Please try again.',
        'state_expired': 'Authorization link expired. Please try again.',
      };
      
      toast.error(errorMessages[googleError] || 'Google connection failed');
      
      searchParams.delete('google_error');
      setSearchParams(searchParams);
    }
  }, [searchParams]);
}
```

```tsx
// components/ExportButton.tsx
import { useGoogleFormsExport } from '@/hooks/useGoogleFormsExport';

export function ExportToGoogleFormsButton({ quizId }: { quizId: string }) {
  const { exportToGoogleForms, isExporting } = useGoogleFormsExport();

  const handleExport = async () => {
    try {
      const result = await exportToGoogleForms(quizId, {
        include_answer_key: true
      });
      
      if (result) {
        window.open(result.form_url, '_blank');
      }
    } catch (error: any) {
      if (error.message === 'PRO_REQUIRED') {
        // Show upgrade modal
        openUpgradeModal();
      } else {
        toast.error('Export failed. Please try again.');
      }
    }
  };

  return (
    <button onClick={handleExport} disabled={isExporting}>
      {isExporting ? 'Exporting...' : 'Export to Google Forms'}
    </button>
  );
}
```

---

## Testing Checklist

- [ ] Pro user without Google connected → Redirects to OAuth
- [ ] OAuth approved → Returns to app and retries export
- [ ] OAuth denied → Shows error message
- [ ] Pro user with Google connected → Export succeeds immediately
- [ ] Premium/Free user → Shows upgrade modal (403)
- [ ] Form URL opens correctly in new tab
- [ ] Pending export cleared after success/error
- [ ] URL params cleaned up after handling

---

## Related Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/google/connect` | GET | Get OAuth URL (alternative to export flow) |
| `/api/auth/google/status` | GET | Check if user is connected to Google |
| `/api/auth/google/disconnect` | POST | Remove Google connection |
| `/api/quizzes/{id}/export` | POST | Export quiz (triggers OAuth if needed) |
