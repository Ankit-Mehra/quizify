"""
Unit tests for SSRF protection in web scraping service.
Tests IPv4, IPv6, and DNS rebinding attack prevention.
"""
import socket
import pytest
from unittest.mock import patch
from fastapi import HTTPException
from services.web_scraping_service import (
    validate_url,
    is_private_ip,
    resolve_hostname_to_ips,
    clear_dns_cache
)


@pytest.fixture(autouse=True)
def clear_cache_between_tests():
    """Clear DNS cache before and after each test to ensure isolation."""
    clear_dns_cache()
    yield
    clear_dns_cache()


class TestIsPrivateIP:
    """Test IP address privacy detection."""
    
    def test_ipv4_localhost(self):
        """Test IPv4 localhost addresses are detected as private."""
        assert is_private_ip('127.0.0.1') is True
        assert is_private_ip('127.0.0.2') is True
        assert is_private_ip('127.255.255.255') is True
    
    def test_ipv4_private_ranges(self):
        """Test IPv4 private network ranges."""
        assert is_private_ip('10.0.0.1') is True
        assert is_private_ip('172.16.0.1') is True
        assert is_private_ip('192.168.1.1') is True
        assert is_private_ip('169.254.0.1') is True  # Link-local
    
    def test_ipv4_public(self):
        """Test IPv4 public addresses are not detected as private."""
        assert is_private_ip('8.8.8.8') is False
        assert is_private_ip('1.1.1.1') is False
        assert is_private_ip('142.250.185.206') is False  # Google
    
    def test_ipv6_localhost(self):
        """Test IPv6 localhost is detected as private."""
        assert is_private_ip('::1') is True
        assert is_private_ip('0:0:0:0:0:0:0:1') is True
    
    def test_ipv6_link_local(self):
        """Test IPv6 link-local addresses."""
        assert is_private_ip('fe80::1') is True
        assert is_private_ip('fe80::abcd:ef12:3456:7890') is True
    
    def test_ipv6_unique_local(self):
        """Test IPv6 unique local addresses (fc00::/7)."""
        assert is_private_ip('fc00::1') is True
        assert is_private_ip('fd00::1') is True
    
    def test_ipv6_public(self):
        """Test IPv6 public addresses are not detected as private."""
        assert is_private_ip('2001:4860:4860::8888') is False  # Google DNS
        assert is_private_ip('2606:4700:4700::1111') is False  # Cloudflare DNS
    
    def test_ipv4_mapped_ipv6(self):
        """Test IPv4-mapped IPv6 addresses."""
        assert is_private_ip('::ffff:127.0.0.1') is True
        assert is_private_ip('::ffff:192.168.1.1') is True
    
    def test_invalid_ip(self):
        """Test invalid IP addresses return False."""
        assert is_private_ip('not-an-ip') is False
        assert is_private_ip('999.999.999.999') is False


class TestResolveHostnameToIPs:
    """Test hostname resolution."""
    
    @patch('services.web_scraping_service.socket.getaddrinfo')
    def test_resolve_ipv4_only(self, mock_getaddrinfo):
        """Test resolving hostname to IPv4 only."""
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 80)),
        ]
        
        ips = resolve_hostname_to_ips('example.com')
        assert '93.184.216.34' in ips
        assert len(ips) == 1
    
    @patch('services.web_scraping_service.socket.getaddrinfo')
    def test_resolve_ipv4_and_ipv6(self, mock_getaddrinfo):
        """Test resolving hostname to both IPv4 and IPv6."""
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 80)),
            (socket.AF_INET6, socket.SOCK_STREAM, 6, '', ('2606:2800:220:1:248:1893:25c8:1946', 80, 0, 0)),
        ]
        
        ips = resolve_hostname_to_ips('example.com')
        assert '93.184.216.34' in ips
        assert '2606:2800:220:1:248:1893:25c8:1946' in ips
        assert len(ips) == 2
    
    @patch('services.web_scraping_service.socket.getaddrinfo')
    def test_resolve_duplicate_ips_removed(self, mock_getaddrinfo):
        """Test that duplicate IPs are removed."""
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 80)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443)),  # Same IP, different port
        ]
        
        ips = resolve_hostname_to_ips('example.com')
        assert len(ips) == 1
        assert '93.184.216.34' in ips
    
    @patch('services.web_scraping_service.socket.getaddrinfo')
    def test_resolve_hostname_not_found(self, mock_getaddrinfo):
        """Test handling of non-existent hostname."""
        import socket as socket_module
        mock_getaddrinfo.side_effect = socket_module.gaierror("Name or service not known")
        
        with pytest.raises(HTTPException) as exc_info:
            resolve_hostname_to_ips('this-domain-does-not-exist-12345.com')
        
        assert exc_info.value.status_code == 400
        assert 'Could not resolve hostname' in exc_info.value.detail


class TestValidateURL:
    """Test URL validation with SSRF protection."""
    
    @patch('services.web_scraping_service.resolve_hostname_to_ips')
    def test_valid_https_url(self, mock_resolve):
        """Test valid HTTPS URLs pass validation."""
        # Mock DNS resolution to return public IPs
        mock_resolve.return_value = ['93.184.216.34']  # example.com public IP
        
        # Should not raise exception
        validate_url('https://example.com')
        
        mock_resolve.return_value = ['142.250.80.68']  # google.com public IP
        validate_url('https://www.google.com/search?q=test')
    
    @patch('services.web_scraping_service.resolve_hostname_to_ips')
    def test_valid_http_url(self, mock_resolve):
        """Test valid HTTP URLs pass validation."""
        # Mock DNS resolution to return public IPs
        mock_resolve.return_value = ['93.184.216.34']  # example.com public IP
        # Should not raise exception
        validate_url('http://example.com')
    
    def test_url_too_long(self):
        """Test URLs exceeding maximum length are rejected."""
        long_url = 'https://example.com/' + 'a' * 3000
        
        with pytest.raises(HTTPException) as exc_info:
            validate_url(long_url)
        
        assert exc_info.value.status_code == 400
        assert 'too long' in exc_info.value.detail.lower()
    
    def test_invalid_protocol_ftp(self):
        """Test FTP protocol is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            validate_url('ftp://example.com/file.txt')
        
        assert exc_info.value.status_code == 400
        assert 'protocol' in exc_info.value.detail.lower()
    
    def test_invalid_protocol_file(self):
        """Test file:// protocol is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            validate_url('file:///etc/passwd')
        
        assert exc_info.value.status_code == 400
        assert 'protocol' in exc_info.value.detail.lower()
    
    def test_localhost_variants_rejected(self):
        """Test various localhost representations are rejected."""
        localhost_urls = [
            'http://localhost/data',
            'http://127.0.0.1/admin',
            'http://0.0.0.0/internal',
            'http://[::1]/api',
        ]
        
        for url in localhost_urls:
            with pytest.raises(HTTPException) as exc_info:
                validate_url(url)
            
            assert exc_info.value.status_code == 400
            assert 'localhost' in exc_info.value.detail.lower()
    
    def test_ipv4_private_direct_rejected(self):
        """Test direct IPv4 private addresses are rejected."""
        private_urls = [
            'http://10.0.0.1/api',
            'http://172.16.0.1/admin',
            'http://192.168.1.1/config',
            'http://169.254.169.254/metadata',  # AWS metadata endpoint
        ]
        
        for url in private_urls:
            with pytest.raises(HTTPException) as exc_info:
                validate_url(url)
            
            assert exc_info.value.status_code == 400
            assert 'private' in exc_info.value.detail.lower()
    
    def test_ipv6_private_direct_rejected(self):
        """Test direct IPv6 private addresses are rejected."""
        private_urls = [
            'http://[fe80::1]/api',
            'http://[fc00::1]/admin',
            'http://[fd00::1]/config',
        ]
        
        for url in private_urls:
            with pytest.raises(HTTPException) as exc_info:
                validate_url(url)
            
            assert exc_info.value.status_code == 400
            assert 'private' in exc_info.value.detail.lower()
    
    @patch('services.web_scraping_service.resolve_hostname_to_ips')
    def test_hostname_resolves_to_private_ipv4_rejected(self, mock_resolve):
        """Test DNS rebinding attack prevention - hostname resolves to private IPv4."""
        mock_resolve.return_value = ['192.168.1.100']
        
        with pytest.raises(HTTPException) as exc_info:
            validate_url('http://evil.com/attack')
        
        assert exc_info.value.status_code == 400
        assert 'private' in exc_info.value.detail.lower()
        assert '192.168.1.100' in exc_info.value.detail
    
    @patch('services.web_scraping_service.resolve_hostname_to_ips')
    def test_hostname_resolves_to_private_ipv6_rejected(self, mock_resolve):
        """Test DNS rebinding attack prevention - hostname resolves to private IPv6."""
        mock_resolve.return_value = ['fe80::1']
        
        with pytest.raises(HTTPException) as exc_info:
            validate_url('http://evil.com/attack')
        
        assert exc_info.value.status_code == 400
        assert 'private' in exc_info.value.detail.lower()
    
    @patch('services.web_scraping_service.resolve_hostname_to_ips')
    def test_hostname_resolves_to_mixed_ips_rejected(self, mock_resolve):
        """Test DNS rebinding - if ANY resolved IP is private, reject."""
        # Mix of public and private IPs (attack scenario)
        mock_resolve.return_value = ['8.8.8.8', '192.168.1.1']
        
        with pytest.raises(HTTPException) as exc_info:
            validate_url('http://evil.com/attack')
        
        assert exc_info.value.status_code == 400
        assert 'private' in exc_info.value.detail.lower()
    
    @patch('services.web_scraping_service.resolve_hostname_to_ips')
    def test_hostname_resolves_to_public_ips_accepted(self, mock_resolve):
        """Test hostname resolving to only public IPs is accepted."""
        mock_resolve.return_value = ['93.184.216.34', '2606:2800:220:1:248:1893:25c8:1946']
        
        # Should not raise exception
        validate_url('http://example.com/article')
    
    def test_missing_hostname_rejected(self):
        """Test URLs without hostname are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            validate_url('http://')
        
        assert exc_info.value.status_code == 400
        assert 'hostname' in exc_info.value.detail.lower()


class TestSSRFAttackScenarios:
    """Test specific SSRF attack scenarios."""
    
    def test_aws_metadata_endpoint_blocked(self):
        """Test AWS EC2 metadata endpoint is blocked."""
        with pytest.raises(HTTPException) as exc_info:
            validate_url('http://169.254.169.254/latest/meta-data/')
        
        assert exc_info.value.status_code == 400
    
    def test_gcp_metadata_endpoint_blocked(self):
        """Test GCP metadata endpoint is blocked."""
        with pytest.raises(HTTPException) as exc_info:
            validate_url('http://metadata.google.internal/computeMetadata/v1/')
        
        # Will fail at DNS resolution if hostname resolves to private IP
        assert exc_info.value.status_code == 400
    
    @patch('services.web_scraping_service.resolve_hostname_to_ips')
    def test_dns_rebinding_localhost(self, mock_resolve):
        """Test DNS rebinding attack to localhost is blocked."""
        mock_resolve.return_value = ['127.0.0.1']
        
        with pytest.raises(HTTPException) as exc_info:
            validate_url('http://attacker-controlled-domain.com/ssrf')
        
        assert exc_info.value.status_code == 400
    
    @patch('services.web_scraping_service.resolve_hostname_to_ips')
    def test_dns_rebinding_internal_network(self, mock_resolve):
        """Test DNS rebinding attack to internal network is blocked."""
        mock_resolve.return_value = ['10.0.0.50']
        
        with pytest.raises(HTTPException) as exc_info:
            validate_url('http://attacker-controlled-domain.com/ssrf')
        
        assert exc_info.value.status_code == 400
