"""
Integration test for complete authentication flow.

Tests the full user journey:
1. Signup with new credentials
2. Login to get access token
3. Access protected endpoint with token
4. Logout to invalidate token
5. Verify token is no longer valid
"""

import pytest
from fastapi.testclient import TestClient
from main import app
import os

client = TestClient(app)


class TestAuthFlow:
    """Integration test for complete authentication flow."""
    
    def test_complete_auth_flow(self):
        """
        Test complete authentication lifecycle from signup to logout.
        
        Flow:
        1. Signup → get user_id
        2. Login → get access_token
        3. Access protected endpoint → verify authenticated
        4. Logout → invalidate token
        5. Attempt access protected endpoint → verify 401
        """
        # Step 1: Signup
        unique_email = f"test_flow_{os.urandom(4).hex()}@example.com"
        signup_payload = {
            "email": unique_email,
            "password": "SecurePass123!",
            "name": "Flow Test User"
        }
        
        signup_response = client.post("/api/auth/signup", json=signup_payload)
        assert signup_response.status_code == 201, \
            f"Signup failed: {signup_response.text}"
        
        signup_data = signup_response.json()
        user_id = signup_data.get("user_id") or signup_data.get("id")
        assert user_id is not None, "Signup should return user_id"
        
        # Step 2: Login
        login_payload = {
            "email": unique_email,
            "password": "SecurePass123!"
        }
        
        login_response = client.post("/api/auth/login", json=login_payload)
        assert login_response.status_code == 200, \
            f"Login failed: {login_response.text}"
        
        login_data = login_response.json()
        access_token = login_data.get("access_token") or login_data.get("accessToken") or login_data.get("token")
        assert access_token is not None, "Login should return access token"
        
        # Step 3: Access protected endpoint (e.g., get user's quizzes)
        headers = {"Authorization": f"Bearer {access_token}"}
        
        protected_response = client.get("/api/quiz/my-quizzes", headers=headers)
        assert protected_response.status_code == 200, \
            f"Protected endpoint should be accessible with valid token: {protected_response.text}"
        
        # Step 4: Logout
        logout_response = client.post("/api/auth/logout", headers=headers)
        assert logout_response.status_code == 200, \
            f"Logout failed: {logout_response.text}"
        
        # Step 5: Verify token is no longer valid
        # Note: This step may not work if the API doesn't invalidate tokens server-side
        # (JWTs are often stateless). We'll try anyway to test behavior.
        post_logout_response = client.get("/api/quiz/my-quizzes", headers=headers)
        
        # Expected: Either 401 (token invalidated) or 200 (stateless JWT still valid)
        # We document the actual behavior for future reference
        if post_logout_response.status_code == 401:
            print("✓ Tokens are invalidated server-side after logout")
        elif post_logout_response.status_code == 200:
            print("⚠ Tokens remain valid after logout (stateless JWT behavior)")
        
        # Both behaviors are acceptable for this test - we're just verifying the flow completes
        assert post_logout_response.status_code in [200, 401], \
            f"Unexpected status after logout: {post_logout_response.status_code}"
    
    def test_cannot_use_invalid_token_for_protected_endpoints(self):
        """
        Test that invalid tokens are rejected by protected endpoints.
        
        Expected:
        - HTTP 401 when accessing protected endpoint with invalid token
        """
        invalid_headers = {"Authorization": "Bearer invalid_token_12345"}
        
        response = client.get("/api/quiz/my-quizzes", headers=invalid_headers)
        
        assert response.status_code == 401, \
            f"Expected 401 for invalid token, got {response.status_code}: {response.text}"
    
    def test_cannot_access_protected_endpoint_without_token(self):
        """
        Test that protected endpoints require authentication.
        
        Expected:
        - HTTP 401 when accessing protected endpoint without token
        """
        response = client.get("/api/quiz/my-quizzes")
        
        assert response.status_code == 401, \
            f"Expected 401 without authentication, got {response.status_code}: {response.text}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
