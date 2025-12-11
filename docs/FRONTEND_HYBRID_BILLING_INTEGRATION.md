# Frontend Integration: Hybrid Credit Billing System

> **Document Version**: 1.0  
> **Last Updated**: December 10, 2025  
> **Backend PR**: #144 (merged to `deploy/staging`)

---

## Table of Contents

1. [Overview](#overview)
2. [Credit System Architecture](#credit-system-architecture)
3. [API Endpoints](#api-endpoints)
4. [TypeScript Interfaces](#typescript-interfaces)
5. [User Flows](#user-flows)
6. [Error Handling](#error-handling)
7. [UI Components](#ui-components)
8. [Migration Notes](#migration-notes)

---

## Overview

The Quizify billing system has been upgraded from a simple quota-based model to a **hybrid credit system** that combines:

- **Monthly Subscription Credits** (Pro users only)
- **Free Monthly Allowance** (all users)
- **Purchased Credit Packs** (one-time purchases, never expire)

### Key Changes for Frontend

| Before | After |
|--------|-------|
| Simple quota counting | Credit-based consumption |
| `quota_exceeded: boolean` | `credits_remaining: number` |
| Fixed limits (5/20/∞) | Flexible credits across 3 buckets |
| No one-time purchases | Credit pack purchases available |
| HTTP 403 for quota errors | HTTP 402 (Payment Required) |

---

## Credit System Architecture

### The 3-Bucket System

Credits are stored and consumed from three separate buckets with a specific priority order:

```
┌─────────────────────────────────────────────────────────────────┐
│                    CREDIT CONSUMPTION ORDER                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   1. PURCHASED CREDITS    ──→   Used FIRST (never expire)       │
│   (credit_units_purchased)                                       │
│                                                                  │
│   2. FREE CREDITS         ──→   Used SECOND (resets monthly)    │
│   (free_credits_remaining)                                       │
│                                                                  │
│   3. SUBSCRIPTION CREDITS ──→   Used LAST (Pro only, monthly)   │
│   (subscription_credits_remaining)                               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Credit Costs by Quiz Type

| Quiz Type | Credits | Units (Internal) |
|-----------|---------|------------------|
| **Standard** | 0.5 credits | 1 unit |
| **Enhanced** | 1.0 credit | 2 units |

> **Internal Note**: The backend uses "units" internally (1 credit = 2 units). All API responses are converted to credits for frontend display.

### Monthly Allowances by Plan

| Plan | Subscription Credits | Free Credits | Total Monthly |
|------|---------------------|--------------|---------------|
| **Free** | 0 | 3 credits | 3 credits |
| **Pro** | 40 credits | 3 credits | 43 credits |

### Storage Quotas by Plan

| Plan | Storage Quota | Description |
|------|---------------|-------------|
| **Free** | 250 MB | Default for new users |
| **Pay-as-you-go** | 2 GB | Users who have purchased credit packs |
| **Pro** | 5 GB | Users with active Pro subscription |

> **Note**: Pay-as-you-go users are free users who have purchased credits but don't have an active Pro subscription. Their storage quota is automatically upgraded to 2 GB upon first credit purchase.

---

## API Endpoints

### 1. Get Credit Balance

**Endpoint**: `GET /api/billing/balance`  
**Auth**: Required (Bearer token)

Returns the user's current credit balance and storage usage.

**Response**:
```json
{
  "plan": "free" | "pro",
  "credits_remaining": 5.5,
  "free_credits_monthly": 3.0,
  "free_credits_remaining": 2.0,
  "subscription_credits_remaining": 0.0,
  "purchased_credits": 3.5,
  "period_end": "2025-01-01T00:00:00Z",
  "storage_used_bytes": 52428800,
  "storage_quota_bytes": 262144000,
  "storage_remaining_bytes": 209715200,
  "storage_used_formatted": "50.0 MB",
  "storage_quota_formatted": "250 MB",
  "storage_usage_percentage": 20.0
}
```

**Field Descriptions**:

| Field | Type | Description |
|-------|------|-------------|
| `plan` | `"free"` \| `"pro"` | Current billing plan |
| `credits_remaining` | `number` | **Total available** = purchased + free + subscription |
| `free_credits_monthly` | `number` | Monthly free allowance (always 3) |
| `free_credits_remaining` | `number` | Remaining free credits this period |
| `subscription_credits_remaining` | `number` | Remaining Pro subscription credits (0 for free users) |
| `purchased_credits` | `number` | Credits from one-time purchases (never expire) |
| `period_end` | `string` \| `null` | ISO timestamp when credits reset |
| `storage_used_bytes` | `number` | Current storage usage in bytes |
| `storage_quota_bytes` | `number` | Maximum storage allowed in bytes |
| `storage_remaining_bytes` | `number` | Remaining storage available |
| `storage_used_formatted` | `string` | Human-readable storage usage (e.g., "50.0 MB") |
| `storage_quota_formatted` | `string` | Human-readable quota (e.g., "250 MB") |
| `storage_usage_percentage` | `number` | Usage percentage (0-100) |

---

### 1b. Get Storage Usage

**Endpoint**: `GET /api/billing/storage`  
**Auth**: Required (Bearer token)

Returns detailed storage quota information.

**Response**:
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "plan_type": "free" | "payg" | "pro",
  "storage_used_bytes": 52428800,
  "storage_quota_bytes": 262144000,
  "storage_remaining_bytes": 209715200,
  "storage_used_formatted": "50.0 MB",
  "storage_quota_formatted": "250 MB",
  "storage_remaining_formatted": "200.0 MB",
  "usage_percentage": 20.0
}
```

**Field Descriptions**:

| Field | Type | Description |
|-------|------|-------------|
| `user_id` | `string` | User's UUID |
| `plan_type` | `"free"` \| `"payg"` \| `"pro"` | Plan type for storage purposes |
| `storage_used_bytes` | `number` | Current storage usage in bytes |
| `storage_quota_bytes` | `number` | Maximum storage allowed in bytes |
| `storage_remaining_bytes` | `number` | Remaining storage available |
| `storage_used_formatted` | `string` | Human-readable usage (e.g., "50.0 MB") |
| `storage_quota_formatted` | `string` | Human-readable quota (e.g., "250 MB") |
| `storage_remaining_formatted` | `string` | Human-readable remaining (e.g., "200.0 MB") |
| `usage_percentage` | `number` | Usage as percentage (0-100) |

---

### 2. Purchase Credit Pack

**Endpoint**: `POST /api/billing/checkout/credits`  
**Auth**: Required (Bearer token)

Creates a Stripe checkout session for one-time credit pack purchase.

**Request Body**:
```json
{
  "pack_size": "5" | "10" | "15"
}
```

**Available Packs**:

| Pack Size | Price | Credits | Standard Quizzes | Enhanced Quizzes |
|-----------|-------|---------|------------------|------------------|
| `"5"` | $5 | 5 credits | 10 quizzes | 5 quizzes |
| `"10"` | $10 | 10 credits | 20 quizzes | 10 quizzes |
| `"15"` | $15 | 15 credits | 30 quizzes | 15 quizzes |

**Response** (Success - 200):
```json
{
  "checkout_url": "https://checkout.stripe.com/c/pay/cs_live_...",
  "session_id": "cs_live_a1b2c3d4e5f6g7h8"
}
```

**Frontend Action**: Redirect user to `checkout_url`.

**Success Callback**: After purchase, redirect to `{SUCCESS_URL}?credits={pack_size}`

---

### 3. Subscribe to Pro Plan

**Endpoint**: `POST /api/billing/checkout`  
**Auth**: Required (Bearer token)

Creates a Stripe checkout session for Pro subscription.

**Request Body**:
```json
{
  "tier": "pro"
}
```

**Response** (New Subscription):
```json
{
  "checkout_url": "https://checkout.stripe.com/c/pay/cs_live_...",
  "session_id": "cs_live_a1b2c3d4e5f6g7h8"
}
```

**Response** (Already Subscribed):
```json
{
  "status": "already_subscribed",
  "message": "You already have an active Pro subscription",
  "subscription_id": "sub_abc123"
}
```

---

### 4. Get Subscription Status

**Endpoint**: `GET /api/billing/subscription-status`  
**Auth**: Required (Bearer token)

**Response**:
```json
{
  "account_tier": "free" | "premium" | "pro",
  "subscription_status": "active" | "canceled" | "past_due" | null,
  "billing_status": "active",
  "stripe_customer_id": "cus_ABC123XYZ789",
  "stripe_subscription_id": "sub_DEF456UVW012",
  "subscription_canceled_at": null,
  "current_period_start": "2025-12-01T00:00:00Z",
  "current_period_end": "2026-01-01T00:00:00Z",
  "current_quiz_count": 42,
  "quota_limit": -1,
  "quota_exceeded": false
}
```

> **Note**: `account_tier: "premium"` is legacy and should be treated as `"pro"`.

---

### 5. Customer Portal

**Endpoint**: `POST /api/billing/portal`  
**Auth**: Required (Bearer token)

Opens Stripe Customer Portal for subscription management.

**Response**:
```json
{
  "portal_url": "https://billing.stripe.com/p/session/..."
}
```

**Frontend Action**: Redirect user to `portal_url`.

---

## TypeScript Interfaces

```typescript
// ============================================================================
// Credit Balance Types
// ============================================================================

interface CreditBalance {
  plan: 'free' | 'pro';
  credits_remaining: number;        // Total available
  free_credits_monthly: number;     // Monthly free allowance (always 3)
  free_credits_remaining: number;   // Remaining free this period
  subscription_credits_remaining: number;  // Pro subscription credits
  purchased_credits: number;        // One-time purchases (never expire)
  period_end: string | null;        // ISO timestamp
}

// ============================================================================
// Credit Pack Purchase Types
// ============================================================================

type CreditPackSize = '5' | '10' | '15';

interface CreditPackCheckoutRequest {
  pack_size: CreditPackSize;
}

interface CheckoutResponse {
  checkout_url: string;
  session_id: string;
}

// ============================================================================
// Subscription Types
// ============================================================================

type BillingPlan = 'free' | 'pro';
type AccountTier = 'free' | 'premium' | 'pro';  // 'premium' is legacy
type SubscriptionStatus = 
  | 'active' 
  | 'canceled' 
  | 'past_due' 
  | 'trialing' 
  | 'incomplete' 
  | 'unpaid' 
  | null;

interface SubscriptionStatusResponse {
  account_tier: AccountTier;
  subscription_status: SubscriptionStatus;
  billing_status: string;
  stripe_customer_id: string | null;
  stripe_subscription_id: string | null;
  subscription_canceled_at: string | null;
  current_period_start: string | null;
  current_period_end: string | null;
  current_quiz_count: number;
  quota_limit: number;  // -1 for unlimited (Pro)
  quota_exceeded: boolean;
}

// ============================================================================
// Upgrade Preview Types
// ============================================================================

interface UpgradePreviewRequest {
  tier: 'pro';
}

interface UpgradePreviewResponse {
  current_tier: string;
  target_tier: string;
  is_upgrade: boolean;
  proration_amount: number;          // Cents
  proration_amount_formatted: string; // "$2.50"
  credit_amount: number;             // Credit for unused time
  credit_amount_formatted: string;
  debit_amount: number;              // Charge for remaining time
  debit_amount_formatted: string;
  next_billing_amount: number;
  next_billing_amount_formatted: string;
  next_billing_date: string;         // ISO timestamp
}

// ============================================================================
// Storage Quota Types
// ============================================================================

type StoragePlanType = 'free' | 'payg' | 'pro';

interface StorageQuotaInfo {
  user_id: string;
  plan_type: StoragePlanType;
  storage_used_bytes: number;
  storage_quota_bytes: number;
  storage_remaining_bytes: number;
  storage_used_formatted: string;     // e.g., "50.0 MB"
  storage_quota_formatted: string;    // e.g., "250 MB"
  storage_remaining_formatted: string; // e.g., "200.0 MB"
  usage_percentage: number;           // 0-100
}

interface StorageQuotaExceededError {
  error: 'storage_quota_exceeded';
  message: string;
  storage_used_bytes: number;
  storage_quota_bytes: number;
  storage_remaining_bytes: number;
  file_size_bytes: number;
  plan: StoragePlanType;
  storage_used_formatted: string;
  storage_quota_formatted: string;
}

// ============================================================================
// Error Types
// ============================================================================

interface InsufficientCreditsError {
  error: 'insufficient_credits';
  message: string;
  available_credits: number;
  required_credits: number;  // 0.5 for standard, 1.0 for enhanced
  plan: 'free' | 'pro';
}

interface BillingError {
  detail: string | InsufficientCreditsError | StorageQuotaExceededError;
}
```

---

## User Flows

### Flow 1: Quiz Generation with Credit Check

```
┌─────────────────────────────────────────────────────────────────┐
│                    QUIZ GENERATION FLOW                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  User clicks    │
                    │ "Generate Quiz" │
                    └────────┬────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │  GET /api/billing/   │
                  │      balance         │
                  └──────────┬───────────┘
                             │
              ┌──────────────┴──────────────┐
              │                              │
              ▼                              ▼
    ┌─────────────────┐           ┌─────────────────┐
    │ credits >= cost │           │ credits < cost  │
    │   (proceed)     │           │  (show modal)   │
    └────────┬────────┘           └────────┬────────┘
             │                             │
             ▼                             ▼
    ┌─────────────────┐          ┌──────────────────┐
    │ POST /api/quiz/ │          │  "Insufficient   │
    │   generate      │          │   Credits" Modal │
    └────────┬────────┘          │                  │
             │                   │ [Buy Credits]    │
    ┌────────┴────────┐          │ [Upgrade to Pro] │
    │                 │          └──────────────────┘
    ▼                 ▼
 SUCCESS           HTTP 402
  (show             (show
  quiz)           purchase
                  options)
```

### Flow 2: Credit Pack Purchase

```
┌─────────────────────────────────────────────────────────────────┐
│                  CREDIT PACK PURCHASE FLOW                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  User selects   │
                    │  credit pack    │
                    │  (5/10/15)      │
                    └────────┬────────┘
                             │
                             ▼
                ┌────────────────────────┐
                │ POST /api/billing/     │
                │   checkout/credits     │
                │                        │
                │ { "pack_size": "10" }  │
                └───────────┬────────────┘
                            │
                            ▼
                ┌────────────────────────┐
                │  Redirect to Stripe    │
                │    checkout_url        │
                └───────────┬────────────┘
                            │
                            ▼
                ┌────────────────────────┐
                │   Stripe Checkout      │
                │   (payment form)       │
                └───────────┬────────────┘
                            │
              ┌─────────────┴─────────────┐
              │                           │
              ▼                           ▼
      ┌───────────────┐          ┌───────────────┐
      │   SUCCESS     │          │   CANCELED    │
      │ /success?     │          │   /cancel     │
      │ credits=10    │          │               │
      └───────┬───────┘          └───────────────┘
              │
              ▼
      ┌───────────────────────────┐
      │  Show success message     │
      │  "10 credits added!"      │
      │                           │
      │  Refresh balance          │
      │  GET /api/billing/balance │
      └───────────────────────────┘
```

### Flow 3: Pro Subscription

```
┌─────────────────────────────────────────────────────────────────┐
│                  PRO SUBSCRIPTION FLOW                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  User clicks    │
                    │ "Upgrade to Pro"│
                    └────────┬────────┘
                             │
                             ▼
                ┌────────────────────────┐
                │ POST /api/billing/     │
                │       checkout         │
                │                        │
                │ { "tier": "pro" }      │
                └───────────┬────────────┘
                            │
              ┌─────────────┴─────────────┐
              │                           │
              ▼                           ▼
     ┌─────────────────┐        ┌─────────────────┐
     │  checkout_url   │        │     status:     │
     │  (new sub)      │        │ already_subscribed│
     └────────┬────────┘        └─────────────────┘
              │
              ▼
      ┌───────────────────────────┐
      │   Stripe Checkout         │
      │   (recurring payment)     │
      └───────────┬───────────────┘
                  │
                  ▼
      ┌───────────────────────────┐
      │  SUCCESS                  │
      │  - 40 subscription credits│
      │  - 3 free credits         │
      │  - Total: 43 credits/mo   │
      └───────────────────────────┘
```

---

## Error Handling

### HTTP 402: Payment Required (Insufficient Credits)

When a quiz generation fails due to insufficient credits:

**Response**:
```json
{
  "detail": {
    "error": "insufficient_credits",
    "message": "Not enough credits. Upgrade to Pro or purchase credits.",
    "available_credits": 0.5,
    "required_credits": 1.0,
    "plan": "free"
  }
}
```

> **Note**: The `message` field is contextual:
> - Free users: "Not enough credits. Upgrade to Pro or purchase credits."
> - Pro users: "Not enough credits. Purchase additional credits to continue."

**Frontend Handling**:

```typescript
async function generateQuiz(request: QuizRequest): Promise<Quiz> {
  try {
    const response = await fetch('/api/quiz/generate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify(request)
    });
    
    if (response.status === 402) {
      const error = await response.json();
      const detail = error.detail as InsufficientCreditsError;
      
      // Show insufficient credits modal
      showInsufficientCreditsModal({
        available: detail.available_credits,
        required: detail.required_credits,
        plan: detail.plan
      });
      
      throw new InsufficientCreditsError(detail);
    }
    
    if (!response.ok) {
      throw new Error('Quiz generation failed');
    }
    
    return await response.json();
  } catch (error) {
    // Handle other errors
    throw error;
  }
}
```

### Other HTTP Error Codes

| Code | Meaning | Action |
|------|---------|--------|
| 400 | Invalid request (bad pack_size, etc.) | Show validation error |
| 401 | Not authenticated | Redirect to login |
| 402 | Insufficient credits OR storage quota exceeded | Show purchase/upgrade modal |
| 404 | Resource not found | Show error message |
| 413 | File too large (>10 MB) | Show file size error |
| 502 | Stripe/payment service error | Show retry message |
| 503 | Service unavailable | Show maintenance message |

---

### HTTP 402: Storage Quota Exceeded

When a file upload fails due to storage quota exceeded:

**Response**:
```json
{
  "detail": {
    "error": "storage_quota_exceeded",
    "message": "Storage quota exceeded. You have used 245 MB of your 250 MB limit. Purchase credits to unlock 2 GB storage, or upgrade to Pro for 5 GB storage.",
    "storage_used_bytes": 256901120,
    "storage_quota_bytes": 262144000,
    "storage_remaining_bytes": 5242880,
    "file_size_bytes": 10485760,
    "plan": "free",
    "storage_used_formatted": "245 MB",
    "storage_quota_formatted": "250 MB"
  }
}
```

> **Note**: The `message` field varies by plan:
> - Free users: "...Purchase credits to unlock 2 GB storage, or upgrade to Pro for 5 GB storage."
> - Pay-as-you-go users: "...Upgrade to Pro for 5 GB storage."
> - Pro users: "...Please delete some files to continue."

**Frontend Handling**:

```typescript
async function uploadFile(file: File): Promise<FileUploadResponse> {
  try {
    const formData = new FormData();
    formData.append('file', file);
    
    const response = await fetch('/api/files/upload', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`
      },
      body: formData
    });
    
    if (response.status === 402) {
      const error = await response.json();
      const detail = error.detail as StorageQuotaExceededError;
      
      // Show storage quota modal
      showStorageQuotaModal({
        used: detail.storage_used_formatted,
        quota: detail.storage_quota_formatted,
        fileSize: formatBytes(detail.file_size_bytes),
        plan: detail.plan
      });
      
      throw new StorageQuotaExceededError(detail);
    }
    
    if (response.status === 413) {
      throw new Error('File exceeds maximum size of 10 MB');
    }
    
    if (!response.ok) {
      throw new Error('File upload failed');
    }
    
    return await response.json();
  } catch (error) {
    throw error;
  }
}
```

---

## UI Components

### 1. Credit Balance Display

```tsx
interface CreditBalanceProps {
  balance: CreditBalance;
}

function CreditBalanceDisplay({ balance }: CreditBalanceProps) {
  return (
    <div className="credit-balance">
      <div className="total-credits">
        <span className="value">{balance.credits_remaining}</span>
        <span className="label">Credits Available</span>
      </div>
      
      <div className="credit-breakdown">
        {balance.purchased_credits > 0 && (
          <div className="bucket purchased">
            <span className="icon">💎</span>
            <span>{balance.purchased_credits} purchased</span>
          </div>
        )}
        
        <div className="bucket free">
          <span className="icon">🎁</span>
          <span>{balance.free_credits_remaining}/{balance.free_credits_monthly} free</span>
        </div>
        
        {balance.plan === 'pro' && (
          <div className="bucket subscription">
            <span className="icon">⭐</span>
            <span>{balance.subscription_credits_remaining} subscription</span>
          </div>
        )}
      </div>
      
      {balance.period_end && (
        <div className="reset-info">
          Resets: {formatDate(balance.period_end)}
        </div>
      )}
    </div>
  );
}
```

### 2. Storage Usage Display

```tsx
interface StorageUsageProps {
  storage: StorageQuotaInfo;
}

function StorageUsageDisplay({ storage }: StorageUsageProps) {
  const isNearLimit = storage.usage_percentage >= 80;
  const isAtLimit = storage.usage_percentage >= 95;
  
  return (
    <div className={`storage-usage ${isAtLimit ? 'critical' : isNearLimit ? 'warning' : ''}`}>
      <div className="storage-header">
        <span className="icon">📁</span>
        <span className="label">Storage</span>
      </div>
      
      <div className="progress-bar">
        <div 
          className="progress-fill" 
          style={{ width: `${Math.min(storage.usage_percentage, 100)}%` }}
        />
      </div>
      
      <div className="storage-info">
        <span className="used">{storage.storage_used_formatted}</span>
        <span className="separator">/</span>
        <span className="quota">{storage.storage_quota_formatted}</span>
      </div>
      
      {isNearLimit && (
        <div className="storage-warning">
          {storage.plan_type === 'free' && (
            <span>Running low! Buy credits to unlock 2 GB storage.</span>
          )}
          {storage.plan_type === 'payg' && (
            <span>Running low! Upgrade to Pro for 5 GB storage.</span>
          )}
          {storage.plan_type === 'pro' && (
            <span>Running low! Consider deleting unused files.</span>
          )}
        </div>
      )}
    </div>
  );
}
```

### 3. Credit Pack Selection

```tsx
const CREDIT_PACKS = [
  { size: '5' as const, price: 5, credits: 5, quizzes: '10 standard or 5 enhanced' },
  { size: '10' as const, price: 10, credits: 10, quizzes: '20 standard or 10 enhanced' },
  { size: '15' as const, price: 15, credits: 15, quizzes: '30 standard or 15 enhanced' },
];

function CreditPackSelector({ onPurchase }: { onPurchase: (size: CreditPackSize) => void }) {
  return (
    <div className="credit-packs">
      <h3>Buy Credit Packs</h3>
      <p className="subtitle">Credits never expire!</p>
      
      <div className="pack-grid">
        {CREDIT_PACKS.map(pack => (
          <div key={pack.size} className="pack-card">
            <div className="credits">{pack.credits} Credits</div>
            <div className="price">${pack.price}</div>
            <div className="quizzes">{pack.quizzes}</div>
            <button onClick={() => onPurchase(pack.size)}>
              Buy Now
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
```

### 4. Insufficient Credits Modal

```tsx
interface InsufficientCreditsModalProps {
  available: number;
  required: number;
  plan: 'free' | 'pro';
  onBuyCredits: () => void;
  onUpgrade: () => void;
  onClose: () => void;
}

function InsufficientCreditsModal({ 
  available, 
  required, 
  plan,
  onBuyCredits,
  onUpgrade,
  onClose 
}: InsufficientCreditsModalProps) {
  return (
    <Modal onClose={onClose}>
      <div className="insufficient-credits-modal">
        <h2>Not Enough Credits</h2>
        
        <div className="credit-info">
          <p>You have <strong>{available} credits</strong></p>
          <p>This quiz requires <strong>{required} credits</strong></p>
        </div>
        
        <div className="actions">
          <button className="primary" onClick={onBuyCredits}>
            Buy Credits
          </button>
          
          {plan === 'free' && (
            <button className="secondary" onClick={onUpgrade}>
              Upgrade to Pro
            </button>
          )}
        </div>
        
        <p className="hint">
          {plan === 'free' 
            ? 'Pro gives you 43 credits/month + priority support'
            : 'Credit packs never expire!'}
        </p>
      </div>
    </Modal>
  );
}
```

### 4. Quiz Cost Indicator

```tsx
interface QuizCostProps {
  mode: 'standard' | 'enhanced';
  balance: CreditBalance;
}

function QuizCostIndicator({ mode, balance }: QuizCostProps) {
  const cost = mode === 'standard' ? 0.5 : 1.0;
  const canAfford = balance.credits_remaining >= cost;
  
  return (
    <div className={`quiz-cost ${canAfford ? 'affordable' : 'insufficient'}`}>
      <span className="cost-label">
        {mode === 'standard' ? 'Standard Quiz' : 'Enhanced Quiz'}
      </span>
      <span className="cost-value">{cost} credit{cost > 1 ? 's' : ''}</span>
      
      {!canAfford && (
        <span className="warning">
          ⚠️ Need {(cost - balance.credits_remaining).toFixed(1)} more credits
        </span>
      )}
    </div>
  );
}
```

### 5. Utility Functions for Credit Handling

```tsx
/**
 * Check if user has sufficient credits for a quiz.
 */
function canAffordQuiz(
  balance: CreditBalance, 
  mode: 'standard' | 'enhanced'
): boolean {
  const cost = mode === 'standard' ? 0.5 : 1.0;
  return balance.credits_remaining >= cost;
}

/**
 * Determine if low-credit warning should be shown.
 */
function shouldShowLowCreditWarning(balance: CreditBalance): boolean {
  // Pro users with active subscription credits don't need warnings
  if (balance.plan === 'pro' && balance.subscription_credits_remaining > 5) {
    return false;
  }
  
  // Show warning when total credits are low (less than 2 standard quizzes)
  return balance.credits_remaining < 2;
}

/**
 * Format credits for display (handles fractional credits).
 */
function formatCredits(credits: number): string {
  if (Number.isInteger(credits)) {
    return credits.toString();
  }
  return credits.toFixed(1);
}
```

---

## Migration Notes

### Breaking Changes

1. **HTTP Status Code Change**
   - Before: HTTP 403 for quota exceeded
   - After: HTTP 402 for insufficient credits
   - **Action**: Update error handlers to check for 402

2. **Response Structure Change**
   - Before: `quota_exceeded: boolean`
   - After: `credits_remaining: number` + detailed breakdown
   - **Action**: Update UI to use credit values instead of boolean

3. **Terminology Change**
   - Before: "Quota" / "Quiz limit"
   - After: "Credits" / "Credit balance"
   - **Action**: Update all user-facing copy

### Backward Compatibility

The following fields are kept for backward compatibility but may be deprecated:

| Field | Status | Migration |
|-------|--------|-----------|
| `account_tier: "premium"` | Legacy | Treat as `"pro"` |
| `quota_limit` | Legacy | Use `credits_remaining` instead |
| `quota_exceeded` | Legacy | Check `credits_remaining <= 0` |
| `current_quiz_count` | Legacy | Use for analytics only |

#### `quota_limit` Values

The backend returns:
- **Pro users**: `quota_limit = -1` (unlimited)
- **Free users**: `quota_limit = 5`

```typescript
function isUnlimited(quotaLimit: number): boolean {
  return quotaLimit === -1;
}
```

**Recommendation**: Use `credits_remaining` for all credit-based logic. The `quota_limit` field is for legacy compatibility only.

### Feature Flag Recommendations

If you need gradual rollout:

```typescript
const BILLING_VERSION = 'v2';  // 'v1' = old quota, 'v2' = credit system

function isNewBillingSystem(): boolean {
  return BILLING_VERSION === 'v2' || featureFlags.get('new_billing_enabled');
}
```

---

## Summary

| Feature | Endpoint | Purpose |
|---------|----------|---------|
| Check balance | `GET /api/billing/balance` | Display available credits & storage |
| Check storage | `GET /api/billing/storage` | Detailed storage quota info |
| Buy credits | `POST /api/billing/checkout/credits` | One-time credit purchase |
| Subscribe | `POST /api/billing/checkout` | Pro subscription |
| Status | `GET /api/billing/subscription-status` | Full subscription info |
| Manage | `POST /api/billing/portal` | Customer portal |

### Quick Reference: Credit Values

| Quiz Type | Cost |
|-----------|------|
| Standard | 0.5 credits |
| Enhanced | 1.0 credit |

| Plan | Monthly Credits |
|------|-----------------|
| Free | 3 credits (free allowance) |
| Pro | 43 credits (40 subscription + 3 free) |

| Pack | Price | Credits |
|------|-------|---------|
| Small | $5 | 5 credits |
| Medium | $10 | 10 credits |
| Large | $15 | 15 credits |

### Quick Reference: Storage Quotas

| Plan | Storage Quota |
|------|---------------|
| Free | 250 MB |
| Pay-as-you-go | 2 GB |
| Pro | 5 GB |

> **Note**: Pay-as-you-go users are free users who have purchased credit packs. Storage quota is automatically upgraded upon first credit purchase.
