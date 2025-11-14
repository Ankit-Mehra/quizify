# Frontend 401 Retry Loop Fix

**Status**: 🚨 CRITICAL - Production Issue  
**Date**: November 14, 2025  
**Issue**: X-Session-ID header not being sent + React Query retrying failed 401 requests indefinitely  

## Problem Summary

After deploying PR #81 (session management enforcement), the frontend is experiencing an infinite retry loop. **Two separate issues** are causing this:

### Issue #1: X-Session-ID Header Missing (PRIMARY ISSUE)
The backend returns `session_id` in login response body, but **frontend is not including it in subsequent requests**. This means:
- Login succeeds → `session_id` returned in response
- Frontend stores `session_id` in localStorage 
- BUT: API client is NOT reading from localStorage and adding `X-Session-ID` header
- Result: Every authenticated request returns 401

### Issue #2: React Query Retrying 401s (AMPLIFICATION ISSUE)
Once requests start failing with 401, React Query's default retry configuration causes infinite loops:
- Backend correctly returns 401 (missing X-Session-ID header)
- React Query retries the same request 3 times
- Multiple components using `useQuery` all retry simultaneously
- Result: 20+ requests per second, application unusable

## Root Cause Analysis

### What's Happening
1. User logs in successfully
2. Backend returns `session_id` in response: `{ "session_id": "sess_abc123...", ... }`
3. Frontend stores it: `localStorage.setItem('session_id', data.session_id)`
4. User navigates to dashboard
5. Dashboard components fetch data: `/api/auth/me`, `/api/quiz/my-quizzes`, `/api/submissions`
6. **BUT**: Requests are missing `X-Session-ID` header
7. Backend returns 401: "Session ID required"
8. React Query retries each request 3 times
9. Infinite loop: New queries start → Fail → Retry → Repeat

### The Missing Piece
Your API client is **NOT injecting the X-Session-ID header** into requests, even though `session_id` exists in localStorage.

**Verify this**:
```javascript
// In browser console after login:
console.log('session_id in storage:', localStorage.getItem('session_id'));
// Should show: "sess_abc123..."

// Then check Network tab → Any API request → Headers
// Request Headers should include: X-Session-ID: sess_abc123...
// If missing → API client not configured correctly
```

---

## Diagnostic Evidence

Production logs show **4 endpoints being called repeatedly every second** (all missing X-Session-ID header):

```
Session ID missing for user 760602fe... on /api/auth/me - returning 401
Session ID missing for user 760602fe... on /api/quiz/my-quizzes - returning 401  
Session ID missing for user 760602fe... on /api/submissions - returning 401
Session ID missing for user 760602fe... on /api/auth/me - returning 401
```

**Pattern**: All 4 requests fail with 401 → React Query retries each one 3 times → Error handlers trigger → New queries start → Infinite loop

## Root Cause

React Query/TanStack Query's default configuration:
- **Default retry count**: 3 attempts with exponential backoff
- **Retry behavior**: Retries happen BEFORE error handlers can clear localStorage
- **Multiple components**: Using `useQuery` hooks that all retry simultaneously
- **Result**: 20+ requests per second, application unusable

## Required Fixes

### FIX #1: Add X-Session-ID Header to All Requests (CRITICAL - MUST DO FIRST)

**Problem**: API client is not reading `session_id` from localStorage and including it in request headers.

**Location**: Your axios/fetch API client configuration (likely `api.ts` or `apiClient.ts`)

**Current (BROKEN)**:
```typescript
// Missing X-Session-ID header injection
const apiClient = axios.create({
  baseURL: process.env.REACT_APP_API_URL,
  withCredentials: true,
});
```

**Fix (REQUIRED)**:
```typescript
import axios from 'axios';

const apiClient = axios.create({
  baseURL: process.env.REACT_APP_API_URL,
  withCredentials: true, // Required for cookies
});

// Add request interceptor to inject X-Session-ID header
apiClient.interceptors.request.use(
  (config) => {
    // Get session_id from localStorage
    const sessionId = localStorage.getItem('session_id');
    
    if (sessionId) {
      // Add X-Session-ID header to EVERY request
      config.headers['X-Session-ID'] = sessionId;
      console.log('Added X-Session-ID header:', sessionId.substring(0, 16) + '...');
    } else {
      console.warn('No session_id in localStorage - request will fail with 401');
    }
    
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

export default apiClient;
```

**Verification**:
1. Open DevTools → Network tab
2. Make any authenticated request (GET /api/auth/me)
3. Click on the request → Headers tab
4. **Look for**: `X-Session-ID: sess_...` in Request Headers
5. **Should see**: Your session ID in the header
6. **If missing**: The interceptor is not working

---

### FIX #2: Disable Retry on 401 Errors (REQUIRED - DO SECOND)

Modify your QueryClient configuration to prevent retries on authentication errors:

```typescript
// In App.tsx or main.tsx where QueryClient is initialized

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error: any) => {
        // Don't retry on authentication errors
        if (error?.response?.status === 401) {
          console.log('401 detected - not retrying');
          return false;
        }
        
        // Don't retry on other client errors (400-499)
        if (error?.response?.status >= 400 && error?.response?.status < 500) {
          return false;
        }
        
        // Retry server errors (500+) up to 3 times
        return failureCount < 3;
      },
      
      // Increase stale time to reduce polling frequency
      staleTime: 5 * 60 * 1000, // 5 minutes
      
      // Disable automatic refetch on window focus during auth issues
      refetchOnWindowFocus: false,
      
      // Disable background refetch during auth issues  
      refetchOnReconnect: false,
    },
    
    mutations: {
      // Also disable mutation retries on 401
      retry: (failureCount, error: any) => {
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
      {/* Your app components */}
    </QueryClientProvider>
  );
}
```

### FIX #3: Early Interception in Axios (OPTIONAL - ADDITIONAL PROTECTION)

Add this to your axios interceptor to prevent React Query from seeing retryable 401 errors:

```typescript
// In your API client setup file

import axios from 'axios';

const axiosInstance = axios.create({
  baseURL: process.env.REACT_APP_API_URL,
});

axiosInstance.interceptors.response.use(
  (response) => response,
  (error) => {
    // Handle 401 errors immediately, before React Query processes them
    if (error.response?.status === 401) {
      console.log('401 detected - clearing auth state');
      
      // Clear storage immediately
      localStorage.removeItem('session_id');
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      
      // Mark error as already handled to prevent retries
      error.config._authErrorHandled = true;
      
      // Redirect to login
      window.location.href = '/login';
      
      // Return rejected promise with non-retryable error
      return Promise.reject(new Error('Authentication required'));
    }
    
    return Promise.reject(error);
  }
);

export default axiosInstance;
```

### FIX #4: Component-Level Guards (NOT RECOMMENDED - TOO MANY PLACES)

For specific components making these 4 API calls, add retry prevention:

```typescript
// Example: User profile query
const { data: user, error } = useQuery({
  queryKey: ['user', 'me'],
  queryFn: () => api.get('/api/auth/me'),
  retry: false, // Disable retry for this specific query
  refetchOnWindowFocus: false,
  refetchOnReconnect: false,
});

// Example: Quiz list query  
const { data: quizzes } = useQuery({
  queryKey: ['quizzes', 'my-quizzes'],
  queryFn: () => api.get('/api/quiz/my-quizzes'),
  retry: false, // Disable retry for this specific query
  enabled: !!user, // Only fetch if user is authenticated
});

// Example: Submissions query
const { data: submissions } = useQuery({
  queryKey: ['submissions'],
  queryFn: () => api.get('/api/submissions'),
  retry: false, // Disable retry for this specific query
  enabled: !!user, // Only fetch if user is authenticated
});
```

## Components Making the Calls

Based on the endpoint pattern, check these likely components:

1. **`/api/auth/me`**: User profile component (header, sidebar, dashboard)
2. **`/api/quiz/my-quizzes`**: Quiz list page/component
3. **`/api/submissions`**: Submissions dashboard/list component

Search your codebase for:
```bash
grep -r "useQuery.*auth/me" src/
grep -r "useQuery.*my-quizzes" src/
grep -r "useQuery.*submissions" src/
```

## Verification Steps

After implementing the fix:

1. **Clear browser cache completely** (Cmd+Shift+Delete on Mac)
2. **Clear localStorage**: Open DevTools → Application → Local Storage → Clear All
3. **Hard reload**: Cmd+Shift+R (Mac) or Ctrl+Shift+R (Windows)
4. **Test scenarios**:
   - ✅ Fresh login → Should NOT see 401 loops
   - ✅ Invalid session → Single 401 → Redirect to login
   - ✅ Expired session → Single 401 → Redirect to login
   - ✅ Multiple tabs → No retry storms

5. **Monitor Network tab**: 
   - Look for repeated 401 responses
   - Should see 1 request → 1 response → redirect
   - NOT: 1 request → 3+ retries → redirect

6. **Check browser console**:
   - Should see single "401 detected - clearing auth state" log
   - NOT: Multiple retry logs

## Testing Checklist

- [ ] QueryClient configured with 401 retry prevention
- [ ] Axios interceptor handles 401 immediately
- [ ] All useQuery hooks either inherit global config or have `retry: false`
- [ ] Browser cache cleared before testing
- [ ] localStorage cleared before testing
- [ ] Network tab shows single 401 per endpoint
- [ ] No rapid retry loops visible
- [ ] Smooth redirect to /login on 401
- [ ] Backend logs show significant reduction in 401 errors

## Expected Behavior After Fix

**Before (Current - BROKEN)**:
```
[0.0s] GET /api/auth/me → 401
[0.1s] GET /api/auth/me → 401 (retry 1)
[0.2s] GET /api/quiz/my-quizzes → 401
[0.3s] GET /api/auth/me → 401 (retry 2)
[0.4s] GET /api/submissions → 401
[0.5s] GET /api/quiz/my-quizzes → 401 (retry 1)
... infinite loop ...
```

**After (Expected - FIXED)**:
```
[0.0s] GET /api/auth/me → 401
[0.0s] Axios interceptor clears localStorage
[0.0s] React Query receives non-retryable error
[0.1s] Redirect to /login
[Done] No more requests
```

## Rollback Plan

If the fix causes other issues, you can temporarily disable retry globally:

```typescript
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false, // Disable ALL retries temporarily
    },
  },
});
```

Then re-enable selectively for queries that need retry (e.g., data fetching on slow networks).

## Related Documentation

- [FRONTEND_SESSION_MANAGEMENT_GUIDE.md](./FRONTEND_SESSION_MANAGEMENT_GUIDE.md) - Complete session management implementation guide
- [React Query Error Handling](https://tanstack.com/query/latest/docs/react/guides/query-retries) - Official docs on retry configuration
- [PR #81](https://github.com/Ankit-Mehra/quizify/pull/81) - Backend changes that triggered this issue

## Support

If you need backend assistance:
1. Check backend logs at Railway dashboard
2. Verify X-Session-ID header is being sent (DevTools → Network → Headers)
3. Confirm session_id exists in localStorage
4. Test with Postman to isolate frontend vs backend issues

---

**Priority**: 🚨 CRITICAL - Deploy ASAP  
**Estimated Fix Time**: 15 minutes  
**Testing Time**: 10 minutes  
**Total**: ~25 minutes to resolve production issue
