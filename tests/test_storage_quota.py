"""
Tests for storage quota feature.

Tests the storage quota enforcement for file uploads:
- Free plan: 250 MB
- Pay-as-you-go: 2 GB
- Pro subscription: 5 GB
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi import HTTPException
from services.storage_service import (
    STORAGE_QUOTA_FREE,
    STORAGE_QUOTA_PAYG,
    STORAGE_QUOTA_PRO,
    format_bytes,
    get_plan_type,
    get_storage_quota_for_plan,
    get_storage_quota_info,
    check_storage_quota,
    validate_storage_quota_or_raise,
)


# ============================================================================
# Unit Tests: format_bytes
# ============================================================================

class TestFormatBytes:
    """Tests for format_bytes utility function."""
    
    def test_format_bytes_zero(self):
        """Test formatting zero bytes."""
        assert format_bytes(0) == "0 B"
    
    def test_format_bytes_negative(self):
        """Test formatting negative bytes returns 0 B."""
        assert format_bytes(-100) == "0 B"
    
    def test_format_bytes_bytes(self):
        """Test formatting small byte values."""
        assert format_bytes(512) == "512 B"
        assert format_bytes(1) == "1 B"
    
    def test_format_bytes_kilobytes(self):
        """Test formatting kilobyte values."""
        assert format_bytes(1024) == "1.0 KB"
        assert format_bytes(1536) == "1.5 KB"
    
    def test_format_bytes_megabytes(self):
        """Test formatting megabyte values."""
        assert format_bytes(1048576) == "1.0 MB"
        assert format_bytes(52428800) == "50.0 MB"
        assert format_bytes(262144000) == "250.0 MB"  # Free quota
    
    def test_format_bytes_gigabytes(self):
        """Test formatting gigabyte values."""
        assert format_bytes(1073741824) == "1.0 GB"
        assert format_bytes(2147483648) == "2.0 GB"  # Pay-as-you-go quota
        assert format_bytes(5368709120) == "5.0 GB"  # Pro quota


# ============================================================================
# Unit Tests: get_plan_type
# ============================================================================

class TestGetPlanType:
    """Tests for plan type determination."""
    
    def test_pro_with_active_subscription(self):
        """Pro users with active subscription get 'pro'."""
        assert get_plan_type("pro", "active", 0) == "pro"
        assert get_plan_type("pro", "active", 100) == "pro"  # Even with purchased credits
    
    def test_pro_with_trialing_subscription(self):
        """Pro users trialing get 'pro'."""
        assert get_plan_type("pro", "trialing", 0) == "pro"
    
    def test_pro_with_canceled_subscription(self):
        """Pro users with canceled subscription but no credits get 'free'."""
        assert get_plan_type("pro", "canceled", 0) == "free"
    
    def test_pro_canceled_with_purchased_credits(self):
        """Pro users with canceled subscription but purchased credits get 'payg'."""
        assert get_plan_type("pro", "canceled", 100) == "payg"
    
    def test_free_with_purchased_credits(self):
        """Free users with purchased credits get 'payg'."""
        assert get_plan_type("free", None, 10) == "payg"
        assert get_plan_type("free", None, 1) == "payg"
    
    def test_free_without_credits(self):
        """Free users without purchased credits get 'free'."""
        assert get_plan_type("free", None, 0) == "free"
        assert get_plan_type(None, None, 0) == "free"


# ============================================================================
# Unit Tests: get_storage_quota_for_plan
# ============================================================================

class TestGetStorageQuotaForPlan:
    """Tests for storage quota values by plan."""
    
    def test_free_quota(self):
        """Free plan gets 250 MB."""
        assert get_storage_quota_for_plan("free") == STORAGE_QUOTA_FREE
        assert get_storage_quota_for_plan("free") == 262_144_000
    
    def test_payg_quota(self):
        """Pay-as-you-go plan gets 2 GB."""
        assert get_storage_quota_for_plan("payg") == STORAGE_QUOTA_PAYG
        assert get_storage_quota_for_plan("payg") == 2_147_483_648
    
    def test_pro_quota(self):
        """Pro plan gets 5 GB."""
        assert get_storage_quota_for_plan("pro") == STORAGE_QUOTA_PRO
        assert get_storage_quota_for_plan("pro") == 5_368_709_120
    
    def test_unknown_plan_defaults_to_free(self):
        """Unknown plan defaults to free quota."""
        assert get_storage_quota_for_plan("unknown") == STORAGE_QUOTA_FREE


# ============================================================================
# Integration Tests: get_storage_quota_info
# ============================================================================

class TestGetStorageQuotaInfo:
    """Tests for getting storage quota info from database."""
    
    @pytest.mark.asyncio
    async def test_free_user_quota_info(self):
        """Free user gets correct quota info."""
        mock_profile = {
            "billing_plan": "free",
            "subscription_status": None,
            "credit_units_purchased": 0,
        }
        
        with patch("services.storage_service.get_supabase") as mock_supabase:
            mock_client = MagicMock()
            mock_supabase.return_value = mock_client
            
            # Mock profile query
            mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = Mock(data=mock_profile)
            
            # Mock RPC for storage usage
            mock_client.rpc.return_value.execute.return_value = Mock(data=0)
            
            info = await get_storage_quota_info("test_user_id")
            
            assert info["plan_type"] == "free"
            assert info["storage_quota_bytes"] == STORAGE_QUOTA_FREE
            assert info["storage_used_bytes"] == 0
            assert info["storage_remaining_bytes"] == STORAGE_QUOTA_FREE
            assert info["usage_percentage"] == 0.0
    
    @pytest.mark.asyncio
    async def test_payg_user_quota_info(self):
        """Pay-as-you-go user gets correct quota info."""
        mock_profile = {
            "billing_plan": "free",
            "subscription_status": None,
            "credit_units_purchased": 20,  # Has purchased credits
        }
        
        with patch("services.storage_service.get_supabase") as mock_supabase:
            mock_client = MagicMock()
            mock_supabase.return_value = mock_client
            
            mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = Mock(data=mock_profile)
            mock_client.rpc.return_value.execute.return_value = Mock(data=1073741824)  # 1 GB used
            
            info = await get_storage_quota_info("test_user_id")
            
            assert info["plan_type"] == "payg"
            assert info["storage_quota_bytes"] == STORAGE_QUOTA_PAYG
            assert info["storage_used_bytes"] == 1073741824
            assert info["storage_remaining_bytes"] == STORAGE_QUOTA_PAYG - 1073741824
            assert info["usage_percentage"] == 50.0
    
    @pytest.mark.asyncio
    async def test_pro_user_quota_info(self):
        """Pro user gets correct quota info."""
        mock_profile = {
            "billing_plan": "pro",
            "subscription_status": "active",
            "credit_units_purchased": 0,
        }
        
        with patch("services.storage_service.get_supabase") as mock_supabase:
            mock_client = MagicMock()
            mock_supabase.return_value = mock_client
            
            mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = Mock(data=mock_profile)
            mock_client.rpc.return_value.execute.return_value = Mock(data=2684354560)  # 2.5 GB used
            
            info = await get_storage_quota_info("test_user_id")
            
            assert info["plan_type"] == "pro"
            assert info["storage_quota_bytes"] == STORAGE_QUOTA_PRO
            assert info["storage_used_bytes"] == 2684354560


# ============================================================================
# Integration Tests: check_storage_quota
# ============================================================================

class TestCheckStorageQuota:
    """Tests for storage quota check."""
    
    @pytest.mark.asyncio
    async def test_upload_allowed_under_quota(self):
        """Upload allowed when under quota."""
        mock_profile = {
            "billing_plan": "free",
            "subscription_status": None,
            "credit_units_purchased": 0,
        }
        
        with patch("services.storage_service.get_supabase") as mock_supabase:
            mock_client = MagicMock()
            mock_supabase.return_value = mock_client
            
            mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = Mock(data=mock_profile)
            mock_client.rpc.return_value.execute.return_value = Mock(data=52428800)  # 50 MB used
            
            allowed, info = await check_storage_quota("test_user_id", 10485760)  # 10 MB file
            
            assert allowed is True
            assert info["storage_remaining_bytes"] > 10485760
    
    @pytest.mark.asyncio
    async def test_upload_blocked_over_quota(self):
        """Upload blocked when would exceed quota."""
        mock_profile = {
            "billing_plan": "free",
            "subscription_status": None,
            "credit_units_purchased": 0,
        }
        
        with patch("services.storage_service.get_supabase") as mock_supabase:
            mock_client = MagicMock()
            mock_supabase.return_value = mock_client
            
            mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = Mock(data=mock_profile)
            mock_client.rpc.return_value.execute.return_value = Mock(data=260000000)  # ~248 MB used
            
            allowed, info = await check_storage_quota("test_user_id", 10485760)  # 10 MB file
            
            assert allowed is False


# ============================================================================
# Integration Tests: validate_storage_quota_or_raise
# ============================================================================

class TestValidateStorageQuotaOrRaise:
    """Tests for storage quota validation with HTTP exception."""
    
    @pytest.mark.asyncio
    async def test_raises_402_when_quota_exceeded(self):
        """Raises HTTP 402 when quota would be exceeded."""
        mock_profile = {
            "billing_plan": "free",
            "subscription_status": None,
            "credit_units_purchased": 0,
        }
        
        with patch("services.storage_service.get_supabase") as mock_supabase:
            mock_client = MagicMock()
            mock_supabase.return_value = mock_client
            
            mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = Mock(data=mock_profile)
            mock_client.rpc.return_value.execute.return_value = Mock(data=260000000)  # ~248 MB used
            
            with pytest.raises(HTTPException) as exc_info:
                await validate_storage_quota_or_raise("test_user_id", 10485760)  # 10 MB file
            
            assert exc_info.value.status_code == 402
            assert exc_info.value.detail["error"] == "storage_quota_exceeded"
            assert "upgrade" in exc_info.value.detail["message"].lower() or "purchase" in exc_info.value.detail["message"].lower()
    
    @pytest.mark.asyncio
    async def test_returns_info_when_allowed(self):
        """Returns quota info when upload is allowed."""
        mock_profile = {
            "billing_plan": "pro",
            "subscription_status": "active",
            "credit_units_purchased": 0,
        }
        
        with patch("services.storage_service.get_supabase") as mock_supabase:
            mock_client = MagicMock()
            mock_supabase.return_value = mock_client
            
            mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = Mock(data=mock_profile)
            mock_client.rpc.return_value.execute.return_value = Mock(data=1073741824)  # 1 GB used
            
            info = await validate_storage_quota_or_raise("test_user_id", 10485760)  # 10 MB file
            
            assert info["plan_type"] == "pro"
            assert info["storage_quota_bytes"] == STORAGE_QUOTA_PRO
    
    @pytest.mark.asyncio
    async def test_error_message_for_free_user(self):
        """Free user gets message about purchasing credits or upgrading."""
        mock_profile = {
            "billing_plan": "free",
            "subscription_status": None,
            "credit_units_purchased": 0,
        }
        
        with patch("services.storage_service.get_supabase") as mock_supabase:
            mock_client = MagicMock()
            mock_supabase.return_value = mock_client
            
            mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = Mock(data=mock_profile)
            mock_client.rpc.return_value.execute.return_value = Mock(data=STORAGE_QUOTA_FREE)  # Full
            
            with pytest.raises(HTTPException) as exc_info:
                await validate_storage_quota_or_raise("test_user_id", 1024)
            
            message = exc_info.value.detail["message"]
            assert "Purchase credits" in message or "purchase credits" in message
            assert "Pro" in message
    
    @pytest.mark.asyncio
    async def test_error_message_for_payg_user(self):
        """Pay-as-you-go user gets message about upgrading to Pro."""
        mock_profile = {
            "billing_plan": "free",
            "subscription_status": None,
            "credit_units_purchased": 20,
        }
        
        with patch("services.storage_service.get_supabase") as mock_supabase:
            mock_client = MagicMock()
            mock_supabase.return_value = mock_client
            
            mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = Mock(data=mock_profile)
            mock_client.rpc.return_value.execute.return_value = Mock(data=STORAGE_QUOTA_PAYG)  # Full
            
            with pytest.raises(HTTPException) as exc_info:
                await validate_storage_quota_or_raise("test_user_id", 1024)
            
            message = exc_info.value.detail["message"]
            assert "Pro" in message
    
    @pytest.mark.asyncio
    async def test_error_message_for_pro_user(self):
        """Pro user gets message about deleting files."""
        mock_profile = {
            "billing_plan": "pro",
            "subscription_status": "active",
            "credit_units_purchased": 0,
        }
        
        with patch("services.storage_service.get_supabase") as mock_supabase:
            mock_client = MagicMock()
            mock_supabase.return_value = mock_client
            
            mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = Mock(data=mock_profile)
            mock_client.rpc.return_value.execute.return_value = Mock(data=STORAGE_QUOTA_PRO)  # Full
            
            with pytest.raises(HTTPException) as exc_info:
                await validate_storage_quota_or_raise("test_user_id", 1024)
            
            message = exc_info.value.detail["message"]
            assert "delete" in message.lower()


# ============================================================================
# Constant Verification Tests
# ============================================================================

class TestStorageQuotaConstants:
    """Verify storage quota constants are correct."""
    
    def test_free_quota_is_250mb(self):
        """Free quota is exactly 250 MB."""
        assert STORAGE_QUOTA_FREE == 250 * 1024 * 1024
    
    def test_payg_quota_is_2gb(self):
        """Pay-as-you-go quota is exactly 2 GB."""
        assert STORAGE_QUOTA_PAYG == 2 * 1024 * 1024 * 1024
    
    def test_pro_quota_is_5gb(self):
        """Pro quota is exactly 5 GB."""
        assert STORAGE_QUOTA_PRO == 5 * 1024 * 1024 * 1024
