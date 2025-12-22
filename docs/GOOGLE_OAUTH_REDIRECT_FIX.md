# Google OAuth Redirect Fix - Production Issue

## Problem Summary

**Date**: December 21, 2025  
**Environment**: Production (www.quizify.ca)  
**Symptom**: After Google Sign-In, user is redirected to `https://www.quizify.ca/?code=a8ee9b3a-...` but not logged in

## Root Cause

Supabase is redirecting the OAuth callback to the **frontend** (`https://www.quizify.ca`) instead of the **backend callback endpoint** (`https://api.quizify.ca/api/auth/google/signin/callback`).

### Why This Happens

1. When a user initiates Google Sign-In, the backend creates an OAuth URL:
   ```python
   oauth_params = {
       "provider": "google",
       "redirect_to": "https://api.quizify.ca/api/auth/google/signin/callback",
       # ...
   }
   ```

2. However, Supabase **ignores** the `redirect_to` parameter if the URL is **not in the allowed redirect URLs list** in your Supabase project settings.

3. Instead, Supabase falls back to the **default Site URL** configured in the project (which is `https://www.quizify.ca`).

4. The frontend receives the authorization code but has no handler for it, so the user is stuck on the homepage.

## Expected Flow

```
User clicks Google Sign-In
    ↓
Frontend → Backend: GET /api/auth/google/signin
    ↓
Backend → Frontend: { "auth_url": "https://supabase.com/auth/..." }
    ↓
Frontend redirects → Google OAuth
    ↓
User authenticates with Google
    ↓
Google → Supabase → Backend: GET /api/auth/google/signin/callback?code=xxx
    ↓
Backend exchanges code for session tokens
    ↓
Backend → Frontend: Redirect with cookies set (login=success&provider=google)
    ↓
Frontend displays success and navigates to dashboard
```

## Actual Flow (Broken)

```
User clicks Google Sign-In
    ↓
[... same until ...]
    ↓
Google → Supabase → Frontend: https://www.quizify.ca/?code=xxx  ❌
    ↓
Frontend has no handler for ?code= parameter
    ↓
User lands on homepage, not logged in
```

## Solution

### Step 1: Add Backend Callback URL to Supabase

1. Go to [Supabase Dashboard](https://supabase.com/dashboard)
2. Select your Quizify project
3. Navigate to **Authentication** → **URL Configuration**
4. Find the **Redirect URLs** section
5. Add the following URLs to the allowlist:

   **Production**:
   ```
   https://api.quizify.ca/api/auth/google/signin/callback
   ```

   **Staging** (if you have staging):
   ```
   https://api-staging.quizify.ca/api/auth/google/signin/callback
   ```

   **Local Development**:
   ```
   http://localhost:8000/api/auth/google/signin/callback
   ```

6. Click **Save**

### Step 2: Verify Site URL

Make sure the **Site URL** in Supabase is set to your frontend:
- Production: `https://www.quizify.ca`
- Staging: `https://staging.quizify.ca` (if applicable)

### Step 3: Test the Fix

1. Clear browser cookies and cache
2. Go to `https://www.quizify.ca/login`
3. Click "Sign in with Google"
4. Complete Google authentication
5. Verify you're redirected to: `https://www.quizify.ca/?login=success&provider=google`
6. Verify you're logged in and can access protected routes

## Verification Checklist

- [ ] Backend callback URL added to Supabase redirect URLs allowlist
- [ ] Site URL correctly set to frontend URL
- [ ] Google OAuth flow completes successfully
- [ ] User is redirected to frontend with `login=success&provider=google` params
- [ ] User is logged in (cookies set, can access dashboard)
- [ ] Works in production environment
- [ ] Works in staging environment (if applicable)

## Technical Details

### Supabase OAuth Flow

Supabase uses the standard OAuth 2.0 authorization code flow with PKCE:

1. **Initiate**: Backend generates PKCE challenge and redirects user to Supabase OAuth endpoint
2. **Authorize**: Supabase redirects to Google for authentication
3. **Callback**: Google sends authorization code to Supabase, which then redirects to `redirect_to` URL
4. **Exchange**: Backend exchanges code + PKCE verifier for session tokens
5. **Session**: Backend sets HttpOnly cookies and redirects to frontend with status

### Security Considerations

- **CSRF Protection**: State parameter stored in signed HttpOnly cookie
- **PKCE**: Code challenge/verifier prevents authorization code interception
- **Allowed URLs**: Supabase only redirects to pre-configured URLs (prevents open redirect)
- **HttpOnly Cookies**: Tokens are never exposed to JavaScript
- **SameSite=None**: Required for cross-origin cookie setting during OAuth flow

### Why `redirect_to` is Ignored

From [Supabase documentation](https://supabase.com/docs/guides/auth/redirect-urls):

> The `redirect_to` parameter is only respected if it's in the **Redirect URLs allowlist**.
> If the URL is not in the allowlist, Supabase will use the **Site URL** instead.

This is a **security feature** to prevent open redirect attacks.

## Related Files

- [../handlers/auth_handlers.py](../handlers/auth_handlers.py) - OAuth handlers
- [../api/auth_routes.py](../api/auth_routes.py) - OAuth routes
- [FRONTEND_GOOGLE_SIGNIN_INTEGRATION.md](FRONTEND_GOOGLE_SIGNIN_INTEGRATION.md) - Frontend integration guide
- [BACKEND_OAUTH_REDIRECT_REQUIREMENTS.md](BACKEND_OAUTH_REDIRECT_REQUIREMENTS.md) - Redirect URL security requirements

## Environment Variables to Check

```bash
# Backend (.env)
BACKEND_URL=https://api.quizify.ca  # Must match Supabase redirect URL domain
FRONTEND_URL=https://www.quizify.ca  # Where users are redirected after OAuth
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
COOKIE_DOMAIN=.quizify.ca  # For cross-subdomain cookie sharing
```

## Troubleshooting

### Still seeing `?code=` instead of `?login=success`?

1. **Check Supabase logs**: Go to Supabase Dashboard → Logs → Auth Logs
2. **Verify redirect URL**: Make sure the exact URL is in the allowlist (case-sensitive, no trailing slash)
3. **Clear browser state**: Cookies, cache, and localStorage
4. **Check backend logs**: Look for "Processing Google Sign-In callback" message
5. **Verify BACKEND_URL**: Must match the domain in Supabase redirect URLs

### Getting CORS errors?

1. **Check COOKIE_DOMAIN**: Should be `.quizify.ca` (with leading dot) for cross-subdomain cookies
2. **Check SameSite settings**: OAuth state cookie uses `SameSite=None; Secure` for cross-origin
3. **Verify credentials**: Frontend must use `credentials: 'include'` in fetch requests

### OAuth state validation failed?

1. **Check cookie settings**: OAuth state cookie must be set with `SameSite=None; Secure`
2. **Verify CSRF token**: Check browser DevTools → Application → Cookies for `oauth_state` cookie
3. **Check expiry**: OAuth state expires after 10 minutes (OAUTH_STATE_MAX_AGE)

## Next Steps

1. ✅ Create this documentation
2. ⏳ Update Supabase redirect URLs in dashboard
3. ⏳ Test OAuth flow in production
4. ⏳ Test OAuth flow in staging (if applicable)
5. ⏳ Update environment variable documentation
6. ⏳ Add monitoring/alerts for OAuth failures

## References

- [Supabase Auth Redirect URLs](https://supabase.com/docs/guides/auth/redirect-urls)
- [OAuth 2.0 Authorization Code Flow with PKCE](https://oauth.net/2/pkce/)
- [OWASP Open Redirect Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html)
