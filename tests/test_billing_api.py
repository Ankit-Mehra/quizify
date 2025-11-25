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

# Override dependencies
app.dependency_overrides[get_current_user_id] = mock_get_current_user_id
app.dependency_overrides[get_current_user_email] = mock_get_current_user_email
app.dependency_overrides[get_current_user_token] = mock_get_current_user_token
app.dependency_overrides[get_billing_service] = mock_get_billing_service_dependency

client = TestClient(app)

class TestBillingAPI:
    
    def setup_method(self):
        # Ensure overrides are set before each test
        app.dependency_overrides[get_current_user_id] = mock_get_current_user_id
        app.dependency_overrides[get_current_user_email] = mock_get_current_user_email
        app.dependency_overrides[get_current_user_token] = mock_get_current_user_token
        app.dependency_overrides[get_billing_service] = mock_get_billing_service_dependency
    
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
            
            # Mock Config
            mock_config_instance = MockConfig.return_value
            mock_config_instance.get_price_id_from_tier.return_value = "price_test_123"
            mock_config_instance.STRIPE_SUCCESS_URL = "http://localhost:3000/success"
            mock_config_instance.STRIPE_CANCEL_URL = "http://localhost:3000/cancel"
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
