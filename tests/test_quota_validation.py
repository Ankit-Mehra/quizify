"""
Unit tests for credit validation logic.
Tests the validate_and_consume_credits function and get_user_tier_info function.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import HTTPException
from handlers.quiz_handlers import validate_and_consume_credits
from services.db_services.supabase_quiz import get_user_tier_info
from schemas.billing import UserBillingState


class TestGetUserTierInfo:
    """Tests for get_user_tier_info function."""
    
    @patch('services.db_services.supabase_quiz.get_supabase')
    def test_get_user_tier_info_success(self, mock_get_supabase):
        """Test successful retrieval of user tier info."""
        # Mock the Supabase client
        mock_supabase = MagicMock()
        mock_get_supabase.return_value = mock_supabase
        
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
        
    @patch('services.db_services.supabase_quiz.get_supabase')
    def test_get_user_tier_info_user_not_found(self, mock_get_supabase):
        """Test error handling when user is not found."""
        # Mock the Supabase client
        mock_supabase = MagicMock()
        mock_get_supabase.return_value = mock_supabase
        
        # Mock empty response
        mock_response = MagicMock()
        mock_response.data = []
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response
        
        # Call the function and expect exception
        with pytest.raises(HTTPException) as exc_info:
            get_user_tier_info('non-existent-user')
        
        assert exc_info.value.status_code == 404
        assert "User not found" in str(exc_info.value.detail)


class TestValidateAndConsumeCredits:
    """Tests for validate_and_consume_credits function."""
    pytestmark = pytest.mark.asyncio
    
    @patch('handlers.quiz_handlers.get_billing_state', new_callable=AsyncMock)
    @patch('handlers.quiz_handlers.consume_units', new_callable=AsyncMock)
    async def test_validate_credits_sufficient(self, mock_consume, mock_get_state):
        """Test credit validation when user has sufficient credits."""
        # Mock billing state with sufficient credits
        mock_get_state.return_value = UserBillingState(
            user_id='test-user-id',
            plan='free',
            credit_units_monthly=6,
            credit_units_remaining=4,
            credit_units_purchased=0
        )
        
        mock_consume.return_value = True

        # Should not raise exception
        await validate_and_consume_credits('test-user-id', quiz_type='enhanced')
        
        # Verify consume was called
        mock_consume.assert_called_once_with('test-user-id', 'enhanced')
        # On success, get_billing_state should NOT be called (no need to fetch state)
        mock_get_state.assert_not_called()
        
    @patch('handlers.quiz_handlers.get_billing_state', new_callable=AsyncMock)
    @patch('handlers.quiz_handlers.consume_units', new_callable=AsyncMock)
    async def test_validate_credits_insufficient(self, mock_consume, mock_get_state):
        """Test credit validation when user has insufficient credits."""
        # Mock billing state with insufficient credits
        mock_get_state.return_value = UserBillingState(
            user_id='test-user-id',
            plan='free',
            credit_units_monthly=6,
            credit_units_remaining=1, # Only 1 left
            credit_units_purchased=0
        )
        
        mock_consume.return_value = False
        
        # Should raise 402 exception (Payment Required)
        with pytest.raises(HTTPException) as exc_info:
            await validate_and_consume_credits('test-user-id', quiz_type='enhanced')
        
        assert exc_info.value.status_code == 402
        detail = exc_info.value.detail
        assert detail['error'] == 'insufficient_credits'
        assert detail['required_credits'] == 1.0
        
        # Verify consume was called (it returns False inside validate_and_consume_credits)
        mock_consume.assert_called_once_with('test-user-id', 'enhanced')
        # On failure, get_billing_state should be called to build error response
        mock_get_state.assert_called_once_with('test-user-id')
        
    @patch('handlers.quiz_handlers.get_billing_state', new_callable=AsyncMock)
    @patch('handlers.quiz_handlers.consume_units', new_callable=AsyncMock)
    async def test_validate_credits_consume_failure(self, mock_consume, mock_get_state):
        """Test credit validation when consume fails (race condition or insufficient)."""
        # Mock billing state with sufficient credits initially
        mock_get_state.return_value = UserBillingState(
            user_id='test-user-id',
            plan='free',
            credit_units_monthly=6,
            credit_units_remaining=4,
            credit_units_purchased=0
        )
        
        # But consume returns False
        mock_consume.return_value = False

        # Should raise 402 exception
        with pytest.raises(HTTPException) as exc_info:
            await validate_and_consume_credits('test-user-id', quiz_type='enhanced')
        
        assert exc_info.value.status_code == 402
        assert exc_info.value.detail['error'] == 'insufficient_credits'
