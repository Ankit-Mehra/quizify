"""
Web scraping service for extracting content from URLs.
Implements SSRF protection and uses Playwright + Trafilatura for robust extraction.
Supports automatic PDF download and text extraction from PDF URLs.
"""
import ipaddress
import socket
import os
import time
import threading
import httpx
from urllib.parse import urlparse
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
import trafilatura
from fastapi import HTTPException
from services.logger import app_logger as logger
from services.url_utils import redact_url_for_logging as _redact_url_for_logging  # Centralized URL redaction
from config import config as app_config
from services.ai_services.doc_service import extract_text_from_pdf
from services.db_services.supabase_file import save_file_to_supabase_async
from services.redis.browser_slots import browser_slot_manager


# Constants
MAX_CONTENT_SIZE = 500 * 1024  # 500KB for HTML content
MAX_PDF_SIZE = 10 * 1024 * 1024  # 10MB for PDF files (same as file upload limit)
MIN_CONTENT_SIZE = 100  # 100 characters
SCRAPE_TIMEOUT = 60000  # 60 seconds in milliseconds (increased from 30s)
FALLBACK_TIMEOUT = 30000  # 30 seconds fallback for faster retry
PDF_DOWNLOAD_TIMEOUT = 30.0  # 30 seconds for PDF downloads

# Resource limits for DoS prevention
MAX_MEMORY_MB = 256  # Maximum memory per browser instance
MAX_CONCURRENT_BROWSERS = 3  # Maximum concurrent browsers per user
JS_EXECUTION_TIMEOUT = 10000  # JavaScript execution timeout (10s)
PAGE_LOAD_TIMEOUT = 5000  # Additional page load timeout (5s)

# DNS cache configuration
# NOTE: DNS caching is DISABLED for security-critical SSRF validation paths.
# The cache is only used for non-security paths like logging/metrics.
# All calls to resolve_hostname_to_ips in validate_url and _validate_redirect_url
# MUST use use_cache=False to prevent DNS rebinding attacks.
DNS_CACHE_TTL = 30  # Cache DNS results for 30 seconds (for non-security paths only)
_dns_cache: dict = {}  # {hostname: (ips, expiry_time)}
_dns_cache_lock = threading.Lock()  # Thread-safe cache access

# Security Note: We avoid --single-process and --no-sandbox flags when possible
# as they disable Chrome's security sandbox. These flags should only be used
# in containerized environments where the container provides isolation.


def _is_running_in_container() -> bool:
    """
    Detect if we're running in a containerized environment.
    
    Returns:
        True if running in a container, False otherwise
    """
    # Check for common container indicators
    container_indicators = [
        os.path.exists('/.dockerenv'),  # Docker
        os.environ.get('RAILWAY_ENVIRONMENT') is not None,  # Railway
        os.environ.get('HEROKU_DYNO_ID') is not None,  # Heroku
        os.environ.get('KUBERNETES_SERVICE_HOST') is not None,  # Kubernetes
        os.environ.get('CONTAINER') == 'true',  # Generic container flag
    ]
    
    # Check cgroup safely
    if os.path.exists('/proc/1/cgroup'):
        try:
            with open('/proc/1/cgroup', 'r') as f:
                if 'docker' in f.read():
                    container_indicators.append(True)
        except (IOError, OSError) as exc:
            # Non-critical: if we can't read cgroup info, we just skip this indicator
            logger.debug("Failed to read /proc/1/cgroup for container detection: %s", exc)
    
    return any(container_indicators)


def _get_chrome_args() -> list:
    """
    Get Chrome launch arguments with security considerations.
    
    Returns:
        List of Chrome arguments optimized for security and environment
    """
    # Base secure arguments
    args = [
        f'--max-old-space-size={MAX_MEMORY_MB}',  # Limit V8 memory
        '--disable-dev-shm-usage',  # Prevent shared memory issues in containers
        '--disable-gpu',  # Disable GPU rendering for headless mode
        '--disable-features=TranslateUI',  # Disable translation popups
        '--disable-renderer-backgrounding',  # Keep renderer active
        '--disable-backgrounding-occluded-windows',  # Prevent backgrounding
        '--disable-background-timer-throttling',  # Prevent timer throttling
        '--memory-pressure-off',  # Disable memory pressure notifications
        f'--max_old_space_size={MAX_MEMORY_MB}',  # Alternative memory limit syntax
        '--disable-extensions',  # Disable extensions for security
        '--disable-plugins',  # Disable plugins for security
        '--disable-web-security',  # Only for scraping - allows CORS bypass
    ]
    
    # Add container-specific arguments if running in a container
    if _is_running_in_container():
        logger.info("Container environment detected - adding --no-sandbox for compatibility")
        args.append('--no-sandbox')  # Required for containerized environments
    else:
        logger.info("Native environment detected - maintaining sandbox security")
    
    return args

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


def is_pdf_url(url: str) -> bool:
    """
    Detect if a URL points to a PDF file.
    
    Checks for:
    - .pdf extension in the path
    - Common PDF hosting patterns (arxiv.org/pdf, etc.)
    
    Args:
        url: The URL to check
        
    Returns:
        True if URL likely points to a PDF, False otherwise
    """
    try:
        parsed_url = urlparse(url)
        # Only lowercase the path for comparison (not the entire URL)
        path = parsed_url.path.lower()
        
        # Check for .pdf extension
        if path.endswith('.pdf'):
            return True
        
        # Check for common PDF hosting patterns
        pdf_patterns = [
            '/pdf/',  # arxiv.org/pdf/..., example.com/documents/pdf/...
            '.pdf/',  # Some URLs have .pdf in the middle: example.com/file.pdf/download
        ]
        
        for pattern in pdf_patterns:
            if pattern in path:
                return True
        
        return False
        
    except Exception as e:
        logger.warning(f"Error checking if URL is PDF: {str(e)}")
        return False


async def download_and_extract_pdf(url: str, user_id: str = None, user_token: str = None) -> tuple[str, bytes]:
    """
    Download PDF from URL and extract text content.
    
    NOTE: URL validation should happen in the caller (scrape_content) before calling this function.
    This function assumes the URL has already been validated for security.
    
    This function:
    1. Downloads the PDF with size limits (10MB max)
    2. Extracts text using PyMuPDF (via doc_service)
    3. Validates extracted content
    4. Returns both text content AND raw PDF bytes (for optional saving)
    
    Args:
        url: The PDF URL to download (assumed to be pre-validated)
        user_id: Unused parameter (kept for backwards compatibility)
        user_token: Unused parameter (kept for backwards compatibility)
        
    Returns:
        Tuple of (extracted_text, pdf_bytes) where:
        - extracted_text (str): Text content extracted from PDF
        - pdf_bytes (bytes): Raw PDF file bytes for optional saving
        
    Raises:
        HTTPException: If download fails, file is too large, or text extraction fails
    
    Note:
        File saving is handled separately by save_pdf_to_user_files() in the caller (scrape_content).
        The user_id and user_token parameters are not used by this function.
    """
    
    logger.info(f"Downloading PDF from URL: {_redact_url_for_logging(url)}")
    
    try:
        # Download PDF with timeout, size limits, and SSRF-safe redirect handling
        # Use custom transport that validates each redirect hop
        # SECURITY: Use follow_redirects=False and handle redirects manually to prevent
        # SSRF TOCTOU (Time-of-Check-Time-of-Use) attacks.
        transport = SSRFSafeTransport()
        async with httpx.AsyncClient(
            timeout=PDF_DOWNLOAD_TIMEOUT,
            follow_redirects=False,
            limits=httpx.Limits(max_connections=5),
            transport=transport
        ) as client:
            
            current_url = url
            redirect_count = 0
            MAX_REDIRECTS = 10
            
            while True:
                # Stream download to check size before downloading entire file
                async with client.stream('GET', current_url) as response:
                    # Handle redirects manually to ensure validation happens before following
                    if response.is_redirect:
                        redirect_count += 1
                        if redirect_count > MAX_REDIRECTS:
                            raise HTTPException(status_code=400, detail="Too many redirects")
                            
                        location = response.headers.get('location')
                        if not location:
                            raise HTTPException(status_code=400, detail="Redirect with no Location header")
                            
                        # Resolve relative URL
                        redirect_url = httpx.URL(location)
                        if not redirect_url.is_absolute_url:
                            redirect_url = httpx.URL(current_url).join(location)
                        
                        current_url = str(redirect_url)
                        logger.debug(f"Following redirect to: {_redact_url_for_logging(current_url)}")
                        
                        # Validate redirect URL (SSRFSafeTransport also does this, but explicit check here is good)
                        _validate_redirect_url(current_url)
                        
                        # Continue to next iteration (response is closed by context manager exit)
                        continue

                    response.raise_for_status()
                    
                    # Check Content-Type header (optional validation)
                    content_type = response.headers.get('content-type', '').lower()
                    logger.debug(f"PDF URL Content-Type: {content_type}")
                    
                    # Check content length if available
                    content_length = response.headers.get('content-length')
                    if content_length:
                        size = int(content_length)
                        if size > MAX_PDF_SIZE:
                            logger.error(f"PDF too large: {size} bytes (max: {MAX_PDF_SIZE})")
                            raise HTTPException(
                                status_code=400,
                                detail=f"PDF file is too large ({size / (1024*1024):.1f}MB). Maximum size is {MAX_PDF_SIZE / (1024*1024)}MB."
                            )
                        logger.info(f"PDF size: {size / (1024*1024):.2f}MB")
                    
                    # Download PDF content using bytearray to avoid O(n) allocations per chunk
                    # from repeated bytes concatenation while supporting streaming-friendly buffering
                    pdf_buffer = bytearray()
                    downloaded_size = 0
                    
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        downloaded_size += len(chunk)
                        
                        # Check size limit during download
                        if downloaded_size > MAX_PDF_SIZE:
                            logger.error(f"PDF download exceeded size limit: {downloaded_size} bytes")
                            raise HTTPException(
                                status_code=400,
                                detail=f"PDF file is too large (>{MAX_PDF_SIZE / (1024*1024)}MB). Maximum size is {MAX_PDF_SIZE / (1024*1024)}MB."
                            )
                        
                        pdf_buffer.extend(chunk)
                    
                    pdf_bytes = bytes(pdf_buffer)
                    logger.info(f"PDF downloaded successfully: {len(pdf_bytes) / (1024*1024):.2f}MB")
                    
                    # Break the loop as we have the file
                    break
        
        # Extract text from PDF
        logger.info("Extracting text from downloaded PDF...")
        text = extract_text_from_pdf(pdf_bytes)
        
        if not text or len(text.strip()) < MIN_CONTENT_SIZE:
            logger.error(f"PDF text extraction returned insufficient content: {len(text)} chars")
            raise HTTPException(
                status_code=400,
                detail="Could not extract meaningful text from PDF. The PDF might be scanned images or empty."
            )
        
        logger.info(f"Successfully extracted {len(text)} characters from PDF")
        
        # Return both text and bytes (bytes can be used to save file if needed)
        return text, pdf_bytes
        
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error downloading PDF: {e.response.status_code}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to download PDF: HTTP {e.response.status_code}. The URL might be invalid or require authentication."
        )
    except httpx.TimeoutException:
        logger.error(f"Timeout downloading PDF from {_redact_url_for_logging(url)}")
        raise HTTPException(
            status_code=408,
            detail=f"PDF download timed out after {PDF_DOWNLOAD_TIMEOUT} seconds. The file might be too large or the server is slow."
        )
    except HTTPException:
        raise  # Re-raise our own HTTP exceptions
    except Exception as e:
        logger.error(f"Error downloading/extracting PDF: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process PDF: {str(e)}"
        )


async def save_pdf_to_user_files(url: str, pdf_bytes: bytes, user_id: str, user_token: str) -> dict | None:
    """
    Save downloaded PDF to user_files table and Supabase storage.
    
    Args:
        url: The PDF URL (for extracting filename)
        pdf_bytes: The PDF file bytes
        user_id: User ID to save file for
        user_token: User authentication token
        
    Returns:
        Dict with file metadata if successful, None if failed:
        - file_id (str): UUID of the saved file
        - storage_path (str): Path in Supabase storage (format: "{user_id}/{uuid}_{filename}")
        
        Returns None on failure (does not raise exception).
    
    Note:
        This function calls save_file_to_supabase_async() which only returns file_id and storage_path.
        For complete file metadata including filename, file_size_bytes, mime_type, and uploaded_at,
        use the GET /files/metadata endpoint after file is saved.
    """
    try:
        # Extract filename from URL or use default
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path) or "downloaded.pdf"
        if not filename.endswith('.pdf'):
            filename += '.pdf'
        
        logger.info(f"Saving PDF file to user_files for user {user_id}: {filename}")
        file_info = await save_file_to_supabase_async(
            user_id=user_id,
            file_bytes=pdf_bytes,
            original_filename=filename,
            token=user_token,
            file_type="application/pdf"
        )
        logger.info(f"PDF saved successfully: file_id={file_info['file_id']}")
        return file_info
        
    except Exception as e:
        logger.error(f"Failed to save PDF to user_files: {str(e)}", exc_info=True)
        # Return None instead of raising - caller can decide how to handle
        return None


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


def _validate_redirect_url(url: str) -> None:
    """
    Validate a redirect URL to prevent SSRF via redirects.
    
    This function is called for each redirect hop to ensure the target
    doesn't resolve to a private/internal IP address.
    
    Args:
        url: The redirect target URL
        
    Raises:
        HTTPException: If the redirect target is a private IP or blocked hostname
    """
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        
        if not hostname:
            # If it's a relative URL, it should have been resolved to absolute before calling this
            raise HTTPException(
                status_code=400,
                detail="Redirect blocked: Invalid URL with no hostname (relative URLs must be resolved first)"
            )
        
        hostname = hostname.lower()
        
        # Check for localhost variants
        localhost_variants = [
            'localhost', '0.0.0.0', '127.0.0.1',
            '::1', '0:0:0:0:0:0:0:1', '::ffff:127.0.0.1'
        ]
        if hostname in localhost_variants:
            logger.warning(f"SSRF attempt blocked: Redirect to localhost ({hostname})")
            raise HTTPException(
                status_code=400,
                detail="Redirect blocked: Cannot redirect to localhost"
            )
        
        # Check if it's a direct IP address
        try:
            ipaddress.ip_address(hostname)
            if is_private_ip(hostname):
                logger.warning(f"SSRF attempt blocked: Redirect to private IP ({hostname})")
                raise HTTPException(
                    status_code=400,
                    detail="Redirect blocked: Cannot redirect to private/reserved IP address"
                )
        except ValueError:
            # It's a hostname - resolve and check
            # SECURITY: Always use fresh DNS lookup (use_cache=False) to prevent DNS rebinding attacks
            resolved_ips = resolve_hostname_to_ips(hostname, use_cache=False)
            for ip in resolved_ips:
                if is_private_ip(ip):
                    logger.warning(f"SSRF attempt blocked: Redirect hostname {hostname} resolves to private IP ({ip})")
                    raise HTTPException(
                        status_code=400,
                        detail="Redirect blocked: Hostname resolves to private/reserved IP address"
                    )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating redirect URL {_redact_url_for_logging(url)}: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Redirect validation failed: {str(e)}"
        )


class SSRFSafeTransport(httpx.AsyncHTTPTransport):
    """
    Custom HTTP transport that validates each redirect hop to prevent SSRF attacks.
    
    This intercepts redirect responses and validates the Location header
    BEFORE allowing the redirect to proceed.
    
    SECURITY: Validation flow:
    1. handle_async_request() validates request URL BEFORE making request
    2. If response is a redirect, Location header is validated BEFORE httpx follows it
    3. When httpx follows redirect, it calls handle_async_request() again for the new URL
    4. This ensures every hop is validated before any connection to that URL is made
    """
    
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        # SECURITY: Validate the request URL BEFORE making the request
        # This is called for every request, including redirect follow-ups
        _validate_redirect_url(str(request.url))
        
        # Proceed with the request using the base transport
        response = await super().handle_async_request(request)
        
        # SECURITY: If there's a redirect, validate the target BEFORE httpx follows it
        # When httpx follows this redirect, it will call handle_async_request again
        # with the new URL, providing double validation
        if response.is_redirect:
            location = response.headers.get('location')
            if location:
                # Handle relative redirects
                redirect_url = httpx.URL(location)
                if not redirect_url.is_absolute_url:
                    redirect_url = request.url.join(location)
                _validate_redirect_url(str(redirect_url))
        
        return response


def resolve_hostname_to_ips(hostname: str, use_cache: bool = False) -> list:
    """
    Resolve hostname to IP addresses (IPv4 and IPv6) to prevent DNS rebinding.
    
    SECURITY NOTE: Default is use_cache=False to prevent DNS rebinding attacks.
    Caching should ONLY be enabled for non-security paths (e.g., logging/metrics).
    All SSRF validation paths MUST use use_cache=False.
    
    Args:
        hostname: The hostname to resolve
        use_cache: Whether to use the DNS cache (default False for security).
                  Only set to True for non-security-critical paths.
        
    Returns:
        List of IP addresses (both IPv4 and IPv6)
        
    Raises:
        HTTPException: If hostname cannot be resolved
    """
    global _dns_cache
    current_time = time.time()
    
    # Check cache first (if enabled) - thread-safe access
    if use_cache:
        with _dns_cache_lock:
            if hostname in _dns_cache:
                cached_ips, expiry = _dns_cache[hostname]
                if current_time < expiry:
                    logger.debug(f"DNS cache hit for {hostname}: {cached_ips}")
                    return cached_ips
                else:
                    # Cache expired - remove stale entry
                    del _dns_cache[hostname]
                    logger.debug(f"DNS cache expired for {hostname}")
    
    try:
        # Get all IP addresses for the hostname (both IPv4 and IPv6)
        addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        ips = list(set([str(addr[4][0]) for addr in addr_info]))
        logger.debug(f"Resolved {hostname} to IPs: {ips}")
        
        # Cache the result with TTL (thread-safe) - only if caching enabled
        if use_cache:
            with _dns_cache_lock:
                _dns_cache[hostname] = (ips, current_time + DNS_CACHE_TTL)
        
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


def clear_dns_cache() -> None:
    """Clear the DNS cache. Useful for testing or forcing fresh lookups."""
    global _dns_cache
    with _dns_cache_lock:
        _dns_cache = {}
    logger.debug("DNS cache cleared")


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
        # SECURITY: Always use fresh DNS lookup (use_cache=False) for initial validation
        try:
            resolved_ips = resolve_hostname_to_ips(hostname, use_cache=False)
            
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


async def _acquire_browser_slot(user_id: str = "anonymous") -> None:
    """
    Acquire a browser slot for the user, enforcing concurrent browser limits.
    
    Uses Redis-based coordination when available, falls back to memory for single instance.
    
    Args:
        user_id: User ID for tracking, defaults to 'anonymous'
        
    Raises:
        HTTPException: If user has exceeded concurrent browser limit
    """
    await browser_slot_manager.acquire_slot(user_id)


async def _release_browser_slot(user_id: str = "anonymous") -> None:
    """
    Release a browser slot for the user.
    
    Uses Redis-based coordination when available, falls back to memory for single instance.
    
    Args:
        user_id: User ID for tracking, defaults to 'anonymous'
    """
    await browser_slot_manager.release_slot(user_id)


async def scrape_content(url: str, user_id: str = "anonymous", user_token: str = None, save_pdf: bool = False) -> tuple[str, dict | None]:
    """
    Scrape content from URL using Playwright + Trafilatura.
    Automatically handles PDF URLs by downloading and extracting text.
    Implements retry logic with different timeout strategies for problematic sites.
    Enhanced with DNS rebinding protection and resource limits to prevent attacks.
    
    Args:
        url: The URL to scrape (HTML or PDF)
        user_id: User ID for resource tracking and limits
        user_token: Optional user token for saving files (required if save_pdf=True for PDFs)
        save_pdf: If True and URL is a PDF, save the PDF to user_files table
        
    Returns:
        Tuple of (extracted_text, file_info_dict or None)
        file_info_dict contains: {"file_id": str, "storage_path": str} if PDF was saved
        
    Raises:
        HTTPException: If scraping fails, content is invalid, timeout occurs, or resource limits exceeded
    """
    # SECURITY: Validate URL once at entry point (SSRF protection)
    validate_url(url)
    
    # Check if URL points to a PDF file - handle automatically
    if is_pdf_url(url):
        logger.info(f"PDF URL detected - downloading and extracting text: {_redact_url_for_logging(url)}")
        # PDF download doesn't need browser slot - URL already validated
        text, pdf_bytes = await download_and_extract_pdf(url, user_id, user_token)
        
        # Optionally save PDF to user_files table
        file_info = None
        if save_pdf and user_id != "anonymous" and user_token:
            file_info = await save_pdf_to_user_files(url, pdf_bytes, user_id, user_token)
            if not file_info:
                logger.warning("PDF file save failed, but continuing with quiz generation")
        
        return text, file_info
    
    # Acquire browser slot (enforces concurrent browser limits) - only for HTML scraping
    await _acquire_browser_slot(user_id)
    
    try:
        # Store original hostname for re-validation
        parsed_url = urlparse(url)
        original_hostname = parsed_url.hostname
        
        logger.info(f"Starting web scraping for URL: {_redact_url_for_logging(url)} (user: {user_id[:8]}...)")
        
        # Try with longer timeout first, then fallback to shorter timeout with different strategy
        timeouts_and_strategies = [
            (SCRAPE_TIMEOUT, 'networkidle', 'First attempt with full timeout and networkidle'),
            (FALLBACK_TIMEOUT, 'domcontentloaded', 'Fallback with shorter timeout and domcontentloaded')
        ]
        
        last_error = None
        
        for timeout, wait_strategy, description in timeouts_and_strategies:
            try:
                logger.info(f"Attempting scrape: {description} (timeout: {timeout/1000}s)")
                
                # SECURITY: Re-validate hostname resolution before connection to prevent DNS rebinding attacks
                # Use use_cache=False to force fresh DNS lookup for this security-critical check
                
                # Check if hostname is an IP literal
                is_ip_literal = False
                if original_hostname:
                    try:
                        ipaddress.ip_address(original_hostname)
                        is_ip_literal = True
                    except ValueError:
                        is_ip_literal = False
                
                if original_hostname and not is_ip_literal:  # Only for hostnames, not IPs
                    try:
                        logger.debug(f"Re-validating hostname resolution for: {original_hostname}")
                        current_ips = resolve_hostname_to_ips(original_hostname, use_cache=False)
                        
                        # Check if ANY current resolved IP is private/reserved
                        for ip in current_ips:
                            if is_private_ip(ip):
                                logger.error(f"DNS rebinding attack detected! Hostname {original_hostname} now resolves to private IP: {ip}")
                                raise HTTPException(
                                    status_code=400,
                                    detail=f"Security error: Hostname resolves to private IP address at connection time ({ip}). Possible DNS rebinding attack."
                                )
                        
                        logger.debug(f"Hostname re-validation passed. Current IPs: {current_ips}")
                        
                    except HTTPException:
                        raise
                    except Exception as dns_error:
                        logger.error(f"DNS re-validation failed for {original_hostname}: {str(dns_error)}")
                        raise HTTPException(
                            status_code=400,
                            detail=f"DNS resolution failed at connection time: {str(dns_error)}"
                        )
                
                async with async_playwright() as p:
                    # Launch browser with security-optimized arguments
                    chrome_args = _get_chrome_args()
                    logger.debug(f"Launching Chrome with args: {chrome_args}")
                    
                    browser = await p.chromium.launch(
                        headless=True,
                        args=chrome_args
                    )
                    
                    # Set up context with security and resource constraints
                    context = await browser.new_context(
                        user_agent=app_config.SCRAPER_USER_AGENT,
                        viewport={'width': 1024, 'height': 768},  # Fixed viewport for consistency
                        java_script_enabled=True,  # Allow JS but with timeout controls
                        ignore_https_errors=False,  # Maintain HTTPS validation
                        bypass_csp=True,  # Bypass CSP for content extraction
                    )
                    
                    page = await context.new_page()
                    
                    # SECURITY: Set up request interception to prevent SSRF via redirects
                    # This validates every request URL (including redirects) before allowing it
                    ssrf_blocked = {"blocked": False, "url": None}
                    
                    async def intercept_request(route, request):
                        """Intercept all requests and validate against SSRF."""
                        request_url = request.url
                        try:
                            _validate_redirect_url(request_url)
                            await route.continue_()
                        except HTTPException:
                            ssrf_blocked["blocked"] = True
                            ssrf_blocked["url"] = request_url  # Keep raw URL for internal error handling
                            # SECURITY: Log redacted URL to prevent leaking tokens/secrets
                            logger.warning(f"Playwright SSRF blocked: {_redact_url_for_logging(request_url)}")
                            await route.abort("accessdenied")
                    
                    # Intercept ALL requests (including navigations and subresources)
                    await page.route("**/*", intercept_request)
                    
                    # Set page timeouts for resource control
                    page.set_default_navigation_timeout(timeout)
                    page.set_default_timeout(JS_EXECUTION_TIMEOUT)
                    
                    # Navigate with current timeout strategy
                    try:
                        logger.info(f"Navigating to URL: {_redact_url_for_logging(url)}")
                        await page.goto(url, timeout=timeout, wait_until=wait_strategy)
                        
                        # Check if SSRF was blocked during navigation
                        if ssrf_blocked["blocked"]:
                            await browser.close()
                            raise HTTPException(
                                status_code=400,
                                detail="Request blocked: URL redirected to private/internal address"
                            )
                    except PlaywrightTimeout:
                        await browser.close()
                        error_msg = f"Timeout while loading URL (strategy: {wait_strategy}, timeout: {timeout/1000}s)"
                        logger.warning(error_msg)
                        last_error = HTTPException(
                            status_code=408,
                            detail=f"Request timeout. The page took longer than {timeout/1000} seconds to load."
                        )
                        continue  # Try next strategy
                    except Exception as e:
                        await browser.close()
                        error_str = str(e).lower()
                        logger.error(f"Error navigating to URL {_redact_url_for_logging(url)}: {error_str}")
                        # Check for common HTTP errors
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
                    logger.info(f"Extracting HTML content from: {_redact_url_for_logging(url)}")
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
                        logger.error(f"Could not extract content from URL: {_redact_url_for_logging(url)}")
                        last_error = HTTPException(
                            status_code=422,
                            detail="Could not extract meaningful content from the page."
                        )
                        continue  # Try next strategy
                    
                    # Validate content size
                    if len(extracted) < MIN_CONTENT_SIZE:
                        logger.error(f"Extracted content too short from URL {_redact_url_for_logging(url)}: {len(extracted)} characters")
                        last_error = HTTPException(
                            status_code=422,
                            detail=f"Extracted content too short (minimum {MIN_CONTENT_SIZE} characters)."
                        )
                        continue  # Try next strategy
                    
                    if len(extracted) > MAX_CONTENT_SIZE:
                        logger.warning(f"Content exceeds max size, truncating: {len(extracted)} -> {MAX_CONTENT_SIZE} bytes")
                        # Truncate to max size
                        extracted = extracted[:MAX_CONTENT_SIZE]
                    
                    logger.info(f"Successfully extracted {len(extracted)} characters from URL: {_redact_url_for_logging(url)} using strategy: {wait_strategy}")
                    # HTML scraping doesn't save files, so return None for file_info
                    return extracted, None
                    
            except HTTPException as he:
                # HTTP exceptions should be raised immediately (don't retry)
                if he.status_code in [404, 403]:
                    raise he
                last_error = he
                continue
            except Exception as e:
                logger.error(f"Unexpected error scraping URL {_redact_url_for_logging(url)} with strategy {wait_strategy}: {str(e)}")
                last_error = HTTPException(
                    status_code=500,
                    detail=f"Error scraping URL: {str(e)}"
                )
                continue
        
        # If we get here, all strategies failed
        logger.error(f"All scraping strategies failed for URL: {_redact_url_for_logging(url)}")
        if last_error:
            raise last_error
        else:
            raise HTTPException(
                status_code=500,
                detail="All scraping attempts failed"
            )
    
    finally:
        # Always release browser slot, even if an error occurred
        await _release_browser_slot(user_id)