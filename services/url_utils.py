"""
URL utilities for safe handling, redaction, and logging.

This module centralizes all URL redaction logic to prevent accidental leakage
of sensitive information (credentials, query params, tokens) in logs and storage.

All URL logging and storage throughout the application should use these helpers.
"""
from urllib.parse import urlparse, urlunparse


def redact_url(url: str, max_path_length: int = None) -> str:
    """
    Redact sensitive information from URL for safe logging and storage.
    
    Removes:
    - Query parameters (may contain API tokens, session IDs, PII)
    - Fragments (may contain sensitive anchors)
    - Username/password credentials (user:pass@host)
    
    Handles:
    - IPv6 addresses with proper bracket formatting
    - Long paths (optionally truncated)
    
    Args:
        url: The full URL to redact
        max_path_length: Optional maximum path length before truncation.
                        If None, path is not truncated.
        
    Returns:
        URL with only scheme, host, and path (no credentials/query/fragment)
        
    Examples:
        >>> redact_url('https://user:pass@example.com/doc.pdf?token=secret')
        'https://example.com/doc.pdf'
        
        >>> redact_url('http://[::1]:8080/path?key=value')
        'http://[::1]:8080/path'
        
        >>> redact_url('https://example.com/very/long/path', max_path_length=10)
        'https://example.com/very/long/'
    """
    try:
        parsed = urlparse(url)
        
        # Strip credentials from netloc by using only hostname (and port if present)
        # parsed.netloc may contain user:pass@host:port, but parsed.hostname is just the host
        # Note: parsed.hostname strips brackets from IPv6 addresses, so we need to re-add them
        hostname = parsed.hostname or ''
        
        # Check if this is an IPv6 address - use ipaddress module for accurate detection
        # (simple colon check would incorrectly match hostnames with ports)
        if hostname:
            try:
                ip = ipaddress.ip_address(hostname)
                if ip.version == 6:
                    hostname = f'[{hostname}]'
            except ValueError:
                pass  # Not an IP address, keep hostname as-is
        
        safe_netloc = hostname
        if parsed.port:
            safe_netloc = f"{safe_netloc}:{parsed.port}"
        
        # Optionally truncate long paths
        path = parsed.path
        if max_path_length and len(path) > max_path_length:
            path = path[:max_path_length]
        
        # Keep only scheme, safe netloc (host:port, no credentials), and path
        # Drop query string, fragment, params, username, and password
        redacted = urlunparse((
            parsed.scheme,
            safe_netloc,
            path,
            '',  # params
            '',  # query (removed)
            ''   # fragment (removed)
        ))
        return redacted
    except Exception:
        # If parsing fails, return a truncated version
        # Strip query params and truncate
        return url.split('?')[0][:100] if url else "unknown"


def redact_url_for_storage(url: str) -> str:
    """
    Redact URL for safe storage in database.
    
    Same as redact_url() but without path truncation, suitable for
    storing in content_source_reference fields.
    
    Args:
        url: The full URL to redact
        
    Returns:
        Redacted URL safe for storage
    """
    return redact_url(url, max_path_length=None)


def redact_url_for_logging(url: str) -> str:
    """
    Redact URL for safe logging with path truncation.
    
    Truncates paths longer than 100 characters to keep logs readable
    while still providing useful context.
    
    Args:
        url: The full URL to redact
        
    Returns:
        Redacted URL safe for logging (path truncated to 100 chars)
    """
    return redact_url(url, max_path_length=100)


# Aliases for backwards compatibility
_redact_url_for_logging = redact_url_for_logging
