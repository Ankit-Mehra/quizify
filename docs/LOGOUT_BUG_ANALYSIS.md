# Logout Bug Analysis: Wrong Device Logged Out

**Date**: November 14, 2025  
**Status**: Root Cause Identified - Frontend Implementation Issue  
**Severity**: Critical UX Bug

---

## Problem Statement

User reported that clicking "Logout Device" on the Android session in the session management UI resulted in the desktop browser being logged out instead, while the mobile device remained logged in.

**User Flow**:
1. User logged in on Desktop (Mac Chrome)
2. User logged in on Mobile (Android Chrome)
3. User viewed session list from Desktop (shows both devices)
4. User clicked "Logout Device" button next to Android session
5. **Expected**: Android session deleted, desktop still logged in
6. **Actual**: Desktop logged out (cookies cleared), Android still logged in

---

## Root Cause Analysis

### Backend Investigation

The backend provides **two different endpoints** for logout operations:

#### 1. `POST /api/auth/logout` - Logout Current Device
**Purpose**: Logout the device making the request  
**Behavior**:
- Deletes session from Redis (if session_id provided)
- **Clears HTTP-only cookies** (access_token, refresh_token) on response
- Intended for main "Logout" button

**Code** (handlers/auth_handlers.py:269-315):
```python
async def logout(
    request: Request,
    response: Response,
    user_id: str = Depends(get_current_user_id),
    session_id: Optional[str] = Query(None, alias="session_id")
):
    """Logout current device."""
    # Delete Redis session
    if session_id:
        session_service.logout(session_id)
    
    # ⚠️ CLEARS COOKIES ON RESPONSE - Affects current browser!
    response.delete_cookie(key="access_token", ...)
    response.delete_cookie(key="refresh_token", ...)
```

#### 2. `DELETE /api/auth/sessions/{session_id}` - Revoke Specific Session
**Purpose**: Revoke a specific session **without affecting current device**  
**Behavior**:
- Deletes target session from Redis
- **Does NOT clear cookies** on current device
- Intended for "Logout Device" buttons in session management UI

**Code** (handlers/auth_handlers.py:808-873):
```python
async def revoke_session(
    session_id_to_revoke: str,
    request: Request,
    user_id: str = Depends(get_current_user_id)
):
    """Revoke a specific session by ID."""
    # Security check: Verify session belongs to user
    session_info = await session_service.validate_session(session_id_to_revoke)
    if session_info.user_id != user_id:
        raise HTTPException(403, detail="You can only revoke your own sessions")
    
    # Delete ONLY the target session
    await session_service.logout(session_id_to_revoke)
    
    # ✅ NO cookie manipulation - current device unaffected
    return {"message": "Session revoked successfully"}
```

---

## The Bug

**Frontend is calling the WRONG endpoint**:
- When clicking "Logout Device" on Android session from Desktop
- Frontend calls: `POST /api/auth/logout?session_id=android_session_id`
- Backend response includes `Set-Cookie` headers that clear Desktop's cookies
- Result: Desktop browser loses authentication, Android unaffected

**What should happen**:
- Frontend should call: `DELETE /api/auth/sessions/android_session_id`
- Backend deletes Android session from Redis only
- No cookie manipulation on response
- Result: Android logged out (401 on next request), Desktop unaffected

---

## Why This Happened

1. **API Design**: Two similar but functionally different endpoints
2. **Naming Confusion**: Both endpoints "logout" sessions, but with different side effects
3. **Cookie Behavior**: HTTP-only cookies automatically sent/cleared by browser, not controllable by frontend
4. **Missing Documentation**: Frontend developer may not have known about `DELETE /sessions/{id}` endpoint

---

## Backend Changes Made

### Fix #1: Added `is_current` Field (PR #79, commit 49251af)

**Purpose**: Help frontend identify which session is the current device

**Change** (handlers/auth_handlers.py:785):
```python
async def get_active_sessions(request: Request, ...):
    # Get current session from request state
    current_session_id = getattr(request.state, "session_id", None)
    
    return [
        {
            "session_id": session.session_id,
            "device_type": session.device_type,
            # ... other fields ...
            "is_current": session.session_id == current_session_id  # ← NEW
        }
        for session in sessions
    ]
```

**API Response** (now includes is_current):
```json
[
  {
    "session_id": "sess_desktop",
    "device_type": "browser",
    "is_current": true  // ← This device (making the request)
  },
  {
    "session_id": "sess_android",
    "device_type": "mobile",
    "is_current": false  // ← Other device
  }
]
```

**Benefit**: Frontend can now:
1. Show "(This Device)" badge on current session
2. Disable "Logout Device" button for current session
3. Verify which endpoint to call based on `is_current` flag

---

### Backend Endpoints Summary

| Endpoint | Method | Use Case | Clears Cookies? | Intended For |
|----------|--------|----------|-----------------|--------------|
| `/api/auth/logout` | POST | Logout current device | ✅ YES | Main "Logout" button |
| `/api/auth/sessions/{id}` | DELETE | Revoke other device | ❌ NO | "Logout Device" in session list |
| `/api/auth/logout-all-devices` | POST | Security action | ✅ YES | "Logout All" button |

---

## Frontend Fix Required

### ❌ Current (Incorrect) Implementation

```javascript
// BAD: Uses /logout for all devices
async function logoutDevice(sessionId) {
  await fetch(`/api/auth/logout?session_id=${sessionId}`, {
    method: 'POST',
    credentials: 'include'
  });
  // Problem: Clears cookies on current browser!
}
```

### ✅ Correct Implementation

```javascript
// GOOD: Uses correct endpoint based on is_current flag
async function logoutDevice(session) {
  if (session.is_current) {
    // Logout THIS device - use /logout
    await fetch('/api/auth/logout', {
      method: 'POST',
      credentials: 'include'
    });
    localStorage.removeItem('session_id');
    window.location.href = '/login';
  } else {
    // Logout OTHER device - use DELETE /sessions/{id}
    await fetch(`/api/auth/sessions/${session.session_id}`, {
      method: 'DELETE',
      headers: {
        'X-Session-ID': localStorage.getItem('session_id')
      },
      credentials: 'include'
    });
    // Refresh session list to remove deleted session
    await loadSessions();
  }
}
```

### Better UX: Separate Buttons

```javascript
// Even better: Different buttons with clear labels
function SessionCard({ session }) {
  const currentSessionId = localStorage.getItem('session_id');
  
  return (
    <div>
      <h4>{session.device_type}</h4>
      {session.is_current && <span>(This Device)</span>}
      
      {session.is_current ? (
        // For current device: Main logout
        <button onClick={logoutCurrentDevice}>
          Logout
        </button>
      ) : (
        // For other devices: Revoke session
        <button onClick={() => revokeSession(session.session_id)}>
          Remove Device
        </button>
      )}
    </div>
  );
}

async function revokeSession(sessionId) {
  await fetch(`/api/auth/sessions/${sessionId}`, {
    method: 'DELETE',
    headers: {
      'X-Session-ID': localStorage.getItem('session_id')
    },
    credentials: 'include'
  });
}

async function logoutCurrentDevice() {
  await fetch('/api/auth/logout', {
    method: 'POST',
    credentials: 'include'
  });
  localStorage.removeItem('session_id');
  window.location.href = '/login';
}
```

---

## Testing Verification

### Test Scenario 1: Revoke Other Device

1. Login on Desktop Chrome → session A created
2. Login on Mobile Safari → session B created
3. From Desktop, call `DELETE /api/auth/sessions/{session_B_id}`
4. **Expected Results**:
   - Backend: Session B deleted from Redis
   - Desktop: Still logged in (cookies intact)
   - Mobile: Next request returns 401 Unauthorized
   - Session list: Only shows session A

### Test Scenario 2: Logout Current Device

1. Login on Desktop Chrome → session A created
2. Login on Mobile Safari → session B created
3. From Desktop, call `POST /api/auth/logout`
4. **Expected Results**:
   - Backend: Session A deleted from Redis
   - Desktop: Cookies cleared, redirected to login
   - Mobile: Still logged in (session B unaffected)
   - Session list (from Mobile): Only shows session B

---

## Backend Security Verification

**Already Implemented** (handlers/auth_handlers.py:841-852):

```python
# SECURITY: Verify session belongs to user before revoking
session_info = await session_service.validate_session(session_id_to_revoke)

if session_info.user_id != user_id:
    logger.warning(
        "User %s attempted to revoke session belonging to %s",
        _short_user_id(user_id),
        _short_user_id(session_info.user_id),
    )
    raise HTTPException(
        status_code=403,
        detail="You can only revoke your own sessions"
    )
```

**Protection**: User A cannot revoke User B's sessions, even if they know the session_id.

---

## Resolution Status

### ✅ Backend Changes Complete (PR #79)

1. **CORS Fix** (commit 15bf8a2): Added `X-Session-ID` to allowed headers
2. **is_current Field** (commit 49251af): Added device identification flag
3. **Documentation**: Created comprehensive frontend guide

### ⏳ Frontend Changes Required

**The frontend must**:
1. Use `DELETE /api/auth/sessions/{id}` for "Logout Device" buttons
2. Reserve `POST /api/auth/logout` for main "Logout" action
3. Use `is_current` flag to show appropriate UI
4. Test multi-device logout scenarios

**Documentation Provided**:
- `docs/FRONTEND_SESSION_MANAGEMENT_GUIDE.md` (complete implementation guide)
- Includes code examples, pitfalls, and testing checklist

---

## Key Takeaways

1. **Cookie Side Effects**: Endpoints that manipulate cookies affect the current browser, not target sessions
2. **Endpoint Design**: Clear separation between "logout self" vs "revoke other" operations
3. **API Documentation**: Critical to document behavioral differences, not just response schemas
4. **Testing Requirements**: Multi-device testing essential for session management features
5. **Frontend Guidance**: Backend must provide clear documentation for complex features

---

## Next Steps

1. ✅ Backend changes complete and ready for production
2. ⏳ Frontend team implements correct endpoint usage
3. ⏳ Test with 2+ devices before production deployment
4. ⏳ Verify cookie behavior in DevTools Network tab
5. ⏳ Confirm session isolation (User A cannot affect User B)

---

**References**:
- PR #79: https://github.com/Ankit-Mehra/quizify/pull/79
- Frontend Guide: `docs/FRONTEND_SESSION_MANAGEMENT_GUIDE.md`
- API Routes: `api/auth_routes.py`
- Auth Handlers: `handlers/auth_handlers.py`
