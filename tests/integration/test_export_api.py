"""
Integration tests for Export API - Tier-based access control.

Tests the export API endpoint tier gating at the HTTP layer:
- Premium tier cannot access Pro-only formats (Google Forms, QTI, Moodle XML)
- Pro tier can access all formats
- Free tier cannot access any export formats
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from uuid import uuid4
import os

from main import app

client = TestClient(app)

# Unique test users per test run
TEST_EMAIL_FREE = f"test_export_free_{os.urandom(4).hex()}@example.com"
TEST_EMAIL_PREMIUM = f"test_export_premium_{os.urandom(4).hex()}@example.com"
TEST_EMAIL_PRO = f"test_export_pro_{os.urandom(4).hex()}@example.com"
TEST_PASSWORD = "SecurePass123!"


@pytest.fixture(scope="module")
def free_tier_auth():
    """Create a free tier test user and return auth token."""
    signup_payload = {
        "email": TEST_EMAIL_FREE,
        "password": TEST_PASSWORD,
        "name": "Free Tier Test User"
    }
    signup_response = client.post("/api/auth/signup", json=signup_payload)
    assert signup_response.status_code == 201
    
    login_payload = {
        "email": TEST_EMAIL_FREE,
        "password": TEST_PASSWORD
    }
    login_response = client.post("/api/auth/login", json=login_payload)
    assert login_response.status_code == 200
    
    data = login_response.json()
    token = data.get("access_token") or data.get("accessToken") or data.get("token")
    return token


@pytest.fixture(scope="module")
def premium_tier_auth():
    """Create a premium tier test user and return auth token."""
    signup_payload = {
        "email": TEST_EMAIL_PREMIUM,
        "password": TEST_PASSWORD,
        "name": "Premium Tier Test User"
    }
    signup_response = client.post("/api/auth/signup", json=signup_payload)
    assert signup_response.status_code == 201
    
    login_payload = {
        "email": TEST_EMAIL_PREMIUM,
        "password": TEST_PASSWORD
    }
    login_response = client.post("/api/auth/login", json=login_payload)
    assert login_response.status_code == 200
    
    data = login_response.json()
    token = data.get("access_token") or data.get("accessToken") or data.get("token")
    return token


@pytest.fixture(scope="module")
def pro_tier_auth():
    """Create a pro tier test user and return auth token."""
    signup_payload = {
        "email": TEST_EMAIL_PRO,
        "password": TEST_PASSWORD,
        "name": "Pro Tier Test User"
    }
    signup_response = client.post("/api/auth/signup", json=signup_payload)
    assert signup_response.status_code == 201
    
    login_payload = {
        "email": TEST_EMAIL_PRO,
        "password": TEST_PASSWORD
    }
    login_response = client.post("/api/auth/login", json=login_payload)
    assert login_response.status_code == 200
    
    data = login_response.json()
    token = data.get("access_token") or data.get("accessToken") or data.get("token")
    return token


def mock_tier_info(tier: str):
    """Create a mock function that returns tier info for the specified tier."""
    def _mock(*args, **kwargs):
        return {"account_tier": tier, "current_quiz_count": 0, "quota_limit": 100}
    return _mock


def mock_quiz_for_export():
    """Create mock quiz data for export tests."""
    from schemas.export import QuizExportData, ExportQuestionMCQ
    from datetime import datetime, timezone
    
    quiz_id = uuid4()
    return QuizExportData(
        quiz_id=quiz_id,
        title="Test Export Quiz",
        created_at=datetime.now(timezone.utc),
        questions=[
            ExportQuestionMCQ(
                id=uuid4(),
                type="multiple_choice",
                question="What is 2+2?",
                options=["3", "4", "5", "6"],
                correct_answer="4",
                explanation="Basic arithmetic"
            )
        ]
    )


@pytest.mark.integration
class TestExportTierGating:
    """Integration tests for export API tier-based access control."""

    def test_premium_tier_cannot_export_google_forms(self, premium_tier_auth):
        """
        Premium tier users should NOT be able to export to Google Forms.
        
        This is a critical security test ensuring the Pro-only gating works
        at the API layer, not just in the tier validator helper.
        """
        headers = {"Authorization": f"Bearer {premium_tier_auth}"}
        quiz_id = str(uuid4())
        
        # Mock the tier lookup to return "premium" via the route's get_user_tier_info call
        with patch("api.export_routes.get_user_tier_info", side_effect=mock_tier_info("premium")):
            with patch("services.exporters.quiz_loader.load_quiz_for_export",
                       return_value=mock_quiz_for_export()):
                
                response = client.post(
                    f"/api/quizzes/{quiz_id}/export",
                    headers=headers,
                    json={"format": "google_forms"}
                )
        
        # Should return 403 tier_insufficient
        assert response.status_code == 403
        data = response.json()
        # API wraps error in 'detail' field
        detail = data.get("detail", data)
        assert detail.get("error") == "tier_insufficient"
        assert detail.get("required_tier") == "pro"
        assert detail.get("requested_format") == "google_forms"

    def test_premium_tier_cannot_export_qti(self, premium_tier_auth):
        """Premium tier users should NOT be able to export QTI."""
        headers = {"Authorization": f"Bearer {premium_tier_auth}"}
        quiz_id = str(uuid4())
        
        with patch("api.export_routes.get_user_tier_info", side_effect=mock_tier_info("premium")):
            with patch("services.exporters.quiz_loader.load_quiz_for_export",
                       return_value=mock_quiz_for_export()):
                
                response = client.post(
                    f"/api/quizzes/{quiz_id}/export",
                    headers=headers,
                    json={"format": "qti"}
                )
        
        assert response.status_code == 403
        data = response.json()
        detail = data.get("detail", data)
        assert detail.get("error") == "tier_insufficient"
        assert detail.get("required_tier") == "pro"

    def test_premium_tier_cannot_export_moodle_xml(self, premium_tier_auth):
        """Premium tier users should NOT be able to export Moodle XML."""
        headers = {"Authorization": f"Bearer {premium_tier_auth}"}
        quiz_id = str(uuid4())
        
        with patch("api.export_routes.get_user_tier_info", side_effect=mock_tier_info("premium")):
            with patch("services.exporters.quiz_loader.load_quiz_for_export",
                       return_value=mock_quiz_for_export()):
                
                response = client.post(
                    f"/api/quizzes/{quiz_id}/export",
                    headers=headers,
                    json={"format": "moodle_xml"}
                )
        
        assert response.status_code == 403
        data = response.json()
        detail = data.get("detail", data)
        assert detail.get("error") == "tier_insufficient"
        assert detail.get("required_tier") == "pro"

    def test_pro_tier_can_initiate_google_forms_export(self, pro_tier_auth):
        """
        Pro tier users CAN initiate Google Forms export (passes tier check).
        
        This tests that the tier gating passes for Pro tier. When no Google account
        is connected, the API returns a 401 with an auth_url for OAuth flow.
        
        Note: A fully successful Google Forms export requires:
        1. Pro tier (tested here - passes)
        2. Connected Google account with valid credentials (returns auth_url if not)
        """
        headers = {"Authorization": f"Bearer {pro_tier_auth}"}
        quiz_id = str(uuid4())
        
        with patch("api.export_routes.get_user_tier_info", side_effect=mock_tier_info("pro")):
            # Patch at the import location in the handler
            with patch("handlers.export_handler.load_quiz_for_export",
                       return_value=mock_quiz_for_export()):
                # Mock get_google_credentials to return None (no credentials)
                with patch("services.google_auth_service.get_google_credentials", return_value=None):
                    # Mock Google auth URL generation
                    with patch("services.google_auth_service.is_google_auth_configured", return_value=True):
                        with patch("services.google_auth_service.generate_auth_url", 
                                   return_value=("https://accounts.google.com/o/oauth2/...", "state123")):
                            
                            response = client.post(
                                f"/api/quizzes/{quiz_id}/export",
                                headers=headers,
                                json={"format": "google_forms"}
                            )
        
        # Should get 401 with auth_url when not connected to Google
        # (Pro tier passes tier check, but needs Google OAuth)
        assert response.status_code == 401, \
            f"Expected 401 for OAuth flow, got {response.status_code}: {response.json()}"
        
        # Ensure we didn't get a tier_insufficient error (Pro should pass tier check)
        if response.status_code == 403:
            assert response.json().get("detail", {}).get("error") != "tier_insufficient", \
                "Pro tier should pass tier validation for Google Forms export"
        
        data = response.json()
        assert data.get("error") == "google_connection_required"
        assert "auth_url" in data
        # Validate it's a well-formed Google OAuth URL
        assert data["auth_url"].startswith("https://accounts.google.com/o/oauth2"), \
            f"Expected Google OAuth URL, got: {data['auth_url']}"
        assert data.get("message") == "Please connect your Google account to export to Google Forms"

    def test_free_tier_cannot_export_any_format(self, free_tier_auth):
        """Free tier users should NOT be able to export any format."""
        headers = {"Authorization": f"Bearer {free_tier_auth}"}
        quiz_id = str(uuid4())
        
        # Test PDF (basic format)
        with patch("api.export_routes.get_user_tier_info", side_effect=mock_tier_info("free")):
            with patch("services.exporters.quiz_loader.load_quiz_for_export",
                       return_value=mock_quiz_for_export()):
                
                response = client.post(
                    f"/api/quizzes/{quiz_id}/export",
                    headers=headers,
                    json={"format": "pdf"}
                )
        
        assert response.status_code == 403
        data = response.json()
        detail = data.get("detail", data)
        assert detail.get("error") == "tier_insufficient"
        # Free tier needs at least Premium for any export
        assert detail.get("required_tier") in ["premium", "pro"]


@pytest.mark.integration
class TestExportFormatsEndpoint:
    """Integration tests for GET /api/quizzes/export/formats endpoint."""

    def test_formats_endpoint_shows_google_forms_as_pro_only(self, premium_tier_auth):
        """
        The formats endpoint should correctly indicate Google Forms requires Pro tier.
        """
        headers = {"Authorization": f"Bearer {premium_tier_auth}"}
        
        with patch("api.export_routes.get_user_tier_info", side_effect=mock_tier_info("premium")):
            response = client.get(
                "/api/quizzes/export/formats",
                headers=headers
            )
        
        assert response.status_code == 200
        data = response.json()
        
        # Google Forms should be marked as requires_pro and not available
        google_forms = data.get("google_forms", {})
        assert google_forms.get("requires_pro") is True
        assert google_forms.get("available") is False
        
        # PDF should be available for Premium
        pdf = data.get("pdf", {})
        assert pdf.get("available") is True
        assert pdf.get("requires_pro") is False

    def test_formats_endpoint_for_pro_tier(self, pro_tier_auth):
        """Pro tier should see all formats as available."""
        headers = {"Authorization": f"Bearer {pro_tier_auth}"}
        
        with patch("api.export_routes.get_user_tier_info", side_effect=mock_tier_info("pro")):
            response = client.get(
                "/api/quizzes/export/formats",
                headers=headers
            )
        
        assert response.status_code == 200
        data = response.json()
        
        # All formats should be available for Pro tier
        assert data.get("google_forms", {}).get("available") is True
        assert data.get("qti", {}).get("available") is True
        assert data.get("moodle_xml", {}).get("available") is True
        assert data.get("pdf", {}).get("available") is True
