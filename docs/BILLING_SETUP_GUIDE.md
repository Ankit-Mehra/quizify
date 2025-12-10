# Billing System Setup Guide

This guide covers all external changes and configurations needed to deploy the Quizify billing system.

---

## Table of Contents

1. [Database Migrations](#1-database-migrations)
2. [Stripe Dashboard Setup](#2-stripe-dashboard-setup)
3. [Environment Variables](#3-environment-variables)
4. [Stripe Webhook Configuration](#4-stripe-webhook-configuration)
5. [Credit System Overview](#5-credit-system-overview)
6. [Testing Checklist](#6-testing-checklist)

---

## 1. Database Migrations

Apply these migrations to your Supabase database **in order**:

### Migration 029: Hybrid Credit System

```bash
# Via Supabase SQL Editor or CLI
psql -f migrations/029_hybrid_credit_system.sql
```

**What it does:**
- Adds `credit_units_purchased`, `free_credit_units_remaining`, `free_credit_units_monthly` columns to `profiles` table
- Adds `billing_plan` column (`free` | `pro`)
- Creates `credit_balance_info` view for querying user credit status
- Sets up `handle_new_user` trigger to initialize new users with credits
- Backfills existing users with appropriate credit values

### Migration 030: Atomic Credit Operations

```bash
psql -f migrations/030_atomic_credit_operations.sql
```

**What it does:**
- Creates `consume_credit_units(user_id, units)` RPC function
- Creates `add_purchased_credit_units(user_id, units)` RPC function
- Both use `FOR UPDATE` row locking to prevent race conditions
- Restricted to `service_role` only (backend calls)

### Applying via Supabase MCP

Alternatively, use the Supabase MCP tools:

```
mcp_supabase_apply_migration with the SQL content
```

---

## 2. Stripe Dashboard Setup

### A. Create Credit Pack Products (One-time Purchases)

Go to **Stripe Dashboard → Products → Add Product**

| Product Name | Price | Type | Credits | Units |
|--------------|-------|------|---------|-------|
| 5 Credits | $5.00 USD | One-time | 5 | 10 |
| 10 Credits | $10.00 USD | One-time | 10 | 20 |
| 15 Credits | $15.00 USD | One-time | 15 | 30 |

**For each product:**
1. Click "Add Product"
2. Name: "5 Credits" (or 10, 15)
3. Pricing: One-time, $5.00 (or $10, $15)
4. Save and copy the **Price ID** (starts with `price_`)

### B. Create Subscription Products (Optional)

| Product Name | Price | Billing | Credits/Month | Units/Month |
|--------------|-------|---------|---------------|-------------|
| Pro Monthly | $X/month | Recurring | 30 | 60 |
| Pro Yearly | $Y/year | Recurring | 30/month | 60/month |

### C. Copy Price IDs

After creating products, you'll have Price IDs like:
- `price_1ABC123...` (5 Credits - $5)
- `price_1DEF456...` (10 Credits - $10)
- `price_1GHI789...` (15 Credits - $15)
- `price_1JKL012...` (Pro Monthly)

---

## 3. Environment Variables

Add these to your `.env` file or Railway/deployment environment:

```bash
# =============================================================================
# STRIPE API KEYS
# =============================================================================
# Get from: https://dashboard.stripe.com/apikeys
STRIPE_SECRET_KEY=<your-stripe-secret-key>          # sk_live_xxx or sk_test_xxx
STRIPE_PUBLISHABLE_KEY=<your-stripe-publishable-key>     # pk_live_xxx or pk_test_xxx

# =============================================================================
# STRIPE WEBHOOK SECRET
# =============================================================================
# Get from: Stripe Dashboard → Developers → Webhooks → Your endpoint → Signing secret
STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxx

# =============================================================================
# CREDIT PACK PRICE IDS
# =============================================================================
# Get from: Stripe Dashboard → Products → Click product → Copy Price ID
STRIPE_PRICE_ID_CREDITS_5=price_xxxxxxxxxxxx    # $5 - 5 credits
STRIPE_PRICE_ID_CREDITS_10=price_xxxxxxxxxxxx   # $10 - 10 credits
STRIPE_PRICE_ID_CREDITS_15=price_xxxxxxxxxxxx   # $15 - 15 credits

# =============================================================================
# SUBSCRIPTION PRICE IDS (if using subscriptions)
# =============================================================================
STRIPE_PRICE_ID_PRO=price_xxxxxxxxxxxx          # Pro Monthly subscription

# =============================================================================
# STRIPE REDIRECT URLS
# =============================================================================
# Where to redirect after checkout
STRIPE_SUCCESS_URL=https://www.quizify.ca/billing/success
STRIPE_CANCEL_URL=https://www.quizify.ca/billing
```

---

## 4. Stripe Webhook Configuration

### A. Create Webhook Endpoint

1. Go to **Stripe Dashboard → Developers → Webhooks**
2. Click **"Add endpoint"**
3. Enter your endpoint URL:
   ```
   https://your-api-domain.com/api/billing/webhook
   ```
   
   For Railway:
   ```
   https://quizify-api.up.railway.app/api/billing/webhook
   ```

### B. Select Events to Listen For

Select these events:

| Event | Purpose |
|-------|---------|
| `checkout.session.completed` | Credit pack purchases & new subscriptions |
| `invoice.paid` | Subscription renewals (monthly credit reset) |
| `customer.subscription.deleted` | Subscription cancellations |
| `customer.subscription.updated` | Plan changes (upgrade/downgrade) |

### C. Copy Webhook Signing Secret

After creating the webhook:
1. Click on your endpoint
2. Click **"Reveal"** under Signing secret
3. Copy the `whsec_...` value
4. Add to `STRIPE_WEBHOOK_SECRET` environment variable

### D. Test Webhook (Development)

For local development, use Stripe CLI:

```bash
# Install Stripe CLI
brew install stripe/stripe-cli/stripe

# Login
stripe login

# Forward webhooks to local server
stripe listen --forward-to localhost:8000/api/billing/webhook

# Copy the webhook signing secret it provides (whsec_...)
```

---

## 5. Credit System Overview

### Credit Packs

| Price | Credits | Units | Standard Quizzes | Enhanced Quizzes |
|-------|---------|-------|------------------|------------------|
| $5 | 5 | 10 | 5 | 2-3 |
| $10 | 10 | 20 | 10 | 5 |
| $15 | 15 | 30 | 15 | 7-8 |

### Quiz Costs

| Quiz Type | Credits | Units |
|-----------|---------|-------|
| Standard | 1 | 2 |
| Enhanced | 2 | 4 |

### 3-Bucket Credit System

Credits are consumed in this priority order:

1. **Purchased Credits** (credit packs) - Never expire, used first
2. **Free Credits** (monthly allowance) - 3 credits/month for all users
3. **Subscription Credits** (Pro only) - 30 credits/month

### User Tiers

| Tier | Monthly Free | Monthly Subscription | Total |
|------|--------------|---------------------|-------|
| Free | 3 credits | 0 | 3 credits/month |
| Pro | 3 credits | 30 credits | 33 credits/month |

---

## 6. Testing Checklist

### Before Going Live

- [ ] **Migrations applied** - Both 029 and 030 migrations run successfully
- [ ] **Stripe products created** - 3 credit packs + subscription (if using)
- [ ] **Environment variables set** - All STRIPE_* variables configured
- [ ] **Webhook endpoint created** - Receiving events from Stripe
- [ ] **Webhook secret configured** - STRIPE_WEBHOOK_SECRET set

### Test Scenarios

#### Credit Pack Purchase
1. Call `POST /api/billing/checkout/credits?pack_size=5`
2. Complete Stripe checkout
3. Verify `checkout.session.completed` webhook received
4. Verify `credit_units_purchased` increased by 10 (5 credits)

#### Credit Consumption
1. Generate a quiz
2. Verify credits deducted in correct priority (purchased → free → subscription)
3. Verify atomic RPC prevents double-spending

#### Subscription Flow (if using)
1. Call `POST /api/billing/checkout/subscription`
2. Complete Stripe checkout
3. Verify subscription active
4. Wait for renewal (or trigger `invoice.paid` manually)
5. Verify credits reset

### Stripe Test Cards

| Card Number | Scenario |
|-------------|----------|
| 4242 4242 4242 4242 | Successful payment |
| 4000 0000 0000 0002 | Card declined |
| 4000 0000 0000 3220 | 3D Secure required |

Use any future expiry date and any 3-digit CVC.

---

## Troubleshooting

### Webhook Not Receiving Events

1. Check Stripe Dashboard → Webhooks → Your endpoint → Recent events
2. Verify endpoint URL is correct and accessible
3. Check for 4xx/5xx errors in webhook logs
4. Ensure `STRIPE_WEBHOOK_SECRET` matches the endpoint's signing secret

### Credits Not Adding After Purchase

1. Check webhook logs for `checkout.session.completed` event
2. Verify `metadata.type` is `"credit_pack"` in the session
3. Check backend logs for RPC errors
4. Verify migration 030 was applied (RPC functions exist)

### RPC Permission Denied

If you see "Access denied: this function requires service_role privileges":
1. Ensure you're using the **service role key** (not anon key)
2. Verify `SUPABASE_KEY` in environment is the service role key
3. Check that migration 030 GRANT statements were applied

---

## Quick Reference

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/billing/checkout/credits?pack_size=5\|10\|15` | POST | Create credit pack checkout |
| `/api/billing/checkout/subscription` | POST | Create subscription checkout |
| `/api/billing/webhook` | POST | Stripe webhook handler |
| `/api/billing/credits` | GET | Get user's credit balance |

### Database Tables/Views

| Name | Type | Description |
|------|------|-------------|
| `profiles` | Table | User profiles with credit columns |
| `user_tier_info` | View | User billing info with credit status |

### RPC Functions

| Function | Parameters | Returns | Description |
|----------|------------|---------|-------------|
| `consume_credit_units` | `user_id`, `units` | `BOOLEAN` | Atomically consume credits |
| `add_purchased_credit_units` | `user_id`, `units` | `VOID` | Add purchased credits |
