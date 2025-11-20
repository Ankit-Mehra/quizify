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

import stripe
from typing import Optional
from fastapi import HTTPException
from config import Config
from supabase import Client
from services.logger import app_logger as logger


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
        stripe.api_key = self.config.STRIPE_SECRET_KEY
    
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
        """
        try:
            # 1. Check if user already has a customer ID
            response = self.supabase.table("profiles").select("stripe_customer_id").eq("id", user_id).single().execute()
            
            if response.data and response.data.get("stripe_customer_id"):
                return response.data["stripe_customer_id"]
            
            # 2. Create new customer in Stripe
            customer = stripe.Customer.create(
                email=email,
                metadata={
                    "user_id": user_id,
                    "environment": "production" if not self.config.is_testing() else "test"
                }
            )
            
            # 3. Update user profile with customer ID
            self.supabase.table("profiles").update({
                "stripe_customer_id": customer.id
            }).eq("id", user_id).execute()
            
            return customer.id
            
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=502, detail=f"Stripe error: {str(e)}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create customer: {str(e)}")
    
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
            tier: Subscription tier ("basic" or "pro")
            
        Returns:
            dict: Checkout session data with keys:
                - checkout_url: URL to redirect user to Stripe Checkout
                - session_id: Stripe Checkout session ID (cs_XXXXXXXXX)
            
        Raises:
            HTTPException: If tier is invalid or checkout session creation fails
        """
        # 1. Validate tier and get price ID
        price_id = self.config.get_price_id_from_tier(tier)
        if not price_id:
            raise HTTPException(status_code=400, detail=f"Invalid subscription tier: {tier}")
            
        try:
            # 2. Get or create customer
            customer_id = await self.get_or_create_customer(user_id, email)
            
            # 3. Create Checkout Session
            session = stripe.checkout.Session.create(
                customer=customer_id,
                payment_method_types=["card"],
                line_items=[{
                    "price": price_id,
                    "quantity": 1,
                }],
                mode="subscription",
                success_url=self.config.STRIPE_SUCCESS_URL + "?session_id={CHECKOUT_SESSION_ID}",
                cancel_url=self.config.STRIPE_CANCEL_URL,
                metadata={
                    "user_id": user_id,
                    "tier": tier
                },
                subscription_data={
                    "metadata": {
                        "user_id": user_id,
                        "tier": tier
                    }
                },
                allow_promotion_codes=True
            )
            
            return {
                "checkout_url": session.url,
                "session_id": session.id
            }
            
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=502, detail=f"Stripe error: {str(e)}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create checkout session: {str(e)}")
    
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
        price_id: str,
        current_period_start: Optional[int] = None,
        current_period_end: Optional[int] = None
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
            current_period_start: Unix timestamp for start of billing period
            current_period_end: Unix timestamp for end of billing period
            
        Raises:
            HTTPException: If price_id is invalid or database update fails
        """
        # 1. Map price_id to tier
        tier = self.config.get_tier_from_price_id(price_id)
        if not tier:
            # Fallback: if price_id is not in config, check if it's a known tier name passed directly
            # This handles cases where we might pass "pro" directly instead of price_id
            # WARNING: This is primarily for testing/legacy support. In production, strict price IDs should be used.
            if self.config.is_testing() and price_id in ["basic", "pro", "educator"]:
                logger.warning(f"Using tier name '{price_id}' as price_id fallback. This should only happen in testing.")
                tier = price_id
            else:
                raise HTTPException(status_code=400, detail=f"Invalid price ID or tier: {price_id}")
        
        try:
            # 2. Prepare update data
            from datetime import datetime, timezone
            
            update_data = {
                "stripe_customer_id": customer_id,
                "stripe_subscription_id": subscription_id,
                "subscription_status": subscription_status,
                "account_tier": tier
            }
            
            if current_period_end:
                update_data["subscription_current_period_end"] = datetime.fromtimestamp(current_period_end, tz=timezone.utc).isoformat()
            
            # 3. Update profiles table
            # We use the service role client (self.supabase) which bypasses RLS
            # This is safe because this method is called by trusted internal handlers
            self.supabase.table("profiles").update(update_data).eq("id", user_id).execute()
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to provision subscription: {str(e)}")
    
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
