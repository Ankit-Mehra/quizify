"""
Web scraping service for extracting content from URLs.
Implements SSRF protection and uses Playwright + Trafilatura for robust extraction.
"""
import ipaddress
import socket
from urllib.parse import urlparse
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
import trafilatura
from fastapi import HTTPException
from services.logger import app_logger as logger
from config import config

# Constants
MAX_CONTENT_SIZE = 500 * 1024  # 500KB
MIN_CONTENT_SIZE = 100  # 100 characters
SCRAPE_TIMEOUT = 60000  # 60 seconds in milliseconds (increased from 30s)
FALLBACK_TIMEOUT = 30000  # 30 seconds fallback for faster retry

# Private IP ranges to block (SSRF prevention) - IPv4 and IPv6
PRIVATE_IP_RANGES = [
    # IPv4 private ranges
    ipaddress.ip_network('127.0.0.0/8'),    # Localhost
    ipaddress.ip_network('10.0.0.0/8'),     # Private
    ipaddress.ip_network('172.16.0.0/12'),  # Private
    ipaddress.ip_network('192.168.0.0/16'), # Private
    ipaddress.ip_network('169.254.0.0/16'), # Link-local
    ipaddress.ip_network('0.0.0.0/8'),      # Current network
    ipaddress.ip_network('100.64.0.0/10'),  # Shared address space (Carrier-grade NAT)
    ipaddress.ip_network('192.0.0.0/24'),   # IETF Protocol assignments
    ipaddress.ip_network('192.0.2.0/24'),   # Documentation (TEST-NET-1)
    ipaddress.ip_network('198.51.100.0/24'),# Documentation (TEST-NET-2)
    ipaddress.ip_network('203.0.113.0/24'), # Documentation (TEST-NET-3)
    ipaddress.ip_network('224.0.0.0/4'),    # Multicast
    ipaddress.ip_network('240.0.0.0/4'),    # Reserved
    ipaddress.ip_network('255.255.255.255/32'), # Broadcast
    
    # IPv6 private ranges
    ipaddress.ip_network('::1/128'),        # Loopback
    ipaddress.ip_network('::/128'),         # Unspecified address
    ipaddress.ip_network('::ffff:0:0/96'),  # IPv4-mapped IPv6 addresses
    ipaddress.ip_network('fe80::/10'),      # Link-local
    ipaddress.ip_network('fc00::/7'),       # Unique local addresses
    ipaddress.ip_network('ff00::/8'),       # Multicast
]


def is_private_ip(ip: str) -> bool:
    """
    Check if an IP address (IPv4 or IPv6) is private/reserved.
    
    Args:
        ip: IP address string
        
    Returns:
        True if IP is private/reserved, False otherwise
    """
    try:
        ip_obj = ipaddress.ip_address(ip)
        for private_range in PRIVATE_IP_RANGES:
            if ip_obj in private_range:
                return True
        return False
    except ValueError:
        # Invalid IP format
        return False


def resolve_hostname_to_ips(hostname: str) -> list:
    """
    Resolve hostname to IP addresses (IPv4 and IPv6) to prevent DNS rebinding.
    
    Args:
        hostname: The hostname to resolve
        
    Returns:
        List of IP addresses (both IPv4 and IPv6)
        
    Raises:
        HTTPException: If hostname cannot be resolved
    """
    try:
        # Get all IP addresses for the hostname (both IPv4 and IPv6)
        addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        ips = list(set([str(addr[4][0]) for addr in addr_info]))
        logger.debug(f"Resolved {hostname} to IPs: {ips}")
        return ips
    except socket.gaierror as e:
        logger.error(f"Failed to resolve hostname {hostname}: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Could not resolve hostname: {hostname}"
        )
    except Exception as e:
        logger.error(f"Error resolving hostname {hostname}: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Error resolving hostname: {str(e)}"
        )


def validate_url(url: str) -> None:
    """
    Validate URL and prevent SSRF attacks.
    Enhanced with IPv6 support and DNS rebinding protection.
    
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
    
    # Validate hostname exists
    if not parsed.hostname:
        raise HTTPException(
            status_code=400,
            detail="Invalid URL: Missing hostname."
        )
    
    hostname = parsed.hostname.lower()
    
    # Check for localhost variants (IPv4 and IPv6)
    localhost_variants = [
        'localhost', '0.0.0.0', '127.0.0.1',
        '::1', '0:0:0:0:0:0:0:1', '::ffff:127.0.0.1'
    ]
    if hostname in localhost_variants:
        raise HTTPException(
            status_code=400,
            detail="Cannot scrape localhost URLs."
        )
    
    # Check if hostname is an IP address (IPv4 or IPv6)
    try:
        # Try to parse as IP address
        ipaddress.ip_address(hostname)
        # It's a direct IP address - check if it's private
        if is_private_ip(hostname):
            raise HTTPException(
                status_code=400,
                detail="Cannot scrape private or reserved IP addresses."
            )
        logger.info(f"URL uses direct IP address: {hostname}")
    except ValueError:
        # Not an IP address - it's a hostname
        # Resolve hostname to IP addresses to prevent DNS rebinding attacks
        try:
            resolved_ips = resolve_hostname_to_ips(hostname)
            
            # Check if ANY resolved IP is private/reserved
            for ip in resolved_ips:
                if is_private_ip(ip):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Cannot scrape URL: Hostname resolves to private/reserved IP address ({ip})."
                    )
            
            logger.info(f"Hostname {hostname} validated - resolves to public IPs: {resolved_ips}")
        except HTTPException:
            # Re-raise HTTP exceptions (from is_private_ip or resolve_hostname_to_ips)
            raise


async def scrape_content(url: str) -> str:
    """
    Scrape content from URL using Playwright + Trafilatura.
    Implements retry logic with different timeout strategies for problematic sites.
    
    Args:
        url: The URL to scrape
        
    Returns:
        Extracted text content from the page
        
    Raises:
        HTTPException: If scraping fails, content is invalid, or timeout occurs
    """
    validate_url(url)
    
    logger.info(f"Starting web scraping for URL: {url}")
    
    # Try with longer timeout first, then fallback to shorter timeout with different strategy
    timeouts_and_strategies = [
        (SCRAPE_TIMEOUT, 'networkidle', 'First attempt with full timeout and networkidle'),
        (FALLBACK_TIMEOUT, 'domcontentloaded', 'Fallback with shorter timeout and domcontentloaded')
    ]
    
    last_error = None
    
    for timeout, wait_strategy, description in timeouts_and_strategies:
        try:
            logger.info(f"Attempting scrape: {description} (timeout: {timeout/1000}s)")
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent=config.SCRAPER_USER_AGENT
                )
                page = await context.new_page()
                
                # Navigate with current timeout strategy
                try:
                    logger.info(f"Navigating to URL: {url}")
                    await page.goto(url, timeout=timeout, wait_until=wait_strategy)
                except PlaywrightTimeout:
                    await browser.close()
                    error_msg = f"Timeout while loading URL: {url} (strategy: {wait_strategy}, timeout: {timeout/1000}s)"
                    logger.warning(error_msg)
                    last_error = HTTPException(
                        status_code=408,
                        detail=f"Request timeout. The page took longer than {timeout/1000} seconds to load."
                    )
                    continue  # Try next strategy
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
                    last_error = HTTPException(
                        status_code=500,
                        detail=f"Error accessing URL: {str(e)}"
                    )
                    continue  # Try next strategy
                
                # Get page HTML
                logger.info(f"Extracting HTML content from: {url}")
                html = await page.content()
                await browser.close()
                
                # Extract main content using Trafilatura
                logger.info("Extracting text content using Trafilatura")
                extracted = trafilatura.extract(
                    html,
                    include_comments=False,
                    include_tables=True,
                    no_fallback=False
                )
                
                if not extracted:
                    logger.error(f"Could not extract content from URL: {url}")
                    last_error = HTTPException(
                        status_code=422,
                        detail="Could not extract meaningful content from the page."
                    )
                    continue  # Try next strategy
                
                # Validate content size
                if len(extracted) < MIN_CONTENT_SIZE:
                    logger.error(f"Extracted content too short from URL {url}: {len(extracted)} characters")
                    last_error = HTTPException(
                        status_code=422,
                        detail=f"Extracted content too short (minimum {MIN_CONTENT_SIZE} characters)."
                    )
                    continue  # Try next strategy
                
                if len(extracted) > MAX_CONTENT_SIZE:
                    logger.warning(f"Content exceeds max size, truncating: {len(extracted)} -> {MAX_CONTENT_SIZE} bytes")
                    # Truncate to max size
                    extracted = extracted[:MAX_CONTENT_SIZE]
                
                logger.info(f"Successfully extracted {len(extracted)} characters from URL: {url} using strategy: {wait_strategy}")
                return extracted
                
        except HTTPException as he:
            # HTTP exceptions should be raised immediately (don't retry)
            if he.status_code in [404, 403]:
                raise he
            last_error = he
            continue
        except Exception as e:
            logger.error(f"Unexpected error scraping URL {url} with strategy {wait_strategy}: {str(e)}")
            last_error = HTTPException(
                status_code=500,
                detail=f"Error scraping URL: {str(e)}"
            )
            continue
    
    # If we get here, all strategies failed
    logger.error(f"All scraping strategies failed for URL: {url}")
    if last_error:
        raise last_error
    else:
        raise HTTPException(
            status_code=500,
            detail="All scraping attempts failed"
        )
