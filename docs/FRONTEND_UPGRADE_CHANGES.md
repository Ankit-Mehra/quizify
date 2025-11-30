# Frontend Changes: Subscription Upgrade Flow

## Summary
The `/api/billing/create-checkout-session` endpoint now handles subscription upgrades and downgrades automatically. The response format has changed.

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
