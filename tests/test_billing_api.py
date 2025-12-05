import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient
from main import app
from dependencies.auth_dependencies import get_current_user_id, get_current_user_email, get_current_user_token
from services.billing_service import BillingService
from api.billing_routes import get_billing_service

# Mock dependencies
async def mock_get_current_user_id():
    return "test-user-id"

async def mock_get_current_user_email():
    return "test@example.com"

async def mock_get_current_user_token():
    return "test-token"

# Mock BillingService
mock_billing_service = MagicMock(spec=BillingService)
mock_billing_service.create_checkout_session = AsyncMock(return_value={
    "checkout_url": "https://checkout.stripe.com/test-session",
    "session_id": "cs_test_123"
})

def mock_get_billing_service_dependency():
    return mock_billing_service

# NOTE: Dependency overrides are set in setup_method() and cleaned in teardown_method()
# to prevent test contamination. Do NOT set them at module level.

client = TestClient(app)

class TestBillingAPI:
    
    def setup_method(self):
        # Ensure overrides are set before each test
        app.dependency_overrides[get_current_user_id] = mock_get_current_user_id
        app.dependency_overrides[get_current_user_email] = mock_get_current_user_email
        app.dependency_overrides[get_current_user_token] = mock_get_current_user_token
        app.dependency_overrides[get_billing_service] = mock_get_billing_service_dependency
    
    def teardown_method(self):
        # CRITICAL: Clean up dependency overrides to prevent test contamination
        # Without this, subsequent tests will still have these overrides active
        app.dependency_overrides.clear()
    
    def test_create_checkout_session_success(self):
        """Test successful checkout session creation"""
        # Reset mock
        mock_billing_service.create_checkout_session.reset_mock()
        mock_billing_service.create_checkout_session.return_value = {
            "checkout_url": "https://checkout.stripe.com/test-session",
            "session_id": "cs_test_123"
        }
        
        response = client.post(
            "/api/billing/create-checkout-session",
            json={"tier": "pro"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["checkout_url"] == "https://checkout.stripe.com/test-session"
        assert data["session_id"] == "cs_test_123"
        
        # Verify service call
        mock_billing_service.create_checkout_session.assert_called_once()
        call_args = mock_billing_service.create_checkout_session.call_args
        assert call_args.kwargs["user_id"] == "test-user-id"
        assert call_args.kwargs["email"] == "test@example.com"
        assert call_args.kwargs["tier"] == "pro"

    def test_create_checkout_session_invalid_tier(self):
        """Test checkout session with invalid tier"""
        # This validation happens in Pydantic schema, so it should return 422
        response = client.post(
            "/api/billing/create-checkout-session",
            json={"tier": "invalid_tier"}
        )
        
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_billing_service_integration(self):
        """
        Test BillingService logic with mocked Stripe.
        This tests the service layer directly, not the API.
        """
        with patch("stripe.Customer.create") as mock_customer_create, \
             patch("stripe.checkout.Session.create") as mock_session_create, \
             patch("stripe.checkout.Session.retrieve") as mock_session_retrieve, \
             patch("services.billing_service.Config") as MockConfig, \
             patch("services.billing_service.get_authed_supabase_client") as mock_authed_client:
            
            # Setup mocks
            mock_supabase = MagicMock()
            # Mock authenticated Supabase client for RLS
            mock_authed_client.return_value = mock_supabase
            # Mock get_or_create_customer DB check (return None to trigger creation)
            mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = None
            
            mock_customer_create.return_value.id = "cus_test_123"
            mock_session_create.return_value.url = "https://checkout.stripe.com/test"
            mock_session_create.return_value.id = "cs_test_123"
            mock_session_create.return_value.status = "open"  # Session must be open to be valid
            
            # Mock Session.retrieve to return the same open session (simulates fresh session)
            mock_session_retrieve.return_value = mock_session_create.return_value
            
            # Mock Config
            mock_config_instance = MockConfig.return_value
            mock_config_instance.get_price_id_from_tier.return_value = "price_test_123"
            mock_config_instance.STRIPE_SUCCESS_URL = "http://localhost:3000/success"
            mock_config_instance.STRIPE_CANCEL_URL = "http://localhost:3000/cancel"
            mock_config_instance.FRONTEND_URL = "http://localhost:3000"
            mock_config_instance.is_testing.return_value = True
            
            # Initialize service
            service = BillingService(mock_supabase)
            
            # Call method - include user_token for RLS (order: user_id, user_token, email, tier)
            result = await service.create_checkout_session("user_123", "test_token", "test@example.com", "pro")
            
            # Verify result
            assert result["checkout_url"] == "https://checkout.stripe.com/test"
            assert result["session_id"] == "cs_test_123"
            
            # Verify Stripe calls
            mock_customer_create.assert_called_once_with(
                email="test@example.com",
                metadata={"user_id": "user_123", "environment": "test"}
            )
            
            mock_session_create.assert_called_once()
            args, kwargs = mock_session_create.call_args
            assert kwargs["customer"] == "cus_test_123"
            assert kwargs["mode"] == "subscription"
            assert kwargs["line_items"][0]["price"] == "price_test_123"


class TestPreviewUpgrade:
    """Tests for the preview_upgrade method in BillingService."""
    
    def setup_method(self):
        # Set up API-level mocks for endpoint tests
        app.dependency_overrides[get_current_user_id] = mock_get_current_user_id
        app.dependency_overrides[get_current_user_email] = mock_get_current_user_email
        app.dependency_overrides[get_current_user_token] = mock_get_current_user_token
        app.dependency_overrides[get_billing_service] = mock_get_billing_service_dependency
    
    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_preview_upgrade_endpoint_success(self):
        """Test successful upgrade preview via API endpoint."""
        # Reset and configure mock for preview_upgrade
        mock_billing_service.preview_upgrade = AsyncMock(return_value={
            "current_tier": "premium",
            "target_tier": "pro",
            "is_upgrade": True,
            "proration_amount": 250,
            "proration_amount_formatted": "$2.50",
            "credit_amount": 500,
            "credit_amount_formatted": "$5.00",
            "debit_amount": 750,
            "debit_amount_formatted": "$7.50",
            "next_billing_amount": 1500,
            "next_billing_amount_formatted": "$15.00/month",
            "next_billing_date": "2025-12-15T00:00:00Z",
            "card_last4": "4242",
            "card_brand": "visa",
            "message": "You'll be charged $2.50 today (prorated). Then $15.00/month starting Dec 15."
        })
        
        response = client.post(
            "/api/billing/preview-upgrade",
            json={"tier": "pro"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["current_tier"] == "premium"
        assert data["target_tier"] == "pro"
        assert data["is_upgrade"] is True
        assert data["proration_amount"] == 250
        assert data["card_last4"] == "4242"
        mock_billing_service.preview_upgrade.assert_called_once()

    def test_preview_upgrade_endpoint_invalid_tier(self):
        """Test preview with invalid tier returns 422."""
        response = client.post(
            "/api/billing/preview-upgrade",
            json={"tier": "invalid_tier"}
        )
        assert response.status_code == 422

    def test_preview_upgrade_endpoint_downgrade(self):
        """Test preview endpoint for downgrade (pro -> premium)."""
        mock_billing_service.preview_upgrade = AsyncMock(return_value={
            "current_tier": "pro",
            "target_tier": "premium",
            "is_upgrade": False,
            "proration_amount": 0,  # No proration for downgrade
            "proration_amount_formatted": "$0.00",
            "credit_amount": 0,
            "credit_amount_formatted": "$0.00",
            "debit_amount": 0,
            "debit_amount_formatted": "$0.00",
            "next_billing_amount": 999,
            "next_billing_amount_formatted": "$9.99/month",
            "next_billing_date": "2025-12-15T00:00:00Z",
            "card_last4": "4242",
            "card_brand": "visa",
            "message": "Your plan will change to premium on Dec 15. You'll keep pro until then."
        })
        
        response = client.post(
            "/api/billing/preview-upgrade",
            json={"tier": "premium"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["is_upgrade"] is False
        # Downgrade has no proration
        assert data["proration_amount"] == 0
        assert data["credit_amount"] == 0
        assert "will change to premium" in data["message"]

    def test_preview_upgrade_endpoint_no_subscription(self):
        """Test preview returns 400 when user has no subscription."""
        from fastapi import HTTPException
        mock_billing_service.preview_upgrade = AsyncMock(
            side_effect=HTTPException(status_code=400, detail="No subscription found. Please subscribe first.")
        )
        
        response = client.post(
            "/api/billing/preview-upgrade",
            json={"tier": "pro"}
        )
        
        assert response.status_code == 400
        assert "subscribe first" in response.json()["detail"].lower()

    def test_preview_upgrade_endpoint_already_on_tier(self):
        """Test preview returns 400 when already on requested tier."""
        from fastapi import HTTPException
        mock_billing_service.preview_upgrade = AsyncMock(
            side_effect=HTTPException(status_code=400, detail="You are already subscribed to pro")
        )
        
        response = client.post(
            "/api/billing/preview-upgrade",
            json={"tier": "pro"}
        )
        
        assert response.status_code == 400
        assert "already subscribed" in response.json()["detail"].lower()

    def test_preview_upgrade_endpoint_zero_proration(self):
        """Test preview handles zero proration edge case."""
        mock_billing_service.preview_upgrade = AsyncMock(return_value={
            "current_tier": "premium",
            "target_tier": "pro",
            "is_upgrade": True,
            "proration_amount": 0,
            "proration_amount_formatted": "$0.00",
            "credit_amount": 500,
            "credit_amount_formatted": "$5.00",
            "debit_amount": 500,
            "debit_amount_formatted": "$5.00",
            "next_billing_amount": 1500,
            "next_billing_amount_formatted": "$15.00/month",
            "next_billing_date": "2025-12-15T00:00:00Z",
            "card_last4": "4242",
            "card_brand": "visa",
            "message": "No charge today - your credit exactly covers the upgrade. Then $15.00/month starting Dec 15."
        })
        
        response = client.post(
            "/api/billing/preview-upgrade",
            json={"tier": "pro"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["proration_amount"] == 0
        assert "No charge today" in data["message"]
        assert "credit exactly covers" in data["message"]

    def test_preview_upgrade_endpoint_negative_proration(self):
        """Test preview handles negative proration (user gets credit)."""
        mock_billing_service.preview_upgrade = AsyncMock(return_value={
            "current_tier": "premium",
            "target_tier": "pro",
            "is_upgrade": True,
            "proration_amount": -100,
            "proration_amount_formatted": "-$1.00",
            "credit_amount": 600,
            "credit_amount_formatted": "$6.00",
            "debit_amount": 500,
            "debit_amount_formatted": "$5.00",
            "next_billing_amount": 1500,
            "next_billing_amount_formatted": "$15.00/month",
            "next_billing_date": "2025-12-15T00:00:00Z",
            "card_last4": "4242",
            "card_brand": "visa",
            "message": "You'll receive a $1.00 credit. Then $15.00/month starting Dec 15."
        })
        
        response = client.post(
            "/api/billing/preview-upgrade",
            json={"tier": "pro"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["proration_amount"] == -100
        assert "receive" in data["message"] and "credit" in data["message"]

    def test_preview_upgrade_endpoint_stripe_error(self):
        """Test preview handles Stripe errors gracefully."""
        from fastapi import HTTPException
        mock_billing_service.preview_upgrade = AsyncMock(
            side_effect=HTTPException(status_code=502, detail="Stripe error: Connection failed")
        )
        
        response = client.post(
            "/api/billing/preview-upgrade",
            json={"tier": "pro"}
        )
        
        assert response.status_code == 502
        assert "Stripe error" in response.json()["detail"]

