"""
Contract tests for POST /api/auth/logout endpoint.

Tests the authentication logout functionality including:
- Successful logout with valid token
- Logout without authentication
- Refresh token lookup fallback for session cleanup
- Security: Session ownership verification
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from main import app
from dependencies.auth_dependencies import get_current_user_id
from services.redis.sessions import SessionInfo

client = TestClient(app)


@pytest.mark.contract
class TestAuthLogout:
    """Contract tests for user logout endpoint."""
    
    def test_successful_logout_returns_200(self, mock_supabase_client, auth_headers):
        """
        Test that logout with valid token returns HTTP 200.
        
        Expected:
        - Status code: 200
        - Success message
        """
        # Override auth dependency
        def override_get_current_user_id():
            return "mock_user_123"
        
        app.dependency_overrides[get_current_user_id] = override_get_current_user_id
        
        try:
            response = client.post("/api/auth/logout", headers=auth_headers)
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
            
            data = response.json()
            assert "message" in data, f"Response missing message: {data}"
            assert data["message"] == "Successfully logged out", f"Unexpected message: {data['message']}"
        finally:
            app.dependency_overrides.clear()
    
    def test_logout_without_auth_returns_401(self, mock_supabase_client):
        """
        Test that logout without authentication returns HTTP 401.
        
        Expected:
        - Status code: 401
        - Error message about missing authentication
        """
        # No headers provided - should fail auth
        response = client.post("/api/auth/logout")
        
        assert response.status_code == 401, \
            f"Expected 401 without auth, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "message" in data, f"Error response missing detail/message: {data}"
    
    def test_logout_with_invalid_token_returns_401(self, mock_supabase_client):
        """
        Test that logout with invalid token returns HTTP 401.
        
        Expected:
        - Status code: 401
        - Error message about invalid token
        """
        headers = {"Authorization": "Bearer invalid_token_123"}
        
        response = client.post("/api/auth/logout", headers=headers)
        
        assert response.status_code == 401, \
            f"Expected 401 with invalid token, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data or "message" in data, f"Error response missing detail/message: {data}"


@pytest.mark.contract
class TestAuthLogoutRefreshTokenFallback:
    """Tests for refresh_token lookup fallback in logout (Priority 3)."""
    
    def test_logout_via_refresh_token_when_no_session_id(self, mock_supabase_client, auth_headers):
        """
        Test that logout successfully finds and deletes session via refresh_token 
        when no session_id is provided.
        
        This tests the Priority 3 fallback mechanism.
        """
        def override_get_current_user_id():
            return "mock_user_123"
        
        app.dependency_overrides[get_current_user_id] = override_get_current_user_id
        
        try:
            # Mock the Redis client and session service
            with patch('handlers.auth_handlers.get_redis_client') as mock_get_redis:
                mock_redis = MagicMock()
                mock_get_redis.return_value = mock_redis
                
                with patch('handlers.auth_handlers.SessionService') as MockSessionService:
                    mock_service = AsyncMock()
                    MockSessionService.return_value = mock_service
                    
                    # Simulate finding session via refresh_token
                    mock_service.find_session_by_refresh_token.return_value = "sess_found_123"
                    mock_service.validate_session.return_value = SessionInfo(
                        session_id="sess_found_123",
                        user_id="mock_user_123",  # Matches the authenticated user
                        device_type="browser",
                        ip_address="hashed_ip",
                        user_agent="Test Browser",
                        created_at="2025-01-01T00:00:00Z",
                        last_active="2025-01-01T00:00:00Z"
                    )
                    mock_service.logout.return_value = True
                    
                    # Mock is_development to return True so X-Refresh-Token header is used
                    with patch('handlers.auth_handlers.app_config.is_development', return_value=True):
                        # Include refresh_token header (dev mode)
                        headers = {**auth_headers, "X-Refresh-Token": "test_refresh_token"}
                        
                        response = client.post("/api/auth/logout", headers=headers)
                        
                        assert response.status_code == 200
                        data = response.json()
                        assert data["message"] == "Successfully logged out"
                        
                        # Verify the fallback was used
                        mock_service.find_session_by_refresh_token.assert_called_once_with("test_refresh_token")
                        mock_service.logout.assert_called_once_with("sess_found_123")
        finally:
            app.dependency_overrides.clear()
    
    def test_logout_rejects_session_belonging_to_different_user(self, mock_supabase_client, auth_headers):
        """
        Security test: Logout should NOT delete a session that belongs to a different user,
        even if the refresh_token is valid.
        """
        def override_get_current_user_id():
            return "mock_user_123"
        
        app.dependency_overrides[get_current_user_id] = override_get_current_user_id
        
        try:
            with patch('handlers.auth_handlers.get_redis_client') as mock_get_redis:
                mock_redis = MagicMock()
                mock_get_redis.return_value = mock_redis
                
                with patch('handlers.auth_handlers.SessionService') as MockSessionService:
                    mock_service = AsyncMock()
                    MockSessionService.return_value = mock_service
                    
                    # Simulate finding session that belongs to a DIFFERENT user
                    mock_service.find_session_by_refresh_token.return_value = "sess_other_456"
                    mock_service.validate_session.return_value = SessionInfo(
                        session_id="sess_other_456",
                        user_id="different_user_789",  # Different user!
                        device_type="browser",
                        ip_address="hashed_ip",
                        user_agent="Test Browser",
                        created_at="2025-01-01T00:00:00Z",
                        last_active="2025-01-01T00:00:00Z"
                    )
                    
                    # Mock is_development to return True so X-Refresh-Token header is used
                    with patch('handlers.auth_handlers.app_config.is_development', return_value=True):
                        headers = {**auth_headers, "X-Refresh-Token": "stolen_refresh_token"}
                        
                        response = client.post("/api/auth/logout", headers=headers)
                        
                        # Should still return 200 (logout clears cookies regardless)
                        assert response.status_code == 200
                        
                        # But should NOT have called logout on the session
                        mock_service.logout.assert_not_called()
        finally:
            app.dependency_overrides.clear()
    
    def test_logout_handles_expired_session_gracefully(self, mock_supabase_client, auth_headers):
        """
        Test that logout handles expired/non-existent sessions gracefully
        during refresh_token lookup.
        """
        def override_get_current_user_id():
            return "mock_user_123"
        
        app.dependency_overrides[get_current_user_id] = override_get_current_user_id
        
        try:
            with patch('handlers.auth_handlers.get_redis_client') as mock_get_redis:
                mock_redis = MagicMock()
                mock_get_redis.return_value = mock_redis
                
                with patch('handlers.auth_handlers.SessionService') as MockSessionService:
                    mock_service = AsyncMock()
                    MockSessionService.return_value = mock_service
                    
                    # Simulate finding a session ID, but session has expired
                    mock_service.find_session_by_refresh_token.return_value = "sess_expired_123"
                    mock_service.validate_session.return_value = None  # Session expired
                    
                    # Mock is_development to return True so X-Refresh-Token header is used
                    with patch('handlers.auth_handlers.app_config.is_development', return_value=True):
                        headers = {**auth_headers, "X-Refresh-Token": "expired_refresh_token"}
                        
                        response = client.post("/api/auth/logout", headers=headers)
                        
                        # Should still return 200 (cookies cleared)
                        assert response.status_code == 200
                        
                        # Should NOT call logout since session is expired
                        mock_service.logout.assert_not_called()
        finally:
            app.dependency_overrides.clear()
    
    def test_dev_mode_checks_header_before_cookie(self, mock_supabase_client, auth_headers):
        """
        Test that in development mode, X-Refresh-Token header is checked
        before the cookie.
        """
        def override_get_current_user_id():
            return "mock_user_123"
        
        app.dependency_overrides[get_current_user_id] = override_get_current_user_id
        
        try:
            with patch('handlers.auth_handlers.get_redis_client') as mock_get_redis:
                mock_redis = MagicMock()
                mock_get_redis.return_value = mock_redis
                
                with patch('handlers.auth_handlers.SessionService') as MockSessionService:
                    mock_service = AsyncMock()
                    MockSessionService.return_value = mock_service
                    
                    with patch('handlers.auth_handlers.app_config') as mock_config:
                        mock_config.is_development.return_value = True
                        
                        mock_service.find_session_by_refresh_token.return_value = "sess_123"
                        mock_service.validate_session.return_value = SessionInfo(
                            session_id="sess_123",
                            user_id="mock_user_123",
                            device_type="browser",
                            ip_address="hashed_ip",
                            user_agent="Test Browser",
                            created_at="2025-01-01T00:00:00Z",
                            last_active="2025-01-01T00:00:00Z"
                        )
                        mock_service.logout.return_value = True
                        
                        # Send token via header (dev mode preference)
                        headers = {**auth_headers, "X-Refresh-Token": "header_token"}
                        
                        response = client.post("/api/auth/logout", headers=headers)
                        
                        assert response.status_code == 200
                        # Verify header token was used
                        mock_service.find_session_by_refresh_token.assert_called_once_with("header_token")
        finally:
            app.dependency_overrides.clear()
    
    def test_logout_handles_lookup_errors_gracefully(self, mock_supabase_client, auth_headers):
        """
        Test that logout continues gracefully if refresh_token lookup fails.
        """
        def override_get_current_user_id():
            return "mock_user_123"
        
        app.dependency_overrides[get_current_user_id] = override_get_current_user_id
        
        try:
            with patch('handlers.auth_handlers.get_redis_client') as mock_get_redis:
                mock_redis = MagicMock()
                mock_get_redis.return_value = mock_redis
                
                with patch('handlers.auth_handlers.SessionService') as MockSessionService:
                    mock_service = AsyncMock()
                    MockSessionService.return_value = mock_service
                    
                    # Simulate Redis error during lookup
                    mock_service.find_session_by_refresh_token.side_effect = Exception("Redis connection failed")
                    
                    headers = {**auth_headers, "X-Refresh-Token": "test_token"}
                    
                    response = client.post("/api/auth/logout", headers=headers)
                    
                    # Should still return 200 (cookies cleared, error logged)
                    assert response.status_code == 200
                    data = response.json()
                    assert data["message"] == "Successfully logged out"
        finally:
            app.dependency_overrides.clear()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
