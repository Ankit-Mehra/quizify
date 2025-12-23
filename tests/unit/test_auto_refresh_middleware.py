"""
Unit tests for the auto-refresh middleware's _extract_refresh_token function.

These tests verify the cookie extraction behavior, particularly:
1. Single cookie extraction
2. Duplicate cookie handling (Starlette returns last value)
3. Empty string cookie handling (returns None)
4. Missing cookie handling (returns None)

Note: We define a local copy of _extract_refresh_token to avoid importing the
middleware module, which has heavy dependencies (Redis, httpx, etc.) that would
complicate unit test isolation. The implementation is simple enough (~3 lines)
that keeping this in sync is trivial, and integration tests cover the full flow.
"""

import pytest
from starlette.testclient import TestClient
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.requests import Request


def _extract_refresh_token(request: Request) -> str | None:
    """
    Extract refresh_token from cookies (local copy for test isolation).
    
    This mirrors middleware.auto_refresh._extract_refresh_token exactly.
    Starlette automatically returns the last value if duplicate cookies exist,
    so we can use the simple request.cookies interface.
    
    Returns None if the cookie is missing or empty.
    """
    token = request.cookies.get("refresh_token")
    return token if token else None


def _test_endpoint(request: Request) -> JSONResponse:
    """Test endpoint that extracts refresh token and returns it."""
    token = _extract_refresh_token(request)
    return JSONResponse({
        "token": token,
        "token_type": type(token).__name__
    })


@pytest.fixture
def test_app():
    """Create a test Starlette app with the test endpoint."""
    app = Starlette(routes=[Route("/", _test_endpoint)])
    return TestClient(app)


class TestExtractRefreshToken:
    """Tests for _extract_refresh_token function."""

    def test_single_cookie_extraction(self, test_app):
        """Test that a single refresh_token cookie is extracted correctly."""
        response = test_app.get("/", headers={"Cookie": "refresh_token=valid_token_123"})
        
        assert response.status_code == 200
        data = response.json()
        assert data["token"] == "valid_token_123"
        assert data["token_type"] == "str"

    def test_duplicate_cookie_returns_last_value(self, test_app):
        """
        Test that when duplicate cookies exist, the last value is returned.
        
        This is important for token refresh scenarios where an old cookie
        might still exist alongside a new one.
        """
        response = test_app.get(
            "/", 
            headers={"Cookie": "refresh_token=old_stale_token; refresh_token=new_valid_token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["token"] == "new_valid_token"

    def test_three_duplicate_cookies_returns_last(self, test_app):
        """Test with three duplicate cookies - should return the last one."""
        response = test_app.get(
            "/",
            headers={"Cookie": "refresh_token=first; refresh_token=second; refresh_token=third"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["token"] == "third"

    def test_empty_cookie_returns_none(self, test_app):
        """Test that an empty cookie value returns None."""
        response = test_app.get("/", headers={"Cookie": "refresh_token="})
        
        assert response.status_code == 200
        data = response.json()
        assert data["token"] is None
        assert data["token_type"] == "NoneType"

    def test_missing_cookie_returns_none(self, test_app):
        """Test that missing refresh_token cookie returns None."""
        response = test_app.get("/", headers={"Cookie": "access_token=some_value"})
        
        assert response.status_code == 200
        data = response.json()
        assert data["token"] is None
        assert data["token_type"] == "NoneType"

    def test_no_cookie_header_returns_none(self, test_app):
        """Test that no Cookie header at all returns None."""
        response = test_app.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["token"] is None
        assert data["token_type"] == "NoneType"

    def test_cookie_with_special_characters(self, test_app):
        """Test that cookies with special characters are handled correctly."""
        # Supabase tokens contain base64 characters including = and -
        token_value = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test-payload_123"
        response = test_app.get("/", headers={"Cookie": f"refresh_token={token_value}"})
        
        assert response.status_code == 200
        data = response.json()
        assert data["token"] == token_value

    def test_whitespace_only_cookie_returns_none(self, test_app):
        """Test that whitespace-only cookie value returns None."""
        response = test_app.get("/", headers={"Cookie": "refresh_token=   "})
        
        assert response.status_code == 200
        data = response.json()
        # Whitespace-only values are falsy strings, so our function converts them
        # to None. Note: Cookie parsing behavior may vary - this test validates
        # current Starlette behavior rather than a specification guarantee.
        assert data["token"] is None
        assert data["token_type"] == "NoneType"

    def test_mixed_cookies_extracts_refresh_token(self, test_app):
        """Test extraction when multiple different cookies are present."""
        response = test_app.get(
            "/",
            headers={"Cookie": "access_token=abc; refresh_token=target_token; session_id=xyz"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["token"] == "target_token"


class TestFunctionSync:
    """
    Verify the test copy of _extract_refresh_token matches production.
    
    This ensures the unit tests remain valid even though they use a local copy
    of the function (to avoid heavy middleware dependencies).
    """

    def test_function_implementation_matches_production(self):
        """
        Verify that the test function implementation matches the production code.
        
        This test reads the actual source code from both files and compares the
        function body to ensure they stay in sync. If this test fails, update
        the local copy in this test file to match middleware/auto_refresh.py.
        """
        import inspect
        import re
        
        # Get the source of our test copy
        test_source = inspect.getsource(_extract_refresh_token)
        
        # Extract just the implementation (the actual logic lines)
        # Skip docstring and get the functional code
        test_lines = test_source.split('\n')
        test_impl_lines = []
        in_docstring = False
        for line in test_lines:
            stripped = line.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                if in_docstring:
                    in_docstring = False
                    continue
                elif stripped.count('"""') == 2 or stripped.count("'''") == 2:
                    continue  # Single-line docstring
                else:
                    in_docstring = True
                    continue
            if in_docstring:
                continue
            if stripped.startswith('def '):
                continue
            if stripped:
                test_impl_lines.append(stripped)
        
        # Read production source directly from file to avoid import
        import pathlib
        middleware_path = pathlib.Path(__file__).parent.parent.parent / "middleware" / "auto_refresh.py"
        middleware_source = middleware_path.read_text()
        
        # Extract _extract_refresh_token function from production code
        # Find the function and extract its body
        pattern = r'def _extract_refresh_token\(request: Request\) -> str \| None:.*?(?=\n(?:def |class |# |[A-Z_]+ = |\Z))'
        match = re.search(pattern, middleware_source, re.DOTALL)
        assert match, "Could not find _extract_refresh_token in middleware/auto_refresh.py"
        
        prod_source = match.group(0)
        prod_lines = prod_source.split('\n')
        prod_impl_lines = []
        in_docstring = False
        for line in prod_lines:
            stripped = line.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                if in_docstring:
                    in_docstring = False
                    continue
                elif stripped.count('"""') == 2 or stripped.count("'''") == 2:
                    continue
                else:
                    in_docstring = True
                    continue
            if in_docstring:
                continue
            if stripped.startswith('def '):
                continue
            if stripped:
                prod_impl_lines.append(stripped)
        
        # Compare the actual implementation
        assert test_impl_lines == prod_impl_lines, (
            f"Test function implementation differs from production!\n"
            f"Test implementation: {test_impl_lines}\n"
            f"Production implementation: {prod_impl_lines}\n"
            f"Please update the test copy to match middleware/auto_refresh.py"
        )
