"""
Centralized configuration module for the Quizify application.

This module provides a single source of truth for environment variables,
testing mode detection, and Supabase client initialization.
"""

import os
from typing import Optional
from supabase import create_client, Client


class Config:
    """
    Application configuration class.
    
    Centralizes all environment variable access and provides
    utility methods for common configuration needs.
    """
    
    # Singleton Supabase client instance (cached to preserve PKCE state)
    _supabase_client: Optional[Client] = None
    
    # Supabase configuration
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
    STORAGE_NAME: str = os.getenv("SUPABASE_STORAGE_NAME", "")
    
    # Testing environment detection
    # IMPORTANT: This is the single source of truth for testing mode
    TESTING: bool = os.getenv("TESTING", "false").lower() == "true"
    
    # Development mode - returns tokens in response for API testing (Postman, etc)
    # In production, tokens are ONLY in HttpOnly cookies (more secure)
    DEVELOPMENT_MODE: bool = os.getenv("DEVELOPMENT_MODE", "false").lower() == "true"
    
    # Cookie domain for cross-subdomain authentication
    # Domain must start with '.' to work across subdomains (www, api, etc.)
    COOKIE_DOMAIN: str = os.getenv("COOKIE_DOMAIN", ".quizify.ca")
    
    # Frontend URL for redirects after email confirmation, password reset, etc.
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "https://www.quizify.ca")
    
    # OpenAI configuration
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    
    # Web scraping configuration
    SCRAPER_USER_AGENT: str = os.getenv(
        "SCRAPER_USER_AGENT",
        "Mozilla/5.0 (compatible; QuizifyBot/1.0; +https://quizify.app/bot)"
    )
    
    # LlamaIndex & RAG Configuration
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    EMBEDDING_DIMENSIONS: int = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "512"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "50"))
    
    # Quality Settings
    ENABLE_RAG_PIPELINE: bool = os.getenv("ENABLE_RAG_PIPELINE", "true").lower() == "true"
    ENABLE_CONCEPT_EXTRACTION: bool = os.getenv("ENABLE_CONCEPT_EXTRACTION", "true").lower() == "true"
    ENABLE_BLOOM_CLASSIFICATION: bool = os.getenv("ENABLE_BLOOM_CLASSIFICATION", "true").lower() == "true"
    ENABLE_FACT_CHECK: bool = os.getenv("ENABLE_FACT_CHECK", "true").lower() == "true"
    
    # Performance Limits
    MAX_CHUNKS_PER_DOCUMENT: int = int(os.getenv("MAX_CHUNKS_PER_DOCUMENT", "100"))
    MAX_CONCEPTS_PER_DOCUMENT: int = int(os.getenv("MAX_CONCEPTS_PER_DOCUMENT", "50"))
    EMBEDDING_BATCH_SIZE: int = int(os.getenv("EMBEDDING_BATCH_SIZE", "20"))
    
    # ============================================================================
    # Redis Configuration (for distributed state management)
    # ============================================================================
    
    # Main connection URL (provided by Railway Redis service)
    # Railway provides: REDIS_URL, REDISHOST, REDISPORT, REDIS_PASSWORD
    # We use REDIS_URL as it contains the complete connection string
    # Format: redis://default:PASSWORD@redis.railway.internal:6379
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL", "redis://localhost:6379")
    
    # Feature flag to enable/disable Redis
    REDIS_ENABLED: bool = os.getenv("REDIS_ENABLED", "true").lower() == "true"
    
    # Connection pool settings
    REDIS_MAX_CONNECTIONS: int = int(os.getenv("REDIS_MAX_CONNECTIONS", "20"))
    REDIS_SOCKET_TIMEOUT: int = int(os.getenv("REDIS_SOCKET_TIMEOUT", "5"))
    REDIS_SOCKET_CONNECT_TIMEOUT: int = int(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "5"))
    
    # Health check interval (seconds)
    REDIS_HEALTH_CHECK_INTERVAL: int = int(os.getenv("REDIS_HEALTH_CHECK_INTERVAL", "30"))
    
    # Cache TTL settings (seconds)
    REDIS_CACHE_TTL_USER_TIER: int = int(os.getenv("REDIS_CACHE_TTL_USER_TIER", "300"))  # 5 minutes
    REDIS_CACHE_TTL_QUIZ_METADATA: int = int(os.getenv("REDIS_CACHE_TTL_QUIZ_METADATA", "1800"))  # 30 minutes
    REDIS_CACHE_TTL_QUIZ_QUESTIONS: int = int(os.getenv("REDIS_CACHE_TTL_QUIZ_QUESTIONS", "3600"))  # 1 hour
    REDIS_CACHE_TTL_SUBMISSIONS: int = int(os.getenv("REDIS_CACHE_TTL_SUBMISSIONS", "600"))  # 10 minutes
    
    # Browser slot settings
    REDIS_BROWSER_SLOT_TTL: int = int(os.getenv("REDIS_BROWSER_SLOT_TTL", "300"))  # 5 minutes
    REDIS_LOCK_TTL: int = int(os.getenv("REDIS_LOCK_TTL", "30"))  # 30 seconds (distributed lock timeout)
    MAX_CONCURRENT_BROWSERS: int = int(os.getenv("MAX_CONCURRENT_BROWSERS", "3"))
    
    # Session settings
    REDIS_SESSION_TTL: int = int(os.getenv("REDIS_SESSION_TTL", "2592000"))  # 30 days (aligned with refresh token)
    MAX_SESSIONS_PER_USER: int = int(os.getenv("MAX_SESSIONS_PER_USER", "5"))  # Lowered for security
    
    # ============================================================================
    # Stripe Configuration (for subscription billing)
    # ============================================================================
    
    # Stripe API keys
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_PUBLISHABLE_KEY: str = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    
    # Stripe Price IDs for subscription plans
    # These are created in Stripe Dashboard and map to our tier system
    STRIPE_PRICE_ID_PREMIUM: str = os.getenv("STRIPE_PRICE_ID_PREMIUM", "")  # Legacy - kept for backward compatibility
    STRIPE_PRICE_ID_PRO: str = os.getenv("STRIPE_PRICE_ID_PRO", "")  # $20/mo - 40 credits (80 units)
    
    # Credit Pack Price IDs (one-time purchases)
    # These are created in Stripe Dashboard as one-time payment products
    # Pricing: $5 / $10 / $15 for 5 / 10 / 15 credits respectively
    STRIPE_PRICE_ID_CREDITS_5: str = os.getenv("STRIPE_PRICE_ID_CREDITS_5", "")   # $5  - 5 credits = 10 units
    STRIPE_PRICE_ID_CREDITS_10: str = os.getenv("STRIPE_PRICE_ID_CREDITS_10", "")  # $10 - 10 credits = 20 units
    STRIPE_PRICE_ID_CREDITS_15: str = os.getenv("STRIPE_PRICE_ID_CREDITS_15", "")  # $15 - 15 credits = 30 units
    
    # Frontend URLs for Stripe redirects
    STRIPE_SUCCESS_URL: str = os.getenv("STRIPE_SUCCESS_URL", f"{os.getenv('FRONTEND_URL', 'https://www.quizify.ca')}/billing/success")
    STRIPE_CANCEL_URL: str = os.getenv("STRIPE_CANCEL_URL", f"{os.getenv('FRONTEND_URL', 'https://www.quizify.ca')}/billing")
    
    # Stripe webhook endpoint (backend)
    STRIPE_WEBHOOK_ENDPOINT: str = os.getenv("STRIPE_WEBHOOK_ENDPOINT", "/api/billing/webhook")
    
    # Billing strict mode - when True, webhooks fail if Redis is unavailable (for multi-instance prod)
    # Set to "true" in production with multiple instances to prevent duplicate processing
    BILLING_REQUIRE_REDIS: bool = os.getenv("BILLING_REQUIRE_REDIS", "false").lower() == "true"
    
    # ============================================================================
    # Cron Job Configuration
    # ============================================================================
    
    # API key for authenticating cron job requests
    # Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
    CRON_API_KEY: str = os.getenv("CRON_API_KEY", "")
    
    # ============================================================================
    # Google OAuth Configuration (for Google Forms Export - Pro Tier Feature)
    # ============================================================================
    
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI: str = os.getenv(
        "GOOGLE_REDIRECT_URI",
        f"{os.getenv('BACKEND_URL', 'http://localhost:8000')}/api/auth/google/callback"
    )
    
    # Encryption key for Google OAuth refresh tokens (Fernet key)
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # CRITICAL: Set this in production! Tokens stored without encryption if not set.
    GOOGLE_TOKEN_ENCRYPTION_KEY: str = os.getenv("GOOGLE_TOKEN_ENCRYPTION_KEY", "")
    
    # ============================================================================
    # Resend Configuration (for contact form emails)
    # ============================================================================
    
    RESEND_API_KEY: str = os.getenv("RESEND_API_KEY", "")
    CONTACT_EMAIL: str = os.getenv("CONTACT_EMAIL", "admin@quizify.ca")
    
    # ============================================================================
    # PostHog Configuration (for LLM analytics and observability)
    # ============================================================================
    
    # PostHog API key (project API key from PostHog settings)
    POSTHOG_API_KEY: str = os.getenv("POSTHOG_API_KEY", "")
    
    # PostHog host (default to US cloud, can be EU cloud or self-hosted)
    POSTHOG_HOST: str = os.getenv("POSTHOG_HOST", "https://us.i.posthog.com")
    
    # Feature flag to enable/disable PostHog LLM analytics
    POSTHOG_LLM_ANALYTICS_ENABLED: bool = os.getenv("POSTHOG_LLM_ANALYTICS_ENABLED", "true").lower() == "true"
    
    @classmethod
    def is_testing(cls) -> bool:
        """
        Check if the application is running in testing mode.
        
        Returns:
            bool: True if TESTING environment variable is set to 'true', False otherwise
        """
        return cls.TESTING
    
    @classmethod
    def is_development(cls) -> bool:
        """
        Check if the application is running in development mode.
        
        In development mode, auth tokens are returned in response body
        for easier API testing with tools like Postman.
        
        Returns:
            bool: True if DEVELOPMENT_MODE environment variable is set to 'true', False otherwise
        """
        return cls.DEVELOPMENT_MODE
    
    @classmethod
    def get_supabase_client(cls) -> Client:
        """
        Get a cached Supabase client instance (singleton pattern).
        
        The client is cached to:
        1. Improve performance by reusing connection pools
        2. Reduce initialization overhead
        
        NOTE: Supabase's OAuth flows (PKCE) are stateless on the backend.
        The authorization code exchange happens server-side via Supabase's API,
        and CSRF protection is handled by our own state parameter + cookie mechanism,
        not by the Supabase client instance.
        
        In testing mode, returns None (tests will mock this).
        In production, fails fast if credentials are missing.
        
        Returns:
            Client: Supabase client instance (cached)
            
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
        
        # Return cached client if available
        if cls._supabase_client is not None:
            return cls._supabase_client
        
        # Create and cache the client
        cls._supabase_client = create_client(
            supabase_url=cls.SUPABASE_URL,
            supabase_key=cls.SUPABASE_KEY
        )
        
        return cls._supabase_client
    
    @classmethod
    def get_authenticated_supabase_client(cls, user_token: str) -> Client:
        """
        Get an authenticated Supabase client with a user token.
        
        This creates a client that uses the user's JWT token instead of the service role key,
        which ensures Row Level Security (RLS) policies are properly enforced.
        
        Args:
            user_token: JWT token for user authentication
            
        Returns:
            Client: Authenticated Supabase client with user token
            
        Raises:
            RuntimeError: If Supabase credentials are not configured
        """
        if not cls.SUPABASE_URL or not cls.SUPABASE_KEY:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_KEY must be set. "
                "Application cannot start without database configuration."
            )
        
        # Create a new client and set the user's access token
        # This makes all operations run under the user's auth context, enforcing RLS
        client = create_client(
            supabase_url=cls.SUPABASE_URL,
            supabase_key=cls.SUPABASE_KEY
        )
        
        # Set the auth token for PostgREST (database) operations
        # This ensures RLS policies see auth.uid() correctly
        client.postgrest.auth(user_token)
        
        # Note: For storage operations, use httpx directly with Authorization header
        # The storage SDK doesn't expose a simple way to set the user token globally
        
        return client
    
    @classmethod
    def validate_stripe_price_id(cls, price_id: str) -> bool:
        """
        Validate that a Stripe price ID matches expected format.
        
        Stripe price IDs start with 'price_' followed by 24 alphanumeric characters.
        
        Args:
            price_id: The Stripe price ID to validate
            
        Returns:
            bool: True if valid format, False otherwise
        """
        if not price_id:
            return False
        
        # Stripe price IDs: price_XXXXXXXXXXXXXXXXXXXX (price_ + 24 chars)
        return price_id.startswith("price_") and len(price_id) == 30
    
    @classmethod
    def get_tier_from_price_id(cls, price_id: str) -> Optional[str]:
        """
        Map a Stripe price ID to our internal tier name.
        
        Args:
            price_id: The Stripe price ID to map
            
        Returns:
            Optional[str]: The tier name ("premium", "pro") or None if not found
        """
        if price_id == cls.STRIPE_PRICE_ID_PREMIUM:
            return "premium"
        elif price_id == cls.STRIPE_PRICE_ID_PRO:
            return "pro"
        return None
    
    @classmethod
    def get_price_id_from_tier(cls, tier: str) -> Optional[str]:
        """
        Map an internal tier name to its Stripe price ID.
        
        Args:
            tier: The tier name ("premium", "pro")
            
        Returns:
            Optional[str]: The Stripe price ID or None if not found
        """
        tier_map = {
            "premium": cls.STRIPE_PRICE_ID_PREMIUM,
            "pro": cls.STRIPE_PRICE_ID_PRO,
        }
        return tier_map.get(tier.lower())
    
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
