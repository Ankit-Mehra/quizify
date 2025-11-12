"""
Unit tests for device type detection from user agent strings.
"""
import pytest
from handlers.auth_handlers import detect_device_type


class TestDeviceDetection:
    """Test device type detection from user agents"""
    
    def test_mobile_devices(self):
        """Test mobile device detection"""
        mobile_agents = [
            "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)",
            "Mozilla/5.0 (iPad; CPU OS 14_0 like Mac OS X)",
            "Mozilla/5.0 (Linux; Android 10; SM-G973F)",
            "Mozilla/5.0 (Windows Phone 10.0; Android 6.0.1)",
        ]
        for agent in mobile_agents:
            assert detect_device_type(agent) == "mobile", f"Failed for: {agent}"
    
    def test_desktop_browsers(self):
        """Test desktop browser detection"""
        browser_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 Edg/91.0.864.59",
        ]
        for agent in browser_agents:
            assert detect_device_type(agent) == "browser", f"Failed for: {agent}"
    
    def test_api_clients(self):
        """Test API client detection"""
        api_agents = [
            "curl/7.68.0",
            "PostmanRuntime/7.28.4",
            "python-requests/2.25.1",
            "HTTPie/2.4.0",
        ]
        for agent in api_agents:
            assert detect_device_type(agent) == "api", f"Failed for: {agent}"
    
    def test_none_or_empty(self):
        """Test None or empty user agent"""
        assert detect_device_type(None) == "api"
        assert detect_device_type("") == "api"
    
    def test_unknown_user_agent(self):
        """Test unknown user agent defaults to api"""
        assert detect_device_type("UnknownBot/1.0") == "api"
