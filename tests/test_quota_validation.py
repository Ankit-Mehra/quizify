"""
Unit tests for quota validation logic.
Tests the validate_user_quota function and get_user_tier_info function.
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from handlers.quiz_handlers import validate_user_quota
from services.db_services.supabase_quiz import get_user_tier_info


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
            'quota_exceeded': False
        }]
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response
        
        # Call the function
        result = get_user_tier_info('test-user-id')
        
        # Assertions
        assert result['account_tier'] == 'free'
        assert result['current_quiz_count'] == 3
        assert result['quota_limit'] == 5
        assert result['quota_exceeded'] is False
        
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


class TestValidateUserQuota:
    """Tests for validate_user_quota function."""
    
    @patch('handlers.quiz_handlers.get_user_tier_info')
    def test_validate_quota_free_tier_under_limit(self, mock_get_tier_info):
        """Test quota validation for free tier user under limit."""
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'email': 'test@example.com',
            'account_tier': 'free',
            'current_quiz_count': 3,
            'quota_limit': 5,
            'quota_exceeded': False
        }
        
        # Should not raise exception
        validate_user_quota('test-user-id')
        
    @patch('handlers.quiz_handlers.get_user_tier_info')
    def test_validate_quota_free_tier_at_limit(self, mock_get_tier_info):
        """Test quota validation for free tier user at limit."""
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'email': 'test@example.com',
            'account_tier': 'free',
            'current_quiz_count': 5,
            'quota_limit': 5,
            'quota_exceeded': True
        }
        
        # Should raise 403 exception
        with pytest.raises(HTTPException) as exc_info:
            validate_user_quota('test-user-id')
        
        assert exc_info.value.status_code == 403
        detail = exc_info.value.detail
        assert detail['current_count'] == 5
        assert detail['quota_limit'] == 5
        assert detail['user_tier'] == 'free'
        assert 'Upgrade to basic for 100 quizzes' in detail['detail']
        
    @patch('handlers.quiz_handlers.get_user_tier_info')
    def test_validate_quota_basic_tier_under_limit(self, mock_get_tier_info):
        """Test quota validation for basic tier user under limit."""
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'email': 'test@example.com',
            'account_tier': 'basic',
            'current_quiz_count': 50,
            'quota_limit': 100,
            'quota_exceeded': False
        }
        
        # Should not raise exception
        validate_user_quota('test-user-id')
        
    @patch('handlers.quiz_handlers.get_user_tier_info')
    def test_validate_quota_basic_tier_at_limit(self, mock_get_tier_info):
        """Test quota validation for basic tier user at limit."""
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'email': 'test@example.com',
            'account_tier': 'basic',
            'current_quiz_count': 100,
            'quota_limit': 100,
            'quota_exceeded': True
        }
        
        # Should raise 403 exception
        with pytest.raises(HTTPException) as exc_info:
            validate_user_quota('test-user-id')
        
        assert exc_info.value.status_code == 403
        detail = exc_info.value.detail
        assert detail['current_count'] == 100
        assert detail['quota_limit'] == 100
        assert detail['user_tier'] == 'basic'
        assert 'Upgrade to educator for 500 quizzes' in detail['detail']
        
    @patch('handlers.quiz_handlers.get_user_tier_info')
    def test_validate_quota_educator_tier_under_limit(self, mock_get_tier_info):
        """Test quota validation for educator tier user under limit."""
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'email': 'test@example.com',
            'account_tier': 'educator',
            'current_quiz_count': 450,
            'quota_limit': 500,
            'quota_exceeded': False
        }
        
        # Should not raise exception
        validate_user_quota('test-user-id')
        
    @patch('handlers.quiz_handlers.get_user_tier_info')
    def test_validate_quota_educator_tier_at_limit(self, mock_get_tier_info):
        """Test quota validation for educator tier user at limit."""
        mock_get_tier_info.return_value = {
            'id': 'test-user-id',
            'email': 'test@example.com',
            'account_tier': 'educator',
            'current_quiz_count': 500,
            'quota_limit': 500,
            'quota_exceeded': True
        }
        
        # Should raise 403 exception
        with pytest.raises(HTTPException) as exc_info:
            validate_user_quota('test-user-id')
        
        assert exc_info.value.status_code == 403
        detail = exc_info.value.detail
        assert detail['current_count'] == 500
        assert detail['quota_limit'] == 500
        assert detail['user_tier'] == 'educator'
