# Epic 2: Checkout Flow Implementation (Days 3-4)

**Status**: Not Started  
**Duration**: 2 days  
**Priority**: Critical (Blocking)  
**Dependencies**: Epic 1 (Infrastructure Setup)

---

## Overview

Implement complete checkout flow including session creation, customer management, redirect handling, and success page integration.

---

## Tasks Breakdown

### Task 2.1: Implement Customer Management (2 hours)

**File**: `services/billing_service.py`

**Action**: Implement `get_or_create_customer()` method

```python
async def get_or_create_customer(
    self, 
    user_id: str, 
    email: str
) -> str:
    """
    Get existing Stripe customer ID or create new customer
    
    Args:
        user_id: Quizify user ID (UUID)
        email: User's email address
        
    Returns:
        Stripe customer ID (cus_xxx)
        
    Raises:
        HTTPException: If database query fails
    """
    try:
        # Get service role client (bypass RLS for internal operation)
        supabase = get_supabase()
        
        # Check if customer exists in database
        result = supabase.table("profiles")\
            .select("stripe_customer_id")\
            .eq("id", user_id)\
            .single()\
            .execute()
        
        # Return existing customer ID if found
        if result.data and result.data.get("stripe_customer_id"):
            logger.info(f"Found existing Stripe customer for user {user_id[:8]}")
            return result.data["stripe_customer_id"]
        
        # Create new Stripe customer
        logger.info(f"Creating new Stripe customer for user {user_id[:8]}")
        customer = stripe.Customer.create(
            email=email,
            metadata={"quizify_user_id": user_id}
        )
        
        # Store customer ID in database
        supabase.table("profiles")\
            .update({"stripe_customer_id": customer.id})\
            .eq("id", user_id)\
            .execute()
        
        logger.info(
            f"Created Stripe customer {customer.id} for user {user_id[:8]}"
        )
        return customer.id
        
    except Exception as e:
        logger.error(
            f"Failed to get/create Stripe customer for user {user_id[:8]}: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to create customer"
        )
```

---

### Task 2.2: Implement Checkout Session Creation (3 hours)

**File**: `services/billing_service.py`

**Action**: Implement `create_checkout_session()` method

```python
async def create_checkout_session(
    self,
    user_id: str,
    email: str,
    price_id: str,
    tier: str
) -> Dict[str, str]:
    """
    Create a Stripe Checkout Session
    
    Args:
        user_id: Quizify user ID
        email: User's email
        price_id: Stripe price ID
        tier: Target tier (basic/educator)
        
    Returns:
        Dict with session_id and url
        
    Raises:
        HTTPException: If price_id invalid or session creation fails
    """
    try:
        # Validate price ID against allowed list
        if not config.validate_stripe_price_id(price_id):
            logger.warning(
                f"Invalid price ID attempted by user {user_id[:8]}: {price_id}"
            )
            raise HTTPException(
                status_code=400,
                detail=f"Invalid price ID: {price_id}"
            )
        
        # Verify tier matches price ID
        expected_tier = config.get_tier_from_price_id(price_id)
        if expected_tier != tier:
            logger.warning(
                f"Tier mismatch for user {user_id[:8]}: "
                f"price_id={price_id}, requested_tier={tier}, expected_tier={expected_tier}"
            )
            raise HTTPException(
                status_code=400,
                detail=f"Price ID does not match tier"
            )
        
        # Check if user already has active subscription
        supabase = get_supabase()
        result = supabase.table("profiles")\
            .select("subscription_status, stripe_subscription_id")\
            .eq("id", user_id)\
            .single()\
            .execute()
        
        if result.data:
            status = result.data.get("subscription_status")
            sub_id = result.data.get("stripe_subscription_id")
            
            if status == "active" and sub_id:
                logger.info(
                    f"User {user_id[:8]} already has active subscription {sub_id}"
                )
                raise HTTPException(
                    status_code=409,
                    detail="You already have an active subscription. "
                           "Please cancel your current subscription first."
                )
        
        # Get or create Stripe customer
        customer_id = await self.get_or_create_customer(user_id, email)
        
        # Create checkout session
        logger.info(
            f"Creating checkout session for user {user_id[:8]}, "
            f"tier={tier}, price_id={price_id}"
        )
        
        session = stripe.checkout.Session.create(
            customer=customer_id,
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{config.FRONTEND_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{config.FRONTEND_URL}/billing/canceled",
            metadata={
                "user_id": user_id,
                "tier": tier
            },
            subscription_data={
                "metadata": {
                    "user_id": user_id,
                    "tier": tier
                }
            },
            allow_promotion_codes=True,  # Allow discount codes
            billing_address_collection="auto",  # Collect billing address
            automatic_tax={"enabled": True}  # Enable Stripe Tax
        )
        
        logger.info(
            f"Created checkout session {session.id} for user {user_id[:8]}"
        )
        
        return {
            "session_id": session.id,
            "url": session.url
        }
        
    except HTTPException:
        # Re-raise HTTPExceptions (already logged)
        raise
    except stripe.error.StripeError as e:
        # Log Stripe-specific errors
        logger.error(
            f"Stripe API error creating checkout session for user {user_id[:8]}: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to create checkout session"
        )
    except Exception as e:
        # Log unexpected errors
        logger.error(
            f"Unexpected error creating checkout session for user {user_id[:8]}: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )
```

---

### Task 2.3: Implement Checkout API Endpoint (1 hour)

**File**: `api/billing_routes.py`

**Action**: Implement `create_checkout_session()` route

```python
from services.billing_service import billing_service

@router.post(
    "/create-checkout-session",
    response_model=CheckoutSessionResponse,
    summary="Create Stripe Checkout Session",
    description="Create a new Stripe Checkout Session for subscription purchase"
)
async def create_checkout_session(
    request: CheckoutSessionRequest,
    current_user: Dict = Depends(get_current_user)
):
    """
    Create Stripe Checkout Session for subscription purchase
    
    **Authentication**: Required (Bearer token)
    
    **Request Body**:
    - `price_id`: Stripe price ID (must be in allowed list)
    - `tier`: Target tier (basic or educator)
    
    **Returns**:
    - `session_id`: Stripe Checkout Session ID
    - `url`: URL to redirect user to for checkout
    
    **Errors**:
    - `400`: Invalid price_id or tier mismatch
    - `409`: User already has active subscription
    - `500`: Stripe API error or internal error
    """
    user_id = current_user["id"]
    email = current_user["email"]
    
    logger.info(
        f"Checkout session request from user {user_id[:8]}: "
        f"price_id={request.price_id}, tier={request.tier}"
    )
    
    # Create checkout session via service
    result = await billing_service.create_checkout_session(
        user_id=user_id,
        email=email,
        price_id=request.price_id,
        tier=request.tier
    )
    
    return CheckoutSessionResponse(**result)
```

---

### Task 2.4: Add Checkout Success Handler (1 hour)

**File**: `handlers/billing_handler.py` (NEW)

**Action**: Create handler for post-checkout verification

```python
"""
Billing Handler - Business Logic
Author: GitHub Copilot
Date: 2025-11-19
"""

from typing import Dict, Optional
import stripe
from fastapi import HTTPException
from config import config
from services.logger import app_logger as logger
from services.supabase_client import get_supabase

async def verify_checkout_session(session_id: str, user_id: str) -> Dict:
    """
    Verify checkout session and return subscription details
    
    Args:
        session_id: Stripe Checkout Session ID
        user_id: Quizify user ID (for verification)
        
    Returns:
        Dict with subscription details
        
    Raises:
        HTTPException: If session invalid or user mismatch
    """
    try:
        # Initialize Stripe
        stripe.api_key = config.STRIPE_SECRET_KEY
        
        # Retrieve session from Stripe
        session = stripe.checkout.Session.retrieve(
            session_id,
            expand=["subscription"]
        )
        
        # Verify session belongs to user
        session_user_id = session.metadata.get("user_id")
        if session_user_id != user_id:
            logger.warning(
                f"Session {session_id} user mismatch: "
                f"expected {user_id[:8]}, got {session_user_id[:8]}"
            )
            raise HTTPException(
                status_code=403,
                detail="Session does not belong to this user"
            )
        
        # Verify payment status
        if session.payment_status != "paid":
            logger.warning(
                f"Session {session_id} payment not complete: "
                f"status={session.payment_status}"
            )
            raise HTTPException(
                status_code=400,
                detail=f"Payment not complete: {session.payment_status}"
            )
        
        # Extract subscription details
        subscription = session.subscription
        if isinstance(subscription, str):
            # Subscription not expanded, fetch it
            subscription = stripe.Subscription.retrieve(subscription)
        
        tier = session.metadata.get("tier", "free")
        
        return {
            "session_id": session.id,
            "customer_id": session.customer,
            "subscription_id": subscription.id,
            "tier": tier,
            "status": subscription.status,
            "current_period_end": subscription.current_period_end,
            "payment_status": session.payment_status
        }
        
    except stripe.error.InvalidRequestError as e:
        logger.error(f"Invalid session ID {session_id}: {e}")
        raise HTTPException(
            status_code=404,
            detail="Checkout session not found"
        )
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error verifying session {session_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to verify checkout session"
        )
    except HTTPException:
        # Re-raise HTTPExceptions
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error verifying session {session_id}: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )
```

---

### Task 2.5: Add Success Verification Endpoint (1 hour)

**File**: `api/billing_routes.py`

**Action**: Add endpoint for frontend to verify checkout success

```python
from handlers.billing_handler import verify_checkout_session

@router.get(
    "/verify-session/{session_id}",
    summary="Verify Checkout Session",
    description="Verify checkout session after successful payment"
)
async def verify_session(
    session_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """
    Verify checkout session and return subscription details
    
    Called by frontend after user returns from Stripe Checkout
    
    **Authentication**: Required (Bearer token)
    
    **Path Parameters**:
    - `session_id`: Stripe Checkout Session ID from redirect URL
    
    **Returns**:
    - Subscription details including tier, status, period end
    
    **Errors**:
    - `403`: Session does not belong to authenticated user
    - `404`: Session ID not found
    - `400`: Payment not complete
    - `500`: Stripe API error
    """
    user_id = current_user["id"]
    
    logger.info(
        f"Verifying checkout session {session_id} for user {user_id[:8]}"
    )
    
    result = await verify_checkout_session(session_id, user_id)
    
    return result
```

---

### Task 2.6: Update Pydantic Schemas (30 minutes)

**File**: `schemas/billing.py`

**Action**: Add session verification response schema

```python
class CheckoutSessionVerification(BaseModel):
    """Response from checkout session verification"""
    session_id: str = Field(..., description="Checkout session ID")
    customer_id: str = Field(..., description="Stripe customer ID")
    subscription_id: str = Field(..., description="Stripe subscription ID")
    tier: str = Field(..., description="Account tier (basic/educator)")
    status: str = Field(..., description="Subscription status")
    current_period_end: int = Field(..., description="Unix timestamp of period end")
    payment_status: str = Field(..., description="Payment status (paid/unpaid)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "cs_test_a1b2c3d4e5f6g7h8i9j0",
                "customer_id": "cus_ABC123xyz",
                "subscription_id": "sub_DEF456uvw",
                "tier": "basic",
                "status": "active",
                "current_period_end": 1734566400,
                "payment_status": "paid"
            }
        }
```

---

### Task 2.7: Add Unit Tests (2 hours)

**File**: `tests/unit/test_billing_service.py` (NEW)

**Action**: Create unit tests for checkout flow

```python
"""
Unit tests for Billing Service - Checkout Flow
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from services.billing_service import billing_service
from fastapi import HTTPException

@pytest.mark.asyncio
class TestCustomerManagement:
    """Test customer creation and retrieval"""
    
    async def test_get_existing_customer(self, mock_supabase):
        """Test retrieving existing Stripe customer ID"""
        # Mock existing customer in database
        mock_supabase.table().select().eq().single().execute.return_value = \
            MagicMock(data={"stripe_customer_id": "cus_test123"})
        
        result = await billing_service.get_or_create_customer(
            user_id="user_123",
            email="test@example.com"
        )
        
        assert result == "cus_test123"
    
    @patch("stripe.Customer.create")
    async def test_create_new_customer(self, mock_create, mock_supabase):
        """Test creating new Stripe customer"""
        # Mock no existing customer
        mock_supabase.table().select().eq().single().execute.return_value = \
            MagicMock(data={"stripe_customer_id": None})
        
        # Mock Stripe customer creation
        mock_create.return_value = MagicMock(id="cus_new123")
        
        result = await billing_service.get_or_create_customer(
            user_id="user_456",
            email="new@example.com"
        )
        
        assert result == "cus_new123"
        mock_create.assert_called_once()

@pytest.mark.asyncio
class TestCheckoutSession:
    """Test checkout session creation"""
    
    @patch("services.billing_service.BillingService.get_or_create_customer")
    @patch("stripe.checkout.Session.create")
    async def test_create_checkout_session_success(
        self, 
        mock_session_create,
        mock_get_customer,
        mock_supabase
    ):
        """Test successful checkout session creation"""
        # Mock customer retrieval
        mock_get_customer.return_value = "cus_test123"
        
        # Mock no existing subscription
        mock_supabase.table().select().eq().single().execute.return_value = \
            MagicMock(data={"subscription_status": None})
        
        # Mock Stripe session creation
        mock_session_create.return_value = MagicMock(
            id="cs_test123",
            url="https://checkout.stripe.com/pay/cs_test123"
        )
        
        result = await billing_service.create_checkout_session(
            user_id="user_123",
            email="test@example.com",
            price_id="price_basic_monthly",
            tier="basic"
        )
        
        assert result["session_id"] == "cs_test123"
        assert result["url"].startswith("https://checkout.stripe.com")
    
    async def test_invalid_price_id(self):
        """Test checkout session with invalid price ID"""
        with pytest.raises(HTTPException) as exc_info:
            await billing_service.create_checkout_session(
                user_id="user_123",
                email="test@example.com",
                price_id="price_invalid",
                tier="basic"
            )
        
        assert exc_info.value.status_code == 400
        assert "Invalid price ID" in exc_info.value.detail
    
    async def test_tier_mismatch(self):
        """Test checkout session with mismatched tier"""
        with pytest.raises(HTTPException) as exc_info:
            await billing_service.create_checkout_session(
                user_id="user_123",
                email="test@example.com",
                price_id="price_basic_monthly",
                tier="educator"  # Wrong tier for basic price
            )
        
        assert exc_info.value.status_code == 400
        assert "does not match tier" in exc_info.value.detail
    
    async def test_existing_subscription_conflict(self, mock_supabase):
        """Test checkout session when user already has subscription"""
        # Mock existing active subscription
        mock_supabase.table().select().eq().single().execute.return_value = \
            MagicMock(data={
                "subscription_status": "active",
                "stripe_subscription_id": "sub_existing"
            })
        
        with pytest.raises(HTTPException) as exc_info:
            await billing_service.create_checkout_session(
                user_id="user_123",
                email="test@example.com",
                price_id="price_basic_monthly",
                tier="basic"
            )
        
        assert exc_info.value.status_code == 409
        assert "already have an active subscription" in exc_info.value.detail
```

---

### Task 2.8: Add Integration Tests (2 hours)

**File**: `tests/integration/test_checkout_flow.py` (NEW)

**Action**: Create end-to-end checkout flow tests

```python
"""
Integration tests for checkout flow
"""

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

class TestCheckoutEndpoint:
    """Test /api/billing/create-checkout-session endpoint"""
    
    def test_create_checkout_session_success(self, auth_headers):
        """Test successful checkout session creation"""
        response = client.post(
            "/api/billing/create-checkout-session",
            headers=auth_headers,
            json={
                "price_id": "price_basic_monthly",
                "tier": "basic"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "url" in data
        assert data["session_id"].startswith("cs_")
        assert "checkout.stripe.com" in data["url"]
    
    def test_create_checkout_session_unauthorized(self):
        """Test checkout session without authentication"""
        response = client.post(
            "/api/billing/create-checkout-session",
            json={
                "price_id": "price_basic_monthly",
                "tier": "basic"
            }
        )
        
        assert response.status_code == 401
    
    def test_create_checkout_session_invalid_price(self, auth_headers):
        """Test checkout session with invalid price ID"""
        response = client.post(
            "/api/billing/create-checkout-session",
            headers=auth_headers,
            json={
                "price_id": "price_invalid_123",
                "tier": "basic"
            }
        )
        
        assert response.status_code == 400
        assert "Invalid price ID" in response.json()["detail"]
```

---

## Verification Checklist

### Code Verification
- [ ] `get_or_create_customer()` implemented with proper error handling
- [ ] `create_checkout_session()` implemented with validation
- [ ] Checkout API endpoint functional
- [ ] Session verification handler created
- [ ] Verification endpoint added
- [ ] Unit tests written and passing
- [ ] Integration tests written and passing

### Manual Testing
```bash
# 1. Start FastAPI server
uvicorn main:app --reload

# 2. Get auth token (use /api/auth/login)
# 3. Create checkout session
curl -X POST http://localhost:8000/api/billing/create-checkout-session \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"price_id":"price_basic_monthly","tier":"basic"}'

# Expected response:
{
  "session_id": "cs_test_...",
  "url": "https://checkout.stripe.com/pay/cs_test_..."
}

# 4. Visit URL in browser
# 5. Use test card: 4242 4242 4242 4242
# 6. After redirect, verify session
curl http://localhost:8000/api/billing/verify-session/cs_test_... \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Stripe Dashboard Verification
- [ ] Customer created in Stripe Dashboard (Customers tab)
- [ ] Checkout Session visible in Payments → Checkout Sessions
- [ ] Subscription created after successful payment

---

## Common Issues & Troubleshooting

### Issue 1: "Invalid price ID" Error
**Solution**: Ensure price IDs in `.env` match those in Stripe Dashboard

### Issue 2: Checkout Session Expires Immediately
**Solution**: Check `success_url` and `cancel_url` are valid URLs

### Issue 3: Customer Already Exists Error
**Solution**: This is expected behavior - function returns existing customer ID

---

## Next Steps

Once complete:
1. ✅ Run tests: `pytest tests/unit/test_billing_service.py -v`
2. ✅ Manual test checkout flow
3. ✅ Commit: `feat: implement checkout flow (Epic 2)`
4. ➡️ Proceed to **Epic 3: Webhook Handling & Provisioning**

---

**Epic Owner**: GitHub Copilot  
**Last Updated**: 2025-11-19
