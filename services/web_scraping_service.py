"""
Web scraping service for extracting content from URLs.
Implements SSRF protection and uses Playwright + Trafilatura for robust extraction.
"""
import re
import ipaddress
from urllib.parse import urlparse
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
import trafilatura
from fastapi import HTTPException
from services.logger import app_logger as logger

# Constants
MAX_CONTENT_SIZE = 500 * 1024  # 500KB
MIN_CONTENT_SIZE = 100  # 100 characters
SCRAPE_TIMEOUT = 30000  # 30 seconds in milliseconds

# Private IP ranges to block (SSRF prevention)
PRIVATE_IP_RANGES = [
    ipaddress.ip_network('127.0.0.0/8'),    # Localhost
    ipaddress.ip_network('10.0.0.0/8'),     # Private
    ipaddress.ip_network('172.16.0.0/12'),  # Private
    ipaddress.ip_network('192.168.0.0/16'), # Private
    ipaddress.ip_network('169.254.0.0/16'), # Link-local
]


def validate_url(url: str) -> None:
    """
    Validate URL and prevent SSRF attacks.
    
    Args:
        url: The URL to validate
        
    Raises:
        HTTPException: If URL is invalid or blocked for security reasons
    """
    # Check URL length
    if len(url) > 2048:
        raise HTTPException(
            status_code=400,
            detail="URL too long. Maximum length is 2048 characters."
        )
    
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid URL format: {str(e)}"
        )
    
    # Check protocol
    if parsed.scheme not in ['http', 'https']:
        raise HTTPException(
            status_code=400,
            detail="Invalid URL protocol. Only HTTP and HTTPS are allowed."
        )
    
    # Check for localhost
    if parsed.hostname in ['localhost', '0.0.0.0', '127.0.0.1']:
        raise HTTPException(
            status_code=400,
            detail="Cannot scrape localhost URLs."
        )
    
    # Check for private IPs
    try:
        ip = ipaddress.ip_address(parsed.hostname)
        for private_range in PRIVATE_IP_RANGES:
            if ip in private_range:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot scrape private IP addresses."
                )
    except ValueError:
        # Not an IP address (it's a hostname), this is okay
        pass


async def scrape_content(url: str) -> str:
    """
    Scrape content from URL using Playwright + Trafilatura.
    
    Args:
        url: The URL to scrape
        
    Returns:
        Extracted text content from the page
        
    Raises:
        HTTPException: If scraping fails, content is invalid, or timeout occurs
    """
    validate_url(url)
    
    logger.info(f"Starting web scraping for URL: {url}")
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (compatible; QuizifyBot/1.0; +https://quizify.app/bot)'
            )
            page = await context.new_page()
            
            # Navigate with timeout
            try:
                logger.info(f"Navigating to URL: {url}")
                await page.goto(url, timeout=SCRAPE_TIMEOUT, wait_until='networkidle')
            except PlaywrightTimeout:
                await browser.close()
                logger.error(f"Timeout while loading URL: {url}")
                raise HTTPException(
                    status_code=408,
                    detail=f"Request timeout. The page took longer than {SCRAPE_TIMEOUT/1000} seconds to load."
                )
            except Exception as e:
                await browser.close()
                logger.error(f"Error navigating to URL {url}: {str(e)}")
                # Check for common HTTP errors
                error_str = str(e).lower()
                if '404' in error_str or 'not found' in error_str:
                    raise HTTPException(
                        status_code=404,
                        detail="The requested URL returned 404 Not Found."
                    )
                elif '403' in error_str or 'forbidden' in error_str:
                    raise HTTPException(
                        status_code=403,
                        detail="The requested URL returned 403 Forbidden. The site may be blocking automated access."
                    )
                raise HTTPException(
                    status_code=500,
                    detail=f"Error accessing URL: {str(e)}"
                )
            
            # Get page HTML
            logger.info(f"Extracting HTML content from: {url}")
            html = await page.content()
            await browser.close()
            
            # Extract main content using Trafilatura
            logger.info(f"Extracting text content using Trafilatura")
            extracted = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=True,
                no_fallback=False
            )
            
            if not extracted:
                logger.error(f"Could not extract content from URL: {url}")
                raise HTTPException(
                    status_code=422,
                    detail="Could not extract meaningful content from the page."
                )
            
            # Validate content size
            if len(extracted) < MIN_CONTENT_SIZE:
                logger.error(f"Extracted content too short from URL {url}: {len(extracted)} characters")
                raise HTTPException(
                    status_code=422,
                    detail=f"Extracted content too short (minimum {MIN_CONTENT_SIZE} characters)."
                )
            
            if len(extracted) > MAX_CONTENT_SIZE:
                logger.warning(f"Content exceeds max size, truncating: {len(extracted)} -> {MAX_CONTENT_SIZE} bytes")
                # Truncate to max size
                extracted = extracted[:MAX_CONTENT_SIZE]
            
            logger.info(f"Successfully extracted {len(extracted)} characters from URL: {url}")
            return extracted
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error scraping URL {url}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error scraping URL: {str(e)}"
        )
