"""
Billing service for Stripe subscription management.

This module handles all Stripe operations including:
- Customer creation and management
- Checkout session creation
- Customer portal session creation
- Subscription provisioning from webhooks
- Subscription cancellation and grace period handling

Epic 1: Infrastructure Setup - Skeleton methods with NotImplementedError
Epic 2-3: Full implementation with Stripe API integration
"""

from typing import Optional
from config import Config
from supabase import Client


class BillingService:
    """
    Service for managing Stripe billing operations.
    
    This service acts as the interface between the API layer and Stripe,
    handling customer management, subscription lifecycle, and webhook processing.
    """
    
    def __init__(self, supabase: Client):
        """
        Initialize the billing service.
        
        Args:
            supabase: Authenticated Supabase client (service role for webhook handling)
        """
        self.supabase = supabase
        self.config = Config()
    
    # ========================================================================
    # Customer Management
    # ========================================================================
    
    async def get_or_create_customer(self, user_id: str, email: str) -> str:
        """
        Get existing Stripe customer ID or create a new customer.
        
        This method checks if the user already has a Stripe customer ID in the database.
        If not, it creates a new Stripe customer and stores the ID.
        
        Args:
            user_id: Supabase user UUID
            email: User's email address
            
        Returns:
            str: Stripe customer ID (cus_XXXXXXXXX)
            
        Raises:
            HTTPException: If customer creation fails
            
        Epic 2: Implement Stripe customer creation logic
        """
        raise NotImplementedError(
            "Customer management will be implemented in Epic 2. "
            "This method will query the profiles table for stripe_customer_id, "
            "create a new Stripe customer if needed, and update the database."
        )
    
    # ========================================================================
    # Checkout Session
    # ========================================================================
    
    async def create_checkout_session(
        self, 
        user_id: str, 
        email: str, 
        tier: str
    ) -> dict:
        """
        Create a Stripe Checkout session for subscription purchase.
        
        This method creates a Stripe Checkout session that allows the user to
        enter payment information and complete the subscription purchase.
        
        Args:
            user_id: Supabase user UUID
            email: User's email address
            tier: Subscription tier ("basic" or "educator")
            
        Returns:
            dict: Checkout session data with keys:
                - checkout_url: URL to redirect user to Stripe Checkout
                - session_id: Stripe Checkout session ID (cs_XXXXXXXXX)
            
        Raises:
            HTTPException: If tier is invalid or checkout session creation fails
            
        Epic 2: Implement Stripe Checkout session creation
        """
        raise NotImplementedError(
            "Checkout session creation will be implemented in Epic 2. "
            "This method will: "
            "1. Validate tier and get price_id from config "
            "2. Get or create Stripe customer "
            "3. Create Stripe Checkout session with price_id, customer_id, and redirect URLs "
            "4. Return checkout URL and session ID"
        )
    
    # ========================================================================
    # Customer Portal
    # ========================================================================
    
    async def create_portal_session(self, user_id: str) -> str:
        """
        Create a Stripe Customer Portal session.
        
        The Customer Portal allows users to manage their subscription:
        - View invoices and payment history
        - Update payment method
        - Cancel subscription
        
        Args:
            user_id: Supabase user UUID
            
        Returns:
            str: Customer Portal URL to redirect user to
            
        Raises:
            HTTPException: If user has no Stripe customer ID or portal creation fails
            
        Epic 4: Implement Customer Portal session creation
        """
        raise NotImplementedError(
            "Customer Portal session creation will be implemented in Epic 4. "
            "This method will: "
            "1. Query profiles table for stripe_customer_id "
            "2. Raise 404 if user has no customer ID (never subscribed) "
            "3. Create Stripe Portal session with customer_id and return_url "
            "4. Return portal URL"
        )
    
    # ========================================================================
    # Webhook Processing - Subscription Provisioning
    # ========================================================================
    
    async def provision_subscription(
        self, 
        user_id: str, 
        customer_id: str,
        subscription_id: str,
        subscription_status: str,
        price_id: str
    ) -> None:
        """
        Provision or update a subscription in the database.
        
        This method is called by the webhook handler when a subscription is created
        or updated (e.g., customer.subscription.created, customer.subscription.updated).
        
        It updates the profiles table with the subscription details and upgrades the
        user's account_tier based on the price_id.
        
        Args:
            user_id: Supabase user UUID
            customer_id: Stripe customer ID (cus_XXXXXXXXX)
            subscription_id: Stripe subscription ID (sub_XXXXXXXXX)
            subscription_status: Stripe subscription status (active, trialing, past_due, etc.)
            price_id: Stripe price ID to determine tier
            
        Raises:
            HTTPException: If price_id is invalid or database update fails
            
        Epic 3: Implement subscription provisioning logic
        """
        raise NotImplementedError(
            "Subscription provisioning will be implemented in Epic 3. "
            "This method will: "
            "1. Map price_id to tier using config.get_tier_from_price_id() "
            "2. Update profiles table with stripe_customer_id, stripe_subscription_id, "
            "   subscription_status, and account_tier "
            "3. Log successful provisioning for monitoring"
        )
    
    async def handle_failed_payment(self, user_id: str, subscription_id: str) -> None:
        """
        Handle failed payment for a subscription.
        
        This method is called by the webhook handler when a payment fails
        (invoice.payment_failed). It updates the subscription status to 'past_due'.
        
        Args:
            user_id: Supabase user UUID
            subscription_id: Stripe subscription ID (sub_XXXXXXXXX)
            
        Epic 3: Implement failed payment handling
        """
        raise NotImplementedError(
            "Failed payment handling will be implemented in Epic 3. "
            "This method will: "
            "1. Update profiles table subscription_status to 'past_due' "
            "2. Log payment failure for monitoring "
            "3. Consider sending email notification to user (future enhancement)"
        )
    
    async def cancel_subscription(
        self, 
        user_id: str, 
        subscription_id: str,
        canceled_at_timestamp: int
    ) -> None:
        """
        Cancel a subscription (from webhook).
        
        This method is called by the webhook handler when a subscription is canceled
        (customer.subscription.deleted). It updates the database to reflect the cancellation
        and records the cancellation timestamp for grace period calculation.
        
        Args:
            user_id: Supabase user UUID
            subscription_id: Stripe subscription ID (sub_XXXXXXXXX)
            canceled_at_timestamp: Unix timestamp when subscription was canceled
            
        Epic 3: Implement subscription cancellation logic
        """
        raise NotImplementedError(
            "Subscription cancellation will be implemented in Epic 3. "
            "This method will: "
            "1. Update profiles table with subscription_status='canceled' "
            "2. Set subscription_canceled_at timestamp for grace period tracking "
            "3. Keep account_tier unchanged (grace period maintains access) "
            "4. Log cancellation for monitoring"
        )
