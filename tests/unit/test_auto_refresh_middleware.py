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
        # Starlette normalizes whitespace-only cookie values to empty strings,
        # which our function treats as falsy and converts to None.
        # Verified empirically: request.cookies.get("refresh_token") returns ""
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

    @staticmethod
    def _extract_impl_lines(source_lines: list[str]) -> list[str]:
        """
        Extract implementation lines from function source, skipping docstrings.
        
        Args:
            source_lines: Lines of source code for a function
            
        Returns:
            List of stripped implementation lines (no docstrings, no def line)
        """
        impl_lines = []
        in_docstring = False
        for line in source_lines:
            stripped = line.strip()
            # Handle docstrings
            if stripped.startswith('"""') or stripped.startswith("'''"):
                quote = '"""' if stripped.startswith('"""') else "'''"
                if in_docstring:
                    in_docstring = False
                    continue
                elif stripped.count(quote) >= 2:
                    continue  # Single-line docstring
                else:
                    in_docstring = True
                    continue
            if in_docstring:
                continue
            # Skip function definition line
            if stripped.startswith('def '):
                continue
            # Keep non-empty implementation lines
            if stripped:
                impl_lines.append(stripped)
        return impl_lines

    def test_function_implementation_matches_production(self):
        """
        Verify that the test function implementation matches the production code.
        
        This test uses Python's AST module to reliably extract the function body,
        avoiding brittle regex patterns. If this test fails, update the local copy
        in this test file to match middleware/auto_refresh.py.
        """
        import ast
        import inspect
        import pathlib
        
        # Get the source of our test copy
        test_source = inspect.getsource(_extract_refresh_token)
        test_impl_lines = self._extract_impl_lines(test_source.split('\n'))
        
        # Read production source and use AST to extract the function
        middleware_path = pathlib.Path(__file__).parent.parent.parent / "middleware" / "auto_refresh.py"
        middleware_source = middleware_path.read_text()
        
        # Parse the module and find our target function
        tree = ast.parse(middleware_source)
        func_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_extract_refresh_token":
                func_node = node
                break
        
        assert func_node is not None, "Could not find _extract_refresh_token in middleware/auto_refresh.py"
        
        # Extract the function source using line numbers from AST
        source_lines = middleware_source.split('\n')
        # node.lineno is 1-indexed, end_lineno is inclusive
        func_lines = source_lines[func_node.lineno - 1:func_node.end_lineno]
        prod_impl_lines = self._extract_impl_lines(func_lines)
        
        # Compare the actual implementation
        assert test_impl_lines == prod_impl_lines, (
            f"Test function implementation differs from production!\n"
            f"Test implementation: {test_impl_lines}\n"
            f"Production implementation: {prod_impl_lines}\n"
            f"Please update the test copy to match middleware/auto_refresh.py"
        )
