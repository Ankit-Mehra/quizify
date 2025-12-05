# Epic 4: Customer Portal Integration (Day 8)

**Status**: Not Started  
**Duration**: 1 day  
**Priority**: High  
**Dependencies**: Epic 1 (Infrastructure), Epic 3 (Provisioning)

---

## Overview

Integrate Stripe Customer Portal to allow users to self-manage subscriptions (change payment method, cancel, view invoices) without contacting support.

---

## Tasks Breakdown

### Task 4.1: Configure Customer Portal in Stripe Dashboard (30 minutes)

**Platform**: Stripe Dashboard

**Actions**:

1. **Navigate to Customer Portal** (https://dashboard.stripe.com/test/settings/billing/portal)

2. **Enable Portal**:
   - Toggle "Activate test link" (test mode)
   - Save changes

3. **Configure Portal Settings**:

**Business Information**:
- Business name: `Quizify`
- Support email: `support@quizify.ca`
- Privacy policy URL: `https://quizify.ca/privacy`
- Terms of service URL: `https://quizify.ca/terms`

**Features**:
- ✅ **Invoice history**: Allow customers to view past invoices
- ✅ **Update payment method**: Allow customers to update card
- ✅ **Cancel subscriptions**: Allow customers to cancel
  - Cancellation behavior: **Cancel immediately** (no proration)
  - Retention: Enable "Save subscription" offer (7-day grace period)
- ✅ **Update plan**: Allow customers to upgrade/downgrade
  - Billing cycle anchor: **Prorate immediately**
  - Products: Select Quizify Basic and Quizify Educator

**Branding**:
- Logo: Upload Quizify logo (optional)
- Accent color: `#4F46E5` (Indigo - matches branding)
- Background color: `#FFFFFF` (White)

4. **Save Configuration**

---

### Task 4.2: Implement Portal Session Creation (1 hour)

**File**: `services/billing_service.py`

**Action**: Implement `create_portal_session()` method

```python
async def create_portal_session(
    self,
    user_id: str,
    return_url: Optional[str] = None
) -> Dict[str, str]:
    """
    Create a Stripe Customer Portal Session
    
    Args:
        user_id: Quizify user ID (UUID)
        return_url: URL to return to after portal (default: dashboard)
        
    Returns:
        Dict with portal URL
        
    Raises:
        HTTPException: If no customer found or Stripe error
    """
    try:
        # Get customer ID from database
        supabase = get_supabase()
        result = supabase.table("profiles")\
            .select("stripe_customer_id")\
            .eq("id", user_id)\
            .single()\
            .execute()
        
        if not result.data or not result.data.get("stripe_customer_id"):
            logger.warning(
                f"User {user_id[:8]} has no Stripe customer ID (never subscribed)"
            )
            raise HTTPException(
                status_code=404,
                detail="No subscription found. You must subscribe before managing your subscription."
            )
        
        customer_id = result.data["stripe_customer_id"]
        
        # Set return URL
        if not return_url:
            return_url = f"{config.FRONTEND_URL}/dashboard"
        
        # Create portal session
        logger.info(
            f"Creating portal session for user {user_id[:8]} "
            f"(customer={customer_id})"
        )
        
        portal_session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url
        )
        
        logger.info(
            f"Created portal session {portal_session.id} for user {user_id[:8]}"
        )
        
        return {"url": portal_session.url}
        
    except HTTPException:
        # Re-raise HTTPExceptions
        raise
    except stripe.error.StripeError as e:
        # Log Stripe errors
        logger.error(
            f"Stripe error creating portal session for user {user_id[:8]}: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to create portal session"
        )
    except Exception as e:
        # Log unexpected errors
        logger.error(
            f"Unexpected error creating portal session for user {user_id[:8]}: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )
```

---

### Task 4.3: Implement Portal API Endpoint (1 hour)

**File**: `api/billing_routes.py`

**Action**: Implement portal session endpoint

```python
from services.billing_service import billing_service
from typing import Optional

class PortalSessionRequest(BaseModel):
    """Optional request body for portal session"""
    return_url: Optional[str] = Field(
        None,
        description="URL to return to after portal (default: dashboard)"
    )

@router.post(
    "/create-portal-session",
    response_model=PortalSessionResponse,
    summary="Create Stripe Customer Portal Session",
    description="Create a Customer Portal Session for subscription management"
)
async def create_portal_session(
    request: Optional[PortalSessionRequest] = None,
    current_user: Dict = Depends(get_current_user)
):
    """
    Create Stripe Customer Portal Session
    
    **Authentication**: Required (Bearer token)
    
    **Request Body** (optional):
    - `return_url`: URL to return to after portal (default: /dashboard)
    
    **Returns**:
    - `url`: URL to redirect user to for portal
    
    **Errors**:
    - `404`: User has no Stripe customer (never subscribed)
    - `500`: Stripe API error or internal error
    
    **Use Cases**:
    - User wants to update payment method
    - User wants to cancel subscription
    - User wants to view invoice history
    - User wants to upgrade/downgrade plan
    """
    user_id = current_user["id"]
    
    return_url = request.return_url if request else None
    
    logger.info(
        f"Portal session request from user {user_id[:8]} "
        f"(return_url={return_url})"
    )
    
    # Create portal session via service
    result = await billing_service.create_portal_session(
        user_id=user_id,
        return_url=return_url
    )
    
    return PortalSessionResponse(**result)
```

---

### Task 4.4: Update Pydantic Schemas (15 minutes)

**File**: `schemas/billing.py`

**Action**: Add request schema for portal

```python
class PortalSessionRequest(BaseModel):
    """Optional request body for portal session creation"""
    return_url: Optional[str] = Field(
        None,
        description="URL to return to after portal (default: dashboard)",
        example="https://app.quizify.ca/dashboard"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "return_url": "https://app.quizify.ca/dashboard"
            }
        }
```

---

### Task 4.5: Handle Portal Webhook Events (2 hours)

**File**: `handlers/billing_handler.py`

**Action**: Add handlers for portal-triggered events

```python
async def handle_customer_updated(event: stripe.Event):
    """
    Handle customer.updated event
    
    This event fires when customer details change in portal
    (e.g., email, payment method).
    """
    customer = event.data.object
    
    # Extract Quizify user ID from customer metadata
    user_id = customer.metadata.get("quizify_user_id")
    
    if not user_id:
        logger.warning(f"Customer {customer.id} has no quizify_user_id metadata")
        return
    
    logger.info(
        f"Customer updated for user {user_id[:8]}: "
        f"customer={customer.id}, email={customer.email}"
    )
    
    # Update email if changed (optional)
    try:
        supabase = get_supabase()
        
        # Only update email if different from current
        result = supabase.table("profiles")\
            .select("email")\
            .eq("id", user_id)\
            .single()\
            .execute()
        
        if result.data:
            current_email = result.data.get("email")
            if current_email != customer.email:
                logger.info(
                    f"Updating email for user {user_id[:8]}: "
                    f"{current_email} -> {customer.email}"
                )
                # Note: Email is in auth.users, not profiles
                # May need Supabase Admin API to update
                
    except Exception as e:
        logger.error(
            f"Failed to update customer details for user {user_id[:8]}: {e}",
            exc_info=True
        )

async def handle_subscription_paused(event: stripe.Event):
    """
    Handle customer.subscription.paused event
    
    This event fires when user pauses subscription in portal.
    """
    subscription = event.data.object
    
    user_id = subscription.metadata.get("user_id")
    
    if not user_id:
        logger.error(f"Missing user_id in subscription {subscription.id}")
        return
    
    logger.info(
        f"Subscription paused for user {user_id[:8]}: "
        f"subscription={subscription.id}"
    )
    
    # Update status to paused (keep tier until period ends)
    try:
        supabase = get_supabase()
        supabase.table("profiles").update({
            "subscription_status": "paused"
        }).eq("id", user_id).execute()
        
    except Exception as e:
        logger.error(
            f"Failed to pause subscription for user {user_id[:8]}: {e}",
            exc_info=True
        )

async def handle_subscription_resumed(event: stripe.Event):
    """
    Handle customer.subscription.resumed event
    
    This event fires when user resumes paused subscription.
    """
    subscription = event.data.object
    
    user_id = subscription.metadata.get("user_id")
    
    if not user_id:
        logger.error(f"Missing user_id in subscription {subscription.id}")
        return
    
    logger.info(
        f"Subscription resumed for user {user_id[:8]}: "
        f"subscription={subscription.id}"
    )
    
    # Update status back to active
    try:
        supabase = get_supabase()
        supabase.table("profiles").update({
            "subscription_status": "active"
        }).eq("id", user_id).execute()
        
    except Exception as e:
        logger.error(
            f"Failed to resume subscription for user {user_id[:8]}: {e}",
            exc_info=True
        )

# Update WEBHOOK_HANDLERS mapping
WEBHOOK_HANDLERS = {
    # ... existing handlers ...
    "customer.updated": handle_customer_updated,
    "customer.subscription.paused": handle_subscription_paused,
    "customer.subscription.resumed": handle_subscription_resumed,
}
```

---

### Task 4.6: Update Webhook Configuration (15 minutes)

**Platform**: Stripe Dashboard

**Actions**:

1. **Go to Webhooks** (https://dashboard.stripe.com/test/webhooks)

2. **Edit Existing Webhook**:
   - Click on your webhook endpoint
   - Click "Add events"
   - Add these events:
     - `customer.updated`
     - `customer.subscription.paused`
     - `customer.subscription.resumed`
   - Save changes

3. **Restart Application** to load updated webhook handlers

---

### Task 4.7: Add Unit Tests (2 hours)

**File**: `tests/unit/test_customer_portal.py` (NEW)

**Action**: Create portal tests

```python
"""
Unit tests for customer portal functionality
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import stripe
from services.billing_service import billing_service

@pytest.mark.asyncio
class TestCustomerPortal:
    """Test customer portal session creation"""
    
    @patch("stripe.billing_portal.Session.create")
    async def test_create_portal_session_success(
        self, 
        mock_create,
        mock_supabase
    ):
        """Test successful portal session creation"""
        # Mock customer ID lookup
        mock_supabase.table().select().eq().single().execute.return_value = \
            MagicMock(data={"stripe_customer_id": "cus_test123"})
        
        # Mock Stripe portal session creation
        mock_create.return_value = MagicMock(
            id="bps_test123",
            url="https://billing.stripe.com/session/test123"
        )
        
        result = await billing_service.create_portal_session(
            user_id="user_123"
        )
        
        assert result["url"].startswith("https://billing.stripe.com")
        mock_create.assert_called_once()
    
    async def test_create_portal_no_customer(self, mock_supabase):
        """Test portal session with no customer ID"""
        # Mock no customer ID
        mock_supabase.table().select().eq().single().execute.return_value = \
            MagicMock(data={"stripe_customer_id": None})
        
        with pytest.raises(HTTPException) as exc_info:
            await billing_service.create_portal_session(user_id="user_123")
        
        assert exc_info.value.status_code == 404
        assert "No subscription found" in exc_info.value.detail
    
    @patch("stripe.billing_portal.Session.create")
    async def test_create_portal_with_return_url(
        self,
        mock_create,
        mock_supabase
    ):
        """Test portal session with custom return URL"""
        mock_supabase.table().select().eq().single().execute.return_value = \
            MagicMock(data={"stripe_customer_id": "cus_test123"})
        
        mock_create.return_value = MagicMock(
            id="bps_test123",
            url="https://billing.stripe.com/session/test123"
        )
        
        custom_url = "https://app.quizify.ca/settings"
        await billing_service.create_portal_session(
            user_id="user_123",
            return_url=custom_url
        )
        
        # Verify return_url passed to Stripe
        call_args = mock_create.call_args[1]
        assert call_args["return_url"] == custom_url
```

---

### Task 4.8: Add Integration Tests (1 hour)

**File**: `tests/integration/test_customer_portal_flow.py` (NEW)

**Action**: Create end-to-end portal tests

```python
"""
Integration tests for customer portal flow
"""

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

class TestCustomerPortalEndpoint:
    """Test /api/billing/create-portal-session endpoint"""
    
    def test_create_portal_session_success(self, auth_headers, setup_subscription):
        """Test successful portal session creation"""
        response = client.post(
            "/api/billing/create-portal-session",
            headers=auth_headers,
            json={}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "url" in data
        assert "billing.stripe.com" in data["url"]
    
    def test_create_portal_session_no_subscription(self, auth_headers):
        """Test portal session for user with no subscription"""
        response = client.post(
            "/api/billing/create-portal-session",
            headers=auth_headers,
            json={}
        )
        
        assert response.status_code == 404
        assert "No subscription found" in response.json()["detail"]
    
    def test_create_portal_session_with_return_url(self, auth_headers, setup_subscription):
        """Test portal session with custom return URL"""
        response = client.post(
            "/api/billing/create-portal-session",
            headers=auth_headers,
            json={"return_url": "https://app.quizify.ca/settings"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "url" in data
```

---

## Verification Checklist

### Stripe Dashboard Verification
- [ ] Customer Portal enabled in test mode
- [ ] Business information configured
- [ ] Portal features enabled (invoices, cancel, update payment)
- [ ] Branding configured (optional)
- [ ] Portal webhook events added to webhook endpoint

### Code Verification
- [ ] `create_portal_session()` service method implemented
- [ ] Portal API endpoint functional
- [ ] Portal webhook handlers added
- [ ] Unit tests written and passing
- [ ] Integration tests written and passing

### Manual Testing
```bash
# 1. Create subscription first (use checkout flow from Epic 2)

# 2. Create portal session
curl -X POST http://localhost:8000/api/billing/create-portal-session \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'

# Expected response:
{
  "url": "https://billing.stripe.com/session/live_..."
}

# 3. Visit URL in browser
# 4. Test portal features:
#    - View invoice history
#    - Update payment method (use test card 4242 4242 4242 4242)
#    - Cancel subscription
#    - View subscription details
```

---

## Common Issues & Troubleshooting

### Issue 1: "No subscription found" Error
**Solution**: User must have completed checkout at least once. Ensure `stripe_customer_id` exists in `profiles` table.

### Issue 2: Portal Shows Wrong Products
**Solution**: In Stripe Dashboard → Customer Portal Settings → Update Plan, ensure Quizify products are selected.

### Issue 3: Portal Redirects to Wrong URL
**Solution**: Check `FRONTEND_URL` in config matches actual frontend URL.

### Issue 4: Cancellation Not Reflected
**Solution**: Verify `customer.subscription.deleted` webhook is configured and handler is working.

---

## Next Steps

Once complete:
1. ✅ Run tests: `pytest tests/unit/test_customer_portal.py -v`
2. ✅ Manual test portal flow
3. ✅ Test cancellation flow end-to-end
4. ✅ Commit: `feat: implement customer portal integration (Epic 4)`
5. ➡️ Proceed to **Epic 5: Subscription State Management**

---

**Epic Owner**: GitHub Copilot  
**Last Updated**: 2025-11-19
