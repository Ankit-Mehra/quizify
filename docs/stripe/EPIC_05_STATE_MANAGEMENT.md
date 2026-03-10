# Epic 5: Subscription State Management (Day 9)

**Status**: Not Started  
**Duration**: 1 day  
**Priority**: High  
**Dependencies**: Epic 1, Epic 3, Epic 4

---

## Overview

Implement comprehensive subscription state management including status queries, quota enforcement, grace period handling, and synchronization with Stripe.

---

## Tasks Breakdown

### Task 5.1: Implement Subscription Status Query (2 hours)

**File**: `services/billing_service.py`

**Action**: Add subscription status retrieval method

```python
async def get_subscription_status(self, user_id: str) -> Dict[str, Any]:
    """
    Get current subscription status for user
    
    Args:
        user_id: Quizify user ID (UUID)
        
    Returns:
        Dict with subscription details
    """
    try:
        supabase = get_supabase()
        
        # Query user_tier_info view for comprehensive status
        result = supabase.table("user_tier_info")\
            .select("*")\
            .eq("id", user_id)\
            .single()\
            .execute()
        
        if not result.data:
            logger.warning(f"User {user_id[:8]} not found in user_tier_info")
            raise HTTPException(status_code=404, detail="User not found")
        
        data = result.data
        
        # Check if user has active subscription
        has_subscription = bool(
            data.get("stripe_subscription_id") and 
            data.get("subscription_status") in ["active", "past_due", "trialing"]
        )
        
        return {
            "has_subscription": has_subscription,
            "tier": data.get("account_tier", "free"),
            "status": data.get("subscription_status"),
            "current_period_end": data.get("subscription_current_period_end"),
            "cancel_at_period_end": data.get("cancel_at_period_end", False),
            "customer_id": data.get("stripe_customer_id"),
            "subscription_id": data.get("stripe_subscription_id"),
            "grace_period_end": data.get("subscription_grace_period_end"),
            "current_quiz_count": data.get("current_quiz_count", 0),
            "quota_limit": data.get("quota_limit", 5),
            "quota_exceeded": data.get("quota_exceeded", False)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error getting subscription status for user {user_id[:8]}: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve subscription status"
        )
```

---

### Task 5.2: Implement Status API Endpoint (1 hour)

**File**: `api/billing_routes.py`

**Action**: Implement subscription status endpoint

```python
@router.get(
    "/subscription-status",
    response_model=SubscriptionStatusResponse,
    summary="Get Subscription Status",
    description="Get current subscription status for authenticated user"
)
async def get_subscription_status(
    current_user: Dict = Depends(get_current_user)
):
    """
    Get current subscription status
    
    **Authentication**: Required (Bearer token)
    
    **Returns**:
    - `has_subscription`: Whether user has active subscription
    - `tier`: Current account tier (free/basic/educator)
    - `status`: Stripe subscription status (active/past_due/canceled/etc)
    - `current_period_end`: Timestamp when current period ends
    - `cancel_at_period_end`: True if subscription set to cancel
    - `customer_id`: Stripe customer ID
    - `subscription_id`: Stripe subscription ID
    - `grace_period_end`: Grace period end for past_due subscriptions
    - `current_quiz_count`: Number of quizzes created this month
    - `quota_limit`: Maximum quizzes allowed per month
    - `quota_exceeded`: True if quota limit reached
    
    **Use Cases**:
    - Display subscription info in user dashboard
    - Show renewal date and cancellation status
    - Display quota usage and limits
    - Determine if upgrade needed
    """
    user_id = current_user["id"]
    
    logger.info(f"Subscription status query from user {user_id[:8]}")
    
    result = await billing_service.get_subscription_status(user_id)
    
    return SubscriptionStatusResponse(**result)
```

---

### Task 5.3: Enhance Quota Enforcement (2 hours)

**File**: `services/tier_service.py`

**Action**: Update quota checks to consider grace periods

```python
from datetime import datetime

async def check_quota_with_grace_period(user_id: str) -> Dict[str, Any]:
    """
    Check quota with grace period consideration
    
    Args:
        user_id: Quizify user ID
        
    Returns:
        Dict with quota status and grace period info
    """
    supabase = get_supabase()
    
    # Get tier info with subscription status
    result = supabase.table("user_tier_info")\
        .select("*")\
        .eq("id", user_id)\
        .single()\
        .execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="User not found")
    
    data = result.data
    
    quota_exceeded = data.get("quota_exceeded", False)
    subscription_status = data.get("subscription_status")
    grace_period_end = data.get("subscription_grace_period_end")
    
    # If quota exceeded and past_due, check grace period
    if quota_exceeded and subscription_status == "past_due" and grace_period_end:
        grace_end_dt = datetime.fromisoformat(grace_period_end.replace("Z", "+00:00"))
        now = datetime.utcnow().replace(tzinfo=grace_end_dt.tzinfo)
        
        in_grace_period = now < grace_end_dt
        
        return {
            "quota_exceeded": True,
            "in_grace_period": in_grace_period,
            "grace_period_end": grace_period_end,
            "can_create_quiz": in_grace_period,  # Allow during grace period
            "message": (
                f"Your payment failed. You have until {grace_period_end} "
                "to update your payment method to continue using your subscription."
                if in_grace_period
                else "Your subscription is past due. Please update your payment method."
            )
        }
    
    return {
        "quota_exceeded": quota_exceeded,
        "in_grace_period": False,
        "grace_period_end": None,
        "can_create_quiz": not quota_exceeded,
        "current_quiz_count": data.get("current_quiz_count", 0),
        "quota_limit": data.get("quota_limit", 5),
        "message": (
            f"Quota exceeded: {data.get('current_quiz_count', 0)}/{data.get('quota_limit', 5)} "
            "quizzes used this month. Upgrade to create more."
            if quota_exceeded
            else None
        )
    }
```

---

### Task 5.4: Update Quiz Creation Validation (1 hour)

**File**: `handlers/quiz_handlers.py`

**Action**: Use grace period-aware quota check

```python
from services.tier_service import check_quota_with_grace_period

async def create_quiz_with_validation(user_id: str, quiz_data: Dict) -> Dict:
    """
    Create quiz with quota validation (grace period aware)
    
    Args:
        user_id: Quizify user ID
        quiz_data: Quiz data to create
        
    Returns:
        Created quiz data
        
    Raises:
        HTTPException: If quota exceeded or validation fails
    """
    # Check quota with grace period consideration
    quota_status = await check_quota_with_grace_period(user_id)
    
    if not quota_status["can_create_quiz"]:
        logger.warning(
            f"Quiz creation denied for user {user_id[:8]}: "
            f"quota_exceeded={quota_status['quota_exceeded']}, "
            f"in_grace_period={quota_status['in_grace_period']}"
        )
        
        raise HTTPException(
            status_code=403,
            detail={
                "error": "Quota exceeded",
                "message": quota_status["message"],
                "quota_exceeded": True,
                "in_grace_period": quota_status["in_grace_period"],
                "grace_period_end": quota_status["grace_period_end"]
            }
        )
    
    # Proceed with quiz creation
    # ... existing quiz creation logic ...
```

---

### Task 5.5: Implement Subscription Sync (2 hours)

**File**: `services/billing_service.py`

**Action**: Add method to sync subscription state from Stripe

```python
async def sync_subscription_from_stripe(self, user_id: str) -> Dict[str, Any]:
    """
    Sync subscription state from Stripe
    
    Useful for manual sync or debugging inconsistencies
    
    Args:
        user_id: Quizify user ID
        
    Returns:
        Updated subscription status
    """
    try:
        supabase = get_supabase()
        
        # Get subscription ID from database
        result = supabase.table("profiles")\
            .select("stripe_subscription_id, stripe_customer_id")\
            .eq("id", user_id)\
            .single()\
            .execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        subscription_id = result.data.get("stripe_subscription_id")
        customer_id = result.data.get("stripe_customer_id")
        
        if not subscription_id:
            logger.info(f"User {user_id[:8]} has no subscription to sync")
            return {"message": "No subscription found"}
        
        # Fetch subscription from Stripe
        logger.info(
            f"Syncing subscription {subscription_id} for user {user_id[:8]}"
        )
        
        stripe.api_key = config.STRIPE_SECRET_KEY
        subscription = stripe.Subscription.retrieve(subscription_id)
        
        # Extract tier from metadata
        tier = subscription.metadata.get("tier", "free")
        
        # Update database with Stripe data
        from datetime import datetime
        period_end_dt = datetime.utcfromtimestamp(subscription.current_period_end)
        
        update_data = {
            "subscription_status": subscription.status,
            "subscription_current_period_end": period_end_dt.isoformat(),
            "cancel_at_period_end": subscription.cancel_at_period_end
        }
        
        # Update tier if subscription is active
        if subscription.status == "active":
            update_data["account_tier"] = tier
            update_data["subscription_grace_period_end"] = None
        
        supabase.table("profiles")\
            .update(update_data)\
            .eq("id", user_id)\
            .execute()
        
        logger.info(
            f"Synced subscription for user {user_id[:8]}: "
            f"status={subscription.status}, tier={tier}"
        )
        
        return {
            "message": "Subscription synced successfully",
            "status": subscription.status,
            "tier": tier,
            "current_period_end": period_end_dt.isoformat()
        }
        
    except stripe.error.InvalidRequestError as e:
        # Subscription not found in Stripe
        logger.warning(
            f"Subscription not found in Stripe for user {user_id[:8]}: {e}"
        )
        
        # Clear invalid subscription ID
        supabase.table("profiles").update({
            "stripe_subscription_id": None,
            "subscription_status": None
        }).eq("id", user_id).execute()
        
        return {"message": "Subscription not found, cleared from database"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error syncing subscription for user {user_id[:8]}: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to sync subscription"
        )
```

---

### Task 5.6: Add Sync API Endpoint (1 hour)

**File**: `api/billing_routes.py`

**Action**: Add admin endpoint for subscription sync

```python
@router.post(
    "/sync-subscription",
    summary="Sync Subscription from Stripe",
    description="Manually sync subscription state from Stripe (admin or self-service)",
    tags=["billing", "admin"]
)
async def sync_subscription(
    current_user: Dict = Depends(get_current_user)
):
    """
    Sync subscription state from Stripe
    
    **Authentication**: Required (Bearer token)
    
    **Use Cases**:
    - Debugging subscription inconsistencies
    - Manual refresh after Stripe Dashboard changes
    - Recovery from webhook failures
    
    **Returns**:
    - Sync status and updated subscription details
    """
    user_id = current_user["id"]
    
    logger.info(f"Manual subscription sync requested by user {user_id[:8]}")
    
    result = await billing_service.sync_subscription_from_stripe(user_id)
    
    return result
```

---

### Task 5.7: Add Subscription Status Dashboard Widget (1 hour)

**File**: `schemas/billing.py`

**Action**: Add extended status response for dashboard

```python
class SubscriptionDashboardWidget(BaseModel):
    """Extended subscription status for dashboard widget"""
    has_subscription: bool
    tier: str
    status: Optional[str] = None
    current_period_end: Optional[datetime] = None
    cancel_at_period_end: bool = False
    
    # Quota info
    current_quiz_count: int
    quota_limit: int
    quota_percentage: float = Field(
        ...,
        description="Percentage of quota used (0-100)"
    )
    quota_exceeded: bool
    
    # Grace period info
    in_grace_period: bool = False
    grace_period_end: Optional[datetime] = None
    
    # Status messages
    status_message: Optional[str] = Field(
        None,
        description="Human-readable status message"
    )
    action_required: bool = Field(
        False,
        description="True if user action required (e.g., payment failed)"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "has_subscription": True,
                "tier": "basic",
                "status": "active",
                "current_period_end": "2025-12-19T00:00:00Z",
                "cancel_at_period_end": False,
                "current_quiz_count": 45,
                "quota_limit": 100,
                "quota_percentage": 45.0,
                "quota_exceeded": False,
                "in_grace_period": False,
                "grace_period_end": None,
                "status_message": "Your subscription is active",
                "action_required": False
            }
        }
```

---

### Task 5.8: Add Unit Tests (2 hours)

**File**: `tests/unit/test_subscription_state.py` (NEW)

**Action**: Create comprehensive state management tests

```python
"""
Unit tests for subscription state management
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from services.billing_service import billing_service
from services.tier_service import check_quota_with_grace_period

@pytest.mark.asyncio
class TestSubscriptionStatus:
    """Test subscription status queries"""
    
    async def test_get_subscription_status_active(self, mock_supabase):
        """Test getting status for active subscription"""
        mock_supabase.table().select().eq().single().execute.return_value = \
            MagicMock(data={
                "id": "user_123",
                "account_tier": "basic",
                "stripe_subscription_id": "sub_test123",
                "subscription_status": "active",
                "current_quiz_count": 45,
                "quota_limit": 100,
                "quota_exceeded": False
            })
        
        result = await billing_service.get_subscription_status("user_123")
        
        assert result["has_subscription"] is True
        assert result["tier"] == "basic"
        assert result["status"] == "active"
    
    async def test_get_subscription_status_free_tier(self, mock_supabase):
        """Test getting status for free tier user"""
        mock_supabase.table().select().eq().single().execute.return_value = \
            MagicMock(data={
                "id": "user_123",
                "account_tier": "free",
                "stripe_subscription_id": None,
                "subscription_status": None,
                "current_quiz_count": 3,
                "quota_limit": 5,
                "quota_exceeded": False
            })
        
        result = await billing_service.get_subscription_status("user_123")
        
        assert result["has_subscription"] is False
        assert result["tier"] == "free"

@pytest.mark.asyncio
class TestGracePeriodHandling:
    """Test grace period quota checks"""
    
    async def test_quota_check_within_grace_period(self, mock_supabase):
        """Test quota check during grace period allows creation"""
        # Grace period ends in 5 days
        grace_end = (datetime.utcnow() + timedelta(days=5)).isoformat()
        
        mock_supabase.table().select().eq().single().execute.return_value = \
            MagicMock(data={
                "id": "user_123",
                "quota_exceeded": True,
                "subscription_status": "past_due",
                "subscription_grace_period_end": grace_end
            })
        
        result = await check_quota_with_grace_period("user_123")
        
        assert result["in_grace_period"] is True
        assert result["can_create_quiz"] is True
    
    async def test_quota_check_grace_period_expired(self, mock_supabase):
        """Test quota check after grace period denies creation"""
        # Grace period ended 1 day ago
        grace_end = (datetime.utcnow() - timedelta(days=1)).isoformat()
        
        mock_supabase.table().select().eq().single().execute.return_value = \
            MagicMock(data={
                "id": "user_123",
                "quota_exceeded": True,
                "subscription_status": "past_due",
                "subscription_grace_period_end": grace_end
            })
        
        result = await check_quota_with_grace_period("user_123")
        
        assert result["in_grace_period"] is False
        assert result["can_create_quiz"] is False

@pytest.mark.asyncio
class TestSubscriptionSync:
    """Test subscription synchronization"""
    
    @patch("stripe.Subscription.retrieve")
    async def test_sync_subscription_success(
        self,
        mock_retrieve,
        mock_supabase
    ):
        """Test successful subscription sync"""
        # Mock database lookup
        mock_supabase.table().select().eq().single().execute.return_value = \
            MagicMock(data={
                "stripe_subscription_id": "sub_test123",
                "stripe_customer_id": "cus_test123"
            })
        
        # Mock Stripe subscription
        mock_retrieve.return_value = MagicMock(
            id="sub_test123",
            status="active",
            current_period_end=1734566400,
            cancel_at_period_end=False,
            metadata={"tier": "basic", "user_id": "user_123"}
        )
        
        result = await billing_service.sync_subscription_from_stripe("user_123")
        
        assert "synced successfully" in result["message"].lower()
        assert result["status"] == "active"
```

---

## Verification Checklist

### Code Verification
- [ ] Subscription status query implemented
- [ ] Status API endpoint functional
- [ ] Grace period quota checks implemented
- [ ] Quiz creation validation updated
- [ ] Subscription sync implemented
- [ ] Sync API endpoint added
- [ ] Unit tests written and passing

### Manual Testing
```bash
# 1. Get subscription status
curl http://localhost:8000/api/billing/subscription-status \
  -H "Authorization: Bearer YOUR_TOKEN"

# 2. Test quota with grace period (simulate past_due)
# Update user to past_due in database, set grace period
# Attempt to create quiz - should succeed

# 3. Test subscription sync
curl -X POST http://localhost:8000/api/billing/sync-subscription \
  -H "Authorization: Bearer YOUR_TOKEN"

# 4. Verify database updated with synced data
```

---

## Common Issues & Troubleshooting

### Issue 1: Grace Period Not Working
**Solution**: Check `subscription_grace_period_end` timestamp is in future and timezone-aware

### Issue 2: Quota Count Incorrect
**Solution**: Verify `user_tier_info` view is querying correctly with `date_trunc('month', ...)`

### Issue 3: Sync Fails with "Subscription Not Found"
**Solution**: Subscription may have been deleted in Stripe. Sync clears invalid IDs automatically.

---

## Next Steps

Once complete:
1. ✅ Run tests: `pytest tests/unit/test_subscription_state.py -v`
2. ✅ Manual test all status scenarios
3. ✅ Test grace period behavior
4. ✅ Commit: `feat: implement subscription state management (Epic 5)`
5. ➡️ Proceed to **Epic 6: Testing & Security**

---

**Epic Owner**: GitHub Copilot  
**Last Updated**: 2025-11-19
