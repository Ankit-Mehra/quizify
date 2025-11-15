# Frontend Session Management Implementation Guide

**Date**: November 15, 2025  
**Version**: 3.0 - Cookie-Based Authentication  
**Status**: Production Ready  
**🔒 SECURITY**: XSS-safe cookie-based authentication only

## 🔒 Security: XSS-Safe Session Management

**As of November 15, 2025**, this backend implements **cookie-based authentication only** to eliminate XSS session replay vulnerabilities.

### Authentication Architecture

**Current Implementation (XSS-Safe)**:
- ✅ Server derives session from httpOnly `refresh_token` cookie
- ✅ `client_session_token` returned for UI display only (HMAC-signed, non-authoritative)
- ✅ No sensitive identifiers in localStorage or headers
- ✅ No X-Session-ID header required or supported

**What This Means**:
- All authentication happens via secure httpOnly cookies
- Frontend stores `client_session_token` for UI purposes only (not for authentication)
- No session identifiers sent in request headers
- XSS attacks cannot steal or replay sessions

---

## Overview

This guide provides complete implementation details for integrating multi-device session management in the Quizify frontend. The backend supports Redis-based session tracking with device identification, allowing users to view and manage active sessions across all devices.

**Cookie-based authentication** eliminates XSS vulnerabilities while maintaining all session management features.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [API Endpoints](#api-endpoints)
3. [Client Session Token Handling](#client-session-token-handling)
4. [Implementation Guide](#implementation-guide)
5. [Common Pitfalls](#common-pitfalls)
6. [Testing Checklist](#testing-checklist)

---

## Architecture Overview

### How Sessions Work

1. **Login Flow (Cookie-Based Authentication)**:
   - User logs in via `POST /api/auth/login`
   - Backend checks session limit (max 5 active sessions per user)
   - If under limit: Creates Redis session with unique `session_id`
   - If limit exceeded: Returns 429 error (user must revoke old sessions)
   - Backend creates `refresh_token` → `session_id` mapping in Redis
   - Backend generates HMAC-signed `client_session_token` for UI
   - Backend returns `client_session_token` in response body
   - Backend sets `access_token` (1 hour TTL) and `refresh_token` (30 days TTL) in HTTP-only cookies
   - Frontend stores `client_session_token` in localStorage (XSS-safe, non-authoritative)

2. **Authenticated Requests (Cookie-Based)**:
   - Frontend includes `credentials: 'include'` → Cookies sent automatically
   - Backend derives session from `refresh_token` cookie (no headers needed)
   - Backend validates session exists in Redis and belongs to user
   - Backend refreshes session TTL (resets to 30 days) on each request
   - Backend returns 401 if session missing, expired, or not found

3. **Multi-Device Support**:
   - Each device has its own `session_id` (internal, server-managed)
   - Backend tracks device type, IP (hashed), user-agent, created_at, last_active timestamps
   - Users can view all active sessions and revoke specific devices
   - Maximum 5 concurrent sessions per user (security limit)

4. **Session Expiration**:
   - Sessions expire after 30 days of inactivity
   - Each authenticated request refreshes the TTL (resets to 30 days)
   - Expired sessions automatically deleted by Redis TTL
   - Backend validates expiration via `is_expired` property before use

### Security Model

- **JWT in HTTP-only cookies**: Protects against XSS attacks (access_token: 1hr, refresh_token: 30 days)
- **Cookie-based session derivation**: Server uses refresh_token to find session (XSS-safe, no localStorage)
- **Client session token (HMAC-signed)**: Non-authoritative UI identifier, safe to expose to JavaScript
- **No session headers required**: All authentication via secure cookies
- **IP address hashing**: Privacy-preserving location tracking (HMAC-SHA256, first 16 chars)
- **User-agent truncation**: Prevents fingerprinting attacks (max 100 chars)
- **RLS policies**: Users can only see/revoke their own sessions
- **Session limits**: Maximum 5 concurrent sessions per user (prevents session flooding attacks)
- **Automatic cleanup**: Expired sessions removed by Redis TTL (30 days of inactivity)
- **XSS Protection**: No sensitive identifiers stored in localStorage
- **Refresh token mapping**: HMAC-SHA256 hash stored in Redis (32-char truncated)
- **Fallback mode**: Service remains available even when Redis is down (sessions not tracked)

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
  "client_session_token": "cst_abc123_a1b2c3d4"   // Store for UI only (XSS-safe)
}
```

**Response** (429 Too Many Requests) - Session Limit Exceeded:
```json
{
  "detail": "Too many active sessions. Please logout from other devices or revoke old sessions."
}
```

**What This Means**: User has 5 or more active sessions. They must either:
1. Use `GET /api/auth/sessions` to view active sessions
2. Use `DELETE /api/auth/sessions/{session_id}` to revoke old/unused devices
3. Use `POST /api/auth/logout-all-devices` to logout all devices and start fresh

**Note**: To get full user details including `account_tier` and `role`, call `GET /api/auth/me` after login.

**Cookies Set** (HTTP-only, secure, SameSite=Lax):
- `access_token`: JWT for authentication (1 hour TTL, refreshed automatically)
- `refresh_token`: JWT for token refresh (30 days TTL, used by `/api/auth/refresh` endpoint)

**Frontend Action**:
```javascript
// After successful login
try {
  const response = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',  // ← REQUIRED for cookies
    body: JSON.stringify({ email, password })
  });

  if (response.status === 429) {
    // Session limit exceeded - user has 10+ active sessions
    const error = await response.json();
    alert(error.detail);
    
    // Redirect to session management page
    window.location.href = '/settings/sessions';
    return;
  }

  if (!response.ok) {
    throw new Error('Login failed');
  }

  const data = await response.json();

  // Store client_session_token for UI display only
  localStorage.setItem('client_session_token', data.client_session_token);
  
  // Redirect to dashboard
  window.location.href = '/dashboard';
  
} catch (error) {
  console.error('Login error:', error);
  alert('Login failed. Please try again.');
}
```

---

### 2. Get Active Sessions
**Endpoint**: `GET /api/auth/sessions`

**Request**:
```javascript
const response = await fetch('/api/auth/sessions', {
  method: 'GET',
  credentials: 'include'  // Server derives session from refresh_token cookie
});
```

**Note**: JWT authentication happens automatically via HTTP-only cookies. No Authorization header needed.

**Response** (200 OK):
```json
[
  {
    "client_session_token": "cst_desktop_a1b2c3d4",
    "device_type": "browser",
    "created_at": "2025-11-14T10:00:00Z",
    "last_active": "2025-11-14T15:30:00Z",
    "ip_address": "7868a1769fe3d0c5",                          // HMAC-SHA256 hash (first 16 chars)
    "user_agent": "Chrome/120.0.0.0 (Mac OS X 10.15.7)",
    "is_expired": false,
    "is_current": true                                          // Server-computed (identifies your device)
  },
  {
    "client_session_token": "cst_mobile_e5f6g7h8",
    "device_type": "mobile",
    "created_at": "2025-11-14T09:00:00Z",
    "last_active": "2025-11-14T14:00:00Z",
    "ip_address": "b726760f4a2e8d1c",                          // HMAC-SHA256 hash (first 16 chars)
    "user_agent": "Chrome/120.0.0.0 (Android 14)",
    "is_expired": false,
    "is_current": false
  }
]
```

**Frontend Action**:
```javascript
const response = await fetch('/api/auth/sessions', {
  method: 'GET',
  credentials: 'include'
});

const sessions = await response.json();

// Display sessions in UI using server-computed is_current flag
sessions.forEach(session => {
  const badge = session.is_current ? '(This Device)' : '';
  const token = session.client_session_token;  // XSS-safe UI identifier
  console.log(`${session.device_type} - ${badge} - Token: ${token}`);
});
```

---

### 3. Revoke Specific Session (Logout Other Device)
**Endpoint**: `DELETE /api/auth/sessions/{client_session_token}`

**⚠️ CRITICAL**: Use this endpoint to logout **OTHER** devices. Do NOT use `POST /api/auth/logout`.

**⚠️ IMPORTANT**: Session revocation takes effect on the target device's next authenticated request. The device will receive a 401 error and must re-login.

**Request**:
```javascript
// Use the client_session_token from the session list
await fetch('/api/auth/sessions/cst_mobile_e5f6g7h8', {
  method: 'DELETE',
  credentials: 'include'
});
```

**Response** (200 OK):
```json
{
  "message": "Session revoked successfully"
}
```

**What Happens Next**:
1. Session deleted from Redis ✅
2. Target device JWT cookie still valid (up to 1 hour) ✅
3. Target device makes next request → Backend validates session → 401 Unauthorized → Device logged out ✅

**⚠️ CRITICAL: Prevent 401 Retry Loops**

When the target device receives 401, your data fetching library (React Query, SWR, etc.) may retry the request multiple times by default. This causes **infinite retry loops** where the device makes 20+ requests per second, all failing with 401.

**YOU MUST**:
1. **Configure React Query/TanStack Query** to not retry on 401 errors
2. **Add axios/fetch interceptor** to clear localStorage and redirect on first 401
3. **Disable automatic refetch** on window focus/reconnect during auth errors

See the **Troubleshooting** section below for complete fix implementation: "🚨 CRITICAL: Revoked Device Gets Stuck in 401 Retry Loop"

**Frontend Action**:
```javascript
async function logoutDevice(clientSessionToken) {
  // Use DELETE to /sessions/{token}, NOT POST to /logout
  const response = await fetch(`/api/auth/sessions/${clientSessionToken}`, {
    method: 'DELETE',
    credentials: 'include'
  });
  
  if (response.ok) {
    console.log('Device logged out successfully');
  }
}

// In your UI click handler
<button onClick={() => logoutDevice(session.client_session_token)}>
  Logout Device
</button>
```

---

### 4. Logout Current Device
**Endpoint**: `POST /api/auth/logout`

**⚠️ USE CASE**: Only for logging out the **CURRENT** device (the one making the request).

**Request**:
```javascript
await fetch('/api/auth/logout', {
  method: 'POST',
  credentials: 'include'
});
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
  const response = await fetch('/api/auth/logout', {
    method: 'POST',
    credentials: 'include'
  });
  
  if (response.ok) {
    // Clear local storage
    localStorage.removeItem('client_session_token');
    
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
```javascript
await fetch('/api/auth/logout-all-devices', {
  method: 'POST',
  credentials: 'include'
});
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
  const response = await fetch('/api/auth/logout-all-devices', {
    method: 'POST',
    credentials: 'include'
  });
  
  if (response.ok) {
    localStorage.removeItem('client_session_token');
    window.location.href = '/login';
  }
}
```

---

## Session Limits and Expiration

### Session Limit (5 Maximum Sessions)

**Limit**: Each user can have maximum **5 active sessions** simultaneously.

**Enforcement**: Checked during login at `POST /api/auth/login`

**Why This Limit**:
- **Security**: Prevents session flooding attacks
- **Performance**: Limits Redis memory usage per user
- **User Control**: Forces users to manage their devices explicitly

**What Happens When Limit Exceeded**:
1. Login request returns **429 Too Many Requests**
2. Response message: "Too many active sessions. Please logout from other devices or revoke old sessions."
3. No session created, user cannot login
4. User must revoke old sessions before creating new ones

**How Users Can Resolve**:

**Option 1: Revoke Specific Sessions**
```javascript
// 1. Get list of active sessions
const sessions = await fetch('/api/auth/sessions', {
  credentials: 'include'
}).then(r => r.json());

// 2. Identify unused/old sessions
const oldSessions = sessions.filter(s => !s.is_current && isOld(s.last_active));

// 3. Revoke old sessions
for (const session of oldSessions) {
  await fetch(`/api/auth/sessions/${session.client_session_token}`, {
    method: 'DELETE',
    credentials: 'include'
  });
}

// 4. Try login again
```

**Option 2: Logout All Devices**
```javascript
// Nuclear option - logout all devices and start fresh
await fetch('/api/auth/logout-all-devices', {
  method: 'POST',
  credentials: 'include'
});

// All sessions deleted, can now login
```

**UI Recommendations**:
- Show "Session limit exceeded" error page
- Display link to "Manage Active Sessions" page
- Allow user to view and revoke old sessions
- Provide "Logout All Devices" button as nuclear option
- After cleanup, redirect back to login

---

### Session Expiration (30 Day TTL)

**Session Lifetime**: 30 days of inactivity

**How It Works**:
1. Session created with 30-day TTL in Redis
2. Every authenticated request refreshes TTL (resets to 30 days)
3. If no requests for 30 days → Session expires and auto-deleted by Redis
4. Next request with expired session → 401 Unauthorized

**TTL Refresh Behavior**:
```
Login at 10:00 AM Jan 1 → Session expires at 10:00 AM Jan 31
User makes request at 2:00 PM Jan 10 → Session expires at 2:00 PM Feb 9 (TTL refreshed)
User makes request at 8:00 PM Jan 20 → Session expires at 8:00 PM Feb 19 (TTL refreshed)
... and so on
```

**Expiration Check**:
- Backend validates `is_expired` property before using session
- `is_expired = (datetime.utcnow() - last_active) > 2592000 seconds`
- If expired, session deleted and 401 returned

**User Experience**:
- Active users: Never experience expiration (TTL constantly refreshed)
- Inactive users: Must re-login after 30 days
- No warning before expiration (clean security model)

**Frontend Handling**:
```javascript
// Every authenticated request can return 401
try {
  const response = await apiRequest('/api/quiz/generate', { ... });
  
  if (response.status === 401) {
    // Session expired or invalid
    localStorage.removeItem('client_session_token');
    window.location.href = '/login?message=Session expired, please login again';
  }
} catch (error) {
  // Handle error
}
```

---

### JWT Token Expiration

**Access Token**: 1 hour TTL
- Used for authentication on every request
- Stored in HTTP-only cookie
- Short-lived for security
- Automatically refreshed via refresh_token

**Refresh Token**: 30 days TTL
- Used to obtain new access_token when it expires
- Stored in HTTP-only cookie
- Long-lived for user convenience
- Used by `POST /api/auth/refresh` endpoint

**Token Refresh Flow**:
1. Access token expires after 1 hour
2. Frontend calls `POST /api/auth/refresh` with refresh_token cookie
3. Backend validates refresh_token with Supabase
4. Backend issues new access_token (1 hour TTL)
5. Backend sets new access_token cookie
6. Frontend can continue making authenticated requests

**Important**: JWT expiration is SEPARATE from Redis session expiration:
- JWT: Controls authentication (1 hour access, 30 days refresh)
- Redis Session: Controls device tracking and revocation (24 hours activity)
- Both must be valid for request to succeed

**Why Two Expiration Systems**:
- JWT: Stateless, scales well, managed by Supabase
- Redis: Stateful, enables multi-device management, instant revocation

---

### Automatic Cleanup

**Redis TTL Cleanup**:
- Redis automatically deletes expired sessions (24 hours TTL)
- No manual cleanup required
- Memory usage stays bounded

**Expired Session References**:
- User's session set (`user_sessions:{user_id}`) may contain references to expired sessions
- Backend provides `cleanup_expired_sessions(user_id)` method to clean these up
- Called automatically when user views session list
- Not critical (expired sessions won't validate anyway)

**Cleanup Example** (automatic, backend handles this):
```python
# Backend automatically cleans up when user lists sessions
sessions = await session_service.list_sessions(user_id)
# Returns only valid, non-expired sessions
# Expired sessions filtered out automatically
```

---

## Client Session Token Handling {#client-session-token-handling}

### What is client_session_token?

**Purpose**: XSS-safe, non-authoritative identifier for UI display and "current device" highlighting.

**Format**: `cst_{session_prefix}_{HMAC_signature}`
- Example: `cst_abc123_a1b2c3d4`
- HMAC-signed using server secret
- Cannot be forged or tampered with
- Safe to expose to JavaScript (non-authoritative)

**NOT Used For**:
- ❌ Authentication (handled by httpOnly cookies)
- ❌ Session validation (backend uses refresh_token cookie)
- ❌ Security checks

**Used For**:
- ✅ UI display ("This Device" badge)
- ✅ Local session identification
- ✅ Client-side session matching

### Where to Store client_session_token

**Recommended**: `localStorage` (persists across browser restarts)

```javascript
// After login
localStorage.setItem('client_session_token', data.client_session_token);

// Later use
const myToken = localStorage.getItem('client_session_token');
```

**Alternative**: `sessionStorage` (clears when browser closes)
```javascript
sessionStorage.setItem('client_session_token', data.client_session_token);
```

### How to Use client_session_token

**1. Display "This Device" Badge**:
```javascript
const myToken = localStorage.getItem('client_session_token');

sessions.forEach(session => {
  // Option 1: Use server-computed is_current flag (recommended)
  const badge = session.is_current ? '(This Device)' : '';
  
  // Option 2: Match client_session_token locally (optional)
  const isMyDevice = session.client_session_token === myToken;
  
  console.log(`${session.device_type} ${badge}`);
});
```

**2. Find Current Session in List**:
```javascript
const myToken = localStorage.getItem('client_session_token');
const currentSession = sessions.find(s => s.client_session_token === myToken);

if (currentSession) {
  console.log('Current device:', currentSession.device_type);
}
```

**3. Validate Token Format (Optional)**:
```javascript
function isValidClientSessionToken(token) {
  // Format: cst_{8_chars}_{16_chars}
  return /^cst_[a-z0-9]{8}_[a-z0-9]{16}$/i.test(token);
}

const token = localStorage.getItem('client_session_token');
if (!isValidClientSessionToken(token)) {
  console.warn('Invalid client_session_token format');
}
```

### How to Send Authenticated Requests

**No headers needed!** Just include credentials for cookie-based authentication.

```javascript
// Fetch API - Cookies sent automatically
fetch('/api/quiz/generate', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  credentials: 'include',  // ← Server derives session from refresh_token cookie
  body: JSON.stringify(quizData)
});

// Axios - Cookies sent automatically
axios.post('/api/quiz/generate', quizData, {
  withCredentials: true  // ← Server derives session from refresh_token cookie
});
```

### CORS Configuration

**Required CORS Headers** (already configured in backend):
```
Access-Control-Allow-Origin: <your-frontend-domain>
Access-Control-Allow-Credentials: true
Access-Control-Allow-Headers: Content-Type, Authorization, Accept
```

**Frontend Must**:
- ✅ Set `credentials: 'include'` (fetch) or `withCredentials: true` (axios)
- ✅ Match exact origin (no wildcards with credentials)
- ✅ No session headers required (authentication via cookies)

---

## Implementation Guide

### Step 1: Setup Session Storage

```javascript
// utils/session.js

export const SessionManager = {
  // Store client_session_token after login (XSS-safe)
  setSession(clientSessionToken) {
    localStorage.setItem('client_session_token', clientSessionToken);
  },
  
  // Get client_session_token (XSS-safe)
  getClientToken() {
    return localStorage.getItem('client_session_token');
  },
  
  // Clear session on logout
  clearSession() {
    localStorage.removeItem('client_session_token');
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
  },
  
  // Check if session exists
  hasSession() {
    return !!localStorage.getItem('client_session_token');
  }
};
```

---

### Step 2A: Create API Client (Fetch-based)

```javascript
// api/client.js

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

export async function apiRequest(endpoint, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers
  };
  
  // No X-Session-ID header needed!
  // Backend derives session from refresh_token cookie automatically
  
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers,
    credentials: 'include'  // ← CRITICAL: Server derives session from refresh_token cookie
  });
  
  // Handle different error scenarios
  if (response.status === 401) {
    // Session expired or invalid
    localStorage.removeItem('client_session_token');
    window.location.href = '/login?message=Session expired';
    throw new Error('Session expired');
  }
  
  if (response.status === 429) {
    // Session limit or rate limit
    const data = await response.json();
    if (data.detail.includes('Too many active sessions')) {
      window.location.href = '/settings/sessions';
    }
    throw new Error(data.detail);
  }
  
  return response;
}
```

---

### Step 2B: Create API Client (Axios-based)

**If using axios**, configure request/response interceptors:

```javascript
// api/client.js

import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

// Create axios instance
const apiClient = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,  // ← CRITICAL: Server derives session from refresh_token cookie
  headers: {
    'Content-Type': 'application/json'
  }
});

// Request interceptor - Log requests (optional)
apiClient.interceptors.request.use(
  (config) => {
    console.debug(`[Request] ${config.method?.toUpperCase()} ${config.url} - Cookie-based auth`);
    return config;
  },
  (error) => {
    console.error('[Request Error]', error);
    return Promise.reject(error);
  }
);

// Response interceptor - Handle errors globally
apiClient.interceptors.response.use(
  (response) => {
    // Success - return response
    return response;
  },
  (error) => {
    const status = error.response?.status;
    const data = error.response?.data;
    
    console.error(`[Response Error] ${status}:`, data);
    
    if (status === 401) {
      // Session expired or invalid
      console.warn('[401] Session expired - redirecting to login');
      localStorage.removeItem('client_session_token');
      localStorage.removeItem('access_token');
      window.location.href = '/login?message=Session expired. Please login again.';
    } else if (status === 429) {
      // Session limit exceeded
      if (data?.detail?.includes('Too many active sessions')) {
        console.warn('[429] Session limit exceeded - redirecting to session management');
        alert('You have reached the maximum number of active sessions (5). Please revoke old sessions.');
        window.location.href = '/settings/sessions';
      }
    } else if (status === 503) {
      // Service unavailable
      console.warn('[503] Service unavailable - fallback mode or downtime');
      alert('Service temporarily unavailable. Please try again in a few moments.');
    }
    
    return Promise.reject(error);
  }
);

export default apiClient;

// Usage:
// import apiClient from './api/client';
// const response = await apiClient.get('/api/auth/me');  // No X-Session-ID needed!
// const quizzes = await apiClient.get('/api/quiz/my-quizzes');
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
      
      // Store client_session_token (XSS-safe UI identifier)
      SessionManager.setSession(data.client_session_token);
      
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
        setSessions(prev => prev.filter(s => s.client_session_token !== clientToken));
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
          <div key={session.client_session_token} className="session-card">
            <div>
              <strong>{session.device_type}</strong>
              {session.is_current && <span> (This Device)</span>}
            </div>
            <div>Last active: {new Date(session.last_active).toLocaleString()}</div>
            <div>Location: {session.ip_address.substring(0, 8)}...</div>
            <div>{session.user_agent}</div>
            
            {!session.is_current && (
              <button onClick={() => revokeSession(session.client_session_token)}>
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
      // Logout current device
      const response = await apiRequest('/api/auth/logout', {
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

## Error Handling

### HTTP Status Codes

#### 401 Unauthorized
**Scenarios**:
1. **Session Expired**: Session older than 30 days or deleted
2. **Session Not Found**: Session ID not in Redis (revoked or never existed)
3. **JWT Invalid**: Refresh token expired or invalid
4. **Cookies Missing**: Browser not sending credentials

**Backend Message Examples**:
```json
{ "detail": "Session expired or invalid" }
{ "detail": "Authentication required" }
```

**Frontend Handling**:
```javascript
if (response.status === 401) {
  // Clear local session
  localStorage.removeItem('client_session_token');
  
  // Redirect to login with message
  const message = 'Your session has expired. Please login again.';
  window.location.href = `/login?message=${encodeURIComponent(message)}`;
}
```

---

#### 403 Forbidden
**Scenarios**:
1. **Session Ownership Violation**: User tries to revoke another user's session
2. **Email Not Verified**: User attempts action requiring verified email

**Backend Message Examples**:
```json
{ "detail": "Session does not belong to authenticated user" }
{ "detail": "Please verify your email address before logging in." }
```

**Frontend Handling**:
```javascript
if (response.status === 403) {
  const data = await response.json();
  
  if (data.detail.includes('verify your email')) {
    // Show email verification required
    alert('Please verify your email before continuing.');
    window.location.href = '/verify-email';
  } else {
    // Generic forbidden error
    alert('You do not have permission to perform this action.');
  }
}
```

---

#### 429 Too Many Requests
**Scenarios**:
1. **Session Limit Exceeded**: User has 10+ active sessions during login
2. **Rate Limiting**: Too many requests in short time (future enhancement)

**Backend Message**:
```json
{ "detail": "Too many active sessions. Please logout from other devices or revoke old sessions." }
```

**Frontend Handling**:
```javascript
if (response.status === 429) {
  const data = await response.json();
  
  if (data.detail.includes('Too many active sessions')) {
    // Show session management page
    alert('You have reached the maximum number of active sessions (5). Please revoke old sessions.');
    window.location.href = '/settings/sessions';
  } else {
    // Generic rate limit
    alert('Too many requests. Please try again later.');
  }
}
```

---

#### 503 Service Unavailable
**Scenarios**:
1. **Redis Unavailable**: Redis connection failed (rare - fallback mode active)
2. **Database Unavailable**: Supabase connection failed

**Backend Message**:
```json
{ "detail": "Session service temporarily unavailable" }
```

**Frontend Handling**:
```javascript
if (response.status === 503) {
  // Service temporarily unavailable
  alert('Service temporarily unavailable. Please try again in a few moments.');
  
  // Retry with exponential backoff
  setTimeout(() => retryRequest(), 5000);
}
```

---

### Fallback Mode (Redis Unavailable)

**What Is Fallback Mode**:
When Redis is unavailable (connection failed, Redis down, etc.), the backend enters "fallback mode" to keep the service available.

**Login Behavior in Fallback Mode**:
```javascript
// Login succeeds, but session_id is NOT returned
{
  "message": "Successfully logged in",
  "user": { ... },
  // ❌ No "session_id" field
}
```

**Backend Logs** (visible in Railway):
```
WARNING - Failed to create Redis session (fallback mode): Connection refused
```

**What This Means**:
- Login still works (users can access the app)
- JWT authentication works (cookies still valid)
- Session management features disabled:
  - ❌ Cannot view active sessions (`GET /api/auth/sessions` returns empty array)
  - ❌ Cannot revoke sessions (`DELETE /api/auth/sessions/{id}` returns 503)
  - ❌ Session limits not enforced (can create unlimited sessions)
  - ❌ Device tracking not available

**Frontend Handling**:
```javascript
// After login
const data = await response.json();

if (!data.client_session_token) {
  console.warn('Session management unavailable (fallback mode)');
  
  // Still store user info and proceed
  // Just don't rely on session features
  window.location.href = '/dashboard';
}

// On session management page
const sessions = await fetch('/api/auth/sessions', {
  credentials: 'include'
}).then(r => r.json());

if (sessions.length === 0) {
  // Could be no sessions OR fallback mode
  showMessage('Session management temporarily unavailable');
}
```

**When Fallback Mode Activates**:
- Redis container restart
- Network connectivity issues
- Redis out of memory
- Redis configuration error

**When Fallback Mode Ends**:
- Redis comes back online
- Backend automatically reconnects
- New logins create sessions normally
- Old sessions may still be in Redis (if Redis just restarted)

---

### Comprehensive Error Handler

**Recommended API Client Error Handler**:
```javascript
async function apiRequest(endpoint, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers
  };
  
  try {
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      ...options,
      headers,
      credentials: 'include'  // Required for cookie-based auth
    });
    
    // Handle different status codes
    if (response.status === 401) {
      // Session expired, revoked, or invalid
      // Use global flag to prevent multiple redirects (retry loop protection)
      if (!window.__authRedirectInProgress) {
        window.__authRedirectInProgress = true;
        console.warn('[401] Session invalid - logging out and redirecting to login');
        localStorage.removeItem('client_session_token');
        
        // Delay redirect slightly to allow cleanup
        setTimeout(() => {
          window.location.href = '/login?message=Session expired. Please login again.';
        }, 100);
      }
      throw new Error('Session expired');
    }
    
    if (response.status === 403) {
      // Forbidden - usually permission issue
      const data = await response.json();
      throw new Error(data.detail || 'Forbidden');
    }
    
    if (response.status === 429) {
      // Too many requests or session limit
      const data = await response.json();
      if (data.detail.includes('Too many active sessions')) {
        window.location.href = '/settings/sessions';
      }
      throw new Error(data.detail);
    }
    
    if (response.status === 503) {
      // Service unavailable - retry
      throw new Error('Service temporarily unavailable');
    }
    
    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.detail || `HTTP ${response.status}`);
    }
    
    return response;
    
  } catch (error) {
    console.error(`API request failed: ${endpoint}`, error);
    throw error;
  }
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
    credentials: 'include'
  });
  // Result: Target device revoked, YOUR session unaffected
}
```

---

### ❌ WRONG: Not Setting `credentials: 'include'`

```javascript
// ❌ JWT cookies not sent, authentication fails
fetch('/api/auth/sessions', {
  method: 'GET'
  // Missing: credentials: 'include'
});
// Result: 401 Unauthorized
```

### ✅ CORRECT: Always Include Credentials

```javascript
// ✅ JWT cookies sent automatically
fetch('/api/auth/sessions', {
  method: 'GET',
  credentials: 'include'  // ← REQUIRED
});
```

---

### ❌ WRONG: Storing Client Session Token in State Only

```javascript
// ❌ Lost on page refresh
const [token, setToken] = useState(null);

// After login
setToken(data.client_session_token);  // Lost when user refreshes page!
```

### ✅ CORRECT: Persist in localStorage

```javascript
// ✅ Survives page refresh
localStorage.setItem('client_session_token', data.client_session_token);

// Later
const token = localStorage.getItem('client_session_token');
```

---

## Testing Checklist

### Functional Testing

- [ ] **Login Flow**
  - [ ] Client session token returned in login response
  - [ ] Client session token stored in localStorage
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
  - [ ] Invalid client_session_token returns 401
  - [ ] Expired sessions cleaned up automatically

- [ ] **CORS**
  - [ ] OPTIONS preflight succeeds (200 OK)
  - [ ] Credentials allowed for same origin

### Browser Compatibility

- [ ] Chrome/Edge (Chromium)
- [ ] Firefox
- [ ] Safari
- [ ] Mobile browsers (iOS Safari, Chrome Android)

---

## Best Practices

1. **Always set credentials: 'include'** for cookie support on all authenticated requests
2. **Store client_session_token in localStorage** for persistence across page refreshes
3. **Use DELETE /sessions/{id}** for revoking other devices
4. **Use POST /logout** only for current device logout
5. **Handle 401 errors** by clearing localStorage and redirecting to login
6. **Show "This Device" badge** for is_current sessions
7. **Disable "Logout Device" button** for current session (prevent self-revoke)
8. **Confirm before logout all devices** (destructive action)
9. **Clear localStorage** on logout
10. **Test session revocation** by verifying 401 error on target device after revoke
11. **Monitor Network tab** to ensure cookies are sent properly

---

## Troubleshooting

### Sessions Not Being Created

**Symptom**: Session list always empty after login

**Check**:
1. Backend logs: Look for "Redis session created"
2. Redis: Check for keys `session:*` and `user_sessions:*`
3. Response: Verify `client_session_token` in login response

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

### 401 Errors After Login

**Symptom**: After login, authenticated requests return 401 Unauthorized

**Root Cause**: Browser not sending cookies with requests (missing `credentials: 'include'`)

**Diagnosis**:
```javascript
// In Network tab → Request Headers:
// Cookie: (missing) ❌
```

**Solution**: Always include credentials

**For Fetch**:
```javascript
fetch('/api/auth/me', {
  credentials: 'include'  // ← REQUIRED
});
```

**For Axios**:
```javascript
axios.create({
  withCredentials: true  // ← REQUIRED
});
```

**Secondary Issue - React Query Retry Loop**:
Configure React Query to prevent retries on 401 errors:

```javascript
import { QueryClient } from '@tanstack/react-query';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {
        // Don't retry on 401 errors
        if (error?.response?.status === 401) {
          return false;
        }
        return failureCount < 3;
      },
    },
  },
});
```

**Verification**:
1. Open DevTools → Network tab
2. Make authenticated request (e.g., GET /api/auth/me)
3. Check Request Headers → should see `Cookie: refresh_token=...`
4. Should get 200 OK response (not 401)
5. Should NOT see rapid retry requests

---

### Device Not Getting Logged Out After Session Revoked

**Symptom**: Revoked Android session, but Android device still works

**Root Cause**: Session revocation takes effect when the target device makes its next authenticated request. The device's JWT cookie remains valid (up to 1 hour) until the next API call.

**How It Works**:
1. Desktop calls `DELETE /api/auth/sessions/{android_session_id}` → Session deleted from Redis ✅
2. Android still has valid JWT cookie (valid for 1 hour) ✅
3. Android makes next request → Backend validates session → 401 Unauthorized → Device logged out ✅

**Check**:
1. Android device Network tab: Verify `credentials: 'include'` is set
2. Backend logs: Look for "Session ... not found for user ..." (session validation working)

**Testing**:
1. Revoke Android session from Desktop
2. On Android, refresh page or trigger any API call
3. Should receive 401 Unauthorized immediately
4. Verify frontend redirects to login page
5. Verify localStorage cleared

---

### Session Revoked Device Keeps Retrying (401 Loop)

**Symptom**: After revoking Device B from Device A, Device B makes hundreds of 401 requests per second instead of logging out once.

**Root Cause**: React Query (or similar data fetching library) retries failed requests automatically. Without proper configuration, it retries 401 errors infinitely.

**What's Happening**:
1. Desktop revokes Android session → Session deleted from Redis ✅
2. Android makes request with revoked `session_id` → Backend returns 401 ✅
3. React Query sees 401 → Retries request → 401 again → Retries again → Infinite loop ❌
4. Multiple components (profile, quizzes, submissions) all retrying simultaneously
5. Result: 20+ requests per second, application frozen

**The Fix - Prevent Retry on 401 Errors**:

```javascript
// In your QueryClient setup (App.tsx or main.tsx)
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Customize retry logic to prevent 401 retries
      retry: (failureCount, error) => {
        // NEVER retry authentication errors
        if (error?.response?.status === 401) {
          console.log('[React Query] 401 detected - not retrying, will redirect to login');
          return false;
        }
        
        // Don't retry other client errors (400-499)
        if (error?.response?.status >= 400 && error?.response?.status < 500) {
          return false;
        }
        
        // Retry server errors (500+) up to 3 times
        return failureCount < 3;
      },
      
      // Reduce automatic refetching to prevent rapid retries
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      staleTime: 5 * 60 * 1000, // 5 minutes
    },
    
    mutations: {
      // Also prevent mutation retries on 401
      retry: (failureCount, error) => {
        if (error?.response?.status === 401) {
          return false;
        }
        return failureCount < 3;
      },
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      {/* Your app */}
    </QueryClientProvider>
  );
}
```

**Additional Protection - Global Flag in API Client**:

```javascript
// In your API client (api.ts or apiClient.ts)

// Global flag to prevent multiple simultaneous redirects
let isRedirecting = false;

const apiClient = axios.create({
  baseURL: process.env.REACT_APP_API_URL,
  withCredentials: true,
});

// Response interceptor - handle 401 ONCE
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && !isRedirecting) {
      // Set flag FIRST to prevent concurrent requests from also redirecting
      isRedirecting = true;
      
      console.warn('[401] Session invalid - clearing auth state and redirecting');
      
      // Clear auth data
      localStorage.removeItem('client_session_token');
      
      // Redirect after brief delay
      setTimeout(() => {
        window.location.href = '/login?message=Your session has been revoked. Please login again.';
      }, 100);
    }
    
    return Promise.reject(error);
  }
);

export default apiClient;
```

**Verification Steps**:
1. Open DevTools → Network tab
2. Revoke current device session from another device
3. Watch Network tab after revocation
4. **Expected**: 1-4 failed requests → Single redirect to /login
5. **Wrong**: Hundreds of 401 requests → Infinite loop (fix not applied)

**Testing Checklist**:
- [ ] React Query configured with `retry: false` for 401 errors
- [ ] Global redirect flag (`isRedirecting`) prevents concurrent redirects
- [ ] localStorage cleared before redirect
- [ ] Only 1 redirect happens (not multiple tabs opening)
- [ ] Network tab shows <10 failed requests before redirect
- [ ] No "Maximum update depth exceeded" errors in console
- [ ] Login page displays "session revoked" message
 
---

## 🔐 Preventing Network Glitches from Logging Users Out

Once the session header flow is stable, the next major stability issue is **false-positive logouts**. Today, `makeAuthenticatedRequest`/`authService.fetchCurrentUser` clear all local state whenever `/api/auth/me` returns anything other than 200—even when the failure is just a transient 502 or a user closing their laptop for a minute. The fix is to classify responses and only destroy local session data on confirmed authentication failures.

### 1. Classify Response Outcomes at the Network Layer

`makeAuthenticatedRequest` should return a discriminated union so callers know whether they are dealing with an auth failure or a flaky network:

```typescript
type AuthRequestResult<T> =
  | { kind: 'success'; data: T; response: Response }
  | { kind: 'auth-error'; status: number; detail?: string }
  | { kind: 'network-error'; error: Error; status?: number };

export async function makeAuthenticatedRequest<T>(input: RequestInfo, init?: RequestInit): Promise<AuthRequestResult<T>> {
  try {
    const response = await fetch(input, init);

    if (response.status === 401 || response.status === 403) {
      // Confirmed auth failure → let caller clear local state/redirect
      const detail = await safeJson(response);
      return { kind: 'auth-error', status: response.status, detail };
    }

    if (!response.ok) {
      // 5xx, 429, gateway timeouts, etc. → treat as network/server error
      const detail = await safeJson(response);
      return {
        kind: 'network-error',
        status: response.status,
        error: new Error(detail ?? `HTTP ${response.status}`),
      };
    }

    const data = (await response.json()) as T;
    return { kind: 'success', data, response };
  } catch (error) {
    return { kind: 'network-error', error: error as Error };
  }
}

async function safeJson(response: Response): Promise<string | undefined> {
  try {
    const body = await response.clone().json();
    return typeof body?.detail === 'string' ? body.detail : undefined;
  } catch {
    return undefined;
  }
}

```

### 2. Upgrade `authService.fetchCurrentUser`

`fetchCurrentUser` should only clear storage when it explicitly receives an `auth-error`. For network issues it should bubble the error up so UI layers can show a toast/retry without forcing logout:

```typescript
export type CurrentUserResult =
  | { kind: 'authenticated'; user: CurrentUser }
  | { kind: 'unauthenticated'; reason: 'missing-session' | 'revoked' }
  | { kind: 'error'; error: Error; status?: number };

export async function fetchCurrentUser(): Promise<CurrentUserResult> {
  const clientToken = localStorage.getItem('client_session_token');
  if (!clientToken) {
    return { kind: 'unauthenticated', reason: 'missing-session' };
  }

  const result = await makeAuthenticatedRequest<CurrentUserResponse>('/api/auth/me', {
    method: 'GET',
    credentials: 'include',
  });

  if (result.kind === 'success') {
    return { kind: 'authenticated', user: result.data };
  }

  if (result.kind === 'auth-error') {
    clearSessionStorage();
    return { kind: 'unauthenticated', reason: 'revoked' };
  }

  // Network/server problem – leave session intact so UI can retry
  return { kind: 'error', error: result.error, status: result.status };
}

function clearSessionStorage() {
  localStorage.removeItem('client_session_token');
}
```

### 3. AuthProvider: Only Redirect on Confirmed Auth Failures

Wrap the provider state machine so transient errors show a non-blocking banner instead of redirecting the user out of the app:

```typescript
type AuthViewState =
  | { status: 'loading' }
  | { status: 'ready'; user: CurrentUser }
  | { status: 'network-error'; error: Error; lastSuccess?: Date }
  | { status: 'unauthenticated' };

useEffect(() => {
  let cancelled = false;
  setState({ status: 'loading' });

  fetchCurrentUser().then((result) => {
    if (cancelled) return;

    switch (result.kind) {
      case 'authenticated':
        setState({ status: 'ready', user: result.user });
        break;
      case 'unauthenticated':
        redirectToLogin('Authentication required');
        break;
      case 'error':
        console.warn('AuthProvider network issue', result.error);
        setState((prev) => ({
          status: 'network-error',
          error: result.error,
          lastSuccess: prev.status === 'ready' ? new Date() : undefined,
        }));
        // Optional: schedule retry/backoff instead of forcing logout
        break;
    }
  });

  return () => {
    cancelled = true;
  };
}, []);
```

UI recommendation: show a toast such as “We’re having trouble reaching Quizify. Your session is still active—retrying automatically.” Keep the dashboard data cached via React Query so the user can continue reading old data until the next successful `/me` fetch.

### 4. `useSessionCheck`: Respect the New Contract

Background session checks (tab focus, 5-minute intervals, etc.) should mirror the same discriminated union so they only eject the user when `fetchCurrentUser` explicitly reports `unauthenticated`:

```typescript
export function useSessionCheck({ intervalMs = 300000, onExpired }: Options) {
  useEffect(() => {
    let timer: number | null = null;
    let cancelled = false;

    async function runCheck(source: 'interval' | 'focus') {
      const result = await fetchCurrentUser();
      if (cancelled) return;

      if (result.kind === 'unauthenticated') {
        onExpired?.(result.reason);
        redirectToLogin('Session expired');
        return;
      }

      if (result.kind === 'error') {
        console.info(`[SessionCheck:${source}] transient issue`, result.error);
        // Optional: surface banner or exponential backoff before next attempt
        return;
      }

      // Success → nothing to do
    }

    if (intervalMs > 0) {
      timer = window.setInterval(() => runCheck('interval'), intervalMs);
    }

    window.addEventListener('focus', () => runCheck('focus'));
    runCheck('init');

    return () => {
      cancelled = true;
      if (timer) window.clearInterval(timer);
      window.removeEventListener('focus', () => runCheck('focus'));
    };
  }, [intervalMs, onExpired]);
}
```

### 5. UX Expectations

| Scenario | Expected Behavior |
| --- | --- |
| Supabase revokes session (401/403) | Local storage cleared, redirect to `/login`, toast “Session expired”. |
| User closes laptop → `/me` times out | Stay on page, show “Reconnecting…” banner, auto retry. |
| Temporary 5xx from `/api/auth/me` | Stay on page, cache remains, retry silently. |
| Missing `session_id` (manual storage clear) | Redirect immediately with “Please login again”. |

This division ensures **valid sessions survive flaky networks**, while truly invalid sessions still force logout instantly.

---

## Quick Reference - Critical Implementation Checklist

**Visual Flow - What Should Happen**:
```
Device A (Desktop)                    Backend Redis              Device B (Revoked)
─────────────────                    ─────────────              ──────────────────
1. User clicks "Logout 
   Android device"
   
2. DELETE /sessions/sess_android
   ────────────────────────────────>
   
                                     3. Delete sess_android     
                                        from Redis
                                        
3. Response: 200 OK                  
   <────────────────────────────────
   
4. Show success message:
   "Android device logged out"
   
                                                                5. User interacts
                                                                   with app
                                                                   
                                                                6. GET /api/auth/me
                                                                   X-Session-ID: sess_android
                                                                   ──────────────────────────>
                                                                   
                                                                7. Validate sess_android
                                                                   → Not found in Redis
                                                                   → Return 401
                                                                   
                                                                8. Response: 401 Unauthorized
                                                                   <──────────────────────────
                                                                   
                                                                9. React Query sees 401
                                                                   → Check retry config
                                                                   → retry: false (configured)
                                                                   → NO RETRY ✅
                                                                   
                                                                10. Axios interceptor catches 401
                                                                    → Set isRedirecting = true
                                                                    → Clear localStorage
                                                                    → Redirect to /login
                                                                    
                                                                11. User sees login page
                                                                    Message: "Session revoked"
                                                                    ✅ DONE
```

**Visual Flow - What's Currently Broken (401 Loop)**:
```
Device B (Revoked)                   Backend                    Result
──────────────────                   ───────                    ──────
1. User interacts with app

2. GET /api/auth/me
   X-Session-ID: sess_android
   ─────────────────────────────────>
   
                                     3. Session not found
                                        → 401 Unauthorized
                                        
4. Response: 401
   <─────────────────────────────────
   
5. React Query: "Retry!" (no config)
   GET /api/auth/me (RETRY 1)
   ─────────────────────────────────>  401 again                 ❌ Retry #1
   
6. React Query: "Retry!" 
   GET /api/auth/me (RETRY 2)
   ─────────────────────────────────>  401 again                 ❌ Retry #2
   
7. React Query: "Retry!"
   GET /api/auth/me (RETRY 3)
   ─────────────────────────────────>  401 again                 ❌ Retry #3
   
8. Meanwhile, other components also retrying:
   GET /api/quiz/my-quizzes × 3      ─>  401, 401, 401          ❌ 3 more
   GET /api/submissions × 3          ─>  401, 401, 401          ❌ 3 more
   
9. React Query decides to refetch:
   [Repeat steps 2-8 infinitely]                                 ❌ INFINITE LOOP
   
10. Result: 20+ requests per second
    Application frozen
    User cannot access anything
```

---

### 🚨 CRITICAL: Revoked Device Gets Stuck in 401 Retry Loop

**Symptom**: After revoking Device B's session from Device A, Device B makes 20+ requests per second, all returning 401, infinite loop

**Root Cause**: React Query (or other data fetching library) retrying failed 401 requests automatically

**What's Happening**:
1. Device A revokes Device B's session → Session deleted from Redis ✅
2. Device B makes request with now-invalid session_id → Backend returns 401 ✅
3. **React Query retries the request 3 times** (default behavior) ❌
4. Multiple components use `useQuery` → All retry simultaneously ❌
5. Error handler eventually triggers → Clears localStorage → Redirects ❌
6. But page reload triggers new queries → Retry loop starts again ❌

**Diagnostic Evidence** (Backend Logs):
```
Session ID missing for user 760602fe... on /api/auth/me - returning 401
Session ID missing for user 760602fe... on /api/quiz/my-quizzes - returning 401
Session ID missing for user 760602fe... on /api/submissions - returning 401
Session ID missing for user 760602fe... on /api/auth/me - returning 401
... (repeats 20+ times per second)
```

**Solution 1: Disable React Query Retry on 401 (REQUIRED)**

```javascript
// In App.tsx or main.tsx where QueryClient is initialized

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error: any) => {
        // Don't retry on authentication errors (401, 403)
        if (error?.response?.status === 401 || error?.response?.status === 403) {
          console.log('Auth error detected - not retrying');
          return false;
        }
        
        // Don't retry on other client errors (400-499)
        if (error?.response?.status >= 400 && error?.response?.status < 500) {
          return false;
        }
        
        // Retry server errors (500+) up to 3 times
        return failureCount < 3;
      },
      
      // Also disable automatic refetch behaviors during auth issues
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      staleTime: 5 * 60 * 1000, // 5 minutes
    },
    
    mutations: {
      retry: (failureCount, error: any) => {
        // Don't retry mutations on auth errors
        if (error?.response?.status === 401 || error?.response?.status === 403) {
          return false;
        }
        return failureCount < 3;
      },
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      {/* Your app components */}
    </QueryClientProvider>
  );
}
```

**Solution 2: Axios Interceptor Early Handling (ADDITIONAL PROTECTION)**

```javascript
// In your axios API client setup

import axios from 'axios';

const apiClient = axios.create({
  baseURL: process.env.REACT_APP_API_URL,
  withCredentials: true,
});

// Track recent 401 errors to prevent retry storms
const recent401s = new Set<string>();

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      const endpoint = error.config?.url || 'unknown';
      
      // If we've seen this endpoint fail recently, don't process again
      if (recent401s.has(endpoint)) {
        console.log('Already handling 401 for', endpoint);
        return Promise.reject(new Error('Auth error - already handled'));
      }
      
      // Mark this endpoint as having failed
      recent401s.add(endpoint);
      setTimeout(() => recent401s.delete(endpoint), 5000);
      
      // Clear auth state immediately
      console.log('401 detected - clearing auth state');
      localStorage.removeItem('session_id');
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      
      // Redirect to login (only once)
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
      
      // Return non-retryable error
      return Promise.reject(new Error('Authentication required'));
    }
    
    return Promise.reject(error);
  }
);
```

**Expected Behavior After Fix**:

**BEFORE (Broken)**:
```
[0.0s] GET /api/auth/me → 401
[0.1s] GET /api/auth/me → 401 (retry 1)
[0.2s] GET /api/quiz/my-quizzes → 401
[0.3s] GET /api/auth/me → 401 (retry 2)
[0.4s] GET /api/submissions → 401
[0.5s] GET /api/quiz/my-quizzes → 401 (retry 1)
... infinite loop ...
```

**AFTER (Fixed)**:
```
[0.0s] GET /api/auth/me → 401
[0.0s] Axios interceptor clears localStorage
[0.0s] React Query receives non-retryable error
[0.1s] Redirect to /login
[Done] No more requests
```

**Verification**:
1. Device A: Revoke Device B's session
2. Device B: Refresh page or trigger API call
3. **Network tab should show**: 1 request per endpoint → 1x 401 response → redirect
4. **Should NOT see**: Multiple retries, rapid fire requests
5. **Backend logs should show**: Single 401 per endpoint, not 20+

**Testing Checklist**:
- [ ] React Query configured to not retry on 401
- [ ] Axios interceptor handles 401 immediately
- [ ] Browser cache cleared before testing
- [ ] localStorage cleared before testing
- [ ] Only 1-4 requests total before redirect (one per component)
- [ ] No retry attempts visible in Network tab
- [ ] Backend logs show <10 total 401s, not hundreds

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

## Quick Reference - Critical Implementation Checklist

Use this checklist to ensure proper session management implementation:

### ✅ Step 1: Login & Session Creation
- [ ] Login returns `client_session_token` in response body: `data.client_session_token`
- [ ] Store in localStorage: `localStorage.setItem('client_session_token', data.client_session_token)`
- [ ] Verify client_session_token is NOT null/undefined after login
- [ ] Check localStorage in browser DevTools → Application tab
- [ ] Verify refresh_token cookie is set (check Application → Cookies)

### ✅ Step 2: Request Configuration
- [ ] All authenticated requests include `credentials: 'include'`
- [ ] Verify cookies sent in Network tab → Request Headers → Cookie
- [ ] No custom session headers required (X-Session-ID removed)

### ✅ Step 3: React Query Configuration
- [ ] Configure QueryClient with `retry: false` for 401 errors
- [ ] Disable `refetchOnWindowFocus` and `refetchOnReconnect`
- [ ] Set reasonable `staleTime` (5 minutes recommended)
- [ ] Apply same config to mutations

### ✅ Step 4: 401 Error Handling
- [ ] Response interceptor catches 401 errors
- [ ] Global flag prevents multiple concurrent redirects
- [ ] Clear localStorage (client_session_token)
- [ ] Single redirect to /login with error message
- [ ] No retry loops (verify in Network tab)

### ✅ Step 5: Session Revocation Handling
- [ ] Revoked device receives 401 on next request
- [ ] 401 handler triggers (see Phase 4)
- [ ] User redirected to login ONCE (not looping)
- [ ] Network tab shows <10 failed requests before redirect
- [ ] No "Maximum update depth exceeded" errors

### ✅ Step 6: Testing Scenarios
- [ ] **Login**: client_session_token stored and cookies sent on subsequent requests
- [ ] **Logout**: client_session_token cleared, cookies cleared, redirect works
- [ ] **Session Revocation**: Other device logs out cleanly (no loop)
- [ ] **Session Expiration**: 401 handled gracefully after 30 days
- [ ] **Session Limit**: 429 error shows when >5 devices active
- [ ] **Network Error**: Proper error handling, user sees message

---

## Code Snippets - Copy/Paste Ready

### API Client Setup (api.ts)
```typescript
import axios from 'axios';

let isRedirecting = false;

const apiClient = axios.create({
  baseURL: process.env.REACT_APP_API_URL,
  withCredentials: true,  // Required for cookie-based auth
});

// Handle 401 errors ONCE
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && !isRedirecting) {
      isRedirecting = true;
      localStorage.removeItem('client_session_token');
      setTimeout(() => {
        window.location.href = '/login?message=Session expired';
      }, 100);
    }
    return Promise.reject(error);
  }
);

export default apiClient;
```

### React Query Setup (App.tsx)
```typescript
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {
        if (error?.response?.status === 401) return false;
        if (error?.response?.status >= 400 && error?.response?.status < 500) return false;
        return failureCount < 3;
      },
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      staleTime: 5 * 60 * 1000,
    },
  },
});
```

### Login Handler (auth.ts)
```typescript
async function login(email: string, password: string) {
  const response = await apiClient.post('/api/auth/login', { email, password });
  const { client_session_token, user } = response.data;
  
  if (client_session_token) {
    localStorage.setItem('client_session_token', client_session_token);
    console.log('Session created successfully');
  } else {
    console.error('No client_session_token in login response!');
  }
  
  return { client_session_token, user };
}
```

### Logout Handler (auth.ts)
```typescript
async function logout() {
  try {
    await apiClient.post('/api/auth/logout');
  } catch (error) {
    console.error('Logout request failed:', error);
  } finally {
    // Always clear local state, even if request fails
    localStorage.removeItem('client_session_token');
    window.location.href = '/login';
  }
}
```

### Revoke Other Device (sessions.ts)
```typescript
async function revokeSession(targetSessionId: string) {
  await apiClient.delete(`/api/auth/sessions/${targetSessionId}`);
  
  console.log('Revoked session:', targetSessionId);
  // Target device will get 401 on next request
}
```

---

## Additional Resources

- **Backend Source**: `handlers/auth_handlers.py`
- **API Routes**: `api/auth_routes.py`
- **Session Service**: `services/redis/sessions.py`
- **Session Limits**: Max 5 devices per user, 30-day expiration
- **Postman Collection**: `postman/Quizify_Auth_API.postman_collection.json`
- **Architecture Doc**: `docs/redis/REDIS_COMPLETE_ARCHITECTURE.md`

---

## Support

For questions or issues:
1. Check backend logs in Railway dashboard
2. Review this guide's troubleshooting section
3. Test with Postman collection to isolate frontend vs backend issues
4. Check Redis keys directly in Railway Redis dashboard
5. Verify cookies are sent in Network tab → Request Headers → Cookie
6. Check localStorage in DevTools → Application → Local Storage

---

**Last Updated**: January 2026  
**Backend Version**: Cookie-only authentication (Production)  
**Architecture**: 100% cookie-based auth, no session headers required
