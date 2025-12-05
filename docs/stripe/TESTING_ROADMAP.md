# Stripe Integration: Testing Roadmap

**Last Updated**: 2025-11-20
**Status**: Phase 1 (Synchronous Bridge) Active

This document outlines the features that are currently testable with the frontend and what will be available in future iterations.

---

## ✅ Phase 1: Immediate Testing (Current State)

The backend currently implements a **Synchronous Provisioning Bridge**. This allows the full "Upgrade to Pro" flow to be tested immediately without waiting for asynchronous webhooks.

### Testable Features
| Feature | Description | Testable Flow |
| :--- | :--- | :--- |
| **Checkout Session Creation** | Create a Stripe Checkout session for a specific tier. | User clicks "Upgrade" -> Redirects to Stripe. |
| **Payment Processing** | Complete a payment on Stripe (Test Mode). | User enters test card details -> Payment succeeds. |
| **Session Verification** | Verify the session ID returned by Stripe. | Frontend calls `verify-session` endpoint. |
| **Instant Provisioning** | **CRITICAL**: User is upgraded to "Pro" *immediately* upon verification. | User returns to dashboard -> Sees "Pro" badge/quota. |
| **Quota Update** | Quota limits increase immediately. | User can generate >5 quizzes (Free limit). |
| **Tier Persistence** | User remains "Pro" on page refresh. | `GET /auth/me` returns `account_tier: "pro"`. |

### How to Test (End-to-End)
1.  **Login** as a Free user.
2.  **Navigate** to Pricing/Billing page.
3.  **Click** "Upgrade to Basic" or "Pro".
4.  **Redirect** to Stripe Checkout (Test Mode).
5.  **Enter** Test Card (e.g., `4242 4242...`).
6.  **Success Redirect** back to your app (e.g., `/payment/success?session_id=...`).
7.  **Verify**: Frontend should show "Payment Successful" and update the UI to "Pro".
8.  **Check Database** (Optional): `profiles` table should have `account_tier='pro'` and `subscription_status='active'`.

---

## ⏳ Phase 2: Webhooks & Lifecycle (Next Iteration - Epic 3)

These features require the implementation of **Stripe Webhooks**. They are **NOT** currently testable from the frontend alone (backend logic exists but is not wired to the webhook endpoint).

### Pending Features
| Feature | Description | Dependency |
| :--- | :--- | :--- |
| **Auto-Renewal** | Subscription renews next month; DB updates automatically. | `invoice.paid` webhook |
| **Cancellation (External)** | User cancels via Stripe email/dashboard; DB updates. | `customer.subscription.deleted` webhook |
| **Failed Payments** | Card expires/fails; User downgraded or put in grace period. | `invoice.payment_failed` webhook |
| **Refunds** | Payment refunded; User downgraded. | `charge.refunded` webhook |

---

## 🔮 Phase 3: Self-Serve Portal (Future - Epic 4)

These features require the **Stripe Customer Portal** integration.

### Pending Features
| Feature | Description | Dependency |
| :--- | :--- | :--- |
| **Manage Subscription** | "Manage Billing" button in app. | `create-portal-session` endpoint |
| **Update Card** | User updates credit card details. | Customer Portal |
| **View Invoices** | User downloads past PDF invoices. | Customer Portal |
| **Cancel Subscription** | User cancels directly from the app. | Customer Portal |

---

## Summary for QA/Frontend Devs

-   **Focus NOW**: Testing the "Happy Path" upgrade flow. Ensure the user gets the features they paid for immediately.
-   **Ignore**: Testing cancellations, renewals, or failed payments for now.
