# Frontend Changes: Subscription Upgrade Flow

## Summary
The `/api/billing/create-checkout-session` endpoint now handles subscription upgrades and downgrades automatically. The response format has changed.

---

## 🆕 NEW: Upgrade Preview Endpoint (Confirmation Modal)

Before processing an upgrade, call this endpoint to show the user what they'll be charged:

### Endpoint: `POST /api/billing/preview-upgrade`

**Request:**
```json
{
  "tier": "pro"
}
```

**Response:**
```json
{
  "current_tier": "premium",
  "target_tier": "pro",
  "is_upgrade": true,
  "proration_amount": 250,
  "proration_amount_formatted": "$2.50",
  "credit_amount": 500,
  "credit_amount_formatted": "$5.00",
  "debit_amount": 750,
  "debit_amount_formatted": "$7.50",
  "next_billing_amount": 1500,
  "next_billing_amount_formatted": "$15.00/month",
  "next_billing_date": "2025-12-15T00:00:00Z",
  "card_last4": "4242",
  "card_brand": "visa",
  "message": "You'll be charged $2.50 today. Then $15.00/month starting Dec 15."
}
```

### TypeScript Interface

```typescript
interface UpgradePreviewResponse {
  current_tier: string;
  target_tier: string;
  is_upgrade: boolean;
  proration_amount: number;           // cents (can be negative for credits)
  proration_amount_formatted: string; // e.g., "$2.50" or "-$1.00"
  credit_amount: number;              // cents, unused time credit
  credit_amount_formatted: string;
  debit_amount: number;               // cents, new plan charge
  debit_amount_formatted: string;
  next_billing_amount: number;        // cents
  next_billing_amount_formatted: string; // e.g., "$15.00/month"
  next_billing_date: string;          // ISO date
  card_last4: string | null;
  card_brand: string | null;          // "visa", "mastercard", etc.
  message: string;                    // Human-readable summary
}
```

### Example Confirmation Modal UI

```
┌─────────────────────────────────────────────────────────┐
│  🚀 Upgrade to Pro                                      │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Proration Breakdown                            │   │
│  │  ─────────────────────────────                  │   │
│  │  Credit for unused Premium:    -$5.00           │   │
│  │  Pro for remaining period:     +$7.50           │   │
│  │  ─────────────────────────────                  │   │
│  │  Amount due today:              $2.50           │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  📅 Then $15.00/month starting Dec 15                  │
│                                                         │
│  💳 Using card ending in ****4242                      │
│                                                         │
│  [Cancel]                      [Confirm Upgrade →]     │
└─────────────────────────────────────────────────────────┘
```

### Recommended Flow

```typescript
async function handleUpgradeClick(targetTier: string): Promise<void> {
  // Step 1: Get preview (show loading state)
  setLoading(true);
  try {
    const preview = await fetch('/api/billing/preview-upgrade', {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${accessToken}`
      },
      body: JSON.stringify({ tier: targetTier })
    });

    if (!preview.ok) {
      const error = await preview.json();
      throw new Error(error.detail);
    }

    const previewData: UpgradePreviewResponse = await preview.json();
    
    // Step 2: Show confirmation modal with proration details
    setPreviewData(previewData);
    setShowConfirmModal(true);
    
  } catch (error) {
    toast.error(error instanceof Error ? error.message : 'Failed to load upgrade details');
  } finally {
    setLoading(false);
  }
}

async function confirmUpgrade(): Promise<void> {
  // Step 3: User confirmed, process the upgrade
  setProcessing(true);
  try {
    const response = await fetch('/api/billing/create-checkout-session', {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${accessToken}`
      },
      body: JSON.stringify({ tier: previewData.target_tier })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail);
    }

    const data = await response.json();
    
    if (data.status === 'upgraded') {
      toast.success(data.message);
      setShowConfirmModal(false);
      await refreshUserProfile();
    }
  } catch (error) {
    toast.error(error instanceof Error ? error.message : 'Upgrade failed');
  } finally {
    setProcessing(false);
  }
}
```

---

## Response Format

### New Subscription (no existing subscription)
```json
{
  "checkout_url": "https://checkout.stripe.com/...",
  "session_id": "cs_xxx"
}
```
**Action**: Redirect user to `checkout_url`

### Upgrade (user moving to higher tier)
```json
{
  "status": "upgraded",
  "message": "Successfully upgraded to pro",
  "subscription_id": "sub_xxx"
}
```
**Action**: Show success message, no redirect needed. Upgrade takes effect immediately with prorated charge.

### Downgrade (user moving to lower tier)
```json
{
  "status": "downgraded",
  "message": "Successfully downgraded to premium (effective next billing cycle)",
  "subscription_id": "sub_xxx"
}
```
**Action**: Show info message. Downgrade takes effect at end of current billing period.

### Already on Same Tier
```json
{
  "status": "already_subscribed",
  "message": "You are already subscribed to pro",
  "subscription_id": "sub_xxx"
}
```
**Action**: Show info message

## Implementation

```typescript
interface CheckoutResponse {
  // New subscription fields
  checkout_url?: string;
  session_id?: string;
  // Upgrade/downgrade fields
  status?: 'upgraded' | 'downgraded' | 'already_subscribed';
  message?: string;
  subscription_id?: string;
}

async function handleTierChange(tier: string): Promise<void> {
  try {
    const response = await fetch('/api/billing/create-checkout-session', {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${accessToken}`
      },
      body: JSON.stringify({ tier })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to process subscription change');
    }

    const data: CheckoutResponse = await response.json();

    if (data.checkout_url) {
      // New subscription - redirect to Stripe Checkout
      window.location.href = data.checkout_url;
    } else if (data.status === 'upgraded') {
      // Upgrade successful - show success and refresh user data
      toast.success(data.message);
      await refreshUserProfile(); // Reload tier info immediately
    } else if (data.status === 'downgraded') {
      // Downgrade scheduled - show info about timing
      toast.info(data.message);
      await refreshUserProfile();
    } else if (data.status === 'already_subscribed') {
      // Already on this tier
      toast.info(data.message);
    }
  } catch (error) {
    console.error('Subscription change failed:', error);
    toast.error(error instanceof Error ? error.message : 'An unexpected error occurred');
  }
}
```

## Key Points
- Check for `checkout_url` first (indicates new subscription requiring Stripe Checkout)
- If no `checkout_url`, check `status` field for upgrade/downgrade result
- After upgrade, refresh user profile to get updated tier immediately
- Downgrades take effect at next billing cycle (no prorated refund)
- Race condition protection: For **new subscriptions only**, double-clicks within the same hour return the same checkout session (via idempotency key). This does **not** apply to upgrades/downgrades, which are processed immediately.
