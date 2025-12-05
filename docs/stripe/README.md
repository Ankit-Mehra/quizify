# Stripe Payment Integration - Overview

## Purpose
Integrate Stripe subscription billing into Quizify to monetize the platform through paid tier subscriptions (Basic and Educator).

## Current State (Before Integration)
- **Tier System**: `free` (5 quizzes), `basic` (100 quizzes), `pro` (unlimited quizzes)
- **Tier Management**: Manual admin-only upgrades via `/api/admin/users/{user_id}/tier`
- **Database**: `public.profiles.account_tier` stores current tier
- **No Payment System**: Users cannot self-upgrade or pay for tiers
- **Note**: Database still has legacy `educator` tier (500 quizzes) - will be migrated to `pro` (unlimited)

## Target State (After Integration)
- **Self-Service Billing**: Users can subscribe to paid tiers via Stripe Checkout
- **Automatic Provisioning**: Webhook-driven tier upgrades on successful payment
- **Customer Portal**: Users can manage subscriptions, update payment methods, cancel
- **Subscription Status Tracking**: Database tracks active/past_due/canceled status
- **Stripe Integration**: Full webhook-driven subscription lifecycle management
- **Tier Migration**: `educator` → `pro` with unlimited quota (no breaking changes)

## Architecture Overview

```
┌─────────────┐         ┌──────────────┐         ┌─────────────┐
│   Frontend  │────────▶│   FastAPI    │────────▶│   Stripe    │
│  Dashboard  │         │   Backend    │         │     API     │
└─────────────┘         └──────────────┘         └─────────────┘
      │                        │                        │
      │                        │                        │
      ▼                        ▼                        ▼
 Checkout UI            Webhook Handler          Checkout Session
 Portal Button          Event Processing         Customer Portal
                        Tier Provisioning        Subscription Mgmt
```

### Data Flow

1. **Subscription Purchase**:
   ```
   User clicks "Upgrade" → Frontend calls /api/billing/create-checkout-session
   → Backend creates Stripe Checkout Session → User redirected to Stripe
   → User completes payment → Stripe sends webhook to /api/billing/webhook
   → Backend provisions tier access → User tier upgraded
   ```

2. **Subscription Management**:
   ```
   User clicks "Manage" → Frontend calls /api/billing/create-portal-session
   → Backend creates Stripe Portal Session → User redirected to portal
   → User updates/cancels subscription → Stripe sends webhook
   → Backend updates tier status → User access modified
   ```

## Implementation Timeline

| Epic | Priority | Time | Status |
|------|----------|------|--------|
| 1. Infrastructure Setup | P0 | 1-2 days | ⏸️ Not Started |
| 2. Checkout Flow | P0 | 3-4 days | ⏸️ Not Started |
| 3. Webhook Handling | P0 | 3-4 days | ⏸️ Not Started |
| 4. Customer Portal | P1 | 1-2 days | ⏸️ Not Started |
| 5. State Management | P1 | 2-3 days | ⏸️ Not Started |
| 6. Testing & Security | P0 | 2-3 days | ⏸️ Not Started |
| 7. Production Deployment | P2 | 1 day | ⏸️ Not Started |

**Total Estimated Time**: 13-19 days (2-3 weeks)

## Documentation Structure

```
docs/stripe/
├── README.md                      # This file - Overview and navigation
├── EPIC_01_INFRASTRUCTURE.md      # Stripe SDK setup, env config, DB migrations
├── EPIC_02_CHECKOUT_FLOW.md       # Create checkout sessions, success/cancel pages
├── EPIC_03_WEBHOOK_HANDLING.md    # Webhook endpoint, event handlers, provisioning
├── EPIC_04_CUSTOMER_PORTAL.md     # Portal configuration, session creation
├── EPIC_05_STATE_MANAGEMENT.md    # Billing service, subscription sync, grace periods
├── EPIC_06_TESTING_SECURITY.md    # Test scenarios, idempotency, security checklist
├── EPIC_07_PRODUCTION.md          # Live mode setup, monitoring, documentation
├── TECHNICAL_REFERENCE.md         # API specs, database schema, code patterns
└── TROUBLESHOOTING.md             # Common issues, debugging, FAQ
```

## Quick Start for Agents

1. **Read Context**: Review this README and `TECHNICAL_REFERENCE.md`
2. **Start with Epic 1**: Follow `EPIC_01_INFRASTRUCTURE.md` step-by-step
3. **Sequential Execution**: Complete epics in order (dependencies exist)
4. **Test After Each Epic**: Validate changes before moving to next epic
5. **Use Technical Reference**: Refer to specs and patterns as needed
6. **Check Troubleshooting**: If stuck, consult `TROUBLESHOOTING.md`

## Key Technical Decisions

### 1. Stripe-Hosted Checkout (Not Embedded)
- **Why**: Faster implementation, Stripe handles PCI compliance, less frontend code
- **Trade-off**: Less UI customization, redirect required
- **Implementation**: Use `ui_mode='hosted'` (default) in Checkout Session

### 2. Webhook-Driven Provisioning (Not Polling)
- **Why**: Real-time updates, scalable, Stripe best practice
- **Trade-off**: Requires public webhook endpoint, signature verification
- **Implementation**: `/api/billing/webhook` receives events from Stripe

### 3. Flexible Billing Mode
- **Why**: Enhanced features (better proration, trial support, invoice schedule)
- **Trade-off**: Requires API version 2025-06-30.basil or later
- **Implementation**: Set `billing_mode='flexible'` in Checkout Session

### 4. No Free Trial (Initially)
- **Why**: Simplified MVP, can add later
- **Trade-off**: Harder to convert free users
- **Implementation**: Can be added in Epic 2 by setting `trial_period_days`

### 5. Customer Portal (Stripe-Hosted)
- **Why**: Full-featured subscription management, no custom UI needed
- **Trade-off**: Less control over UX
- **Implementation**: Configure in Stripe Dashboard, create portal sessions

## Database Changes

### New Columns in `public.profiles`
```sql
stripe_customer_id TEXT UNIQUE          -- Stripe customer identifier
stripe_subscription_id TEXT             -- Active subscription ID
subscription_status TEXT                -- active/past_due/canceled/etc
subscription_current_period_end TIMESTAMPTZ  -- Next billing date
subscription_grace_period_end TIMESTAMPTZ    -- Grace period for failed payments
```

### Updated View: `user_tier_info`
Now includes subscription status for frontend display.

## Environment Variables (New)

```bash
# Stripe API Keys
STRIPE_SECRET_KEY=sk_test_...          # Secret key (backend only)
STRIPE_PUBLISHABLE_KEY=pk_test_...     # Publishable key (frontend safe)
STRIPE_WEBHOOK_SECRET=whsec_...        # Webhook signature verification

# Stripe Product IDs (created in Dashboard)
STRIPE_PRICE_ID_BASIC=price_...   # Basic tier monthly price ($5/mo)
STRIPE_PRICE_ID_PRO=price_...     # Pro tier monthly price ($15/mo - unlimited quizzes)
# Optional: Annual pricing (17% discount)
# STRIPE_PRICE_ID_BASIC_ANNUAL=price_...    # $50/year
# STRIPE_PRICE_ID_PRO_ANNUAL=price_...      # $150/year
```

## Pricing Structure

| Tier | Monthly | Annual | Features |
|------|---------|--------|----------|
| Free | $0 | $0 | 5 quizzes/month |
| Basic | $5.00 | $50/year (17% off) | 100 quizzes/month |
| Pro | $15.00 | $150/year (17% off) | Unlimited quizzes/month |

## Security Considerations

1. **Webhook Signature Verification**: Always verify `Stripe-Signature` header
2. **Price ID Validation**: Never trust frontend price IDs, validate server-side
3. **Customer Isolation**: RLS policies prevent users from accessing others' subscriptions
4. **API Key Protection**: Never expose secret keys to frontend
5. **Idempotency**: Handle duplicate webhook events gracefully
6. **HTTPS Only**: Stripe webhooks require HTTPS in production
7. **Rate Limiting**: Apply rate limits to checkout endpoint

## Testing Strategy

### Test Mode (Development)
- Use Stripe test keys (`sk_test_*`, `pk_test_*`)
- Use Stripe test cards (e.g., `4242 4242 4242 4242`)
- Use Stripe CLI for local webhook testing
- Test all payment scenarios (success, failure, cancellation)

### Production Mode
- Switch to live keys (`sk_live_*`, `pk_live_*`)
- Configure live webhook endpoint in Stripe Dashboard
- Monitor webhook failures and payment errors
- Set up alerts for failed payments

## Monitoring & Observability

1. **Stripe Dashboard**: Monitor payments, subscriptions, disputes
2. **Webhook Logs**: Track event processing in Railway logs
3. **Failed Payments**: Daily reports of payment failures
4. **Churn Metrics**: Track subscription cancellations
5. **Error Alerts**: Webhook failures, API errors, provisioning issues

## Success Criteria

- [ ] Users can subscribe to Basic/Educator tiers via Stripe Checkout
- [ ] Successful payment automatically upgrades user tier
- [ ] Failed payment triggers email notification
- [ ] Subscription cancellation downgrades to free tier
- [ ] Customer portal allows users to manage subscriptions
- [ ] All webhook events processed idempotently
- [ ] Test mode fully functional with test cards
- [ ] Production mode deployed with live keys
- [ ] Documentation complete and up-to-date
- [ ] Monitoring and alerts configured

## Next Steps for Agent

1. **Review Technical Reference**: Read `TECHNICAL_REFERENCE.md` for API specs
2. **Start Epic 1**: Open `EPIC_01_INFRASTRUCTURE.md` and begin implementation
3. **Follow Step-by-Step**: Each epic has detailed implementation instructions
4. **Test Thoroughly**: Validate each epic before moving to the next
5. **Ask Questions**: If unclear, check `TROUBLESHOOTING.md` or ask for clarification

## Support & Resources

- **Stripe Documentation**: https://docs.stripe.com/billing/subscriptions/build-subscriptions
- **Stripe API Reference**: https://docs.stripe.com/api
- **Stripe Test Cards**: https://docs.stripe.com/testing
- **Stripe CLI**: https://docs.stripe.com/stripe-cli
- **Webhook Testing**: https://docs.stripe.com/webhooks/test

---

**Last Updated**: 2025-11-19  
**Status**: Planning Phase  
**Next Action**: Begin Epic 1 - Infrastructure Setup
