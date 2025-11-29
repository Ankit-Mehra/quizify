# Frontend Changes: Subscription Upgrade Flow

## Summary
The `/api/billing/create-checkout` endpoint now handles subscription upgrades automatically. The response format has changed.

## Response Format

### New Subscription (no existing subscription)
```json
{
  "checkout_url": "https://checkout.stripe.com/...",
  "session_id": "cs_xxx"
}
```
**Action**: Redirect user to `checkout_url`

### Upgrade (user already has a subscription)
```json
{
  "status": "upgraded",
  "message": "Successfully upgraded to pro",
  "subscription_id": "sub_xxx"
}
```
**Action**: Show success message, no redirect needed

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
const response = await fetch('/api/billing/create-checkout', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ tier: 'pro' })
});

const data = await response.json();

if (data.checkout_url) {
  // New subscription - redirect to Stripe
  window.location.href = data.checkout_url;
} else if (data.status === 'upgraded') {
  // Upgrade successful - show success and refresh user data
  toast.success(data.message);
  await refreshUserProfile(); // Reload tier info
} else if (data.status === 'already_subscribed') {
  // Already on this tier
  toast.info(data.message);
}
```

## Key Points
- Check for `checkout_url` first (indicates new subscription)
- If no `checkout_url`, check `status` field for upgrade result
- After upgrade, refresh user profile to get updated tier
