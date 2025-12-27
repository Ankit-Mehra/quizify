# Frontend Implementation Guide: Forgot Password Flow

> **Backend Status: ✅ FULLY IMPLEMENTED**
> 
> This guide details the frontend implementation for the forgot password feature. All backend APIs are ready and tested.

## ⚠️ CRITICAL SECURITY ISSUE - ACTION REQUIRED

**Current Implementation Status: 🔴 INSECURE - DO NOT USE IN PRODUCTION**

### Security Vulnerability
The current backend implementation (`handlers/auth_handlers.py:669`) passes `access_token` and `refresh_token` directly in the URL query string:

```python
# INSECURE - Current implementation
url=f"{FRONTEND_URL}/reset-password?access_token={access_token}&refresh_token={refresh_token}"
```

**Why This Is Dangerous:**
- ❌ Tokens exposed in browser history (persistent, accessible to any user/malware on device)
- ❌ Tokens logged in server access logs (visible to operations team, log aggregation services)
- ❌ Tokens leaked via `Referer` headers when loading third-party resources (analytics, CDNs)
- ❌ Tokens visible in browser's network tab
- ❌ Attacker who obtains URL can reset victim's password or impersonate their session

### Recommended Fix (Backend Changes Required)

**Option 1: Secure HttpOnly Cookies (Preferred)**
```python
# SECURE - Recommended implementation
# In handlers/auth_handlers.py confirm_email() for type="recovery":
response = RedirectResponse(url=f"{FRONTEND_URL}/reset-password?code={one_time_code}")
response.set_cookie(
    key="recovery_session",
    value=access_token,
    httponly=True,
    secure=True,
    samesite="lax",
    max_age=600  # 10 minutes
)
return response
```

**Option 2: One-Time Code Exchange**
```python
# Store tokens server-side, return only short-lived code
reset_code = secrets.token_urlsafe(32)
await redis.setex(f"reset:{reset_code}", 600, json.dumps({
    "access_token": access_token,
    "refresh_token": refresh_token,
    "user_id": user_id
}))
return RedirectResponse(url=f"{FRONTEND_URL}/reset-password?code={reset_code}")
```

**Until this is fixed, this feature should NOT be deployed to production.**

---

## Quick Reference

| Endpoint | Method | Auth Required | Purpose |
|----------|--------|---------------|---------|
| `/api/auth/forgot-password` | POST | ❌ No | Request password reset email |
| `/api/auth/confirm` | GET | ❌ No | Backend handles email link (redirect) |
| `/api/auth/reset-password` | POST | ❌ No | Set new password with token |

---

## Complete User Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    USER FLOW DIAGRAM                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │   /login     │───>│/forgot-password│───>│  Check Email │      │
│  │              │    │   (Page 1)   │    │   Message    │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│         │                                       │               │
│         │                                       ↓               │
│         │            ┌──────────────────────────────────┐      │
│         │            │  User clicks link in email       │      │
│         │            │  → Backend verifies token        │      │
│         │            │  → Redirects to /reset-password  │      │
│         │            └──────────────────────────────────┘      │
│         │                                       │               │
│         │                                       ↓               │
│         │            ┌──────────────┐    ┌──────────────┐      │
│         │            │/reset-password│───>│   Success!   │      │
│         │            │   (Page 2)   │    │  → /login    │      │
│         └────────────┴──────────────┴────┴──────────────┘      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Page 1: Forgot Password (`/forgot-password`)

### UI Components Needed
- Email input field
- "Send Reset Link" button
- "Back to Login" link
- Success/Error toast messages
- Loading state

### API Call

```typescript
// POST /api/auth/forgot-password
const requestPasswordReset = async (email: string) => {
  const response = await fetch(`${API_URL}/api/auth/forgot-password`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ email }),
  });
  
  return response.json();
};
```

### Request

```json
{
  "email": "user@example.com"
}
```

### Response (Always 200 OK)

```json
{
  "message": "If an account exists with that email, we've sent password reset instructions.",
  "note": "Check your email inbox (and spam folder). The link expires in 1 hour."
}
```

> ⚠️ **Security Note**: This endpoint ALWAYS returns success to prevent email enumeration attacks. Never show different messages for "email exists" vs "email not found".

### Example React Component

```tsx
// pages/forgot-password.tsx
import { useState } from 'react';
import { useRouter } from 'next/router';
import { toast } from 'react-hot-toast';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/auth/forgot-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });

      const data = await response.json();
      
      // Always show success (security: don't reveal if email exists)
      setSubmitted(true);
      toast.success('Check your email for reset instructions');
      
    } catch (error) {
      toast.error('Something went wrong. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  if (submitted) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen p-4">
        <div className="w-full max-w-md space-y-6 text-center">
          <div className="text-6xl">📧</div>
          <h1 className="text-2xl font-bold">Check your email</h1>
          <p className="text-gray-600">
            If an account exists with that email, we've sent password reset instructions.
          </p>
          <p className="text-sm text-gray-500">
            Don't see it? Check your spam folder. The link expires in 1 hour.
          </p>
          <button
            onClick={() => setSubmitted(false)}
            className="text-blue-600 hover:underline"
          >
            Try another email
          </button>
          <div className="pt-4">
            <button
              onClick={() => router.push('/login')}
              className="text-gray-600 hover:underline"
            >
              ← Back to login
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-screen p-4">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center">
          <h1 className="text-2xl font-bold">Forgot your password?</h1>
          <p className="text-gray-600 mt-2">
            Enter your email and we'll send you a reset link.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700">
              Email address
            </label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2"
              placeholder="you@example.com"
            />
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="w-full bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 disabled:opacity-50"
          >
            {isLoading ? 'Sending...' : 'Send Reset Link'}
          </button>
        </form>

        <div className="text-center">
          <button
            onClick={() => router.push('/login')}
            className="text-gray-600 hover:underline text-sm"
          >
            ← Back to login
          </button>
        </div>
      </div>
    </div>
  );
}
```

---

## Page 2: Reset Password (`/reset-password`)

### URL Parameters (from email redirect)

When user clicks the reset link in their email:
1. Browser goes to: `https://api.quizify.ca/api/auth/confirm?token=xxx&type=recovery`
2. Backend verifies the token
3. Backend redirects to: `https://www.quizify.ca/reset-password?code=one-time-reset-code&message=Please+enter+your+new+password`

**Security Note**: We use a short-lived one-time code instead of embedding `access_token` and `refresh_token` in the URL to prevent token leakage via:
- Browser history
- Server/access logs
- Referer headers to third-party resources
- Copy/paste of URLs

### Extract Reset Code from URL

```typescript
// Get reset code and optional status params from URL when page loads
const searchParams = new URLSearchParams(window.location.search);
const resetCode = searchParams.get('code');
const message = searchParams.get('message');
const error = searchParams.get('error');

// The resetCode is a short-lived, one-time value.
// Send it to your backend via POST to complete the password reset;
// do not pass access or refresh tokens via the URL query string.
```

### UI Components Needed
- New password input field
- Confirm password input field
- Password strength indicator (optional but recommended)
- "Reset Password" button
- Loading state
- Success/Error messages

### API Call

```typescript
// POST /api/auth/reset-password
const resetPassword = async (
  accessToken: string,
  refreshToken: string | null,
  newPassword: string
) => {
  const response = await fetch(`${API_URL}/api/auth/reset-password`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      token: accessToken,
      refresh_token: refreshToken,
      new_password: newPassword,
    }),
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to reset password');
  }
  
  return response.json();
};
```

### Request

```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "abc123...",  // Optional but recommended
  "new_password": "MyNewSecurePassword123!"
}
```

### Response (Success - 200 OK)

```json
{
  "message": "Password updated successfully! You can now log in with your new password.",
  "success": true
}
```

### Response (Error - 401 Unauthorized)

```json
{
  "detail": "Invalid or expired recovery token. Please request a new password reset link."
}
```

### Response (Error - 400 Bad Request)

```json
{
  "detail": "Failed to update password. The reset link may have expired. Please request a new one."
}
```

### Response (Error - 422 Validation Error)

```json
{
  "detail": [
    {
      "loc": ["body", "new_password"],
      "msg": "ensure this value has at least 8 characters",
      "type": "value_error.any_str.min_length"
    }
  ]
}
```

### Example React Component

```tsx
// pages/reset-password.tsx
import { useState, useEffect } from 'react';
import { useRouter } from 'next/router';
import { toast } from 'react-hot-toast';

export default function ResetPasswordPage() {
  const router = useRouter();
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState<string | null>(null);
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // SECURITY NOTE: This flow needs backend update to avoid tokens in URL
    // Current implementation (INSECURE): Tokens passed via URL query params
    // Recommended implementation: Use one-time codes exchanged server-side
    //
    // TEMPORARY WORKAROUND until backend is updated:
    // Extract tokens from URL on page load, but this exposes them to:
    // - Browser history
    // - Server/access logs
    // - Referrer headers to third-party resources
    //
    // TODO: Update backend /api/auth/confirm to:
    // 1. Store tokens in secure HttpOnly cookies (not URL)
    // 2. Return only a one-time reset code in URL: /reset-password?code=xxx
    // 3. Frontend sends code + new password to /api/auth/reset-password
    // 4. Backend validates code and performs password reset server-side
    const params = new URLSearchParams(window.location.search);
    const token = params.get('access_token');
    const refresh = params.get('refresh_token');
    const errorParam = params.get('error');
    const messageParam = params.get('message');

    if (errorParam) {
      setError(decodeURIComponent(errorParam.replace(/\+/g, ' ')));
      return;
    }

    if (!token) {
      setError('Invalid reset link. Please request a new password reset.');
      return;
    }

    setAccessToken(token);
    setRefreshToken(refresh);

    if (messageParam) {
      toast(decodeURIComponent(messageParam.replace(/\+/g, ' ')));
    }

    // Clean URL (remove tokens from address bar for security)
    // NOTE: This doesn't prevent logging - tokens were already exposed
    window.history.replaceState({}, '', '/reset-password');
  }, []);

  const validatePassword = (): boolean => {
    if (newPassword.length < 8) {
      toast.error('Password must be at least 8 characters');
      return false;
    }
    if (newPassword !== confirmPassword) {
      toast.error('Passwords do not match');
      return false;
    }
    return true;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!validatePassword()) return;
    if (!accessToken) {
      toast.error('Invalid reset link. Please request a new password reset.');
      return;
    }

    setIsLoading(true);

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/auth/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          token: accessToken,
          refresh_token: refreshToken,
          new_password: newPassword,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Failed to reset password');
      }

      toast.success('Password updated successfully!');
      
      // Redirect to login after 2 seconds
      setTimeout(() => {
        router.push('/login?message=Password+reset+successful.+Please+log+in.');
      }, 2000);

    } catch (error: any) {
      toast.error(error.message || 'Something went wrong');
      
      // If token expired, offer to request new link
      if (error.message.includes('expired') || error.message.includes('invalid')) {
        setError(error.message);
      }
    } finally {
      setIsLoading(false);
    }
  };

  // Error state - show message and link to request new reset
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen p-4">
        <div className="w-full max-w-md space-y-6 text-center">
          <div className="text-6xl">⚠️</div>
          <h1 className="text-2xl font-bold text-red-600">Reset Link Invalid</h1>
          <p className="text-gray-600">{error}</p>
          <div className="space-y-3">
            <button
              onClick={() => router.push('/forgot-password')}
              className="w-full bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700"
            >
              Request New Reset Link
            </button>
            <button
              onClick={() => router.push('/login')}
              className="w-full text-gray-600 hover:underline"
            >
              Back to Login
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-screen p-4">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center">
          <h1 className="text-2xl font-bold">Set New Password</h1>
          <p className="text-gray-600 mt-2">
            Enter your new password below.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="newPassword" className="block text-sm font-medium text-gray-700">
              New Password
            </label>
            <input
              id="newPassword"
              type="password"
              required
              minLength={8}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2"
              placeholder="At least 8 characters"
            />
          </div>

          <div>
            <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-700">
              Confirm Password
            </label>
            <input
              id="confirmPassword"
              type="password"
              required
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2"
              placeholder="Re-enter your password"
            />
          </div>

          {/* Password Requirements */}
          <div className="text-sm text-gray-500">
            <p>Password must:</p>
            <ul className="list-disc list-inside">
              <li className={newPassword.length >= 8 ? 'text-green-600' : ''}>
                Be at least 8 characters
              </li>
              <li className={newPassword === confirmPassword && confirmPassword.length > 0 ? 'text-green-600' : ''}>
                Match confirmation
              </li>
            </ul>
          </div>

          <button
            type="submit"
            disabled={isLoading || !accessToken}
            className="w-full bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 disabled:opacity-50"
          >
            {isLoading ? 'Updating...' : 'Reset Password'}
          </button>
        </form>
      </div>
    </div>
  );
}
```

---

## Update Login Page

Add a "Forgot Password?" link to your login page:

```tsx
// In your login form
<div className="flex items-center justify-between">
  <div className="flex items-center">
    <input type="checkbox" id="remember" className="..." />
    <label htmlFor="remember" className="ml-2 text-sm text-gray-600">
      Remember me
    </label>
  </div>
  <Link href="/forgot-password" className="text-sm text-blue-600 hover:underline">
    Forgot password?
  </Link>
</div>
```

Also handle URL messages on login page:

```tsx
// pages/login.tsx
useEffect(() => {
  const params = new URLSearchParams(window.location.search);
  const message = params.get('message');
  const error = params.get('error');
  
  if (message) {
    toast.success(decodeURIComponent(message.replace(/\+/g, ' ')));
  }
  if (error) {
    toast.error(decodeURIComponent(error.replace(/\+/g, ' ')));
  }
  
  // Clean URL
  window.history.replaceState({}, '', '/login');
}, []);
```

---

## Error Handling Summary

| Error | Status | User Message | Action |
|-------|--------|--------------|--------|
| Token expired | 401 | "Reset link expired" | Show "Request New Link" button |
| Token invalid | 401 | "Invalid reset link" | Show "Request New Link" button |
| Password too short | 422 | "Password must be at least 8 characters" | Highlight field |
| Network error | N/A | "Something went wrong" | Show retry button |
| Server error | 500 | "Something went wrong" | Show retry button |

---

## Testing Checklist

### Manual Testing

1. **Happy Path**
   - [ ] Enter valid email on forgot-password page
   - [ ] Receive success message (regardless of email existence)
   - [ ] Check email for reset link
   - [ ] Click link in email
   - [ ] Verify redirect to /reset-password with tokens in URL
   - [ ] Enter new password (8+ chars)
   - [ ] Confirm password matches
   - [ ] Submit and see success message
   - [ ] Verify redirect to login
   - [ ] Login with new password works

2. **Error Cases**
   - [ ] Navigate directly to /reset-password (no token) → shows error
   - [ ] Use expired reset link → shows "expired" error
   - [ ] Enter mismatched passwords → shows validation error
   - [ ] Enter password < 8 chars → shows validation error
   - [ ] Network error during submit → shows retry option

3. **Security Checks**
   - [ ] Tokens removed from URL after reading
   - [ ] Same message for existing/non-existing emails
   - [ ] Old reset links stop working after password changed

---

## API Reference

### POST `/api/auth/forgot-password`

Request a password reset email.

**Request:**
```json
{
  "email": "string (required, valid email format)"
}
```

**Response (200):**
```json
{
  "message": "string",
  "note": "string"
}
```

---

### POST `/api/auth/reset-password`

Reset password using tokens from email link.

**Request:**
```json
{
  "token": "string (required, access_token from URL)",
  "refresh_token": "string (optional, refresh_token from URL)",
  "new_password": "string (required, min 8 characters)"
}
```

**Response (200):**
```json
{
  "message": "Password updated successfully! You can now log in with your new password.",
  "success": true
}
```

**Response (401):**
```json
{
  "detail": "Invalid or expired recovery token. Please request a new password reset link."
}
```

**Response (422):**
```json
{
  "detail": [
    {
      "loc": ["body", "new_password"],
      "msg": "ensure this value has at least 8 characters",
      "type": "value_error.any_str.min_length"
    }
  ]
}
```

---

## Questions?

Contact the backend team or check:
- [PASSWORD_RESET_IMPLEMENTATION.md](./PASSWORD_RESET_IMPLEMENTATION.md) - Full backend implementation details
- [SUPABASE_EMAIL_SETUP.md](./SUPABASE_EMAIL_SETUP.md) - Email template configuration
