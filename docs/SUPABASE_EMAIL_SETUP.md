# Supabase Email Configuration for Quizify

## Email Template for Signup Confirmation

Use this template in **Supabase Dashboard → Authentication → Email Templates → Confirm signup**:

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif; background-color: #f4f4f4;">
  <!-- Wrapper table for email client compatibility -->
  <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #f4f4f4;">
    <tr>
      <td style="padding: 20px 0;">
        <!-- Main content table (the "card") -->
        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="margin: 0 auto; background-color: #ffffff; border: 2px solid #e5e7eb; border-radius: 8px;">
          <tr>
            <td style="padding: 40px 40px 30px 40px;">
              <!-- Logo -->
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                <tr>
                  <td style="text-align: center; padding-bottom: 30px;">
                    <h1 style="margin: 0; color: #6366f1; font-size: 32px;">🎓 Quizify</h1>
                  </td>
                </tr>
              </table>
              
              <!-- Heading -->
              <h2 style="color: #1f2937; font-size: 24px; margin: 0 0 20px 0; font-weight: 600;">Welcome to Quizify!</h2>
              
              <!-- Body text -->
              <p style="color: #374151; font-size: 16px; line-height: 1.6; margin: 0 0 16px 0;">Hey there, genius-in-the-making! 🚀</p>
              
              <p style="color: #374151; font-size: 16px; line-height: 1.6; margin: 0 0 24px 0;">You've joined Quizify, the place where curiosity gets a gold star. 🌟 Before you start flexing your quiz skills, hit the button below to verify your email.</p>
              
              <!-- Button -->
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                <tr>
                  <td style="text-align: center; padding: 20px 0;">
                    <a href="https://api.quizify.ca/api/auth/confirm?token={{ .TokenHash }}&type=signup" style="display: inline-block; padding: 14px 28px; background-color: #6366f1; color: #ffffff; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 16px;">Verify Email Address</a>
                  </td>
                </tr>
              </table>
              
              <!-- Warning box -->
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="margin: 20px 0;">
                <tr>
                  <td style="background-color: #fef3c7; border-left: 4px solid #f59e0b; padding: 12px; border-radius: 4px;">
                    <p style="margin: 0; color: #92400e; font-size: 14px; line-height: 1.5;">
                      <strong>⚠️ Important:</strong> This link will expire in 24 hours for security reasons.
                    </p>
                  </td>
                </tr>
              </table>
              
              <!-- Alternative link -->
              <p style="color: #374151; font-size: 14px; line-height: 1.6; margin: 20px 0 8px 0;">If the button doesn't work, copy and paste this link into your browser:</p>
              <p style="color: #6366f1; font-size: 12px; line-height: 1.5; word-break: break-all; margin: 0 0 20px 0;">https://api.quizify.ca/api/auth/confirm?token={{ .TokenHash }}&type=signup</p>
              
              <!-- Disclaimer -->
              <p style="color: #6b7280; font-size: 14px; line-height: 1.6; margin: 0;">If you didn't create an account with Quizify, you can safely ignore this email.</p>
            </td>
          </tr>
          
          <!-- Footer -->
          <tr>
            <td style="padding: 20px 40px 30px 40px; border-top: 1px solid #e5e7eb;">
              <p style="margin: 0 0 8px 0; color: #1f2937; font-size: 14px; font-weight: 600;">The Quizify Team</p>
              <p style="margin: 0; color: #9ca3af; font-size: 12px; line-height: 1.5;">This is an automated message, please do not reply to this email.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
```

## Overview
Supabase handles email verification automatically using magic links. When a user signs up, Supabase sends them an email with a verification link. No backend endpoint is needed!

## Email Verification Flow

```
1. User signs up via POST /auth/signup
   ↓
2. Supabase sends verification email with magic link
   ↓
3. User clicks link in email
   ↓
4. Supabase verifies email automatically
   ↓
5. User is redirected to your frontend
   ↓
6. Frontend shows "Email verified!" message
   ↓
7. User can now login via POST /auth/login
```

## Configuration Steps

### 1. Access Supabase Dashboard
1. Go to [https://app.supabase.com](https://app.supabase.com)
2. Select your project
3. Navigate to **Authentication** → **Email Templates**

### 2. Configure Email Templates

#### A. Confirm Signup Template
This is the email users receive after signing up.

**Default Template Variables:**
- `{{ .ConfirmationURL }}` - The magic link for email verification
- `{{ .SiteURL }}` - Your application URL
- `{{ .Email }}` - The user's email address
- `{{ .Token }}` - The verification token (if using OTP)

**📧 Why Tables for Email HTML?**
Email clients (Gmail, Outlook, Apple Mail) don't support modern CSS like flexbox, grid, or box-shadow. We use HTML tables with inline styles because:
- ✅ Tables work consistently across all email clients
- ✅ Inline styles are more reliable than `<style>` tags
- ✅ Borders using `border` attribute + inline styles are guaranteed to render
- ✅ This is the industry standard for professional email templates

**Example HTML Template (Email Client Compatible):**
```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif; background-color: #f4f4f4;">
  <!-- Wrapper table for email client compatibility -->
  <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #f4f4f4;">
    <tr>
      <td style="padding: 20px 0;">
        <!-- Main content table (the "card") -->
        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="margin: 0 auto; background-color: #ffffff; border: 2px solid #e5e7eb; border-radius: 8px;">
          <tr>
            <td style="padding: 40px 40px 30px 40px;">
              <!-- Logo -->
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                <tr>
                  <td style="text-align: center; padding-bottom: 30px;">
                    <h1 style="margin: 0; color: #6366f1; font-size: 32px;">🎓 Quizify</h1>
                  </td>
                </tr>
              </table>
              
              <!-- Heading -->
              <h2 style="color: #1f2937; font-size: 24px; margin: 0 0 20px 0; font-weight: 600;">Welcome to Quizify!</h2>
              
              <!-- Body text -->
              <p style="color: #374151; font-size: 16px; line-height: 1.6; margin: 0 0 16px 0;">Hey there, genius-in-the-making! 🚀</p>
              
              <p style="color: #374151; font-size: 16px; line-height: 1.6; margin: 0 0 24px 0;">You've joined Quizify, the place where curiosity gets a gold star. 🌟 Before you start flexing your quiz skills, hit the button below to verify your email.</p>
              
              <!-- Button -->
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                <tr>
                  <td style="text-align: center; padding: 20px 0;">
                    <a href="{{ .ConfirmationURL }}" style="display: inline-block; padding: 14px 28px; background-color: #6366f1; color: #ffffff; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 16px;">Verify Email Address</a>
                  </td>
                </tr>
              </table>
              
              <!-- Warning box -->
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="margin: 20px 0;">
                <tr>
                  <td style="background-color: #fef3c7; border-left: 4px solid #f59e0b; padding: 12px; border-radius: 4px;">
                    <p style="margin: 0; color: #92400e; font-size: 14px; line-height: 1.5;">
                      <strong>⚠️ Important:</strong> This link will expire in 24 hours for security reasons.
                    </p>
                  </td>
                </tr>
              </table>
              
              <!-- Alternative link -->
              <p style="color: #374151; font-size: 14px; line-height: 1.6; margin: 20px 0 8px 0;">If the button doesn't work, copy and paste this link into your browser:</p>
              <p style="color: #6366f1; font-size: 12px; line-height: 1.5; word-break: break-all; margin: 0 0 20px 0;">{{ .ConfirmationURL }}</p>
              
              <!-- Disclaimer -->
              <p style="color: #6b7280; font-size: 14px; line-height: 1.6; margin: 0;">If you didn't create an account with Quizify, you can safely ignore this email.</p>
            </td>
          </tr>
          
          <!-- Footer -->
          <tr>
            <td style="padding: 20px 40px 30px 40px; border-top: 1px solid #e5e7eb;">
              <p style="margin: 0 0 8px 0; color: #1f2937; font-size: 14px; font-weight: 600;">The Quizify Team</p>
              <p style="margin: 0; color: #9ca3af; font-size: 12px; line-height: 1.5;">This is an automated message, please do not reply to this email.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
```

### 3. Configure Redirect URLs

#### In Supabase Dashboard:
1. Go to **Authentication** → **URL Configuration**
2. Set **Site URL**: Your frontend URL (e.g., `https://quizify.app` or `http://localhost:3000` for local dev)
3. Add **Redirect URLs** (whitelist):
   - `https://quizify.app/auth/verified`
   - `http://localhost:3000/auth/verified` (for local development)
   - Any other URLs you want to allow

#### Example Configuration:
```
Site URL: https://quizify.app
Redirect URLs:
  - https://quizify.app/*
  - http://localhost:3000/*
  - http://localhost:5173/*  (if using Vite)
```

### 4. Configure Email Redirect in Template

Update the confirmation URL to redirect to your frontend:

```html
<a href="{{ .ConfirmationURL }}?redirect_to=https://quizify.app/auth/verified" class="button">
  Verify Email Address
</a>
```

Or set it globally in **Authentication** → **URL Configuration** → **Redirect URL after email confirmation**

### 5. Frontend Handler

Create a page at `/auth/verified` that handles the redirect:

**Example React/Next.js Page:**
```typescript
// pages/auth/verified.tsx or app/auth/verified/page.tsx

'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

export default function EmailVerifiedPage() {
  const [status, setStatus] = useState<'verifying' | 'success' | 'error'>('verifying');
  const router = useRouter();

  useEffect(() => {
    // Check if there's an error in the URL (Supabase adds error params if verification fails)
    const hashParams = new URLSearchParams(window.location.hash.substring(1));
    const error = hashParams.get('error');
    const errorDescription = hashParams.get('error_description');

    if (error) {
      setStatus('error');
      console.error('Email verification error:', errorDescription);
    } else {
      // Success! Email is verified
      setStatus('success');
      
      // Redirect to login after 3 seconds
      setTimeout(() => {
        router.push('/auth/login');
      }, 3000);
    }
  }, [router]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="max-w-md w-full bg-white rounded-lg shadow-lg p-8 text-center">
        {status === 'verifying' && (
          <>
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto"></div>
            <h2 className="mt-4 text-xl font-semibold">Verifying your email...</h2>
          </>
        )}
        
        {status === 'success' && (
          <>
            <div className="text-green-500 text-6xl mb-4">✓</div>
            <h2 className="text-2xl font-bold text-gray-900 mb-2">
              Email Verified Successfully!
            </h2>
            <p className="text-gray-600 mb-4">
              Your email has been confirmed. You can now log in to your account.
            </p>
            <p className="text-sm text-gray-500">
              Redirecting to login page...
            </p>
          </>
        )}
        
        {status === 'error' && (
          <>
            <div className="text-red-500 text-6xl mb-4">✗</div>
            <h2 className="text-2xl font-bold text-gray-900 mb-2">
              Verification Failed
            </h2>
            <p className="text-gray-600 mb-4">
              The verification link may have expired or is invalid.
            </p>
            <button
              onClick={() => router.push('/auth/signup')}
              className="bg-indigo-600 text-white px-6 py-2 rounded-md hover:bg-indigo-700"
            >
              Back to Signup
            </button>
          </>
        )}
      </div>
    </div>
  );
}
```

### 6. Additional Email Templates to Customize

#### B. Magic Link Template
Used when users request a magic link to sign in without password.

#### C. Change Email Address Template
Sent when users change their email address and need to verify the new one.

**Change Email Template (Email Client Compatible):**
```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif; background-color: #f4f4f4;">
  <!-- Wrapper table for email client compatibility -->
  <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #f4f4f4;">
    <tr>
      <td style="padding: 20px 0;">
        <!-- Main content table (the "card") -->
        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="margin: 0 auto; background-color: #ffffff; border: 2px solid #e5e7eb; border-radius: 8px;">
          <tr>
            <td style="padding: 40px 40px 30px 40px;">
              <!-- Logo -->
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                <tr>
                  <td style="text-align: center; padding-bottom: 30px;">
                    <h1 style="margin: 0; color: #6366f1; font-size: 32px;">🎓 Quizify</h1>
                  </td>
                </tr>
              </table>
              
              <!-- Heading -->
              <h2 style="color: #1f2937; font-size: 24px; margin: 0 0 20px 0; font-weight: 600;">New Email, Who Dis? 📧</h2>
              
              <!-- Body text -->
              <p style="color: #374151; font-size: 16px; line-height: 1.6; margin: 0 0 16px 0;">Hey there, email-changer extraordinaire!</p>
              
              <p style="color: #374151; font-size: 16px; line-height: 1.6; margin: 0 0 16px 0;">You (or someone pretending to be you) requested to change your Quizify email to this address. If that sounds right, click the button below to confirm the change.</p>
              
              <p style="color: #374151; font-size: 16px; line-height: 1.6; margin: 0 0 24px 0;">Once confirmed, you'll use this new email for all your quiz adventures! 🚀</p>
              
              <!-- Button -->
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                <tr>
                  <td style="text-align: center; padding: 20px 0;">
                    <a href="https://api.quizify.ca/api/auth/confirm?token={{ .TokenHash }}&type=email_change" style="display: inline-block; padding: 14px 28px; background-color: #6366f1; color: #ffffff; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 16px;">Confirm New Email</a>
                  </td>
                </tr>
              </table>
              
              <!-- Warning box -->
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="margin: 20px 0;">
                <tr>
                  <td style="background-color: #dbeafe; border-left: 4px solid #3b82f6; padding: 12px; border-radius: 4px;">
                    <p style="margin: 0; color: #1e3a8a; font-size: 14px; line-height: 1.5;">
                      <strong>📧 Note:</strong> You'll need to confirm this change from both your new and current email addresses.
                    </p>
                  </td>
                </tr>
              </table>
              
              <!-- Alternative link -->
              <p style="color: #374151; font-size: 14px; line-height: 1.6; margin: 20px 0 8px 0;">Button not working? Copy and paste this link into your browser:</p>
              <p style="color: #6366f1; font-size: 12px; line-height: 1.5; word-break: break-all; margin: 0 0 20px 0;">https://api.quizify.ca/api/auth/confirm?token={{ .TokenHash }}&type=email_change</p>
              
              <!-- Disclaimer -->
              <p style="color: #6b7280; font-size: 14px; line-height: 1.6; margin: 0;">Didn't request this change? Your account might be under attack! 🚨 Please secure your account immediately or contact support.</p>
            </td>
          </tr>
          
          <!-- Footer -->
          <tr>
            <td style="padding: 20px 40px 30px 40px; border-top: 1px solid #e5e7eb;">
              <p style="margin: 0 0 8px 0; color: #1f2937; font-size: 14px; font-weight: 600;">The Quizify Team</p>
              <p style="margin: 0; color: #9ca3af; font-size: 12px; line-height: 1.5;">This is an automated message, please do not reply to this email.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
```

#### D. Reset Password Template
Sent when users request a password reset.

**Reset Password Template (Email Client Compatible):**
```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif; background-color: #f4f4f4;">
  <!-- Wrapper table for email client compatibility -->
  <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #f4f4f4;">
    <tr>
      <td style="padding: 20px 0;">
        <!-- Main content table (the "card") -->
        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="margin: 0 auto; background-color: #ffffff; border: 2px solid #e5e7eb; border-radius: 8px;">
          <tr>
            <td style="padding: 40px 40px 30px 40px;">
              <!-- Logo -->
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                <tr>
                  <td style="text-align: center; padding-bottom: 30px;">
                    <h1 style="margin: 0; color: #6366f1; font-size: 32px;">🎓 Quizify</h1>
                  </td>
                </tr>
              </table>
              
              <!-- Heading -->
              <h2 style="color: #1f2937; font-size: 24px; margin: 0 0 20px 0; font-weight: 600;">Oops, Forgot Your Password? 🔐</h2>
              
              <!-- Body text -->
              <p style="color: #374151; font-size: 16px; line-height: 1.6; margin: 0 0 16px 0;">No worries, happens to the best of us!</p>
              
              <p style="color: #374151; font-size: 16px; line-height: 1.6; margin: 0 0 16px 0;">Someone (hopefully you!) requested a password reset for your Quizify account. Click the button below to create a shiny new password and get back to acing those quizzes! 🌟</p>
              
              <p style="color: #374151; font-size: 16px; line-height: 1.6; margin: 0 0 24px 0;">If you didn't request this, no action needed. Your current password is safe and sound.</p>
              
              <!-- Button -->
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                <tr>
                  <td style="text-align: center; padding: 20px 0;">
                    <a href="https://api.quizify.ca/api/auth/confirm?token={{ .TokenHash }}&type=recovery" style="display: inline-block; padding: 14px 28px; background-color: #6366f1; color: #ffffff; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 16px;">Reset My Password</a>
                  </td>
                </tr>
              </table>
              
              <!-- Warning box -->
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="margin: 20px 0;">
                <tr>
                  <td style="background-color: #fef3c7; border-left: 4px solid #f59e0b; padding: 12px; border-radius: 4px;">
                    <p style="margin: 0; color: #92400e; font-size: 14px; line-height: 1.5;">
                      <strong>⚠️ Important:</strong> This reset link expires in 1 hour for security reasons.
                    </p>
                  </td>
                </tr>
              </table>
              
              <!-- Alternative link -->
              <p style="color: #374151; font-size: 14px; line-height: 1.6; margin: 20px 0 8px 0;">Button playing hide-and-seek? Use this link instead:</p>
              <p style="color: #6366f1; font-size: 12px; line-height: 1.5; word-break: break-all; margin: 0 0 20px 0;">https://api.quizify.ca/api/auth/confirm?token={{ .TokenHash }}&type=recovery</p>
              
              <!-- Disclaimer -->
              <p style="color: #6b7280; font-size: 14px; line-height: 1.6; margin: 0;">Didn't request a password reset? Someone might be trying to access your account. 🚨 Please secure your account or contact our support team ASAP!</p>
            </td>
          </tr>
          
          <!-- Footer -->
          <tr>
            <td style="padding: 20px 40px 30px 40px; border-top: 1px solid #e5e7eb;">
              <p style="margin: 0 0 8px 0; color: #1f2937; font-size: 14px; font-weight: 600;">The Quizify Team</p>
              <p style="margin: 0; color: #9ca3af; font-size: 12px; line-height: 1.5;">This is an automated message, please do not reply to this email.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
```

## Testing Email Verification

### Local Development
1. Sign up a new user via Postman: `POST /auth/signup`
2. Check the terminal logs - Supabase may log the verification URL in development mode
3. Alternatively, check your email inbox (if SMTP is configured)
4. Click the verification link
5. Verify the redirect works correctly
6. Try logging in - should work now!

### Production
1. Configure custom SMTP in Supabase Dashboard:
   - **Authentication** → **Email**
   - Add your SMTP credentials (e.g., SendGrid, AWS SES, Mailgun)
2. Test the full flow with real emails

## Troubleshooting

### Issue: "Email not confirmed" error on login
**Solution:** User hasn't clicked the verification link yet. Check:
- Email was delivered (check spam folder)
- Link hasn't expired (24 hours default)
- SMTP is configured correctly

### Issue: Verification link returns error
**Solution:** 
- Check redirect URL is whitelisted in Supabase
- Verify the URL pattern matches exactly
- Check browser console for errors

### Issue: Users not receiving emails
**Solution:**
- Verify SMTP settings in Supabase Dashboard
- Check email provider limits (Supabase free tier has email limits)
- Configure custom SMTP provider (recommended for production)

### Issue: Email template looks different in email client vs Supabase preview
**Why this happens:**
- Supabase preview uses a modern browser with full CSS support
- Email clients (Gmail, Outlook) strip out most CSS for security
- Box shadows, advanced borders, and many CSS properties don't work in emails

**Solution:**
- Use the table-based template provided above (works in all email clients)
- Always test in actual email clients, not just Supabase preview
- Use inline styles only (no external stylesheets or `<style>` tags)
- Use `border` attribute on tables: `<table border="2" style="border: 2px solid #e5e7eb;">`
- Avoid: flexbox, grid, position, float, box-shadow, transform

**Test your email template in:**
- Gmail (web + mobile app)
- Outlook (desktop + web)
- Apple Mail
- Yahoo Mail

**Helpful tool:** [Litmus](https://www.litmus.com) or [Email on Acid](https://www.emailonacid.com) for testing across all clients

## Advanced: Custom Email Provider

For production, use a dedicated email service:

### SendGrid Setup
```bash
1. Create SendGrid account
2. Generate API key
3. In Supabase Dashboard → Authentication → Email:
   - SMTP Host: smtp.sendgrid.net
   - SMTP Port: 587
   - SMTP User: apikey
   - SMTP Password: <your-sendgrid-api-key>
   - SMTP Sender Email: noreply@yourdomain.com
```

### AWS SES Setup
```bash
1. Verify your domain in AWS SES
2. Create SMTP credentials
3. In Supabase Dashboard:
   - SMTP Host: email-smtp.us-east-1.amazonaws.com
   - SMTP Port: 587
   - SMTP User: <your-ses-username>
   - SMTP Password: <your-ses-password>
```

## Security Best Practices

1. ✅ **Always use HTTPS** for production redirect URLs
2. ✅ **Whitelist specific redirect URLs** - don't use wildcards in production
3. ✅ **Set appropriate token expiration** (default 24 hours is good)
4. ✅ **Use custom SMTP** in production for better deliverability
5. ✅ **Monitor email bounces** and handle them appropriately
6. ✅ **Test email templates** thoroughly before deploying

## Related Configuration

### Disable Email Verification (Not Recommended)
If you want to skip email verification for testing:
1. Go to **Authentication** → **Providers** → **Email**
2. Uncheck **Confirm email**
3. ⚠️ **WARNING:** This is insecure and should only be used for local development

### Rate Limiting
Supabase automatically rate-limits email sending:
- Free tier: ~30 emails/hour
- Pro tier: Higher limits + custom SMTP recommended

## Email Template for Password Recovery

Use this in **Supabase Dashboard → Authentication → Email Templates → Reset Password**:

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif; background-color: #f4f4f4;">
  <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #f4f4f4;">
    <tr>
      <td style="padding: 20px 0;">
        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="margin: 0 auto; background-color: #ffffff; border: 2px solid #e5e7eb; border-radius: 8px;">
          <tr>
            <td style="padding: 40px 40px 30px 40px;">
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                <tr>
                  <td style="text-align: center; padding-bottom: 30px;">
                    <h1 style="margin: 0; color: #6366f1; font-size: 32px;">🎓 Quizify</h1>
                  </td>
                </tr>
              </table>
              
              <h2 style="color: #1f2937; font-size: 24px; margin: 0 0 20px 0; font-weight: 600;">Reset Your Password</h2>
              
              <p style="color: #374151; font-size: 16px; line-height: 1.6; margin: 0 0 16px 0;">Hello! 👋</p>
              
              <p style="color: #374151; font-size: 16px; line-height: 1.6; margin: 0 0 24px 0;">You requested to reset your Quizify password. Click the button below to create a new password and regain access to your account.</p>
              
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                <tr>
                  <td style="text-align: center; padding: 20px 0;">
                    <a href="https://api.quizify.ca/api/auth/confirm?token={{ .TokenHash }}&type=recovery" style="display: inline-block; padding: 14px 28px; background-color: #6366f1; color: #ffffff; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 16px;">Reset Password</a>
                  </td>
                </tr>
              </table>
              
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="margin: 20px 0;">
                <tr>
                  <td style="background-color: #fef3c7; border-left: 4px solid #f59e0b; padding: 12px; border-radius: 4px;">
                    <p style="margin: 0; color: #92400e; font-size: 14px; line-height: 1.5;">
                      <strong>⚠️ Important:</strong> This link will expire in 1 hour for security reasons.
                    </p>
                  </td>
                </tr>
              </table>
              
              <p style="color: #374151; font-size: 14px; line-height: 1.6; margin: 20px 0 8px 0;">If the button doesn't work, copy and paste this link:</p>
              <p style="color: #6366f1; font-size: 12px; line-height: 1.5; word-break: break-all; margin: 0 0 20px 0;">https://api.quizify.ca/api/auth/confirm?token={{ .TokenHash }}&type=recovery</p>
              
              <p style="color: #6b7280; font-size: 14px; line-height: 1.6; margin: 0;">If you didn't request a password reset, please ignore this email or contact support if you have concerns.</p>
            </td>
          </tr>
          
          <tr>
            <td style="padding: 20px 40px 30px 40px; border-top: 1px solid #e5e7eb;">
              <p style="margin: 0 0 8px 0; color: #1f2937; font-size: 14px; font-weight: 600;">The Quizify Team</p>
              <p style="margin: 0; color: #9ca3af; font-size: 12px; line-height: 1.5;">This is an automated message, please do not reply to this email.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
```

## Summary Checklist

- [ ] Customize email templates with your branding
- [ ] Set Site URL in Supabase Dashboard
- [ ] Add redirect URLs to whitelist
- [ ] Create frontend `/auth/verified` page
- [ ] Configure custom SMTP for production
- [ ] Test full signup → verify → login flow
- [ ] Remove any custom verify-email endpoints (handled by Supabase)

---

**Need Help?**
- [Supabase Email Templates Docs](https://supabase.com/docs/guides/auth/auth-email-templates)
- [Supabase Auth Configuration](https://supabase.com/docs/guides/auth/auth-smtp)

````
