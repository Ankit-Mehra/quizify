# Frontend Session Management Implementation Guide

**Date**: November 14, 2025  
**Version**: 1.0  
**Status**: Production Ready

## Overview

This guide provides complete implementation details for integrating multi-device session management in the Quizify frontend. The backend supports Redis-based session tracking with device identification, allowing users to view and manage active sessions across all devices.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [API Endpoints](#api-endpoints)
3. [Session ID Handling](#session-id-handling)
4. [Implementation Guide](#implementation-guide)
5. [Common Pitfalls](#common-pitfalls)
6. [Testing Checklist](#testing-checklist)

---

## Architecture Overview

### How Sessions Work

1. **Login Flow**:
   - User logs in via `POST /api/auth/login`
   - Backend creates Redis session with unique `session_id`
   - Backend returns `session_id` in response body
   - Backend sets `access_token` and `refresh_token` in HTTP-only cookies
   - Frontend stores `session_id` in localStorage/sessionStorage

2. **Authenticated Requests**:
   - Frontend sends `session_id` via `X-Session-ID` header
   - Backend validates session exists in Redis and belongs to user
   - Backend refreshes session TTL (24 hours) on each request

3. **Multi-Device Support**:
   - Each device has its own `session_id`
   - Backend tracks device type, IP (hashed), user-agent, timestamps
   - Users can view all active sessions and revoke specific devices

### Security Model

- **JWT in HTTP-only cookies**: Protects against XSS attacks
- **Session ID in header**: Allows device-specific tracking
- **IP address hashing**: Privacy-preserving location tracking
- **User-agent truncation**: Prevents fingerprinting attacks
- **RLS policies**: Users can only see/revoke their own sessions

---

## API Endpoints

### 1. Login
**Endpoint**: `POST /api/auth/login`

**Request**:
```json
{
  "email": "user@example.com",
  "password": "SecurePass123!"
}
```

**Response** (200 OK):
```json
{
  "message": "Successfully logged in",
  "user": {
    "id": "760602fe-...",
    "email": "user@example.com"
  },
  "session_id": "sess_abc123def456..."  // ← STORE THIS
}
```

**Note**: To get full user details including `account_tier` and `role`, call `GET /api/auth/me` after login.

**Cookies Set** (HTTP-only):
- `access_token`: JWT for authentication (1 hour TTL)
- `refresh_token`: JWT for token refresh (30 days TTL)

**Frontend Action**:
```javascript
// After successful login
const response = await fetch('/api/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  credentials: 'include',  // ← REQUIRED for cookies
  body: JSON.stringify({ email, password })
});

const data = await response.json();

// Store session_id for this device
localStorage.setItem('session_id', data.session_id);
```

---

### 2. Get Active Sessions
**Endpoint**: `GET /api/auth/sessions`

**Request Headers**:
```
X-Session-ID: sess_abc123...  // ← Current device session ID
```

**Note**: JWT authentication happens automatically via HTTP-only cookies. No need to manually set Authorization header.

**Response** (200 OK):
```json
[
  {
    "session_id": "sess_desktop_xyz",
    "device_type": "browser",
    "created_at": "2025-11-14T10:00:00Z",
    "last_active": "2025-11-14T15:30:00Z",
    "ip_address": "7868a1769fe3d0c5",  // SHA-256 hash (first 16 chars)
    "user_agent": "Chrome/120.0.0.0 (Mac OS X 10.15.7)",
    "is_expired": false,
    "is_current": true  // ← THIS DEVICE (matches X-Session-ID)
  },
  {
    "session_id": "sess_mobile_abc",
    "device_type": "mobile",
    "created_at": "2025-11-14T09:00:00Z",
    "last_active": "2025-11-14T14:00:00Z",
    "ip_address": "b726760f4a2e8d1c",  // SHA-256 hash (first 16 chars)
    "user_agent": "Chrome/120.0.0.0 (Android 14)",
    "is_expired": false,
    "is_current": false  // ← OTHER DEVICE
  }
]
```

**Frontend Action**:
```javascript
const sessionId = localStorage.getItem('session_id');

const response = await fetch('/api/auth/sessions', {
  method: 'GET',
  headers: {
    'X-Session-ID': sessionId  // ← Include current session
  },
  credentials: 'include'
});

const sessions = await response.json();

// Display sessions in UI
sessions.forEach(session => {
  const badge = session.is_current ? '(This Device)' : '';
  console.log(`${session.device_type} - ${badge}`);
});
```

---

### 3. Revoke Specific Session (Logout Other Device)
**Endpoint**: `DELETE /api/auth/sessions/{session_id}`

**⚠️ CRITICAL**: Use this endpoint to logout **OTHER** devices. Do NOT use `POST /api/auth/logout`.

**⚠️ IMPORTANT**: Session revocation takes effect on the target device's next authenticated request. The device will receive a 401 error and must re-login.

**Request**:
```
DELETE /api/auth/sessions/sess_mobile_abc
X-Session-ID: sess_desktop_xyz  // ← Current device session
```

**Response** (200 OK):
```json
{
  "message": "Session revoked successfully",
  "session_id": "sess_mobile_abc"
}
```

**What Happens Next**:
1. Session deleted from Redis ✅
2. Target device JWT cookie still valid (up to 1 hour) ✅
3. Target device makes next request:
   - **WITH** `X-Session-ID` → Backend validates → 401 Unauthorized → Device logged out ✅
   - **WITHOUT** `X-Session-ID` → Backend returns 401 Unauthorized → User must login ✅

**Frontend Action**:
```javascript
async function logoutDevice(sessionIdToRevoke) {
  const currentSessionId = localStorage.getItem('session_id');
  
  // ⚠️ IMPORTANT: Use DELETE to /sessions/{id}, NOT POST to /logout
  const response = await fetch(`/api/auth/sessions/${sessionIdToRevoke}`, {
    method: 'DELETE',
    headers: {
      'X-Session-ID': currentSessionId  // ← YOUR device
    },
    credentials: 'include'
  });
  
  if (response.ok) {
    // Remove from UI
    console.log('Device logged out successfully');
  }
}

// In your UI click handler
<button onClick={() => logoutDevice(session.session_id)}>
  Logout Device
</button>
```

---

### 4. Logout Current Device
**Endpoint**: `POST /api/auth/logout`

**⚠️ USE CASE**: Only for logging out the **CURRENT** device (the one making the request).

**Request**:
```
POST /api/auth/logout?session_id=sess_desktop_xyz
```

**Response** (200 OK):
```json
{
  "message": "Successfully logged out"
}
```

**Side Effects**:
- Deletes session from Redis
- Clears `access_token` and `refresh_token` cookies
- User must login again on this device

**Frontend Action**:
```javascript
async function logoutCurrentDevice() {
  const sessionId = localStorage.getItem('session_id');
  
  const response = await fetch(`/api/auth/logout?session_id=${sessionId}`, {
    method: 'POST',
    credentials: 'include'
  });
  
  if (response.ok) {
    // Clear local storage
    localStorage.removeItem('session_id');
    
    // Redirect to login
    window.location.href = '/login';
  }
}
```

---

### 5. Logout All Devices
**Endpoint**: `POST /api/auth/logout-all-devices`

**USE CASE**: Security action (password change, suspicious activity) to force re-login on all devices.

**Request**:
```
POST /api/auth/logout-all-devices
X-Session-ID: sess_desktop_xyz
```

**Response** (200 OK):
```json
{
  "message": "Successfully logged out from 3 device(s)",
  "devices_logged_out": 3
}
```

**Side Effects**:
- Deletes ALL sessions from Redis
- Clears cookies on current device
- All other devices will get 401 Unauthorized on next request

**Frontend Action**:
```javascript
async function logoutAllDevices() {
  const sessionId = localStorage.getItem('session_id');
  
  const response = await fetch('/api/auth/logout-all-devices', {
    method: 'POST',
    headers: {
      'X-Session-ID': sessionId
    },
    credentials: 'include'
  });
  
  if (response.ok) {
    localStorage.removeItem('session_id');
    window.location.href = '/login';
  }
}
```

---

## Session ID Handling

### Where to Store Session ID

**Recommended**: `localStorage` (persists across browser restarts)

```javascript
// After login
localStorage.setItem('session_id', sessionId);

// On every authenticated request
const sessionId = localStorage.getItem('session_id');
```

**Alternative**: `sessionStorage` (clears when browser closes)
- Use if you want session to expire when browser closes
- Each tab will have its own session

**❌ DON'T**: Store in cookies
- Backend already uses cookies for JWT tokens
- Session ID should be in header for flexibility

---

### How to Send Session ID

**ALWAYS** include `X-Session-ID` header in authenticated requests:

```javascript
// Fetch API
fetch('/api/quiz/generate', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-Session-ID': localStorage.getItem('session_id')
  },
  credentials: 'include',  // ← For JWT cookies
  body: JSON.stringify(quizData)
});

// Axios
axios.post('/api/quiz/generate', quizData, {
  headers: {
    'X-Session-ID': localStorage.getItem('session_id')
  },
  withCredentials: true  // ← For JWT cookies
});
```

---

### CORS Configuration

**Required CORS Headers** (already configured in backend):
```
Access-Control-Allow-Origin: <your-frontend-domain>
Access-Control-Allow-Credentials: true
Access-Control-Allow-Headers: Content-Type, Authorization, Accept, X-Session-ID
```

**Frontend Must**:
- Set `credentials: 'include'` (fetch) or `withCredentials: true` (axios)
- Match exact origin (no wildcards with credentials)

---

## Implementation Guide

### Step 1: Setup Session Storage

```javascript
// utils/session.js

export const SessionManager = {
  // Store session ID after login
  setSession(sessionId) {
    localStorage.setItem('session_id', sessionId);
  },
  
  // Get current session ID
  getSession() {
    return localStorage.getItem('session_id');
  },
  
  // Clear session on logout
  clearSession() {
    localStorage.removeItem('session_id');
  },
  
  // Check if session exists
  hasSession() {
    return !!localStorage.getItem('session_id');
  }
};
```

---

### Step 2: Create API Client

```javascript
// api/client.js

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

export async function apiRequest(endpoint, options = {}) {
  const sessionId = localStorage.getItem('session_id');
  
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers
  };
  
  // Add session ID if available
  if (sessionId) {
    headers['X-Session-ID'] = sessionId;
  }
  
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers,
    credentials: 'include'  // ← CRITICAL for cookies
  });
  
  // Handle 401 Unauthorized (session expired)
  if (response.status === 401) {
    localStorage.removeItem('session_id');
    window.location.href = '/login';
    throw new Error('Session expired');
  }
  
  return response;
}
```

---

### Step 3: Login Component

```javascript
// components/Login.jsx

import { SessionManager } from '../utils/session';
import { apiRequest } from '../api/client';

export function Login() {
  async function handleLogin(email, password) {
    try {
      const response = await apiRequest('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password })
      });
      
      const data = await response.json();
      
      // ⚠️ CRITICAL: Store session ID
      SessionManager.setSession(data.session_id);
      
      // Redirect to dashboard
      window.location.href = '/dashboard';
    } catch (error) {
      console.error('Login failed:', error);
    }
  }
  
  return (
    <form onSubmit={(e) => {
      e.preventDefault();
      handleLogin(e.target.email.value, e.target.password.value);
    }}>
      {/* Form fields */}
    </form>
  );
}
```

---

### Step 4: Session Management Component

```javascript
// components/SessionManager.jsx

import { useState, useEffect } from 'react';
import { apiRequest } from '../api/client';
import { SessionManager } from '../utils/session';

export function ActiveSessions() {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  
  useEffect(() => {
    loadSessions();
  }, []);
  
  async function loadSessions() {
    try {
      const response = await apiRequest('/api/auth/sessions');
      const data = await response.json();
      setSessions(data);
    } catch (error) {
      console.error('Failed to load sessions:', error);
    } finally {
      setLoading(false);
    }
  }
  
  async function revokeSession(sessionId) {
    try {
      // ⚠️ CRITICAL: Use DELETE /sessions/{id}, NOT /logout
      const response = await apiRequest(`/api/auth/sessions/${sessionId}`, {
        method: 'DELETE'
      });
      
      if (response.ok) {
        // Remove from UI
        setSessions(prev => prev.filter(s => s.session_id !== sessionId));
        alert('Device logged out successfully');
      }
    } catch (error) {
      console.error('Failed to revoke session:', error);
    }
  }
  
  async function logoutAllDevices() {
    if (!confirm('Logout from all devices?')) return;
    
    try {
      const response = await apiRequest('/api/auth/logout-all-devices', {
        method: 'POST'
      });
      
      if (response.ok) {
        SessionManager.clearSession();
        window.location.href = '/login';
      }
    } catch (error) {
      console.error('Failed to logout all devices:', error);
    }
  }
  
  if (loading) return <div>Loading sessions...</div>;
  
  return (
    <div>
      <h2>Active Sessions</h2>
      <button onClick={logoutAllDevices}>Logout All Devices</button>
      
      <div>
        {sessions.map(session => (
          <div key={session.session_id} className="session-card">
            <div>
              <strong>{session.device_type}</strong>
              {session.is_current && <span> (This Device)</span>}
            </div>
            <div>Last active: {new Date(session.last_active).toLocaleString()}</div>
            <div>Location: {session.ip_address.substring(0, 8)}...</div>
            <div>{session.user_agent}</div>
            
            {!session.is_current && (
              <button onClick={() => revokeSession(session.session_id)}>
                Logout Device
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
```

---

### Step 5: Logout Component

```javascript
// components/Logout.jsx

import { apiRequest } from '../api/client';
import { SessionManager } from '../utils/session';

export function LogoutButton() {
  async function handleLogout() {
    try {
      const sessionId = SessionManager.getSession();
      
      // Logout current device only
      const response = await apiRequest(`/api/auth/logout?session_id=${sessionId}`, {
        method: 'POST'
      });
      
      if (response.ok) {
        SessionManager.clearSession();
        window.location.href = '/login';
      }
    } catch (error) {
      console.error('Logout failed:', error);
    }
  }
  
  return (
    <button onClick={handleLogout}>
      Logout
    </button>
  );
}
```

---

## Common Pitfalls

### ❌ WRONG: Using `/logout` to Remove Other Devices

```javascript
// ❌ DON'T DO THIS - This logs out YOUR device, not the target device!
async function logoutDevice(sessionId) {
  await fetch(`/api/auth/logout?session_id=${sessionId}`, {
    method: 'POST',
    credentials: 'include'
  });
  // Result: YOUR cookies cleared, target device still logged in
}
```

### ✅ CORRECT: Using `/sessions/{id}` to Remove Other Devices

```javascript
// ✅ DO THIS - Revokes target device without affecting yours
async function logoutDevice(sessionId) {
  await fetch(`/api/auth/sessions/${sessionId}`, {
    method: 'DELETE',
    headers: {
      'X-Session-ID': localStorage.getItem('session_id')  // YOUR session
    },
    credentials: 'include'
  });
  // Result: Target device revoked, YOUR session unaffected
}
```

---

### ❌ WRONG: Not Sending `X-Session-ID` Header

```javascript
// ❌ Session not tracked
fetch('/api/quiz/generate', {
  method: 'POST',
  credentials: 'include',
  body: JSON.stringify(data)
});
// Backend returns: 401 Unauthorized - "Session ID required"
```

### ✅ CORRECT: Always Include Session Header

```javascript
// ✅ Session properly tracked
fetch('/api/quiz/generate', {
  method: 'POST',
  headers: {
    'X-Session-ID': localStorage.getItem('session_id')
  },
  credentials: 'include',
  body: JSON.stringify(data)
});
```

---

### ❌ WRONG: Not Setting `credentials: 'include'`

```javascript
// ❌ JWT cookies not sent, authentication fails
fetch('/api/auth/sessions', {
  headers: {
    'X-Session-ID': sessionId
  }
  // Missing: credentials: 'include'
});
// Result: 401 Unauthorized
```

### ✅ CORRECT: Always Include Credentials

```javascript
// ✅ JWT cookies sent automatically
fetch('/api/auth/sessions', {
  headers: {
    'X-Session-ID': sessionId
  },
  credentials: 'include'  // ← REQUIRED
});
```

---

### ❌ WRONG: Storing Session ID in State Only

```javascript
// ❌ Lost on page refresh
const [sessionId, setSessionId] = useState(null);

// After login
setSessionId(data.session_id);  // Lost when user refreshes page!
```

### ✅ CORRECT: Persist in localStorage

```javascript
// ✅ Survives page refresh
localStorage.setItem('session_id', data.session_id);

// Later
const sessionId = localStorage.getItem('session_id');
```

---

## Testing Checklist

### Functional Testing

- [ ] **Login Flow**
  - [ ] Session ID returned in login response
  - [ ] Session ID stored in localStorage
  - [ ] Cookies set properly (check DevTools Application tab)

- [ ] **Session List**
  - [ ] GET `/api/auth/sessions` returns sessions
  - [ ] Current device has `is_current: true`
  - [ ] Other devices have `is_current: false`
  - [ ] Device types detected correctly (browser vs mobile)

- [ ] **Revoke Other Device**
  - [ ] Clicking "Logout Device" on non-current session
  - [ ] Target device session deleted from backend
  - [ ] Current device still logged in
  - [ ] Session list updates correctly

- [ ] **Logout Current Device**
  - [ ] Clicking main "Logout" button
  - [ ] Current session deleted from backend
  - [ ] Cookies cleared
  - [ ] Redirected to login page
  - [ ] localStorage cleared

- [ ] **Logout All Devices**
  - [ ] All sessions deleted from backend
  - [ ] All devices return 401 on next request
  - [ ] Current device logged out

### Multi-Device Testing

- [ ] Login on Desktop Chrome
- [ ] Login on Mobile Safari (same account)
- [ ] Verify 2 sessions visible in session list
- [ ] From Desktop: Revoke mobile session
- [ ] Verify mobile gets 401 on next request
- [ ] Verify desktop still works

### Error Handling

- [ ] **Session Expired**
  - [ ] Backend returns 401 when session not in Redis
  - [ ] Frontend redirects to login
  - [ ] localStorage cleared

- [ ] **Redis Unavailable**
  - [ ] Backend gracefully falls back (logs warning)
  - [ ] Login still works (session not created)
  - [ ] GET /sessions returns empty array `[]`
  - [ ] DELETE /sessions/{id} returns 503 error

- [ ] **Network Errors**
  - [ ] Retry logic for transient failures
  - [ ] User-friendly error messages

### Security Testing

- [ ] **Session Isolation**
  - [ ] User A cannot revoke User B's sessions
  - [ ] Backend returns 403 Forbidden

- [ ] **Session Validation**
  - [ ] Invalid session_id returns 401
  - [ ] Expired sessions cleaned up automatically

- [ ] **CORS**
  - [ ] OPTIONS preflight succeeds (200 OK)
  - [ ] `X-Session-ID` header allowed
  - [ ] Credentials allowed for same origin

### Browser Compatibility

- [ ] Chrome/Edge (Chromium)
- [ ] Firefox
- [ ] Safari
- [ ] Mobile browsers (iOS Safari, Chrome Android)

---

## Best Practices

1. **⚠️ CRITICAL: Always send X-Session-ID header** on ALL authenticated requests
   - Without this header, requests will receive a 401 Unauthorized error
   - Session management features (revocation, limits) require this header
   - Device will be immediately logged out if header is missing
2. **Always set credentials: 'include'** for cookie support
3. **Store session_id in localStorage** for persistence across page refreshes
4. **Use DELETE /sessions/{id}** for revoking other devices
5. **Use POST /logout** only for current device logout
6. **Handle 401 errors** by clearing localStorage and redirecting to login
7. **Show "This Device" badge** for is_current sessions
8. **Disable "Logout Device" button** for current session (prevent self-revoke)
9. **Confirm before logout all devices** (destructive action)
10. **Clear localStorage** on logout
11. **Test session revocation** by verifying 401 error on target device after revoke
12. **Monitor Network tab** to ensure X-Session-ID header is sent on every request

---

## Troubleshooting

### Sessions Not Being Created

**Symptom**: Session list always empty after login

**Check**:
1. Backend logs: Look for "Redis session created"
2. Redis: Check for keys `session:*` and `user_sessions:*`
3. Response: Verify `session_id` in login response

**Solutions**:
- Ensure Redis is running and connected
- Check backend logs for Redis errors
- Verify `REDIS_ENABLED=true` in backend env

---

### Wrong Device Getting Logged Out

**Symptom**: Clicking "Logout Device" on mobile logs out desktop

**Check**:
1. Network tab: Verify correct endpoint called
2. Request: Check if `DELETE /sessions/{id}` or `POST /logout`

**Solution**:
- Use `DELETE /api/auth/sessions/{sessionId}` for other devices
- Use `POST /api/auth/logout` ONLY for current device

---

### Device Not Getting Logged Out After Session Revoked

**Symptom**: Revoked Android session, but Android device still works

**Root Cause**: Session revocation takes effect when the target device makes its next authenticated request. The device's JWT cookie remains valid (up to 1 hour) until the next API call.

**How It Works**:
1. Desktop calls `DELETE /api/auth/sessions/{android_session_id}` → Session deleted from Redis ✅
2. Android still has valid JWT cookie (valid for 1 hour) ✅
3. Android makes next request:
   - **WITH** `X-Session-ID` header → Backend validates session → 401 Unauthorized → Device logged out ✅
   - **WITHOUT** `X-Session-ID` header → Backend returns 401 Unauthorized → Device logged out ✅

**Check**:
1. Android device Network tab: Verify `X-Session-ID` header is being sent
2. Backend logs: Look for "Session ID missing for user ... - returning 401 (session required)"
3. Backend logs: Look for "Session ... not found for user ..." (session validation working)

**Solution**:
```javascript
// CRITICAL: Ensure X-Session-ID is sent on EVERY authenticated request

// ❌ WRONG - No session header
fetch('/api/quiz/generate', {
  method: 'POST',
  credentials: 'include',
  body: JSON.stringify(data)
});
// Backend returns: 401 Unauthorized - "Session ID required"

// ✅ CORRECT - Always include session header
fetch('/api/quiz/generate', {
  method: 'POST',
  headers: {
    'X-Session-ID': localStorage.getItem('session_id')  // ← REQUIRED
  },
  credentials: 'include',
  body: JSON.stringify(data)
});
// Result: Backend validates session, returns 401 if revoked
```

**Testing**:
1. Revoke Android session from Desktop
2. On Android, refresh page or trigger any API call
3. Should receive 401 Unauthorized immediately
4. Verify frontend redirects to login page
5. Verify localStorage cleared

---

### CORS Errors

**Symptom**: "Response to preflight request doesn't pass access control check"

**Check**:
1. Network tab: Look for OPTIONS request with 400 status
2. Console: CORS error mentioning `X-Session-ID`

**Solution**:
- Backend must include `X-Session-ID` in `allow_headers`
- Frontend must set `credentials: 'include'`
- Clear browser cache (CORS headers cached aggressively)

---

### Session Not Validated

**Symptom**: Backend logs "Session ID missing for user ... - returning 401 (session required)"

**Check**:
1. Network tab: Verify `X-Session-ID` header present in request
2. localStorage: Check if `session_id` stored
3. Frontend receives 401 Unauthorized response

**Solution**:
- Add `X-Session-ID` header to all authenticated requests
- Verify session_id not null/undefined before sending
- Ensure session_id stored in localStorage after login

---

## Additional Resources

- **Backend Source**: `handlers/auth_handlers.py`
- **API Routes**: `api/auth_routes.py`
- **Session Service**: `services/redis/sessions.py`
- **Postman Collection**: `postman/Quizify_Auth_API.postman_collection.json`
- **Architecture Doc**: `docs/redis/REDIS_COMPLETE_ARCHITECTURE.md`

---

## Support

For questions or issues:
1. Check backend logs in Railway dashboard
2. Review this guide's troubleshooting section
3. Test with Postman collection to isolate frontend vs backend issues
4. Check Redis keys directly in Railway Redis dashboard

---

**Last Updated**: November 14, 2025  
**Backend Version**: Compatible with PR #79 (CORS fix + is_current field)
