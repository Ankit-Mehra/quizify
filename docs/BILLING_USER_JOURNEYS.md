# Billing System User Journeys

This document visualizes the user journeys and backend processes for Quizify's hybrid credit-based billing system.

> **Last Updated**: After migrations 031 & 032 - Split free/paid credit buckets + Atomic operations

## System Overview

The billing system uses a **3-bucket credit architecture** with **atomic operations** to prevent race conditions:

```mermaid
%%{init: {'theme': 'dark'}}%%
flowchart TB
    subgraph Users["User Tiers"]
        Free["🆓 Free Tier"]
        Pro["⭐ Pro Tier"]
    end
    
    subgraph Buckets["Credit Buckets (3 Types)"]
        Purchased["💰 Purchased Credits<br/>(credit_units_purchased)<br/>Never expire"]
        FreeBucket["🎁 Free Credits<br/>(free_credit_units_remaining)<br/>6 units/month for all users"]
        Subscription["📅 Subscription Credits<br/>(credit_units_remaining)<br/>Pro only, reset on invoice.paid"]
    end
    
    subgraph Consumption["Quiz Generation"]
        Standard["📝 Standard Quiz<br/>1 unit (0.5 credits)"]
        Enhanced["🚀 Enhanced Quiz<br/>2 units (1 credit)"]
    end
    
    subgraph Order["Consumption Order (Optimized)"]
        First["1️⃣ Purchased First"]
        Second["2️⃣ Free Second"]
        Third["3️⃣ Subscription Last"]
    end
    
    Free --> FreeBucket
    Free -.-> Purchased
    Pro --> FreeBucket
    Pro --> Subscription
    Pro -.-> Purchased
    
    Purchased --> First
    FreeBucket --> Second
    Subscription --> Third
    
    First --> Consumption
    Second --> Consumption
    Third --> Consumption
```

> **Key Change (Migration 032)**: Consumption order is now `Purchased → Free → Subscription` to preserve paid subscription credits longest.

## Credit Bucket Reference

### Buckets by Tier

| Bucket | Free Tier | Pro Tier | Reset Mechanism |
|--------|-----------|----------|-----------------|
| **Purchased** (`credit_units_purchased`) | ✅ Can buy | ✅ Can buy | Never resets |
| **Free** (`free_credit_units_remaining`) | 6 units/month | 6 units/month | Cron job (free users) / `invoice.paid` (Pro users) |
| **Subscription** (`credit_units_remaining`) | ❌ N/A | 60 units/month | `invoice.paid` webhook |

### Consumption Priority (Updated)

| Priority | Bucket | Rationale |
|----------|--------|-----------|
| 1️⃣ First | Purchased | Use one-time purchases first (never expire anyway) |
| 2️⃣ Second | Free | Use free allowance before paid subscription |
| 3️⃣ Last | Subscription | Preserve paid subscription credits longest |

### Unit Costs

| Item | Units | Credits |
|------|-------|---------|
| Standard Quiz | 1 unit | 0.5 credits |
| Enhanced Quiz | 2 units | 1 credit |

### Credit Packs (One-time Purchase)

| Pack Size | Units | Price ID Config |
|-----------|-------|-----------------|
| 10 credits | 20 units | `STRIPE_PRICE_ID_CREDITS_10` |
| 30 credits | 60 units | `STRIPE_PRICE_ID_CREDITS_30` |
| 100 credits | 200 units | `STRIPE_PRICE_ID_CREDITS_100` |

---

## Free Tier User Journey

```mermaid
%%{init: {'theme': 'dark'}}%%
sequenceDiagram
    autonumber
    participant User as 👤 Free User
    participant Frontend as 🖥️ Frontend
    participant API as 🔧 FastAPI
    participant Billing as 💳 Billing Service
    participant Supabase as 🗄️ Supabase
    participant Cron as ⏰ Cron Job

    Note over User,Cron: 🆓 FREE TIER JOURNEY (3-Bucket System)

    Note over User,Supabase: ═══ INITIAL SIGN UP ═══
    User->>Frontend: Sign up for account
    Frontend->>API: POST /api/auth/signup
    API->>Supabase: Create user in auth.users
    Supabase->>Supabase: Trigger: handle_new_user()
    Note over Supabase: Creates profile with:<br/>• credit_units_remaining: 0<br/>• credit_units_purchased: 0<br/>• free_credit_units_remaining: 6<br/>• current_period_end: calendar month end
    API-->>Frontend: Account created
    Frontend-->>User: Welcome! You have 3 free credits

    Note over User,Supabase: ═══ QUIZ GENERATION (Atomic RPC) ═══
    User->>Frontend: Generate Standard Quiz
    Frontend->>API: POST /api/quiz/generate {quiz_type: "standard"}
    API->>Billing: consume_units(user_id, "standard")
    Billing->>Supabase: RPC: consume_credit_units(user_id, 1)
    Note over Supabase: Atomic operation with row lock<br/>Order: purchased → free → subscription
    Supabase-->>Billing: true (success)
    Billing-->>API: ✅ Consumption successful
    API->>API: Generate quiz via OpenAI
    API-->>Frontend: Quiz data
    Frontend-->>User: Quiz ready! (5 free units remaining)

    Note over User,Supabase: ═══ PURCHASE CREDIT PACK ═══
    User->>Frontend: Buy 10 credits pack
    Frontend->>API: POST /api/billing/checkout/credits {pack_size: "10"}
    API->>API: Create Stripe checkout (mode: payment)
    Note over User: ... completes Stripe payment ...
    API->>Billing: add_purchased_units(user_id, 20)
    Billing->>Supabase: RPC: add_purchased_credit_units(user_id, 20)
    Note over Supabase: Atomic increment (race-safe)
    Note over User: Now has: purchased=20, free=5

    Note over User,Supabase: ═══ QUIZ WITH PURCHASED CREDITS ═══
    User->>Frontend: Generate Enhanced Quiz
    Frontend->>API: POST /api/quiz/generate {quiz_type: "enhanced"}
    API->>Billing: consume_units(user_id, "enhanced")
    Billing->>Supabase: RPC: consume_credit_units(user_id, 2)
    Note over Supabase: Atomic: purchased used FIRST!
    Billing-->>API: ✅ Success
    Frontend-->>User: Quiz ready! (purchased: 18, free: 5)

    Note over Cron,Supabase: ═══ MONTHLY RESET (Free Users Only) ═══
    Cron->>API: POST /cron/reset-monthly-credits (X-Cron-API-Key)
    API->>API: Validate CRON_API_KEY (required in production)
    API->>Billing: reset_expired_monthly_credits()
    Billing->>Supabase: SELECT expired profiles WHERE NOT active Pro
    Supabase-->>Billing: Free users needing reset
    Note over Billing: Pro users with active subs SKIPPED!
    loop Each expired FREE user
        Billing->>Supabase: UPDATE free_credit_units_remaining = 6
    end
    Billing-->>API: {reset_count: N}
    API-->>Cron: 200 OK
    Note over User: Free credits refreshed! (calendar month boundaries)
```

---

## Pro Tier User Journey

```mermaid
%%{init: {'theme': 'dark'}}%%
sequenceDiagram
    autonumber
    participant User as 👤 User
    participant Frontend as 🖥️ Frontend
    participant API as 🔧 FastAPI
    participant Billing as 💳 Billing Service
    participant Stripe as 💵 Stripe
    participant Supabase as 🗄️ Supabase

    Note over User,Supabase: ⭐ PRO TIER JOURNEY (3-Bucket System)

    %% ── Upgrade Flow ──────────────────────────────
    Note over User,Stripe: 🔄 Subscribe to Pro
    User->>Frontend: Click "Upgrade to Pro"
    Frontend->>API: POST /api/billing/checkout<br/>{tier: "pro"}
    API->>Stripe: Create Checkout Session<br/>(mode: subscription)
    Stripe-->>API: Session URL
    Frontend->>Stripe: Redirect to Stripe Checkout
    User->>Stripe: Enter payment details
    Stripe-->>User: Payment successful

    %% ── Webhook Processing ────────────────────────
    Note over Stripe,Supabase: 📨 Webhook: checkout.session.completed
    Stripe->>API: POST /api/billing/webhook<br/>checkout.session.completed
    API->>Billing: handle_checkout_completed()
    
    Billing->>Supabase: UPDATE profiles SET<br/>billing_plan = 'pro',<br/>credit_units_remaining = 60,<br/>free_credit_units_remaining = 6,<br/>current_period_end = subscription_end
    
    Note over Supabase: Pro user now has:<br/>• subscription: 60 units<br/>• free: 6 units (also reset!)<br/>• purchased: preserved
    
    Billing-->>API: ✅ Upgrade complete
    API-->>Stripe: 200 OK

    %% ── Pro Usage ─────────────────────────────────
    Note over User,Supabase: 🎯 Pro User Generates Quizzes
    User->>Frontend: Generate Enhanced Quiz
    Frontend->>API: POST /api/quiz/generate<br/>{quiz_type: "enhanced"}
    API->>Billing: consume_units(user_id, "enhanced")
    Billing->>Supabase: RPC: consume_credit_units(user_id, 2)
    
    Note over Supabase: Order: purchased → FREE → subscription<br/>No purchased, use FREE first!
    
    Billing-->>API: ✅ Success
    Frontend-->>User: Quiz ready!<br/>(free: 4, subscription: 60)

    %% ── Pro Monthly Reset (via Invoice) ──────────
    Note over Stripe,Supabase: 📅 Monthly Renewal: invoice.paid
    Stripe->>Stripe: Monthly billing cycle
    Stripe->>API: POST /api/billing/webhook<br/>invoice.paid
    API->>Billing: handle_invoice_paid()
    
    Billing->>Supabase: Get user by stripe_customer_id
    Supabase-->>Billing: User data
    
    Billing->>Supabase: UPDATE profiles SET<br/>credit_units_remaining = 60,<br/>free_credit_units_remaining = 6,<br/>current_period_start = period_start,<br/>current_period_end = period_end
    
    Note over Supabase: Resets BOTH subscription AND free!<br/>Purchased unchanged
    
    Billing-->>API: ✅ All credits refreshed
    API-->>Stripe: 200 OK

    %% ── Cancellation ──────────────────────────────
    Note over Stripe,Supabase: ❌ Subscription Cancelled
    Stripe->>API: POST /api/billing/webhook<br/>customer.subscription.deleted
    API->>Billing: handle_subscription_cancelled()
    
    Billing->>Supabase: UPDATE profiles SET<br/>billing_plan = 'free',<br/>credit_units_remaining = 0
    
    Note over Supabase: After cancellation:<br/>• subscription: 0 (cleared)<br/>• free: preserved<br/>• purchased: preserved
    
    Billing-->>API: ✅ Downgraded to free
```

---

## Credit Pack Purchase Flow

```mermaid
%%{init: {'theme': 'dark'}}%%
sequenceDiagram
    autonumber
    participant User as 👤 User (Any Tier)
    participant Frontend as 🖥️ Frontend
    participant API as 🔧 FastAPI
    participant Billing as 💳 Billing Service
    participant Stripe as 💵 Stripe
    participant Supabase as 🗄️ Supabase

    Note over User,Supabase: 💰 CREDIT PACK PURCHASE

    %% ── Purchase Flow ─────────────────────────────
    Note over User,Stripe: 🛒 Buy Credit Pack
    User->>Frontend: Select "30 Credits" pack
    Frontend->>API: POST /api/billing/checkout/credits<br/>{pack_size: "30"}
    API->>API: Validate pack_size ∈ ["10", "30", "100"]
    API->>API: units = CREDIT_PACK_UNITS["30"] = 60
    API->>Stripe: Create Checkout Session<br/>(mode: payment, metadata: {type: credit_pack})
    Stripe-->>API: Session URL
    Frontend->>Stripe: Redirect to checkout
    User->>Stripe: Complete payment
    Stripe-->>User: Success!

    %% ── Webhook - Add to Purchased Bucket (Atomic) ─────
    Note over Stripe,Supabase: 📦 Fulfill Credit Pack (Atomic)
    Stripe->>API: POST /api/billing/webhook<br/>checkout.session.completed
    API->>API: Check mode == 'payment'<br/>and metadata.type == 'credit_pack'
    API->>Billing: add_purchased_units(user_id, 60)
    
    Billing->>Supabase: RPC: add_purchased_credit_units(user_id, 60)
    Note over Supabase: Atomic increment with row lock<br/>Prevents race conditions
    
    Note over Supabase: Purchased bucket only!<br/>Free & subscription unchanged
    
    Billing-->>API: ✅ Credits added
    API-->>Stripe: 200 OK
```

---

## Credit Consumption Logic (Atomic RPC)

```mermaid
%%{init: {'theme': 'dark'}}%%
flowchart TB
    Start([Generate Quiz Request]) --> CheckType{Quiz Type?}
    
    CheckType -->|Standard| Units1[Units needed: 1]
    CheckType -->|Enhanced| Units2[Units needed: 2]
    
    Units1 --> CallRPC
    Units2 --> CallRPC
    
    CallRPC[Call RPC: consume_credit_units<br/>with FOR UPDATE lock] --> LockRow
    
    LockRow[🔒 Lock profile row<br/>Prevents concurrent access] --> CheckTotal{total available<br/>>= needed?}
    
    CheckTotal -->|No| Reject[❌ Return FALSE<br/>API returns 402]
    CheckTotal -->|Yes| DeductPurchased
    
    DeductPurchased{purchased >= needed?}
    DeductPurchased -->|Yes| TakePurchased[Deduct ALL from<br/>purchased bucket]
    DeductPurchased -->|No| PartialPurchased[Take what's available<br/>from purchased]
    
    PartialPurchased --> DeductFree
    
    DeductFree{free >= remaining?}
    DeductFree -->|Yes| TakeFree[Deduct rest from<br/>FREE bucket]
    DeductFree -->|No| PartialFree[Take what's available<br/>from free]
    
    PartialFree --> DeductSubscription[Deduct rest from<br/>subscription bucket]
    
    TakePurchased --> UpdateDB
    TakeFree --> UpdateDB
    DeductSubscription --> UpdateDB
    
    UpdateDB[Atomic UPDATE all 3 buckets<br/>Release row lock 🔓] --> Success
    
    Success[✅ Return TRUE<br/>Generate Quiz via OpenAI] --> Return([Return Quiz Data])
    Reject --> Upsell([Show upgrade/<br/>purchase options])
    
    style Start fill:#e1f5fe,color:#1a1a1a
    style Return fill:#c8e6c9,color:#1a1a1a
    style Reject fill:#ffcdd2,color:#1a1a1a
    style Upsell fill:#fff3e0,color:#1a1a1a
    style LockRow fill:#fff9c4,color:#1a1a1a
    style DeductPurchased fill:#fff9c4,color:#1a1a1a
    style DeductFree fill:#c8e6c9,color:#1a1a1a
    style DeductSubscription fill:#e1bee7,color:#1a1a1a
```

> **Key Improvement (Migration 032)**: All credit operations now use PostgreSQL RPCs with `FOR UPDATE` row locking to prevent double-spending under concurrent load.

---

## Tier Comparison (3-Bucket)

```mermaid
%%{init: {'theme': 'dark'}}%%
flowchart LR
    subgraph Free["🆓 Free Tier"]
        F1["🎁 Free: 6 units/month"]
        F2["📅 Subscription: N/A"]
        F3["💰 Purchased: Can buy"]
        F4["⏰ Reset: Cron job<br/>(calendar month)"]
    end
    
    subgraph Pro["⭐ Pro Tier"]
        P1["🎁 Free: 6 units/month"]
        P2["📅 Subscription: 60 units/month"]
        P3["💰 Purchased: Can buy"]
        P4["⏰ Reset: invoice.paid<br/>(both free + subscription)"]
    end
    
    subgraph Packs["💰 Credit Packs"]
        C1["10 credits = 20 units"]
        C2["30 credits = 60 units"]
        C3["100 credits = 200 units"]
        C4["Never expire"]
        C5["Used FIRST"]
    end
```

---

## Monthly Reset Scenarios

This section documents all credit reset scenarios and how they're handled:

### Scenario Matrix

| User Type | Reset Trigger | What Resets | Period Handling |
|-----------|---------------|-------------|-----------------|
| **Free user** (expired period) | Cron job | `free_credit_units_remaining` → 6 | Calendar month boundaries |
| **Free user** (null period) | Cron job | `free_credit_units_remaining` → 6 | Sets calendar month boundaries |
| **Pro user** (active sub) | `invoice.paid` webhook | Both `free` (→6) AND `subscription` (→60) | Stripe period dates |
| **Pro user** (trialing) | `invoice.paid` webhook | Both `free` (→6) AND `subscription` (→60) | Stripe period dates |
| **Cancelled Pro** (now free) | Cron job | `free_credit_units_remaining` → 6 | Calendar month boundaries |
| **New signup** | Trigger: `handle_new_user()` | Initial: `free` = 6, `subscription` = 0 | Calendar month start → next month |

### Reset Flow Diagram

```mermaid
%%{init: {'theme': 'dark'}}%%
flowchart TB
    subgraph Triggers["Reset Triggers"]
        Cron["⏰ Cron Job<br/>(runs daily)"]
        Invoice["💳 Stripe invoice.paid<br/>(monthly renewal)"]
        Signup["👤 New User Signup<br/>(trigger)"]
    end
    
    subgraph UserTypes["User Classification"]
        FreeActive["Free User<br/>(period expired)"]
        FreeNull["Free User<br/>(null period)"]
        ProActive["Pro User<br/>(active/trialing sub)"]
        CancelledPro["Cancelled Pro<br/>(no active sub)"]
    end
    
    subgraph Actions["Reset Actions"]
        ResetFreeOnly["Reset FREE bucket only<br/>free_credit_units_remaining = 6"]
        ResetBoth["Reset BOTH buckets<br/>subscription = 60, free = 6"]
        InitialCredits["Initialize credits<br/>free = 6, subscription = 0"]
    end
    
    subgraph Periods["Period Handling"]
        CalendarMonth["📅 Calendar Month<br/>date_trunc('month', now())<br/>→ next month start"]
        StripePeriod["💳 Stripe Period<br/>current_period_start<br/>→ current_period_end"]
    end
    
    Cron --> FreeActive
    Cron --> FreeNull
    Cron --> CancelledPro
    Cron -.->|SKIPPED| ProActive
    
    Invoice --> ProActive
    Signup --> InitialCredits
    
    FreeActive --> ResetFreeOnly
    FreeNull --> ResetFreeOnly
    CancelledPro --> ResetFreeOnly
    ProActive --> ResetBoth
    
    ResetFreeOnly --> CalendarMonth
    ResetBoth --> StripePeriod
    InitialCredits --> CalendarMonth
    
    style ProActive fill:#e1bee7,color:#1a1a1a
    style ResetBoth fill:#c8e6c9,color:#1a1a1a
    style StripePeriod fill:#fff9c4,color:#1a1a1a
```

### Detailed Scenarios

#### 1️⃣ Free User Monthly Reset (Cron)

```mermaid
%%{init: {'theme': 'dark'}}%%
sequenceDiagram
    participant Cron as ⏰ Cron Job
    participant API as 🔧 API
    participant Billing as 💳 Billing Service
    participant DB as 🗄️ Supabase

    Note over Cron,DB: Free User: Period Expired

    Cron->>API: POST /cron/reset-monthly-credits
    API->>Billing: reset_expired_monthly_credits()
    
    Billing->>DB: SELECT profiles WHERE<br/>period_end <= NOW()<br/>AND (billing_plan != 'pro'<br/>OR subscription_status NOT IN ('active', 'trialing'))
    
    DB-->>Billing: [{id: "user123", billing_plan: "free", period_end: "2024-12-01"}]
    
    Note over Billing: ✅ Free user - PROCESS
    
    Billing->>DB: UPDATE profiles SET<br/>free_credit_units_remaining = 6,<br/>current_period_start = '2024-12-01',<br/>current_period_end = '2025-01-01'
    
    Note over DB: Uses calendar month boundaries!
    
    Billing-->>API: {reset_count: 1}
```

#### 2️⃣ Pro User Monthly Reset (Stripe Webhook)

```mermaid
%%{init: {'theme': 'dark'}}%%
sequenceDiagram
    participant Stripe as 💳 Stripe
    participant API as 🔧 API
    participant Billing as 💳 Billing Service
    participant DB as 🗄️ Supabase

    Note over Stripe,DB: Pro User: Subscription Renewal

    Stripe->>API: POST /billing/webhook<br/>invoice.paid
    API->>Billing: handle_invoice_paid()
    
    Billing->>Stripe: Get subscription details
    Stripe-->>Billing: {period_start: 1733011200, period_end: 1735689600}
    
    Billing->>DB: UPDATE profiles SET<br/>credit_units_remaining = 60,<br/>free_credit_units_remaining = 6,<br/>current_period_start = '2024-12-01',<br/>current_period_end = '2025-01-01'
    
    Note over DB: Resets BOTH buckets!<br/>Uses Stripe period dates
    
    Billing-->>API: ✅ Credits refreshed
```

#### 3️⃣ Pro User Skipped by Cron

```mermaid
%%{init: {'theme': 'dark'}}%%
sequenceDiagram
    participant Cron as ⏰ Cron Job
    participant Billing as 💳 Billing Service
    participant DB as 🗄️ Supabase

    Note over Cron,DB: Pro User with Active Sub: SKIPPED

    Cron->>Billing: reset_expired_monthly_credits()
    
    Billing->>DB: SELECT profiles WHERE period_end <= NOW()
    
    DB-->>Billing: [{id: "pro_user", billing_plan: "pro",<br/>subscription_status: "active"}]
    
    Note over Billing: ❌ Pro + active sub - SKIP!<br/>Managed by Stripe webhook
    
    Billing->>Billing: Filter out Pro active users
    
    Note over Billing: 0 users to reset
```

#### 4️⃣ Cancelled Pro User (Now Free)

```mermaid
%%{init: {'theme': 'dark'}}%%
sequenceDiagram
    participant Cron as ⏰ Cron Job
    participant Billing as 💳 Billing Service
    participant DB as 🗄️ Supabase

    Note over Cron,DB: Cancelled Pro: Treated as Free

    Cron->>Billing: reset_expired_monthly_credits()
    
    Billing->>DB: SELECT profiles WHERE period_end <= NOW()
    
    DB-->>Billing: [{id: "ex_pro", billing_plan: "pro",<br/>subscription_status: "canceled"}]
    
    Note over Billing: ✅ Pro but CANCELED - PROCESS!<br/>(subscription_status not in active/trialing)
    
    Billing->>DB: UPDATE profiles SET<br/>free_credit_units_remaining = 6,<br/>current_period_start = month_start,<br/>current_period_end = next_month
    
    Note over DB: Only free bucket reset<br/>(subscription bucket is 0 anyway)
```

---

## Reset Mechanisms Summary

| Bucket | Free Users | Pro Users (Active) | Pro Users (Cancelled) |
|--------|------------|--------------------|-----------------------|
| **Free** | Cron → 6 | `invoice.paid` → 6 | Cron → 6 |
| **Subscription** | N/A (always 0) | `invoice.paid` → 60 | N/A (cleared on cancel) |
| **Purchased** | Never resets | Never resets | Never resets |
| **Period Source** | Calendar month | Stripe period | Calendar month |

### Cron Job Flow (Free Credits Reset - Free Users Only)

```mermaid
%%{init: {'theme': 'dark'}}%%
sequenceDiagram
    participant Railway as ⏰ Railway Cron
    participant API as 🔧 Cron Endpoint
    participant Billing as 💳 Billing Service
    participant DB as 🗄️ Supabase

    Note over Railway,DB: Runs daily at midnight UTC

    Railway->>API: POST /api/cron/reset-monthly-credits<br/>X-Cron-API-Key: {secret}
    
    alt Production: CRON_API_KEY not set
        API->>API: ❌ 503 Service Unavailable<br/>(blocked for security)
    else Development: CRON_API_KEY not set
        API->>API: ⚠️ Log warning, allow (dev mode)
    else CRON_API_KEY set
        API->>API: ✅ Validate key matches
        alt Invalid key
            API-->>Railway: 401 Unauthorized
        end
    end
    
    API->>Billing: reset_expired_monthly_credits()
    
    Billing->>DB: SELECT id, billing_plan, subscription_status<br/>FROM profiles<br/>WHERE current_period_end <= NOW()<br/>OR current_period_end IS NULL
    DB-->>Billing: All users needing reset
    
    Note over Billing: Filter: SKIP Pro users with<br/>subscription_status IN ('active', 'trialing')
    
    Billing->>Billing: free_profiles = filter(not active Pro)
    
    loop Each FREE user (expired period)
        Billing->>DB: UPDATE profiles SET<br/>free_credit_units_remaining = 6,<br/>current_period_start = date_trunc('month', now()),<br/>current_period_end = date_trunc('month', now()) + '1 month'
    end
    
    Note over Billing: Uses CALENDAR MONTH boundaries<br/>Not rolling 30 days!
    
    Billing-->>API: {reset_count: N, skipped_pro: M}
    API-->>Railway: 200 OK
```

---

## Stripe Webhook Events

| Event | Mode | Handler | Action |
|-------|------|---------|--------|
| `checkout.session.completed` | subscription | `handle_checkout_completed` | Set `billing_plan='pro'`, `credit_units_remaining=60`, `free_credit_units_remaining=6` |
| `checkout.session.completed` | payment | `handle_credit_pack_purchase` | Atomic add to `credit_units_purchased` via RPC |
| `invoice.paid` | - | `handle_invoice_paid` | Reset BOTH `credit_units_remaining=60` AND `free_credit_units_remaining=6` |
| `customer.subscription.deleted` | - | `handle_subscription_cancelled` | Set `billing_plan='free'`, `credit_units_remaining=0` |

---

## Database Schema (After Migrations 031 & 032)

```mermaid
%%{init: {'theme': 'dark'}}%%
erDiagram
    profiles {
        uuid id PK
        text billing_plan "free | pro"
        int credit_units_monthly "Legacy (kept for compat)"
        int credit_units_remaining "Subscription bucket (Pro)"
        int credit_units_purchased "Purchased bucket (never expires)"
        int free_credit_units_monthly "Free allowance (default 6)"
        int free_credit_units_remaining "Free bucket remaining"
        timestamp current_period_start "Period start"
        timestamp current_period_end "Period end (for reset)"
        text stripe_customer_id
        text stripe_subscription_id
        text subscription_status
    }
```

### Key Column Descriptions

| Column | Purpose | Reset By |
|--------|---------|----------|
| `credit_units_remaining` | Pro subscription credits (60/month) | `invoice.paid` webhook |
| `credit_units_purchased` | One-time purchased credits | Never resets |
| `free_credit_units_remaining` | Free monthly allowance | Cron job |
| `free_credit_units_monthly` | Monthly free allowance amount (default 6) | Manual only |
| `current_period_end` | When to reset free credits | Updated on reset |

---

## API Response: `/api/billing/balance`

```json
{
  "plan": "free",
  "credits_remaining": 8.0,
  "free_credits_monthly": 3.0,
  "free_credits_remaining": 3.0,
  "subscription_credits_remaining": 0.0,
  "purchased_credits": 5.0,
  "period_end": "2025-01-09T00:00:00Z"
}
```

### Response Fields

| Field | Description |
|-------|-------------|
| `plan` | Current billing plan (`free` or `pro`) |
| `credits_remaining` | Total across all buckets (for UI display) |
| `free_credits_monthly` | Monthly free allowance (always 3 credits) |
| `free_credits_remaining` | Remaining in free bucket |
| `subscription_credits_remaining` | Remaining in subscription bucket (Pro only) |
| `purchased_credits` | Remaining in purchased bucket |
| `period_end` | When free credits reset |

---

## Configuration Reference

### Environment Variables

| Variable | Purpose | Required |
|----------|---------|----------|
| `STRIPE_SECRET_KEY` | Stripe API authentication | ✅ |
| `STRIPE_WEBHOOK_SECRET` | Webhook signature verification | ✅ |
| `STRIPE_PRICE_ID_PRO` | Pro subscription price ID | ✅ |
| `STRIPE_PRICE_ID_CREDITS_10` | 10-credit pack price ID | ✅ |
| `STRIPE_PRICE_ID_CREDITS_30` | 30-credit pack price ID | ✅ |
| `STRIPE_PRICE_ID_CREDITS_100` | 100-credit pack price ID | ✅ |
| `CRON_API_KEY` | Cron endpoint authentication | ✅ Required in production |

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/billing/balance` | GET | Get detailed credit balance (3 buckets) |
| `/api/billing/checkout` | POST | Create Pro subscription checkout |
| `/api/billing/checkout/credits` | POST | Create credit pack checkout |
| `/api/billing/webhook` | POST | Handle Stripe webhooks |
| `/api/cron/reset-monthly-credits` | POST | Reset expired free credits (FREE users only) |

---

## Migration Notes

### Migration 031 - Split Free/Paid Buckets

1. **New columns added to `profiles`**:
   - `free_credit_units_monthly` (default 6)
   - `free_credit_units_remaining` (default 6)

2. **Existing data redistributed**:
   - Total units preserved
   - Up to 6 units moved to free bucket
   - Remainder stays in subscription bucket

3. **Period windows ensured**:
   - Null `current_period_start`/`end` backfilled with calendar month boundaries

4. **Trigger updated**:
   - `handle_new_user()` now seeds all 3 buckets
   - Uses calendar month boundaries (not rolling 30 days)

5. **View refreshed**:
   - `user_tier_info.monthly_credits` now correctly reports:
     - Pro: (60 + 6) / 2 = **33 credits/month**
     - Free: 6 / 2 = **3 credits/month**

### Migration 032 - Atomic Credit Operations

1. **New RPC functions**:
   - `consume_credit_units(user_id, units)` - Atomic debit with row lock
   - `add_purchased_credit_units(user_id, units)` - Atomic increment

2. **Security**:
   - Functions restricted to `service_role` only
   - Checks JWT claim, `current_user`, and `session_user`
   - Prevents any authenticated user from calling directly

3. **Consumption priority fixed**:
   - Order: `Purchased → Free → Subscription`
   - Preserves paid subscription credits longest

4. **Race condition prevention**:
   - Uses `FOR UPDATE` row locking
   - Concurrent quiz starts cannot double-spend

---

## Security Improvements

### RPC Access Control

```sql
-- Only service_role can call these functions
v_is_service_role := (
    v_caller_role = 'service_role' OR
    current_user = 'service_role' OR
    session_user IN ('postgres', 'service_role')
);

IF NOT v_is_service_role THEN
    RAISE EXCEPTION 'Access denied: requires service_role';
END IF;
```

### Cron Endpoint Protection

| Environment | `CRON_API_KEY` Set | Behavior |
|-------------|-------------------|----------|
| Production | ❌ No | 503 Service Unavailable (blocked) |
| Production | ✅ Yes | Validates key, 401 if invalid |
| Development | ❌ No | ⚠️ Allows with warning (intentional) |
| Development | ✅ Yes | Validates key normally |

---

## Checklist: Scenarios Handled ✅

| Scenario | Status | Implementation |
|----------|--------|----------------|
| Free user monthly reset | ✅ | Cron job with calendar month boundaries |
| Pro user monthly reset | ✅ | `invoice.paid` webhook resets both buckets |
| Pro free credits reset | ✅ | Reset alongside subscription on `invoice.paid` |
| Cancelled Pro reset | ✅ | Cron job handles (not active/trialing) |
| New user initialization | ✅ | Trigger sets calendar month period |
| Concurrent quiz prevention | ✅ | Atomic RPC with `FOR UPDATE` lock |
| Credit pack race condition | ✅ | Atomic increment RPC |
| Pro skipped by cron | ✅ | Filter excludes active/trialing subs |
| Period drift prevention | ✅ | Calendar month boundaries everywhere |
| Cron security in prod | ✅ | Requires `CRON_API_KEY`, blocks if unset |
| RPC security | ✅ | Restricted to service_role only |
| Monthly credits view | ✅ | Pro shows 33, Free shows 3 |
