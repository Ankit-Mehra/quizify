# Stripe Frontend Integration Guide

**Version**: 1.0
**Backend Status**: Phase 1 (Synchronous Provisioning)
**Auth Required**: Yes (Bearer Token)

This guide details how the frontend should integrate with the Quizify backend to handle Stripe subscriptions.

---

## 1. Overview of the Flow

1.  **User Selection**: User selects a plan (Basic/Pro) on the pricing page.
2.  **Initiate Checkout**: Frontend calls `POST /api/billing/create-checkout-session`.
3.  **Redirect**: Frontend redirects user to the returned `checkout_url`.
4.  **Payment**: User completes payment on Stripe.
5.  **Return**: Stripe redirects user back to `STRIPE_SUCCESS_URL` (e.g., `https://quizify.ca/payment/success?session_id=cs_test_...`).
6.  **Verification**: Frontend extracts `session_id` from URL and calls `GET /api/billing/verify-session/{session_id}`.
7.  **Completion**: On success, frontend refreshes user profile (`/auth/me`) and displays success message.

---

## 2. API Endpoints

### A. Create Checkout Session
Initiates the upgrade process.

-   **Endpoint**: `POST /api/billing/create-checkout-session`
-   **Auth**: Required
-   **Body**:
    ```json
    {
      "tier": "basic" | "pro"
    }
    ```
-   **Response**:
    ```json
    {
      "checkout_url": "https://checkout.stripe.com/c/pay/cs_test_...",
      "session_id": "cs_test_..."
    }
    ```

### B. Verify Session (The "Callback")
Verifies payment and **immediately upgrades** the user. Call this on the success page.

-   **Endpoint**: `GET /api/billing/verify-session/{session_id}`
-   **Auth**: Required
-   **Response**:
    ```json
    {
      "session_id": "cs_test_...",
      "customer_id": "cus_...",
      "subscription_id": "sub_...",
      "tier": "pro",
      "status": "active",
      "current_period_end": 1735689600,
      "payment_status": "paid"
    }
    ```
-   **Error Handling**:
    -   `400`: Payment not complete (do not upgrade user).
    -   `403`: Session belongs to a different user.
    -   `404`: Session not found.

---

## 3. TypeScript Interfaces

```typescript
// Request to create session
export interface CreateCheckoutSessionRequest {
  tier: 'basic' | 'pro';
}

// Response from create session
export interface CreateCheckoutSessionResponse {
  checkout_url: string;
  session_id: string;
}

// Response from verification
export interface CheckoutVerificationResponse {
  session_id: string;
  customer_id: string;
  subscription_id: string;
  tier: 'basic' | 'pro';
  status: 'active' | 'trialing' | 'past_due' | 'canceled';
  current_period_end: number; // Unix timestamp
  payment_status: 'paid' | 'unpaid' | 'no_payment_required';
}
```

---

## 4. Implementation Example (React)

### Pricing Card Component
```tsx
const handleUpgrade = async (tier: 'basic' | 'pro') => {
  try {
    const response = await api.post('/billing/create-checkout-session', { tier });
    // Redirect to Stripe
    window.location.href = response.data.checkout_url;
  } catch (error) {
    console.error("Failed to start checkout", error);
    toast.error("Could not initialize checkout");
  }
};
```

### Success Page Component (`/payment/success`)
```tsx
const PaymentSuccessPage = () => {
  const [searchParams] = useSearchParams();
  const sessionId = searchParams.get('session_id');
  const { refreshUserProfile } = useAuth(); // Hook to re-fetch /auth/me

  useEffect(() => {
    if (sessionId) {
      verifyPayment(sessionId);
    }
  }, [sessionId]);

  const verifyPayment = async (id: string) => {
    try {
      await api.get(`/billing/verify-session/${id}`);
      // CRITICAL: Refresh user profile to update UI with new tier
      await refreshUserProfile(); 
      toast.success("Upgrade successful! You are now a Pro member.");
    } catch (error: any) {
      const status = error?.response?.status;
      if (status === 403) {
        toast.error("This payment session does not belong to your account. Please log in with the correct user.");
      } else if (status === 400) {
        toast.error("Payment incomplete. Please finish the payment process in Stripe.");
      } else if (status === 404) {
        toast.error("Payment session not found. Please check your link or try again.");
      } else {
        toast.error("Payment verification failed. Please contact support.");
      }
    }
  };

  return <div>Verifying your payment...</div>;
};
```

---

## 5. Key Considerations for Frontend Devs

1.  **User State Sync**: The backend updates the database *during* the `verify-session` call. You **MUST** re-fetch the user profile (e.g., `GET /auth/me`) after verification succeeds to ensure the UI reflects the new "Pro" status (e.g., unlocking features, hiding upgrade buttons).
2.  **Error Handling**: If `verify-session` fails, do **not** show the user as upgraded. Show a support contact message.
3.  **Idempotency**: The `verify-session` endpoint is safe to call multiple times. If the user refreshes the success page, it will simply verify the status again without side effects.
