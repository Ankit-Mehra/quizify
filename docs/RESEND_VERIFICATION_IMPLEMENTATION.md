# Resend Verification Email - Implementation

## ✅ What Was Implemented

### Endpoint
**POST /api/auth/resend-verification**

### Purpose
Allows users to request a new verification email if:
- They didn't receive the original signup email
- The original link expired (24 hours)
- They accidentally deleted the email
- Email went to spam and got auto-deleted

---

## 📋 API Specification

### Request
```http
POST /api/auth/resend-verification
Content-Type: application/json

{
  "email": "user@example.com"
}
```

### Response (Always Success)
```json
{
  "message": "If your email is registered and unverified, we've sent a new verification link.",
  "note": "Check your email inbox (and spam folder). The link expires in 24 hours.",
  "email": "user@example.com"
}
```

### Error Handling
**Always returns 200 with success message**, even if:
- ❌ Email doesn't exist in database
- ✅ Email is already verified
- ⏱️ Rate limit exceeded
- 💥 Supabase API error

**Why?** To prevent email enumeration attacks (attacker can't discover which emails are registered).

---

## 🔄 Complete Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. User tries to log in but gets "Email not verified" error     │
│    OR user can't find original verification email               │
└────────────────────────────┬────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. Frontend shows "Resend verification email" link/button       │
│    User clicks it                                                │
└────────────────────────────┬────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. Frontend shows modal/page asking for email                   │
│    User enters email and submits                                │
└────────────────────────────┬────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. POST /api/auth/resend-verification                           │
│    Body: { "email": "user@example.com" }                        │
└────────────────────────────┬────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. Backend calls supabase.auth.resend()                         │
│    - type: "signup"                                              │
│    - email: user's email                                         │
└────────────────────────────┬────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│ 6. Supabase sends NEW verification email (if user exists)       │
│    Link: https://api.quizify.ca/api/auth/confirm?               │
│          token=new_token&type=signup                             │
│    (Old link becomes invalid)                                    │
└────────────────────────────┬────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│ 7. Backend ALWAYS returns success message                       │
│    Frontend shows: "Check your email for verification link"     │
└────────────────────────────┬────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│ 8. User checks email, clicks new verification link              │
│    → Same flow as original signup verification                  │
│    → Redirect to login with success message                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🎨 Frontend Implementation

### Scenario 1: On Login Page (After Failed Login)

```typescript
// After user tries to log in with unverified email
if (loginError === "Email not verified") {
  return (
    <div className="alert alert-warning">
      <p>Please verify your email before logging in.</p>
      <button onClick={() => resendVerification(email)}>
        Resend verification email
      </button>
    </div>
  );
}

const resendVerification = async (email: string) => {
  const response = await fetch('/api/auth/resend-verification', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email })
  });
  
  const data = await response.json();
  showToast('success', data.message);
};
```

### Scenario 2: Dedicated "Resend Verification" Page

```typescript
// /resend-verification page
export default function ResendVerificationPage() {
  const [email, setEmail] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showSuccess, setShowSuccess] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    
    try {
      const response = await fetch('/api/auth/resend-verification', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      });
      
      const data = await response.json();
      setShowSuccess(true);
      
    } catch (error) {
      showToast('error', 'Failed to send email. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  if (showSuccess) {
    return (
      <div className="success-message">
        <h2>✓ Verification Email Sent</h2>
        <p>If your email is registered, we've sent a new verification link.</p>
        <p>Check your inbox (and spam folder).</p>
        <Link href="/login">Back to Login</Link>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit}>
      <h1>Resend Verification Email</h1>
      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="Enter your email"
        required
      />
      <button type="submit" disabled={isLoading}>
        {isLoading ? 'Sending...' : 'Resend Verification Email'}
      </button>
      <Link href="/login">Back to Login</Link>
    </form>
  );
}
```

### Scenario 3: Add Link to Signup Success Page

```typescript
// After user signs up
export default function SignupSuccessPage() {
  const email = useSearchParams().get('email');
  
  return (
    <div>
      <h1>Check Your Email</h1>
      <p>We've sent a verification link to {email}</p>
      <p>Click the link to verify your account.</p>
      
      <div className="mt-4">
        <p className="text-sm text-gray-600">
          Didn't receive the email?{' '}
          <button 
            onClick={() => resendVerification(email)}
            className="text-blue-600 underline"
          >
            Resend verification email
          </button>
        </p>
      </div>
    </div>
  );
}
```

---

## 🔐 Security Features

### 1. **Email Enumeration Prevention**
- Always returns success, never reveals if email exists
- Prevents attackers from discovering registered emails
- Logs actual status server-side only

### 2. **Rate Limiting** (Recommended to Add)
```python
# Add to handler (future enhancement)
from slowapi import Limiter

@limiter.limit("3/hour")  # Max 3 resend requests per hour per IP
async def resend_verification_email(request: ResendVerificationRequest):
    # ... existing code
```

### 3. **Token Invalidation**
- New verification email invalidates old token
- Only the latest link works
- Prevents confusion from multiple emails

### 4. **Already Verified Handling**
- Supabase silently ignores resend for verified emails
- No error shown to user
- No additional email sent

---

## 🧪 Testing

### Manual Testing
```bash
# 1. Sign up a new user (don't verify yet)
curl -X POST http://localhost:8000/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "TestPass123!",
    "name": "Test User"
  }'

# 2. Request resend verification
curl -X POST http://localhost:8000/api/auth/resend-verification \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com"}'

# Expected: Success message (check email for new link)

# 3. Try with non-existent email (should still return success)
curl -X POST http://localhost:8000/api/auth/resend-verification \
  -H "Content-Type: application/json" \
  -d '{"email": "doesnotexist@example.com"}'

# Expected: Same success message (security feature)

# 4. Try with already verified email
# First verify the email, then try resending
curl -X POST http://localhost:8000/api/auth/resend-verification \
  -H "Content-Type: application/json" \
  -d '{"email": "verified@example.com"}'

# Expected: Success message (no email actually sent)
```

### Edge Cases to Test
- [x] Email doesn't exist → Returns success
- [x] Email exists but unverified → Sends new email
- [x] Email exists and already verified → Returns success (no email sent)
- [x] Invalid email format → Pydantic validation error (422)
- [x] Supabase API error → Still returns success message
- [ ] Rate limiting (if implemented) → 429 after threshold

---

## 📊 When to Use Each Endpoint

| Situation | Endpoint to Use | Authentication Required |
|-----------|----------------|------------------------|
| User forgot password | `POST /forgot-password` | ❌ No |
| User signed up but no email | `POST /resend-verification` | ❌ No |
| User wants to change password (logged in) | `PATCH /change-password` | ✅ Yes |
| User wants to reset forgotten password | `POST /reset-password` | ❌ No (uses recovery token) |
| User wants to change email | `PATCH /update-email` | ✅ Yes |

---

## 🚀 Deployment Checklist

- [x] Schema created (`ResendVerificationRequest`)
- [x] Handler implemented (`resend_verification_email`)
- [x] Route registered (`POST /api/auth/resend-verification`)
- [ ] Frontend "Resend verification" UI implemented
- [ ] Link added to login page error message
- [ ] Link added to signup success page
- [ ] Rate limiting configured (optional but recommended)
- [ ] Test in production environment
- [ ] Monitor logs for abuse patterns

---

## 💡 Future Enhancements

### 1. **Add Rate Limiting**
Prevent abuse by limiting resends per email/IP:
```python
# Max 3 resends per email per hour
# Max 10 resends per IP per hour
```

### 2. **Show Cooldown Timer**
```json
{
  "message": "Verification email sent!",
  "can_resend_at": "2025-10-24T15:30:00Z",
  "cooldown_seconds": 60
}
```

Frontend can show countdown: "Resend available in 60 seconds"

### 3. **Track Resend Attempts**
Log to analytics:
- How many users need to resend?
- Are emails going to spam?
- Is email delivery failing?

### 4. **Add Email Delivery Status**
Check if email was delivered:
```python
# Use Supabase webhook or email service API
# Show user: "Email delivered" or "Email bounced"
```

---

## 📚 Related Documentation

- [PASSWORD_RESET_IMPLEMENTATION.md](./PASSWORD_RESET_IMPLEMENTATION.md) - Password reset flow
- [SUPABASE_EMAIL_SETUP.md](./SUPABASE_EMAIL_SETUP.md) - Email templates
- [Frontend Instructions](./FRONTEND_EMAIL_FLOWS.md) - Frontend implementation guide

---

## ✅ Summary

**Resend verification is NOW COMPLETE!**

Users can now:
- ✅ Request a new verification email if they didn't receive the original
- ✅ Get a new link if the old one expired
- ✅ Resend from login page or dedicated page

Backend properly:
- ✅ Calls Supabase resend API
- ✅ Prevents email enumeration (always returns success)
- ✅ Invalidates old verification tokens
- ✅ Handles already-verified emails gracefully

**Next Step:** Implement frontend UI for resend verification functionality.
