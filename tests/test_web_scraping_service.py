"""
Unit tests for web scraping service.
Tests URL validation, SSRF protection, and error handling.
"""
import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeout
from unittest.mock import AsyncMock, Mock, patch
from fastapi import HTTPException
from services.web_scraping_service import validate_url, scrape_content


class TestValidateUrl:
    """Tests for URL validation and SSRF protection."""
    
    def test_validate_url_valid_http(self):
        """Test that valid HTTP URLs pass validation."""
        # Should not raise exception
        validate_url("http://example.com/page")
    
    def test_validate_url_valid_https(self):
        """Test that valid HTTPS URLs pass validation."""
        # Should not raise exception
        validate_url("https://example.com/page")
    
    def test_validate_url_rejects_localhost(self):
        """Test that localhost URLs are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            validate_url("http://localhost:8080/data")
        
        assert exc_info.value.status_code == 400
        assert "localhost" in exc_info.value.detail.lower()
    
    def test_validate_url_rejects_127_0_0_1(self):
        """Test that 127.0.0.1 URLs are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            validate_url("http://127.0.0.1/data")
        
        assert exc_info.value.status_code == 400
        assert "localhost" in exc_info.value.detail.lower()
    
    def test_validate_url_rejects_0_0_0_0(self):
        """Test that 0.0.0.0 URLs are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            validate_url("http://0.0.0.0/data")
        
        assert exc_info.value.status_code == 400
        assert "localhost" in exc_info.value.detail.lower()
    
    def test_validate_url_rejects_private_ip_192_168(self):
        """Test that private IP 192.168.x.x URLs are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            validate_url("http://192.168.1.1/admin")
        
        assert exc_info.value.status_code == 400
        assert "private" in exc_info.value.detail.lower()
        assert "reserved" in exc_info.value.detail.lower()
    
    def test_validate_url_rejects_private_ip_10(self):
        """Test that private IP 10.x.x.x URLs are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            validate_url("http://10.0.0.1/data")
        
        assert exc_info.value.status_code == 400
        assert "private" in exc_info.value.detail.lower()
        assert "reserved" in exc_info.value.detail.lower()
    
    def test_validate_url_rejects_private_ip_172(self):
        """Test that private IP 172.16-31.x.x URLs are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            validate_url("http://172.16.0.1/data")
        
        assert exc_info.value.status_code == 400
        assert "private" in exc_info.value.detail.lower()
        assert "reserved" in exc_info.value.detail.lower()
    
    def test_validate_url_rejects_link_local(self):
        """Test that link-local IP 169.254.x.x URLs are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            validate_url("http://169.254.1.1/data")
        
        assert exc_info.value.status_code == 400
        assert "private" in exc_info.value.detail.lower()
        assert "reserved" in exc_info.value.detail.lower()
    
    def test_validate_url_rejects_invalid_protocol(self):
        """Test that non-HTTP/HTTPS protocols are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            validate_url("ftp://example.com/file")
        
        assert exc_info.value.status_code == 400
        assert "protocol" in exc_info.value.detail.lower()
    
    def test_validate_url_rejects_file_protocol(self):
        """Test that file:// protocol is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            validate_url("file:///etc/passwd")
        
        assert exc_info.value.status_code == 400
        assert "protocol" in exc_info.value.detail.lower()
    
    def test_validate_url_rejects_too_long(self):
        """Test that URLs longer than 2048 characters are rejected."""
        long_url = "http://example.com/" + "a" * 2050
        with pytest.raises(HTTPException) as exc_info:
            validate_url(long_url)
        
        assert exc_info.value.status_code == 400
        assert "too long" in exc_info.value.detail.lower()
    
    @patch('services.web_scraping_service.resolve_hostname_to_ips')
    def test_validate_url_accepts_valid_domain(self, mock_resolve):
        """Test that valid domain names pass validation."""
        # Mock DNS resolution to return public IPs
        mock_resolve.return_value = ['93.184.216.34']  # example.com IP
        
        # Should not raise exception
        validate_url("https://en.wikipedia.org/wiki/Machine_Learning")
        validate_url("https://www.example.com/path/to/page")
        validate_url("https://subdomain.example.com/page")


class TestScrapeContent:
    """Tests for content scraping functionality."""

    @pytest.mark.asyncio
    @patch("services.web_scraping_service.async_playwright")
    @patch("services.web_scraping_service.trafilatura.extract")
    async def test_scrape_content_success(self, mock_extract, mock_playwright):
        """Test successful content scraping."""

        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html><body>Test content</body></html>")
        mock_page.set_default_navigation_timeout = Mock()
        mock_page.set_default_timeout = Mock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        playwright_manager = AsyncMock()
        playwright_manager.chromium.launch = AsyncMock(return_value=mock_browser)
        mock_playwright.return_value.__aenter__ = AsyncMock(return_value=playwright_manager)
        mock_playwright.return_value.__aexit__ = AsyncMock(return_value=None)

        extracted_content = (
            "This is extracted content from the web page that is long enough to pass "
            "validation. It contains more than one hundred characters."
        )
        mock_extract.return_value = extracted_content

        content, metadata = await scrape_content("https://example.com/page")

        assert content == extracted_content
        assert metadata is None
        mock_page.goto.assert_called_once()

    @pytest.mark.asyncio
    async def test_scrape_content_rejects_invalid_url(self):
        """Test that scraping rejects invalid URLs."""

        with pytest.raises(HTTPException) as exc_info:
            await scrape_content("http://localhost/data")

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @patch("services.web_scraping_service.resolve_hostname_to_ips")
    @patch("services.web_scraping_service.async_playwright")
    async def test_scrape_content_handles_timeout(self, mock_playwright, mock_resolve):
        """Test that scraping handles page load timeouts."""

        mock_resolve.return_value = ["93.184.216.34"]

        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(side_effect=PlaywrightTimeout("Timeout"))
        mock_page.set_default_navigation_timeout = Mock()
        mock_page.set_default_timeout = Mock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        playwright_manager = AsyncMock()
        playwright_manager.chromium.launch = AsyncMock(return_value=mock_browser)
        mock_playwright.return_value.__aenter__ = AsyncMock(return_value=playwright_manager)
        mock_playwright.return_value.__aexit__ = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await scrape_content("https://slow-site.com/page")

        assert exc_info.value.status_code == 408
        assert "timeout" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    @patch("services.web_scraping_service.async_playwright")
    @patch("services.web_scraping_service.trafilatura.extract")
    async def test_scrape_content_handles_no_content(self, mock_extract, mock_playwright):
        """Test that scraping handles pages with no extractable content."""

        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html><body></body></html>")
        mock_page.set_default_navigation_timeout = Mock()
        mock_page.set_default_timeout = Mock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        playwright_manager = AsyncMock()
        playwright_manager.chromium.launch = AsyncMock(return_value=mock_browser)
        mock_playwright.return_value.__aenter__ = AsyncMock(return_value=playwright_manager)
        mock_playwright.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_extract.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await scrape_content("https://example.com/empty")

        assert exc_info.value.status_code == 422
        assert "could not extract" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    @patch("services.web_scraping_service.async_playwright")
    @patch("services.web_scraping_service.trafilatura.extract")
    async def test_scrape_content_handles_short_content(self, mock_extract, mock_playwright):
        """Test that scraping rejects content that's too short."""

        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html><body>Short</body></html>")
        mock_page.set_default_navigation_timeout = Mock()
        mock_page.set_default_timeout = Mock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        playwright_manager = AsyncMock()
        playwright_manager.chromium.launch = AsyncMock(return_value=mock_browser)
        mock_playwright.return_value.__aenter__ = AsyncMock(return_value=playwright_manager)
        mock_playwright.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_extract.return_value = "Short"

        with pytest.raises(HTTPException) as exc_info:
            await scrape_content("https://example.com/short")

        assert exc_info.value.status_code == 422
        assert "too short" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    @patch("services.web_scraping_service.async_playwright")
    @patch("services.web_scraping_service.trafilatura.extract")
    async def test_scrape_content_truncates_long_content(self, mock_extract, mock_playwright):
        """Test that scraping truncates overly long content."""

        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html><body>Content</body></html>")
        mock_page.set_default_navigation_timeout = Mock()
        mock_page.set_default_timeout = Mock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        playwright_manager = AsyncMock()
        playwright_manager.chromium.launch = AsyncMock(return_value=mock_browser)
        mock_playwright.return_value.__aenter__ = AsyncMock(return_value=playwright_manager)
        mock_playwright.return_value.__aexit__ = AsyncMock(return_value=None)

        long_content = "a" * (500 * 1024 + 1000)
        mock_extract.return_value = long_content

        content, metadata = await scrape_content("https://example.com/long")

        assert len(content) == 500 * 1024
        assert metadata is None
