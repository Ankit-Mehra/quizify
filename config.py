"""
Centralized configuration module for the Quizify application.

This module provides a single source of truth for environment variables,
testing mode detection, and Supabase client initialization.
"""

import os
from supabase import create_client, Client


class Config:
    """
    Application configuration class.
    
    Centralizes all environment variable access and provides
    utility methods for common configuration needs.
    """
    
    # Supabase configuration
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
    STORAGE_NAME: str = os.getenv("SUPABASE_STORAGE_NAME", "")
    
    # Testing environment detection
    # IMPORTANT: This is the single source of truth for testing mode
    TESTING: bool = os.getenv("TESTING", "false").lower() == "true"
    
    # OpenAI configuration
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    
    @classmethod
    def is_testing(cls) -> bool:
        """
        Check if the application is running in testing mode.
        
        Returns:
            bool: True if TESTING environment variable is set to 'true', False otherwise
        """
        return cls.TESTING
    
    @classmethod
    def get_supabase_client(cls) -> Client:
        """
        Get a Supabase client instance.
        
        In testing mode, returns None (tests will mock this).
        In production, fails fast if credentials are missing.
        
        Returns:
            Client: Supabase client instance
            
        Raises:
            RuntimeError: If Supabase credentials are not configured (non-testing mode)
        """
        if cls.is_testing():
            return None  # type: ignore - Tests will mock database functions
        
        if not cls.SUPABASE_URL or not cls.SUPABASE_KEY:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_KEY must be set. "
                "Application cannot start without database configuration."
            )
        
        return create_client(
            supabase_url=cls.SUPABASE_URL,
            supabase_key=cls.SUPABASE_KEY
        )
    
    @classmethod
    def get_authenticated_supabase_client(cls, user_token: str) -> Client:
        """
        Get an authenticated Supabase client with a user token.
        
        Args:
            user_token: JWT token for user authentication
            
        Returns:
            Client: Authenticated Supabase client
            
        Raises:
            RuntimeError: If Supabase credentials are not configured
        """
        if not cls.SUPABASE_URL or not cls.SUPABASE_KEY:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_KEY must be set. "
                "Application cannot start without database configuration."
            )
        
        client = create_client(cls.SUPABASE_URL, cls.SUPABASE_KEY)
        client.auth.session = {'access_token': user_token}  # type: ignore
        return client
    
    @classmethod
    def validate_config(cls) -> None:
        """
        Validate that all required configuration is present.
        
        Should be called at application startup (not in testing mode).
        
        Raises:
            RuntimeError: If required configuration is missing
        """
        if cls.is_testing():
            return  # Skip validation in testing mode
            
        required = {
            "SUPABASE_URL": cls.SUPABASE_URL,
            "SUPABASE_KEY": cls.SUPABASE_KEY,
        }
        
        missing = [key for key, value in required.items() if not value]
        
        if missing:
            raise RuntimeError(
                f"Missing required environment variables: {', '.join(missing)}. "
                f"Application cannot start without proper configuration."
            )


# Singleton instance for convenient access
config = Config()
