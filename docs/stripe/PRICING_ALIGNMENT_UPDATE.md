# Pricing Alignment Update - Epic 1

## Summary
Updated Stripe integration pricing to align with the **October 2025 cost breakdown analysis** which showed optimal profit margins at lower price points.

## Changes Made

### Pricing Structure (Before vs After)

| Change | Previous Plan | Updated Plan | Rationale |
|--------|--------------|--------------|-----------|
| **Basic Tier** | $9.99/mo - 100 quizzes | **$5/mo - 100 quizzes** | Cost analysis showed 97% profit margin at $5/mo |
| **Top Tier** | Educator: $19.99/mo - 500 quizzes | **Pro: $15/mo - Unlimited** | Better value proposition, same 97% profit margin |
| **Tier Name** | Educator | **Pro** | More universal appeal, not just for educators |

### Files Updated

1. **`docs/stripe/README.md`**
   - Updated pricing table: Basic $5/mo, Pro $15/mo
   - Changed tier references from "educator" to "pro"
   - Added note about `educator` → `pro` migration

2. **`config.py`**
   - Changed `STRIPE_PRICE_ID_EDUCATOR` → `STRIPE_PRICE_ID_PRO`
   - Updated price ID mapping methods
   - Added backward compatibility for existing `educator` users
   - Updated comments with new pricing ($5/mo, $15/mo)

3. **`.env.example`**
   - Updated Stripe price ID documentation
   - Changed from `STRIPE_PRICE_ID_EDUCATOR` to `STRIPE_PRICE_ID_PRO`
   - Updated pricing examples ($5/mo Basic, $15/mo Pro)

4. **`schemas/billing.py`**
   - Updated `CheckoutSessionRequest` to accept `"basic"` or `"pro"` (was `"educator"`)
   - Updated `SubscriptionStatusResponse` to accept `"pro"` as valid tier
   - Kept `"educator"` for backward compatibility with existing users

5. **`services/billing_service.py`**
   - Updated docstrings to reference "pro" instead of "educator"

6. **`api/billing_routes.py`**
   - Updated endpoint descriptions with new pricing
   - Changed "Upgrade to Educator" to "Upgrade to Pro ($15/mo)"

7. **`migrations/016_add_pro_tier_unlimited_quota.sql`** (NEW)
   - Added "pro" tier with quota_limit = 999999 (unlimited)
   - Pro tier users never hit quota_exceeded = true
   - Maintains backward compatibility with "educator" tier (500 quizzes)
   - Updated `user_tier_info` view to support pro tier

## Backward Compatibility

✅ **No Breaking Changes**
- Existing `educator` tier users remain unchanged
- Database view supports both `educator` (500) and `pro` (unlimited)
- Config.py maps both tier names to `STRIPE_PRICE_ID_PRO`
- Schemas accept both tier names in responses

## Profit Margin Analysis (from COST_BREAKDOWN.md)

### Infrastructure Costs per User
- Free tier: ~$0.01/user/month
- Basic tier: ~$0.15/user/month
- Pro tier: ~$0.50/user/month

### Profit Margins
- Basic ($5/mo): **97% profit margin** ($5 - $0.15 = $4.85 profit)
- Pro ($15/mo): **97% profit margin** ($15 - $0.50 = $14.50 profit)

### Why These Prices?
1. **Competitive Advantage**: $5/mo is psychologically easier to justify than $9.99
2. **High Margins**: 97% profit margins mean we can afford customer acquisition costs
3. **Unlimited Pro**: Removes mental barrier of counting quizzes, increases perceived value
4. **Cost-Effective**: AI costs only $0.00125 per quiz (GPT-3.5), so unlimited is sustainable

## Migration Strategy

### For New Users
- All new Stripe subscriptions create `pro` tier (unlimited quota)
- No confusion with tier names

### For Existing Educator Users (Optional)
If you want to migrate existing `educator` users to `pro`:
```sql
-- Run this migration separately when ready
UPDATE public.profiles 
SET account_tier = 'pro' 
WHERE account_tier = 'educator';
```

**Recommendation**: Don't migrate immediately. Let existing educator users keep 500 quota until they voluntarily upgrade or renew.

## Testing Checklist

Before deploying to production:
- [ ] Verify `STRIPE_PRICE_ID_PRO` environment variable is set
- [ ] Create Stripe product/price in Dashboard for Pro tier ($15/mo)
- [ ] Test checkout flow with `tier: "pro"`
- [ ] Verify quota_limit returns 999999 for pro users
- [ ] Verify quota_exceeded is always FALSE for pro users
- [ ] Test backward compatibility with existing educator users

## Next Steps

1. **Apply Migration 016**: Run `016_add_pro_tier_unlimited_quota.sql` on Supabase
2. **Create Stripe Products**: 
   - Basic: $5/mo recurring (100 quizzes)
   - Pro: $15/mo recurring (unlimited quizzes)
3. **Update Frontend**: Change "Upgrade to Educator" buttons to "Upgrade to Pro - Unlimited Quizzes"
4. **Continue Epic 2**: Implement checkout flow with new pricing

---

**Last Updated**: 2025-11-19  
**Status**: Epic 1 - Pricing Alignment Complete  
**Next Action**: Continue with Epic 2 - Checkout Flow Implementation
