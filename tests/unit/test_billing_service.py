"""
Unit tests for BillingService helper methods.

Tests the _get_attr unified accessor for both dict and Stripe API objects.
"""
from unittest.mock import MagicMock
from services.billing_service import BillingService


class TestGetAttrHelper:
    """Test the _get_attr static method for unified attribute access."""
    
    def test_get_attr_from_dict(self):
        """_get_attr should return value from dict using .get()"""
        data = {"status": "active", "customer": "cus_123"}
        
        assert BillingService._get_attr(data, "status") == "active"
        assert BillingService._get_attr(data, "customer") == "cus_123"
    
    def test_get_attr_from_dict_with_default(self):
        """_get_attr should return default when key not in dict"""
        data = {"status": "active"}
        
        assert BillingService._get_attr(data, "missing") is None
        assert BillingService._get_attr(data, "missing", "default") == "default"
    
    def test_get_attr_from_object(self):
        """_get_attr should return value from object using getattr()"""
        # Simulate a Stripe API object (uses attribute access)
        mock_subscription = MagicMock()
        mock_subscription.status = "active"
        mock_subscription.customer = "cus_456"
        mock_subscription.current_period_start = 1700000000
        mock_subscription.current_period_end = 1702678400
        
        assert BillingService._get_attr(mock_subscription, "status") == "active"
        assert BillingService._get_attr(mock_subscription, "customer") == "cus_456"
        assert BillingService._get_attr(mock_subscription, "current_period_start") == 1700000000
        assert BillingService._get_attr(mock_subscription, "current_period_end") == 1702678400
    
    def test_get_attr_from_object_with_default(self):
        """_get_attr should return default when attribute not on object"""
        mock_obj = MagicMock(spec=[])  # Empty spec means no attributes
        
        assert BillingService._get_attr(mock_obj, "missing") is None
        assert BillingService._get_attr(mock_obj, "missing", "default") == "default"
    
    def test_get_attr_with_none_object(self):
        """_get_attr should return default when object is None"""
        assert BillingService._get_attr(None, "any_key") is None
        assert BillingService._get_attr(None, "any_key", "default") == "default"
    
    def test_get_attr_with_nested_dict(self):
        """_get_attr should work with nested dict access"""
        data = {"metadata": {"user_id": "uuid-123", "plan": "pro"}}
        
        # First level access
        metadata = BillingService._get_attr(data, "metadata", {})
        assert metadata == {"user_id": "uuid-123", "plan": "pro"}
        
        # Second level access
        user_id = BillingService._get_attr(metadata, "user_id")
        assert user_id == "uuid-123"
    
    def test_get_attr_with_nested_object(self):
        """_get_attr should work with nested object access (Stripe metadata)"""
        # Simulate Stripe subscription with metadata object
        mock_metadata = MagicMock()
        mock_metadata.user_id = "uuid-456"
        mock_metadata.plan = "basic"
        
        mock_subscription = MagicMock()
        mock_subscription.metadata = mock_metadata
        
        # First level access
        metadata = BillingService._get_attr(mock_subscription, "metadata", {})
        assert metadata == mock_metadata
        
        # Second level access
        user_id = BillingService._get_attr(metadata, "user_id")
        assert user_id == "uuid-456"
    
    def test_get_attr_with_empty_dict_default(self):
        """_get_attr should return empty dict when specified as default"""
        data = {}
        
        result = BillingService._get_attr(data, "metadata", {})
        assert result == {}
        assert isinstance(result, dict)
    
    def test_get_attr_with_integer_values(self):
        """_get_attr should correctly return integer values (like timestamps)"""
        # Dict access
        dict_data = {
            "current_period_start": 1700000000,
            "current_period_end": 1702678400
        }
        assert BillingService._get_attr(dict_data, "current_period_start") == 1700000000
        
        # Object access
        mock_obj = MagicMock()
        mock_obj.current_period_start = 1700000000
        mock_obj.current_period_end = 1702678400
        assert BillingService._get_attr(mock_obj, "current_period_start") == 1700000000
    
    def test_get_attr_with_none_value(self):
        """_get_attr should distinguish between missing key and None value"""
        # Dict with None value
        dict_data = {"nullable_field": None, "other_field": "value"}
        assert BillingService._get_attr(dict_data, "nullable_field") is None
        assert BillingService._get_attr(dict_data, "nullable_field", "default") is None  # Key exists, value is None
        
        # Object with None value
        mock_obj = MagicMock()
        mock_obj.nullable_field = None
        assert BillingService._get_attr(mock_obj, "nullable_field") is None


class TestExtractPriceIdFromSubscription:
    """Test price ID extraction from Stripe subscription objects.
    
    Note: These tests call the method directly on a mock instance to avoid
    needing a full BillingService initialization which requires Stripe API key.
    """
    
    def test_extract_price_id_from_dict_subscription(self):
        """Should extract price_id from dict-style subscription (webhook data)."""
        subscription = {
            "id": "sub_123",
            "items": {
                "data": [
                    {"price": {"id": "price_abc123"}}
                ]
            }
        }
        
        # Call the method directly on the class with a mock self
        mock_self = MagicMock()
        mock_self._get_attr = BillingService._get_attr
        
        price_id = BillingService._extract_price_id_from_subscription(
            mock_self,
            subscription, 
            context="test"
        )
        assert price_id == "price_abc123"
    
    def test_extract_price_id_from_object_subscription(self):
        """Should extract price_id from Stripe API object subscription."""
        # Simulate Stripe API object structure
        mock_price = MagicMock()
        mock_price.id = "price_xyz789"
        
        mock_item = MagicMock()
        mock_item.price = mock_price
        
        mock_items = MagicMock()
        mock_items.data = [mock_item]
        
        mock_subscription = MagicMock()
        mock_subscription.id = "sub_456"
        mock_subscription.items = mock_items
        
        # Call the method directly on the class with a mock self
        mock_self = MagicMock()
        mock_self._get_attr = BillingService._get_attr
        
        price_id = BillingService._extract_price_id_from_subscription(
            mock_self,
            mock_subscription,
            context="test"
        )
        assert price_id == "price_xyz789"
    
    def test_extract_price_id_returns_none_for_empty_items(self):
        """Should return None when subscription has no items."""
        subscription = {
            "id": "sub_123",
            "items": {"data": []}
        }
        
        mock_self = MagicMock()
        mock_self._get_attr = BillingService._get_attr
        
        price_id = BillingService._extract_price_id_from_subscription(
            mock_self,
            subscription,
            context="test"
        )
        assert price_id is None
    
    def test_extract_price_id_returns_none_for_missing_items(self):
        """Should return None when subscription has no items key."""
        subscription = {"id": "sub_123"}
        
        mock_self = MagicMock()
        mock_self._get_attr = BillingService._get_attr
        
        price_id = BillingService._extract_price_id_from_subscription(
            mock_self,
            subscription,
            context="test"
        )
        assert price_id is None


class TestExtractPeriodDatesFromSubscription:
    """Test billing period extraction from Stripe subscription objects.
    
    Per Stripe API docs, current_period_start and current_period_end are
    on subscription ITEMS (items.data[].current_period_start/end), NOT on
    the subscription object itself.
    """
    
    def test_extract_period_dates_from_dict_subscription(self):
        """Should extract period dates from dict-style subscription (webhook data)."""
        subscription = {
            "id": "sub_123",
            "items": {
                "data": [
                    {
                        "current_period_start": 1700000000,
                        "current_period_end": 1702678400,
                        "price": {"id": "price_abc123"}
                    }
                ]
            }
        }
        
        mock_self = MagicMock()
        mock_self._get_attr = BillingService._get_attr
        
        start, end = BillingService._extract_period_dates_from_subscription(
            mock_self,
            subscription,
            context="test"
        )
        assert start == 1700000000
        assert end == 1702678400
    
    def test_extract_period_dates_from_object_subscription(self):
        """Should extract period dates from Stripe API object subscription."""
        # Create mock item
        mock_item = MagicMock()
        mock_item.current_period_start = 1700000000
        mock_item.current_period_end = 1702678400
        
        # Create mock items container
        mock_items = MagicMock()
        mock_items.data = [mock_item]
        
        # Create mock subscription
        mock_subscription = MagicMock()
        mock_subscription.id = "sub_456"
        mock_subscription.items = mock_items
        
        mock_self = MagicMock()
        mock_self._get_attr = BillingService._get_attr
        
        start, end = BillingService._extract_period_dates_from_subscription(
            mock_self,
            mock_subscription,
            context="test"
        )
        assert start == 1700000000
        assert end == 1702678400
    
    def test_extract_period_dates_returns_none_for_empty_items(self):
        """Should return (None, None) when subscription has no items."""
        subscription = {
            "id": "sub_123",
            "items": {"data": []}
        }
        
        mock_self = MagicMock()
        mock_self._get_attr = BillingService._get_attr
        
        start, end = BillingService._extract_period_dates_from_subscription(
            mock_self,
            subscription,
            context="test"
        )
        assert start is None
        assert end is None
    
    def test_extract_period_dates_returns_none_for_missing_items(self):
        """Should return (None, None) when subscription has no items key."""
        subscription = {"id": "sub_123"}
        
        mock_self = MagicMock()
        mock_self._get_attr = BillingService._get_attr
        
        start, end = BillingService._extract_period_dates_from_subscription(
            mock_self,
            subscription,
            context="test"
        )
        assert start is None
        assert end is None
    
    def test_extract_period_dates_handles_multiple_items(self):
        """Should extract period dates from first subscription item when multiple exist."""
        subscription = {
            "id": "sub_123",
            "items": {
                "data": [
                    {
                        "current_period_start": 1700000000,
                        "current_period_end": 1702678400,
                        "price": {"id": "price_first"}
                    },
                    {
                        "current_period_start": 1705000000,
                        "current_period_end": 1707678400,
                        "price": {"id": "price_second"}
                    }
                ]
            }
        }
        
        mock_self = MagicMock()
        mock_self._get_attr = BillingService._get_attr
        
        start, end = BillingService._extract_period_dates_from_subscription(
            mock_self,
            subscription,
            context="test"
        )
        # Should use first item's period dates
        assert start == 1700000000
        assert end == 1702678400
