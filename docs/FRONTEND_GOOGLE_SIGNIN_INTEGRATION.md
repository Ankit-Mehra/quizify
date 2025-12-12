# Frontend Integration: Google Sign-In OAuth

This guide covers the frontend implementation for Google Sign-In authentication. The backend handles all OAuth flows - the frontend only needs to initiate the flow and handle callbacks.

## Overview

```
┌─────────────┐        ┌─────────────┐        ┌─────────────┐
│   Frontend  │        │   Backend   │        │   Google    │
└──────┬──────┘        └──────┬──────┘        └──────┬──────┘
       │                      │                      │
       │  GET /google/signin  │                      │
       │─────────────────────>│                      │
       │                      │                      │
       │  { auth_url }        │                      │
       │<─────────────────────│                      │
       │                      │                      │
       │  Redirect to Google  │                      │
       │─────────────────────────────────────────────>│
       │                      │                      │
       │                      │    Callback with code│
       │<─────────────────────────────────────────────│
       │                      │                      │
       │  GET /callback?code= │                      │
       │─────────────────────>│                      │
       │                      │  Exchange code       │
       │                      │─────────────────────>│
       │                      │  Tokens              │
       │                      │<─────────────────────│
       │                      │                      │
       │  Set cookies + redirect                     │
       │<─────────────────────│                      │
       │                      │                      │
```

## API Endpoints

### 1. Initiate Google Sign-In

**Endpoint**: `GET /api/auth/google/signin`

**Query Parameters**:
- `redirect_url` (optional): Where to redirect after successful sign-in. Defaults to `FRONTEND_URL`.

**Response**:
```json
{
  "auth_url": "https://accounts.google.com/o/oauth2/v2/auth?..."
}
```

> **Note**: The `state` parameter is encoded in the auth_url and managed internally by the backend. Frontend doesn't need to handle it separately.

### 2. OAuth Callback (handled automatically)

**Endpoint**: `GET /api/auth/google/signin/callback`

This endpoint is called by Google after user authorizes. The backend:
1. Exchanges the authorization code for tokens
2. Creates/updates user in Supabase
3. Sets HTTP-only cookies (`access_token`, `refresh_token`)
4. Redirects to the frontend with status

**Redirect URL**: 
- Success: `{redirect_url}?login=success&provider=google`
- New user: `{redirect_url}?login=success&provider=google&new_user=true`
- Error: `{redirect_url}?error=oauth_error&message=...`

> The `redirect_url` is either the one passed to `/google/signin` or defaults to `FRONTEND_URL`.

### 3. Token-based Sign-In (alternative for Google Sign-In button)

**Endpoint**: `POST /api/auth/google/signin/token`

**Request Body**:
```json
{
  "id_token": "google-id-token-from-gsi-button"
}
```

> **Note**: This endpoint does not redirect. It returns tokens directly in the response body.

**Response**:
```json
{
  "message": "Google Sign-In successful",
  "user_id": "uuid",
  "email": "user@gmail.com",
  "is_new_user": false,
  "access_token": "eyJ...",   // Only in dev/test mode
  "refresh_token": "..."      // Only in dev/test mode
}
```

> **Note**: `access_token` and `refresh_token` are only included in development/test mode. In production, tokens are only available via HttpOnly cookies.

---

## React Implementation

### Option 1: Redirect Flow (Recommended)

This is the simplest approach - redirect user to backend, which handles everything.

```tsx
// hooks/useGoogleSignIn.ts
import { useState } from 'react';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export function useGoogleSignIn() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const signInWithGoogle = async (redirectUrl?: string) => {
    setIsLoading(true);
    setError(null);

    try {
      // Build URL with optional redirect
      const params = new URLSearchParams();
      if (redirectUrl) {
        params.set('redirect_url', redirectUrl);
      }

      const url = `${API_BASE_URL}/api/auth/google/signin${params.toString() ? '?' + params.toString() : ''}`;
      
      // Fetch the OAuth URL from backend
      const response = await fetch(url, {
        credentials: 'include', // Include cookies
      });

      if (!response.ok) {
        throw new Error('Failed to initiate Google Sign-In');
      }

      const data = await response.json();

      // Redirect to Google OAuth
      // Note: CSRF state is managed internally by the backend
      window.location.href = data.auth_url;

    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-in failed');
      setIsLoading(false);
    }
  };

  return { signInWithGoogle, isLoading, error };
}
```

```tsx
// components/GoogleSignInButton.tsx
import { useGoogleSignIn } from '@/hooks/useGoogleSignIn';
import { Button } from '@/components/ui/button';

interface GoogleSignInButtonProps {
  redirectUrl?: string;
  className?: string;
}

export function GoogleSignInButton({ redirectUrl, className }: GoogleSignInButtonProps) {
  const { signInWithGoogle, isLoading, error } = useGoogleSignIn();

  return (
    <div className={className}>
      <Button
        onClick={() => signInWithGoogle(redirectUrl)}
        disabled={isLoading}
        variant="outline"
        className="w-full flex items-center justify-center gap-2"
      >
        {isLoading ? (
          <span className="animate-spin">⏳</span>
        ) : (
          <GoogleIcon className="w-5 h-5" />
        )}
        {isLoading ? 'Redirecting...' : 'Continue with Google'}
      </Button>
      {error && (
        <p className="text-sm text-red-500 mt-2">{error}</p>
      )}
    </div>
  );
}

function GoogleIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24">
      <path
        fill="#4285F4"
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
      />
      <path
        fill="#34A853"
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
      />
      <path
        fill="#FBBC05"
        d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
      />
      <path
        fill="#EA4335"
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
      />
    </svg>
  );
}
```

### Option 2: Google Sign-In Button (One Tap / GSI)

If you want to use Google's official Sign-In button with their SDK:

```tsx
// hooks/useGoogleOneTap.ts
import { useEffect, useCallback } from 'react';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;

interface GoogleCredentialResponse {
  credential: string;
  select_by: string;
}

export function useGoogleOneTap(onSuccess?: (user: any) => void) {
  const handleCredentialResponse = useCallback(async (response: GoogleCredentialResponse) => {
    try {
      // Send the ID token to our backend
      const result = await fetch(`${API_BASE_URL}/api/auth/google/signin/token`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({
          id_token: response.credential,
        }),
      });

      if (!result.ok) {
        throw new Error('Token exchange failed');
      }

      const data = await result.json();
      
      // SECURITY: Do NOT store tokens in localStorage (XSS risk)
      // The backend sets HttpOnly cookies automatically - just use credentials: 'include'
      // for subsequent requests to send the auth cookies
      
      if (onSuccess) {
        onSuccess(data);
      }

    } catch (error) {
      console.error('Google Sign-In failed:', error);
    }
  }, [onSuccess]);

  useEffect(() => {
    // Load Google Identity Services script
    const script = document.createElement('script');
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    script.defer = true;
    document.body.appendChild(script);

    script.onload = () => {
      if (window.google) {
        window.google.accounts.id.initialize({
          client_id: GOOGLE_CLIENT_ID,
          callback: handleCredentialResponse,
          auto_select: false,
          cancel_on_tap_outside: true,
        });

        // Optionally show One Tap prompt
        window.google.accounts.id.prompt();
      }
    };

    return () => {
      document.body.removeChild(script);
    };
  }, [handleCredentialResponse]);
}

// TypeScript types for Google Identity Services
declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: any) => void;
          prompt: (callback?: (notification: any) => void) => void;
          renderButton: (element: HTMLElement, config: any) => void;
          disableAutoSelect: () => void;
        };
      };
    };
  }
}
```

```tsx
// components/GoogleOneTapSignIn.tsx
import { useEffect, useRef } from 'react';
import { useGoogleOneTap } from '@/hooks/useGoogleOneTap';
import { useNavigate } from 'react-router-dom';

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;

export function GoogleOneTapSignIn() {
  const buttonRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  useGoogleOneTap((user) => {
    // Handle successful sign-in
    console.log('Signed in as:', user.email);
    navigate('/dashboard');
  });

  useEffect(() => {
    // Render the Google Sign-In button
    if (window.google && buttonRef.current) {
      window.google.accounts.id.renderButton(buttonRef.current, {
        type: 'standard',
        theme: 'outline',
        size: 'large',
        text: 'continue_with',
        shape: 'rectangular',
        logo_alignment: 'left',
        width: 280,
      });
    }
  }, []);

  return <div ref={buttonRef} className="google-signin-button" />;
}
```

---

## Callback Page

Create a callback page to handle the OAuth redirect:

```tsx
// pages/AuthCallback.tsx
import { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { Loader2, CheckCircle, XCircle } from 'lucide-react';

export function AuthCallbackPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading');
  const [message, setMessage] = useState('');

  useEffect(() => {
    const loginStatus = searchParams.get('login');
    const provider = searchParams.get('provider');
    const errorMessage = searchParams.get('message');

    // Handle Google OAuth callback
    if (provider === 'google') {
      if (loginStatus === 'success') {
        setStatus('success');
        setMessage('Successfully signed in with Google!');
        
        // Redirect to dashboard after a brief delay
        setTimeout(() => {
          navigate('/dashboard', { replace: true });
        }, 1500);

      } else if (loginStatus === 'error') {
        setStatus('error');
        setMessage(errorMessage || 'Sign-in failed. Please try again.');
      }
    } else {
      // No recognized params - might be a direct visit
      navigate('/', { replace: true });
    }
  }, [searchParams, navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="text-center p-8 bg-white rounded-lg shadow-md max-w-md">
        {status === 'loading' && (
          <>
            <Loader2 className="w-12 h-12 mx-auto text-blue-500 animate-spin" />
            <h2 className="mt-4 text-xl font-semibold text-gray-700">
              Completing sign-in...
            </h2>
          </>
        )}

        {status === 'success' && (
          <>
            <CheckCircle className="w-12 h-12 mx-auto text-green-500" />
            <h2 className="mt-4 text-xl font-semibold text-gray-700">
              {message}
            </h2>
            <p className="mt-2 text-gray-500">Redirecting to dashboard...</p>
          </>
        )}

        {status === 'error' && (
          <>
            <XCircle className="w-12 h-12 mx-auto text-red-500" />
            <h2 className="mt-4 text-xl font-semibold text-gray-700">
              Sign-in Failed
            </h2>
            <p className="mt-2 text-gray-500">{message}</p>
            <button
              onClick={() => navigate('/login')}
              className="mt-4 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
            >
              Try Again
            </button>
          </>
        )}
      </div>
    </div>
  );
}
```

---

## Login Page Integration

```tsx
// pages/Login.tsx
import { useState } from 'react';
import { GoogleSignInButton } from '@/components/GoogleSignInButton';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Separator } from '@/components/ui/separator';

export function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleEmailLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    // ... email/password login logic
    setIsLoading(false);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4">
      <div className="max-w-md w-full space-y-8">
        <div className="text-center">
          <h1 className="text-3xl font-bold text-gray-900">Welcome to Quizify</h1>
          <p className="mt-2 text-gray-600">Sign in to your account</p>
        </div>

        <div className="bg-white p-8 rounded-lg shadow-md space-y-6">
          {/* Google Sign-In */}
          <GoogleSignInButton 
            redirectUrl="/dashboard"
            className="w-full"
          />

          <div className="relative">
            <Separator />
            <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 bg-white px-2 text-sm text-gray-500">
              or continue with email
            </span>
          </div>

          {/* Email/Password Form */}
          <form onSubmit={handleEmailLogin} className="space-y-4">
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-gray-700">
                Email
              </label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                required
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-gray-700">
                Password
              </label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
              />
            </div>

            <Button type="submit" className="w-full" disabled={isLoading}>
              {isLoading ? 'Signing in...' : 'Sign in'}
            </Button>
          </form>

          <p className="text-center text-sm text-gray-600">
            Don't have an account?{' '}
            <a href="/signup" className="text-blue-600 hover:underline">
              Sign up
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
```

---

## Router Setup

```tsx
// App.tsx or routes.tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { LoginPage } from '@/pages/Login';
import { AuthCallbackPage } from '@/pages/AuthCallback';
import { DashboardPage } from '@/pages/Dashboard';
import { ProtectedRoute } from '@/components/ProtectedRoute';

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/auth/callback" element={<AuthCallbackPage />} />
        
        {/* Protected routes */}
        <Route element={<ProtectedRoute />}>
          <Route path="/dashboard" element={<DashboardPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
```

---

## Auth Context (Optional)

```tsx
// contexts/AuthContext.tsx
import { createContext, useContext, useState, useEffect, ReactNode } from 'react';

interface User {
  id: string;
  email: string;
  display_name: string | null;
  avatar_url: string | null;
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  signOut: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refreshUser = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/me`, {
        credentials: 'include',
      });

      if (response.ok) {
        const data = await response.json();
        setUser(data.user);
      } else {
        setUser(null);
      }
    } catch (error) {
      console.error('Failed to fetch user:', error);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  };

  const signOut = async () => {
    try {
      await fetch(`${API_BASE_URL}/api/auth/logout`, {
        method: 'POST',
        credentials: 'include',
      });
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      setUser(null);
      window.location.href = '/login';
    }
  };

  useEffect(() => {
    refreshUser();
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: !!user,
        signOut,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
```

---

## User Avatar Display

```tsx
// components/UserAvatar.tsx
import { useAuth } from '@/contexts/AuthContext';

interface UserAvatarProps {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

const sizeClasses = {
  sm: 'w-8 h-8 text-sm',
  md: 'w-10 h-10 text-base',
  lg: 'w-12 h-12 text-lg',
};

export function UserAvatar({ size = 'md', className = '' }: UserAvatarProps) {
  const { user } = useAuth();

  if (!user) return null;

  const initials = user.display_name
    ? user.display_name
        .split(' ')
        .map((n) => n[0])
        .join('')
        .toUpperCase()
        .slice(0, 2)
    : user.email[0].toUpperCase();

  return (
    <div className={`${sizeClasses[size]} ${className}`}>
      {user.avatar_url ? (
        <img
          src={user.avatar_url}
          alt={user.display_name || user.email}
          className="w-full h-full rounded-full object-cover"
          referrerPolicy="no-referrer"
        />
      ) : (
        <div className="w-full h-full rounded-full bg-blue-500 text-white flex items-center justify-center font-medium">
          {initials}
        </div>
      )}
    </div>
  );
}
```

---

## Environment Variables

Add these to your frontend `.env` file:

```bash
# .env
VITE_API_URL=http://localhost:8000
VITE_GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
```

---

## Security Considerations

1. **CSRF Protection**: The OAuth flow uses a `state` parameter that should be validated on callback
2. **Token Storage**: Access tokens are stored in HTTP-only cookies by the backend (most secure)
3. **Redirect Validation**: Backend validates redirect URLs against allowed domains
4. **ID Token Validation**: Backend verifies Google ID tokens before creating sessions

---

## Avatar Sync

The backend **automatically syncs the user's Google profile picture** during sign-in. No frontend action is required.

### How It Works

1. When a user signs in with Google, Supabase receives their profile metadata including:
   - `avatar_url` or `picture` (Google profile photo URL)
   - `full_name` or `name` (display name)

2. A database trigger (`handle_new_user`) automatically extracts this data and stores it in the `profiles` table:
   ```sql
   -- Automatically executed on new user signup
   INSERT INTO profiles (id, avatar_url, display_name, ...)
   VALUES (user_id, google_avatar_url, google_name, ...)
   ```

3. The avatar URL is then available via the `/api/auth/me` endpoint in the `avatar_url` field.

### Accessing the Avatar

The avatar is returned in the user object from `/api/auth/me`:

```json
{
  "user_id": "uuid",
  "email": "user@gmail.com",
  "display_name": "John Doe",
  "avatar_url": "https://lh3.googleusercontent.com/a/...",
  "account_tier": "free",
  ...
}
```

### Avatar URL Characteristics

- **Domain**: Google avatars come from `lh3.googleusercontent.com`
- **HTTPS**: Always served over HTTPS
- **Referrer Policy**: Use `referrerPolicy="no-referrer"` on `<img>` tags to avoid 403 errors
- **Persistence**: Stored in your database, so it persists even if user changes Google photo (until next sign-in)

### Updating Avatar on Subsequent Sign-ins

When an existing user signs in again with Google:
- If their Google avatar has changed, the trigger updates `profiles.avatar_url`
- The `ON CONFLICT ... DO UPDATE` clause handles this automatically:
  ```sql
  ON CONFLICT (id) DO UPDATE SET
    avatar_url = COALESCE(EXCLUDED.avatar_url, profiles.avatar_url)
  ```

### Fallback for No Avatar

If a user signed up via email/password (no OAuth), `avatar_url` will be `null`. The `UserAvatar` component handles this by showing initials:

```tsx
{user.avatar_url ? (
  <img src={user.avatar_url} ... />
) : (
  <div className="initials-avatar">{initials}</div>
)}
```

---

## Testing Checklist

- [ ] Click "Continue with Google" initiates OAuth flow
- [ ] User is redirected to Google consent screen
- [ ] After consent, user is redirected back to `/auth/callback`
- [ ] Success callback shows success message and redirects to dashboard
- [ ] Error callback shows error message with retry option
- [ ] User avatar displays correctly after sign-in
- [ ] Auth state persists across page refreshes
- [ ] Sign out clears session and redirects to login
