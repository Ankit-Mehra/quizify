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

    # Supabase configuration
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    STORAGE_NAME: str = os.getenv("SUPABASE_STORAGE_NAME", "")

    # Testing environment detection
    # IMPORTANT: This is the single source of truth for testing mode
    TESTING: bool = os.getenv("TESTING", "false").lower() == "true"

    # Development mode - returns tokens in response for API testing (Postman, etc)
    # In production, tokens are ONLY in HttpOnly cookies (more secure)
    DEVELOPMENT_MODE: bool = os.getenv("DEVELOPMENT_MODE", "false").lower() == "true"
    
    # Cookie domain for cross-subdomain authentication
    # Set to ".quizify.ca" for production (works across www, api subdomains)
    # For staging/development, set to empty string "" or leave unset—both result in COOKIE_DOMAIN=None,
    # which causes cookies to be set without a domain attribute (current host only).
    # Domain must start with '.' to work across subdomains
    _cookie_domain_raw: str = os.getenv("COOKIE_DOMAIN", "")
    COOKIE_DOMAIN: str = _cookie_domain_raw if _cookie_domain_raw else None  # type: ignore
    
    # Frontend URL for redirects after email confirmation, password reset, etc.
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "https://www.quizify.ca")
    
    # Backend URL for OAuth callbacks (where Google/Supabase redirects after auth)
    BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")
    
    # Supabase JWT Secret for CSRF token signing in OAuth flows
    # In production, this MUST be set for secure OAuth state validation
    SUPABASE_JWT_SECRET: str = os.getenv("SUPABASE_JWT_SECRET", "")
    
    # OpenAI configuration
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    
    # Web scraping configuration
    SCRAPER_USER_AGENT: str = os.getenv(
        "SCRAPER_USER_AGENT",
        "Mozilla/5.0 (compatible; QuizifyBot/1.0; +https://quizify.app/bot)"
    )
    
    # ============================================================================
    # AI Model Configuration
    # ============================================================================
    # Centralized model selection - change models in ONE place
    # Primary model: Used for quiz generation (higher quality, slightly more expensive)
    # Mini model: Used for verification, explanation, concept extraction (cost-efficient)
    
    # Default LLM Provider - switch between providers via environment variable
    # Supported: "openai" (default), "gemini", "groq"
    DEFAULT_LLM_PROVIDER: str = os.getenv("DEFAULT_LLM_PROVIDER", "openai")
    
    # OpenAI Models (tiered: primary > mini > nano)
    OPENAI_MODEL_PRIMARY: str = os.getenv("OPENAI_MODEL_PRIMARY", "gpt-4.1")
    OPENAI_MODEL_MINI: str = os.getenv("OPENAI_MODEL_MINI", "gpt-4.1-mini")
    OPENAI_MODEL_NANO: str = os.getenv("OPENAI_MODEL_NANO", "gpt-4.1-nano")
    
    # Gemini Models (tiered: primary > mini > nano)
    GEMINI_MODEL_PRIMARY: str = os.getenv("GEMINI_MODEL_PRIMARY", "gemini-2.0-flash")
    GEMINI_MODEL_MINI: str = os.getenv("GEMINI_MODEL_MINI", "gemini-2.0-flash")
    GEMINI_MODEL_NANO: str = os.getenv("GEMINI_MODEL_NANO", "gemini-2.0-flash-lite")
    
    # Groq Models (tiered: primary > mini > nano)
    GROQ_MODEL_PRIMARY: str = os.getenv("GROQ_MODEL_PRIMARY", "llama-3.3-70b-versatile")
    GROQ_MODEL_MINI: str = os.getenv("GROQ_MODEL_MINI", "llama-3.1-8b-instant")
    GROQ_MODEL_NANO: str = os.getenv("GROQ_MODEL_NANO", "llama-3.1-8b-instant")
    
    # ============================================================================
    # Provider-Agnostic Model Getters (use these in services!)
    # ============================================================================
    # These return the correct model based on DEFAULT_LLM_PROVIDER
    
    @property
    def LLM_MODEL_PRIMARY(self) -> str:
        """Primary model for quiz generation (highest quality)."""
        provider = self.DEFAULT_LLM_PROVIDER
        if provider == "gemini":
            return self.GEMINI_MODEL_PRIMARY
        elif provider == "groq":
            return self.GROQ_MODEL_PRIMARY
        return self.OPENAI_MODEL_PRIMARY
    
    @property
    def LLM_MODEL_MINI(self) -> str:
        """Mini model for explanations, verification (balanced)."""
        provider = self.DEFAULT_LLM_PROVIDER
        if provider == "gemini":
            return self.GEMINI_MODEL_MINI
        elif provider == "groq":
            return self.GROQ_MODEL_MINI
        return self.OPENAI_MODEL_MINI
    
    @property
    def LLM_MODEL_NANO(self) -> str:
        """Nano model for concept extraction (fastest)."""
        provider = self.DEFAULT_LLM_PROVIDER
        if provider == "gemini":
            return self.GEMINI_MODEL_NANO
        elif provider == "groq":
            return self.GROQ_MODEL_NANO
        return self.OPENAI_MODEL_NANO
    
    # Legacy aliases (for backward compatibility)
    @property
    def GEMINI_MODEL_DEFAULT(self) -> str:
        return self.GEMINI_MODEL_PRIMARY
    
    @property
    def GROQ_MODEL_DEFAULT(self) -> str:
        return self.GROQ_MODEL_PRIMARY
    
    # ============================================================================
    # OpenAI-Only Model Getters (for services that MUST use OpenAI)
    # ============================================================================
    # These are used by services that require OpenAI specifically:
    # - Embedding-based services (RAG, concept extraction) - OpenAI embeddings only
    # - Enhanced quiz mode - uses OpenAI client for all operations
    # - Flashcard generation - uses OpenAI client
    # NOTE: Groq/Gemini don't support embeddings, so these services must use OpenAI
    
    @property
    def OPENAI_MODEL_FOR_RAG(self) -> str:
        """Model for RAG/embedding-based operations (always uses OpenAI)."""
        return self.OPENAI_MODEL_NANO
    
    @property  
    def OPENAI_MODEL_FOR_CONCEPTS(self) -> str:
        """Model for concept extraction (always uses OpenAI)."""
        return self.OPENAI_MODEL_NANO
    
    @property
    def OPENAI_MODEL_FOR_FLASHCARDS(self) -> str:
        """Model for flashcard generation (always uses OpenAI)."""
        return self.OPENAI_MODEL_MINI
    
    # LlamaIndex & RAG Configuration
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    EMBEDDING_DIMENSIONS: int = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "512"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "50"))
    
    # ============================================================================
    # Flashcard Generation Configuration
    # ============================================================================
    # These settings control flashcard generation behavior
    
    # Card count calculation: ~1 card per N words of source content
    FLASHCARD_CARDS_PER_100_WORDS: int = int(os.getenv("FLASHCARD_CARDS_PER_100_WORDS", "1"))
    
    # Minimum cards to generate per request (ensures enough study material)
    FLASHCARD_MIN_CARDS: int = int(os.getenv("FLASHCARD_MIN_CARDS", "3"))
    
    # Maximum cards per single LLM request (prevents context overflow)
    FLASHCARD_MAX_CARDS_PER_REQUEST: int = int(os.getenv("FLASHCARD_MAX_CARDS_PER_REQUEST", "50"))
    
    # Maximum tokens to send to LLM in single request
    FLASHCARD_MAX_CONTENT_TOKENS: int = int(os.getenv("FLASHCARD_MAX_CONTENT_TOKENS", "6000"))
    
    # Word count threshold for switching to chunked generation
    FLASHCARD_CHUNK_THRESHOLD_WORDS: int = int(os.getenv("FLASHCARD_CHUNK_THRESHOLD_WORDS", "3000"))
    
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
    def get_service_role_client(cls) -> Client:
        """
        Get a Supabase client with Service Role (Admin) privileges.
        
        WARNING: This client bypasses Row Level Security (RLS).
        Use ONLY for:
        - Stripe/external webhooks (no user context)
        - Cron jobs (system tasks)
        - Accessing auth.users data (e.g., user_tier_info view)
        - Billing operations (credit consumption, subscription management)
        
        Returns:
            Client: Supabase client with admin privileges
            
        Raises:
            RuntimeError: If SUPABASE_SERVICE_ROLE_KEY is not configured
        """
        if cls.is_testing():
            return None  # type: ignore
        
        if not cls.SUPABASE_URL or not cls.SUPABASE_SERVICE_ROLE_KEY:
            raise RuntimeError(
                "SUPABASE_SERVICE_ROLE_KEY is required for admin operations. "
                "Set it in your environment variables."
            )
        
        # Debug: Log which key type is being used (safe - only shows prefix)
        key_prefix = cls.SUPABASE_SERVICE_ROLE_KEY[:20] if cls.SUPABASE_SERVICE_ROLE_KEY else "EMPTY"
        import logging
        logging.getLogger("app").debug("Creating service role client with key prefix: %s...", key_prefix)
            
        return create_client(cls.SUPABASE_URL, cls.SUPABASE_SERVICE_ROLE_KEY)

    @classmethod
    def get_supabase_client(cls) -> Client:
        """
        Get a Supabase client instance (service role).
        
        DEPRECATED: Use get_service_role_client() for admin tasks
        or get_authenticated_supabase_client() for user operations.
        
        Kept for backward compatibility - aliases to get_service_role_client().
        """
        return cls.get_service_role_client()
    
    @classmethod
    def get_authenticated_supabase_client(cls, user_token: str) -> Client:
        """
        Get an authenticated Supabase client with a user token.
        
        This creates a client that uses the user's JWT token with the anon key,
        ensuring Row Level Security (RLS) policies are properly enforced.
        
        Use this for ALL user-initiated operations:
        - Creating/reading/updating quizzes
        - File uploads/downloads
        - User profile operations
        - Share link management
        
        Args:
            user_token: JWT access token for user authentication
            
        Returns:
            Client: Authenticated Supabase client with RLS enforcement
            
        Raises:
            RuntimeError: If Supabase credentials are not configured
        """
        if cls.is_testing():
            return None  # type: ignore
            
        if not cls.SUPABASE_URL or not cls.SUPABASE_KEY:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_KEY (anon key) must be set."
            )
        
        # Create client with anon key (respects RLS)
        client = create_client(
            supabase_url=cls.SUPABASE_URL,
            supabase_key=cls.SUPABASE_KEY  # This is the anon key
        )
        
        # Set the user's JWT for PostgREST operations
        # This makes auth.uid() return the user's ID in RLS policies
        client.postgrest.auth(user_token)
        
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
