# Backend OAuth Redirect URL Requirements

## Issue Encountered

When initiating Google OAuth from a Vercel preview deployment (e.g., `https://quizify-front-theta.vercel.app`), the OAuth callback was redirecting users to production (`https://www.quizify.ca`) instead of back to the preview environment where they started.

## ❌ REJECTED: Absolute URL Approach (Security Risk)

The initial proposal was to have the frontend send full absolute URLs:
```
GET /api/auth/google/signin?redirect_url=https://quizify-front-theta.vercel.app/dashboard
```

**This approach was REJECTED due to security concerns:**

1. **Open Redirect Attack Vector**: Even with allowlist validation, patterns like `https://[\w-]+\.vercel.app` allow ANY Vercel app, including attacker-controlled ones.
2. **OAuth Best Practice**: The OAuth 2.0 spec recommends exact match for redirect URIs, not pattern matching.
3. **Subdomain Takeover Risk**: Attackers could register similar-looking domains that match patterns.

## ✅ CORRECT: Relative Path Approach (Current Implementation)

The backend ONLY accepts **relative paths** and always uses `FRONTEND_URL` as the base:

```
GET /api/auth/google/signin?redirect_url=/dashboard
```

### How It Works

1. Frontend sends relative path: `/dashboard`
2. Backend validates it's a safe relative path (no `://`, no `//`, no control chars)
3. Backend prepends `FRONTEND_URL` environment variable: `https://www.quizify.ca/dashboard`
4. User is redirected to the full URL

### Handling Vercel Preview Deployments

For preview deployments, you have two options:

#### Option A: Per-Environment Backend (Recommended)
Each Vercel preview deployment uses its own backend instance with matching `FRONTEND_URL`:
- Preview frontend: `https://quizify-xyz.vercel.app`
- Preview backend `FRONTEND_URL`: `https://quizify-xyz.vercel.app`

#### Option B: Shared Backend with Origin Header
The backend could optionally read the `Origin` header from the OAuth initiation request and use that as the redirect base (validated against an allowlist). This requires backend changes.

## Frontend Requirements

1. **Only send relative paths**: `/dashboard`, `/quiz/123`, etc.
2. **Never send absolute URLs**: The backend will reject them
3. **Configure environment correctly**: Each deployment's `FRONTEND_URL` should match

## Backend Implementation (Current)

```python
def validate_redirect_url(redirect_url: Optional[str]) -> Optional[str]:
    """Only accepts relative paths starting with /"""
    if not redirect_url:
        return None
    
    # Reject control characters (CRLF injection)
    if any(c in redirect_url for c in "\r\n\x00"):
        return None
    
    # Only allow relative paths starting with /
    if redirect_url.startswith("/") and not redirect_url.startswith("//"):
        if "://" in redirect_url:  # Reject embedded protocols
            return None
        return redirect_url
    
    return None  # Reject absolute URLs
```

## Security Benefits

1. **No open redirect**: Backend always controls the domain via `FRONTEND_URL`
2. **Simple validation**: Just check for `/` prefix and reject dangerous patterns
3. **Defense in depth**: Even if validation has bugs, attacker can only control path, not domain

## Testing Checklist

- [x] Relative path `/dashboard` works correctly
- [x] Absolute URL `https://evil.com` is rejected
- [x] Protocol-relative URL `//evil.com` is rejected  
- [x] Embedded protocol `/foo://bar` is rejected
- [x] CRLF injection `/%0d%0a` is rejected
- [ ] Preview deployment uses correct `FRONTEND_URL` (frontend team)
