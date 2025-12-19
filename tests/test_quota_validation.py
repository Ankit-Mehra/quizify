"""
Unit tests for credit reservation/refund logic.
Tests the reserve_credits_atomic, refund_credits_on_failure, and finalize_credits_after_success functions.

Updated to use the atomic credit reservation pattern that prevents TOCTOU race conditions.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import HTTPException
from handlers.quiz_handlers import reserve_credits_atomic, refund_credits_on_failure, finalize_credits_after_success
from services.db_services.supabase_quiz import get_user_tier_info
from schemas.billing import UserBillingState


class TestGetUserTierInfo:
    """Tests for get_user_tier_info function."""
    
    @patch('services.db_services.supabase_quiz.app_config.get_service_role_client')
    def test_get_user_tier_info_success(self, mock_get_service_role_client):
        """Test successful retrieval of user tier info."""
        # Mock the Supabase service role client
        mock_supabase = MagicMock()
        mock_get_service_role_client.return_value = mock_supabase
        
        # Mock the response
        mock_response = MagicMock()
        mock_response.data = [{
            'id': 'test-user-id',
            'email': 'test@example.com',
            'account_tier': 'free',
            'current_quiz_count': 3,
            'quota_limit': 5,
            'quizzes_attempted': 3,
            'quota_exceeded': False,
            'credit_units_monthly': 6,
            'credit_units_remaining': 4,
            'credit_units_purchased': 0
        }]
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response
        
        # Call the function
        result = get_user_tier_info('test-user-id')
        
        # Assertions
        assert result['account_tier'] == 'free'
        assert result['credit_units_remaining'] == 4
        
    @patch('services.db_services.supabase_quiz.app_config.get_service_role_client')
    def test_get_user_tier_info_user_not_found(self, mock_get_service_role_client):
        """Test error handling when user is not found."""
        # Mock the Supabase service role client
        mock_supabase = MagicMock()
        mock_get_service_role_client.return_value = mock_supabase
        
        # Mock empty response
        mock_response = MagicMock()
        mock_response.data = []
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response
        
        # Call the function and expect exception
        with pytest.raises(HTTPException) as exc_info:
            get_user_tier_info('non-existent-user')
        
        assert exc_info.value.status_code == 404
        assert "User not found" in str(exc_info.value.detail)


class TestReserveCreditsAtomic:
    """Tests for reserve_credits_atomic function (atomic consume before generation)."""
    pytestmark = pytest.mark.asyncio
    
    @patch('handlers.quiz_handlers.consume_units', new_callable=AsyncMock)
    async def test_reserve_credits_success(self, mock_consume):
        """Test credit reservation succeeds when user has sufficient credits."""
        mock_consume.return_value = True
        
        # Should not raise exception
        await reserve_credits_atomic('test-user-id', quiz_type='enhanced')
        
        # Verify consume_units was called atomically
        mock_consume.assert_called_once_with('test-user-id', 'enhanced')
    
    @patch('handlers.quiz_handlers.get_billing_state', new_callable=AsyncMock)
    @patch('handlers.quiz_handlers.consume_units', new_callable=AsyncMock)
    async def test_reserve_credits_insufficient_free_user(self, mock_consume, mock_get_state):
        """Test credit reservation fails with 402 for free user with insufficient credits."""
        mock_consume.return_value = False  # Atomic consume failed
        mock_get_state.return_value = UserBillingState(
            user_id='test-user-id',
            plan='free',
            credit_units_monthly=6,
            credit_units_remaining=0,
            credit_units_purchased=0,
            free_credit_units_monthly=6,
            free_credit_units_remaining=0
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await reserve_credits_atomic('test-user-id', quiz_type='enhanced')
        
        assert exc_info.value.status_code == 402
        detail = exc_info.value.detail
        assert detail['error'] == 'insufficient_credits'
        assert 'Upgrade' in detail['message']  # Free users should see upgrade prompt
    
    @patch('handlers.quiz_handlers.get_billing_state', new_callable=AsyncMock)
    @patch('handlers.quiz_handlers.consume_units', new_callable=AsyncMock)
    async def test_reserve_credits_insufficient_pro_user(self, mock_consume, mock_get_state):
        """Test credit reservation fails with 402 for pro user with insufficient credits."""
        mock_consume.return_value = False  # Atomic consume failed
        mock_get_state.return_value = UserBillingState(
            user_id='test-user-id',
            plan='pro',
            credit_units_monthly=80,
            credit_units_remaining=0,
            credit_units_purchased=0,
            free_credit_units_monthly=6,
            free_credit_units_remaining=0
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await reserve_credits_atomic('test-user-id', quiz_type='standard')
        
        assert exc_info.value.status_code == 402
        detail = exc_info.value.detail
        assert detail['error'] == 'insufficient_credits'
        assert 'Purchase' in detail['message']  # Pro users should see purchase prompt


class TestRefundCreditsOnFailure:
    """Tests for refund_credits_on_failure function (refund after failed generation)."""
    pytestmark = pytest.mark.asyncio
    
    @patch('handlers.quiz_handlers.invalidate_user_tier_cache', new_callable=AsyncMock)
    @patch('handlers.quiz_handlers.refund_units', new_callable=AsyncMock)
    async def test_refund_credits_success(self, mock_refund, mock_invalidate):
        """Test credit refund succeeds after failed generation."""
        mock_refund.return_value = True
        mock_invalidate.return_value = None
        
        # Should not raise
        await refund_credits_on_failure('test-user-id', quiz_type='enhanced')
        
        mock_refund.assert_called_once_with('test-user-id', 'enhanced')
        mock_invalidate.assert_called_once_with('test-user-id')
    
    @patch('handlers.quiz_handlers.invalidate_user_tier_cache', new_callable=AsyncMock)
    @patch('handlers.quiz_handlers.refund_units', new_callable=AsyncMock)
    async def test_refund_credits_handles_failure_gracefully(self, mock_refund, mock_invalidate):
        """Test credit refund failure is logged but doesn't raise."""
        mock_refund.return_value = False  # Refund failed
        mock_invalidate.return_value = None
        
        # Should not raise even if refund fails (best-effort)
        await refund_credits_on_failure('test-user-id', quiz_type='standard')
        
        mock_refund.assert_called_once_with('test-user-id', 'standard')
        # Cache should still be invalidated
        mock_invalidate.assert_called_once_with('test-user-id')


class TestFinalizeCreditsAfterSuccess:
    """Tests for finalize_credits_after_success function."""
    pytestmark = pytest.mark.asyncio
    
    @patch('handlers.quiz_handlers.invalidate_user_tier_cache', new_callable=AsyncMock)
    async def test_finalize_credits_invalidates_cache(self, mock_invalidate):
        """Test finalize_credits_after_success invalidates the cache."""
        mock_invalidate.return_value = None
        
        # Should not raise
        await finalize_credits_after_success('test-user-id', quiz_type='enhanced')
        
        mock_invalidate.assert_called_once_with('test-user-id')
