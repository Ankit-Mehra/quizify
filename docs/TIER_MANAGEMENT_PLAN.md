# 🎯 Tier Management System - Current Status & Next Steps

## ✅ What We've Implemented

### 1. Quota Enforcement (COMPLETE)
- ✅ Free tier: 5 quizzes limit
- ✅ Basic tier: 100 quizzes limit  
- ✅ Educator tier: 500 quizzes limit
- ✅ All 3 quiz endpoints protected
- ✅ Proper error messages with upgrade suggestions
- ✅ 13 integration tests passing

### 2. Auto Profile Creation (COMPLETE)
- ✅ Every new signup gets a profile automatically
- ✅ Default tier: `free`
- ✅ Database trigger working (< 1ms)
- ✅ All existing users backfilled

---

## ❌ What's Missing - Tier Upgrade System

Currently, **all users are stuck on the free tier forever!** 

There's no way to:
- ❌ Upgrade from free → basic
- ❌ Upgrade from basic → educator
- ❌ Handle payments
- ❌ Manually change user tiers (admin panel)

---

## 🚀 Options for Tier Management

### Option 1: Manual Admin Panel (Quickest - 2-4 hours)

**Build a simple admin interface to manually change user tiers**

#### What to build:
1. Admin-only API endpoint to update user tier
2. Simple admin page in your frontend
3. Authentication check (only admins can access)

#### Implementation:

**Backend:**
```python
# api/admin_routes.py (NEW FILE)
from fastapi import APIRouter, Depends, HTTPException, status
from dependencies.auth_dependencies import get_current_user
from services.db_services.supabase_quiz import get_supabase_admin_client

router = APIRouter(prefix="/api/admin", tags=["admin"])

ADMIN_EMAILS = ["your-admin@example.com"]  # Add your admin emails

@router.put("/users/{user_id}/tier")
async def update_user_tier(
    user_id: str,
    new_tier: str,
    current_user: dict = Depends(get_current_user)
):
    """Admin endpoint to manually update user tier"""
    
    # Check if user is admin
    if current_user.get('email') not in ADMIN_EMAILS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can update user tiers"
        )
    
    # Validate tier
    if new_tier not in ['free', 'basic', 'educator']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tier. Must be: free, basic, or educator"
        )
    
    # Update tier
    supabase = get_supabase_admin_client()
    result = supabase.table('profiles').update({
        'account_tier': new_tier,
        'updated_at': 'NOW()'
    }).eq('id', user_id).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return {
        "message": f"User tier updated to {new_tier}",
        "user_id": user_id,
        "new_tier": new_tier
    }

@router.get("/users")
async def list_users_with_tiers(
    current_user: dict = Depends(get_current_user)
):
    """Admin endpoint to list all users and their tiers"""
    
    if current_user.get('email') not in ADMIN_EMAILS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can view user list"
        )
    
    supabase = get_supabase_admin_client()
    
    # Get all users with their tier info
    result = supabase.rpc('get_all_user_tiers').execute()
    
    return result.data
```

**Database Function:**
```sql
-- Add to migrations/004_admin_functions.sql
CREATE OR REPLACE FUNCTION public.get_all_user_tiers()
RETURNS TABLE (
    user_id UUID,
    email TEXT,
    account_tier TEXT,
    current_quiz_count BIGINT,
    quota_limit INTEGER,
    quota_exceeded BOOLEAN,
    created_at TIMESTAMPTZ
) 
LANGUAGE SQL
SECURITY DEFINER
AS $$
    SELECT 
        u.id as user_id,
        u.email,
        p.account_tier,
        COALESCE(qc.quiz_count, 0) as current_quiz_count,
        CASE p.account_tier
            WHEN 'free' THEN 5
            WHEN 'basic' THEN 100
            WHEN 'educator' THEN 500
        END as quota_limit,
        COALESCE(qc.quiz_count, 0) >= CASE p.account_tier
            WHEN 'free' THEN 5
            WHEN 'basic' THEN 100
            WHEN 'educator' THEN 500
        END as quota_exceeded,
        u.created_at
    FROM auth.users u
    LEFT JOIN public.profiles p ON u.id = p.id
    LEFT JOIN user_quiz_counts qc ON u.id = qc.user_id
    ORDER BY u.created_at DESC;
$$;

GRANT EXECUTE ON FUNCTION public.get_all_user_tiers() TO authenticated;
```

**Frontend (Simple HTML page):**
```html
<!-- admin.html -->
<div id="admin-panel">
    <h1>User Management</h1>
    <table>
        <thead>
            <tr>
                <th>Email</th>
                <th>Current Tier</th>
                <th>Quizzes Used</th>
                <th>Quota</th>
                <th>Change Tier</th>
            </tr>
        </thead>
        <tbody id="users-table">
            <!-- Users populated via JavaScript -->
        </tbody>
    </table>
</div>

<script>
async function loadUsers() {
    const response = await fetch('/api/admin/users', {
        headers: { 'Authorization': `Bearer ${token}` }
    });
    const users = await response.json();
    
    const tbody = document.getElementById('users-table');
    tbody.innerHTML = users.map(user => `
        <tr>
            <td>${user.email}</td>
            <td>${user.account_tier}</td>
            <td>${user.current_quiz_count}</td>
            <td>${user.quota_limit}</td>
            <td>
                <select onchange="updateTier('${user.user_id}', this.value)">
                    <option value="free" ${user.account_tier === 'free' ? 'selected' : ''}>Free</option>
                    <option value="basic" ${user.account_tier === 'basic' ? 'selected' : ''}>Basic</option>
                    <option value="educator" ${user.account_tier === 'educator' ? 'selected' : ''}>Educator</option>
                </select>
            </td>
        </tr>
    `).join('');
}

async function updateTier(userId, newTier) {
    await fetch(`/api/admin/users/${userId}/tier?new_tier=${newTier}`, {
        method: 'PUT',
        headers: { 'Authorization': `Bearer ${token}` }
    });
    alert('Tier updated!');
    loadUsers();
}
</script>
```

**Pros:**
- ✅ Quick to implement (2-4 hours)
- ✅ Full control over who gets what tier
- ✅ No payment integration needed yet
- ✅ Can manually handle early customers

**Cons:**
- ❌ Not scalable for many users
- ❌ Manual work required for each upgrade
- ❌ No automated payment flow

---

### Option 2: Payment Integration (Production-ready - 1-2 weeks)

**Integrate with Stripe for automated tier management**

#### What to build:
1. Stripe integration (Stripe Checkout or Payment Links)
2. Webhook handler for payment events
3. Automatic tier upgrades on successful payment
4. Subscription management
5. Tier downgrade on cancellation

#### Implementation Overview:

```python
# services/stripe_service.py
import stripe
from config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY

PRICE_IDS = {
    'basic': 'price_xxx',    # Your Stripe price ID for basic
    'educator': 'price_yyy'  # Your Stripe price ID for educator
}

async def create_checkout_session(user_id: str, tier: str):
    """Create a Stripe checkout session for tier upgrade"""
    session = stripe.checkout.Session.create(
        customer_email=user.email,
        payment_method_types=['card'],
        line_items=[{
            'price': PRICE_IDS[tier],
            'quantity': 1,
        }],
        mode='subscription',
        success_url=f'{settings.FRONTEND_URL}/upgrade/success',
        cancel_url=f'{settings.FRONTEND_URL}/upgrade/cancel',
        metadata={
            'user_id': user_id,
            'tier': tier
        }
    )
    return session

# api/payment_routes.py
@router.post("/create-checkout")
async def create_checkout(
    tier: str,
    current_user: dict = Depends(get_current_user)
):
    """Create Stripe checkout session for tier upgrade"""
    session = await create_checkout_session(current_user['id'], tier)
    return {"checkout_url": session.url}

@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhooks for payment events"""
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    
    event = stripe.Webhook.construct_event(
        payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
    )
    
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        user_id = session['metadata']['user_id']
        tier = session['metadata']['tier']
        
        # Update user tier
        supabase = get_supabase_admin_client()
        supabase.table('profiles').update({
            'account_tier': tier
        }).eq('id', user_id).execute()
    
    return {"status": "success"}
```

**Pros:**
- ✅ Fully automated
- ✅ Scalable to thousands of users
- ✅ Professional payment handling
- ✅ Recurring revenue via subscriptions

**Cons:**
- ❌ Takes 1-2 weeks to implement properly
- ❌ Requires Stripe account and setup
- ❌ More complex testing needed
- ❌ Webhook infrastructure needed

---

### Option 3: Simple Payment Links (Middle Ground - 4-8 hours)

**Use Stripe Payment Links (no code required) + manual tier updates**

#### How it works:
1. Create payment links in Stripe dashboard for each tier
2. Users pay via Stripe-hosted page
3. You receive email notification
4. You manually update user tier via admin panel

**Steps:**
1. Go to Stripe Dashboard → Payment Links
2. Create link for "Basic - $X/month"
3. Create link for "Educator - $Y/month"
4. Add links to your app's upgrade page
5. When payment succeeds, manually update tier via admin panel

**Pros:**
- ✅ No payment code needed
- ✅ Professional checkout page
- ✅ Can start accepting payments immediately
- ✅ Combine with Option 1 (admin panel)

**Cons:**
- ❌ Manual tier updates still needed
- ❌ Not fully automated
- ❌ Won't scale well beyond 10-20 customers

---

## 🎯 Recommended Approach (Based on Your Stage)

### Phase 1: NOW (Today - Manual Admin Panel)
**Use Option 1 - Build simple admin panel**

This lets you:
- ✅ Start testing with beta users
- ✅ Manually upgrade early adopters
- ✅ Validate pricing before building payment system
- ✅ Keep development simple

### Phase 2: LATER (When you have paying customers - Stripe Integration)
**Upgrade to Option 2 - Full payment integration**

Once you have:
- 10+ paying customers
- Validated pricing
- Clear demand for paid tiers

---

## 📋 Implementation Checklist - Phase 1 (Recommended NOW)

### Step 1: Create Admin API (30 mins)
- [ ] Create `api/admin_routes.py`
- [ ] Add endpoint to list users with tiers
- [ ] Add endpoint to update user tier
- [ ] Add admin email check

### Step 2: Create Database Function (15 mins)
- [ ] Create `migrations/004_admin_functions.sql`
- [ ] Add `get_all_user_tiers()` function
- [ ] Test function works

### Step 3: Register Admin Routes (5 mins)
- [ ] Import admin routes in `main.py`
- [ ] Add to app routers

### Step 4: Test Manually (20 mins)
- [ ] Test listing users
- [ ] Test updating tier from free → basic
- [ ] Test quota changes after tier update
- [ ] Verify user can generate more quizzes

### Step 5: (Optional) Build Simple Frontend (1-2 hours)
- [ ] Create admin page with table
- [ ] Add tier dropdown for each user
- [ ] Test updating tiers via UI

**Total Time: 2-4 hours**

---

## 🔧 Quick Start Commands

```bash
# 1. Create admin routes file
touch api/admin_routes.py

# 2. Create migration
touch migrations/004_admin_functions.sql

# 3. Test admin endpoint
curl -X GET http://localhost:8000/api/admin/users \
  -H "Authorization: Bearer YOUR_TOKEN"

# 4. Update a user's tier
curl -X PUT http://localhost:8000/api/admin/users/USER_ID/tier?new_tier=basic \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## 💡 Bottom Line

**You have 3 options:**

1. **Quick & Simple (2-4 hrs)** → Manual admin panel ✅ RECOMMENDED NOW
2. **Professional (1-2 weeks)** → Full Stripe integration
3. **Middle Ground (4-8 hrs)** → Payment links + manual updates

**Start with Option 1**, validate your pricing and demand, then upgrade to Option 2 when you have real paying customers!

---

Would you like me to implement **Option 1 (Admin Panel)** right now? It'll take about 30 minutes to get the basic version working! 🚀
