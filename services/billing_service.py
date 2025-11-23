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
import asyncio
from typing import Optional
from datetime import datetime, timezone
from fastapi import HTTPException
from config import Config
from supabase import Client
from services.logger import app_logger as logger
from services.db_services.supabase_quiz import invalidate_user_tier_cache

# Subscription status constants
STATUS_ACTIVE = "active"
STATUS_CANCELED = "canceled"
STATUS_PAST_DUE = "past_due"
STATUS_TRIALING = "trialing"
STATUS_INCOMPLETE = "incomplete"
STATUS_INCOMPLETE_EXPIRED = "incomplete_expired"
STATUS_UNPAID = "unpaid"


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
        
        # Validate Stripe API key is set
        if not self.config.STRIPE_SECRET_KEY:
            raise RuntimeError("STRIPE_SECRET_KEY environment variable is not set")
        
        stripe.api_key = self.config.STRIPE_SECRET_KEY
        logger.info(f"Stripe API initialized with key: {self.config.STRIPE_SECRET_KEY[:7]}...")
    
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
            logger.info(f"Getting or creating Stripe customer for user {user_id[:8]}")
            
            # 1. Check if user already has a customer ID
            response = self.supabase.table("profiles").select("stripe_customer_id").eq("id", user_id).execute()
            
            # Check if profile exists and has a customer ID
            if response.data and len(response.data) > 0 and response.data[0].get("stripe_customer_id"):
                customer_id = response.data[0]["stripe_customer_id"]
                logger.info(f"Found existing Stripe customer: {customer_id}")
                return customer_id
            
            logger.info(f"Creating new Stripe customer for email: {email}")
            
            # 2. Create new customer in Stripe
            customer = stripe.Customer.create(
                email=email,
                metadata={
                    "user_id": user_id,
                    "environment": "production" if not self.config.is_testing() else "test"
                }
            )
            
            logger.info(f"Stripe customer created: {customer.id}")
            
            # 3. Update user profile with customer ID
            self.supabase.table("profiles").update({
                "stripe_customer_id": customer.id
            }).eq("id", user_id).execute()
            
            logger.info(f"Updated profile with Stripe customer ID")
            
            return customer.id
            
        except stripe.StripeError as e:
            logger.error(f"Stripe error creating customer: {str(e)}")
            raise HTTPException(status_code=502, detail=f"Stripe error: {str(e)}")
        except Exception as e:
            logger.error(f"Error in get_or_create_customer: {str(e)}", exc_info=True)
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
        logger.info(f"Creating checkout session for user {user_id[:8]} - tier: {tier}")
        price_id = self.config.get_price_id_from_tier(tier)
        if not price_id:
            logger.error(f"Invalid tier '{tier}' or price ID not configured")
            raise HTTPException(status_code=400, detail=f"Invalid subscription tier: {tier}")
        
        logger.info(f"Using Stripe price ID: {price_id}")
            
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
                success_url=f"{self.config.STRIPE_SUCCESS_URL.rstrip('/')}?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=self.config.STRIPE_CANCEL_URL.rstrip('/'),
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
            
        except stripe.StripeError as e:
            logger.error(f"Stripe API error: {str(e)}")
            raise HTTPException(status_code=502, detail=f"Stripe error: {str(e)}")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error creating checkout session: {str(e)}", exc_info=True)
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
            
        Epic 4: Customer Portal session creation IMPLEMENTED
        """
        try:
            # 1. Get stripe_customer_id from profiles
            response = self.supabase.table("profiles").select("stripe_customer_id").eq("id", user_id).execute()
            
            if not response.data or len(response.data) == 0 or not response.data[0].get("stripe_customer_id"):
                logger.warning(f"User {user_id[:8]} has no Stripe customer ID")
                raise HTTPException(
                    status_code=404,
                    detail="No subscription found. Please subscribe first."
                )
            
            customer_id = response.data[0]["stripe_customer_id"]
            logger.info(f"Creating portal session for customer {customer_id}")
            
            # 2. Create portal session with return URL
            portal_session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=f"{self.config.FRONTEND_URL.rstrip('/')}/billing"
            )
            
            logger.info(f"Portal session created: {portal_session.id}")
            return portal_session.url
            
        except HTTPException:
            raise
        except stripe.StripeError as e:
            logger.error(f"Stripe error creating portal session: {e}")
            raise HTTPException(status_code=502, detail=f"Stripe error: {str(e)}")
        except Exception as e:
            logger.error(f"Error creating portal session: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to create portal session: {str(e)}")
    
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
            if self.config.is_testing() and price_id in ["basic", "pro"]:
                logger.warning(f"Using tier name '{price_id}' as price_id fallback. This should only happen in testing.")
                tier = price_id
            else:
                raise HTTPException(status_code=400, detail=f"Invalid price ID or tier: {price_id}")
        
        try:
            # 2. Prepare update data
            update_data = {
                "stripe_customer_id": customer_id,
                "stripe_subscription_id": subscription_id,
                "subscription_status": subscription_status,
                "account_tier": tier
            }
            
            # Update billing period for quota tracking (Migration 017)
            if current_period_start:
                update_data["current_period_start"] = datetime.fromtimestamp(current_period_start, tz=timezone.utc).isoformat()
            
            if current_period_end:
                update_data["current_period_end"] = datetime.fromtimestamp(current_period_end, tz=timezone.utc).isoformat()
            
            # 3. Update profiles table
            # We use the service role client (self.supabase) which bypasses RLS
            # This is safe because this method is called by trusted internal handlers
            response = self.supabase.table("profiles").update(update_data).eq("id", user_id).execute()
            
            if not response.data:
                logger.error(f"No profile found for user {user_id[:8]} during provisioning")
                raise HTTPException(status_code=404, detail="User profile not found")
            
            logger.info(f"Successfully provisioned subscription {subscription_id} for user {user_id[:8]}")
            
            # 4. Invalidate user tier cache after successful provisioning
            # This ensures the next API call fetches fresh data showing the upgraded tier
            try:
                # Run cache invalidation asynchronously
                asyncio.create_task(invalidate_user_tier_cache(user_id))
                logger.info(f"Invalidated tier cache for user {user_id[:8]} after provisioning")
            except Exception as cache_error:
                # Cache invalidation failure should not break provisioning
                logger.warning(f"Failed to invalidate cache for user {user_id[:8]}: {cache_error}")
            
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
            
        Epic 3: Subscription cancellation IMPLEMENTED
        """
        try:
            canceled_at = datetime.fromtimestamp(canceled_at_timestamp, tz=timezone.utc)
            
            # Update subscription status to canceled
            # Keep account_tier unchanged (grace period maintains access until period_end)
            self.supabase.table("profiles").update({
                "subscription_status": STATUS_CANCELED,
                "subscription_canceled_at": canceled_at.isoformat()
            }).eq("id", user_id).execute()
            
            logger.info(f"Subscription {subscription_id} canceled for user {user_id[:8]}")
            
            # Invalidate cache
            try:
                asyncio.create_task(invalidate_user_tier_cache(user_id))
            except Exception as cache_error:
                logger.warning(f"Failed to invalidate cache for user {user_id[:8]}: {cache_error}")
                
        except Exception as e:
            logger.error(f"Error canceling subscription: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to cancel subscription: {str(e)}")
    
    # ========================================================================
    # Webhook Event Handlers
    # ========================================================================
    
    async def handle_checkout_completed(self, session: dict) -> None:
        """
        Handle checkout.session.completed webhook event.
        
        Args:
            session: Stripe Checkout Session object
        """
        user_id = session.get("metadata", {}).get("user_id")
        if not user_id:
            logger.error(f"No user_id in checkout session {session.get('id')}")
            return
        
        # Get subscription details
        subscription_id = session.get("subscription")
        if not subscription_id:
            logger.warning(f"No subscription in checkout session {session.get('id')}")
            return
        
        # Fetch full subscription details
        subscription = stripe.Subscription.retrieve(subscription_id)
        
        # Extract price_id from subscription items
        items = subscription.get("items")
        if not items or not items.get("data"):
            logger.error(f"No items in subscription {subscription_id}")
            return
        
        first_item = items.get("data")[0]
        price_id = first_item.get("price", {}).get("id")
        
        logger.info(f"Checkout completed for user {user_id[:8]}, subscription {subscription_id}")
        
        # Provision subscription
        await self.provision_subscription(
            user_id=user_id,
            customer_id=session.get("customer"),
            subscription_id=subscription_id,
            subscription_status=subscription.get("status"),
            price_id=price_id,
            current_period_start=subscription.get("current_period_start"),
            current_period_end=subscription.get("current_period_end")
        )
    
    async def handle_subscription_created(self, subscription: dict) -> None:
        """
        Handle customer.subscription.created webhook event.
        
        Args:
            subscription: Stripe Subscription object
        """
        user_id = subscription.get("metadata", {}).get("user_id")
        if not user_id:
            logger.error(f"No user_id in subscription {subscription.get('id')}")
            return
        
        # Extract price_id from subscription items
        items = subscription.get("items")
        if not items or not items.get("data"):
            logger.error(f"No items in subscription {subscription.get('id')}")
            return
        
        first_item = items["data"][0]
        price_id = first_item.get("price", {}).get("id")
        
        logger.info(f"Subscription created: {subscription.get('id')} for user {user_id[:8]}")
        
        # Provision subscription
        await self.provision_subscription(
            user_id=user_id,
            customer_id=subscription.get("customer"),
            subscription_id=subscription.get("id"),
            subscription_status=subscription.get("status"),
            price_id=price_id,
            current_period_start=subscription.get("current_period_start"),
            current_period_end=subscription.get("current_period_end")
        )
    
    async def handle_subscription_updated(self, subscription: dict) -> None:
        """
        Handle customer.subscription.updated webhook event.
        
        This handles both status changes (active, canceled, past_due) and cancellations.
        When a subscription is canceled via the Customer Portal, Stripe sends this event
        with status="canceled" and canceled_at=<timestamp>.
        
        Args:
            subscription: Stripe Subscription object
        """
        user_id = subscription.get("metadata", {}).get("user_id")
        if not user_id:
            logger.warning(f"No user_id in subscription {subscription.get('id')}, skipping update")
            return
        
        # Extract price_id from subscription items
        items = subscription.get("items")
        if not items or not items.get("data"):
            logger.error(f"No items in subscription {subscription.get('id')}")
            return
        
        first_item = items["data"][0]
        price_id = first_item.get("price", {}).get("id")
        
        subscription_status = subscription.get("status")
        canceled_at = subscription.get("canceled_at")
        
        logger.info(f"Subscription updated: {subscription.get('id')} for user {user_id[:8]} - status: {subscription_status}, canceled_at: {canceled_at}")
        
        # Update subscription details
        await self.provision_subscription(
            user_id=user_id,
            customer_id=subscription.get("customer"),
            subscription_id=subscription.get("id"),
            subscription_status=subscription_status,
            price_id=price_id,
            current_period_start=subscription.get("current_period_start"),
            current_period_end=subscription.get("current_period_end")
        )
        
        # If subscription was canceled, update the canceled_at timestamp
        if canceled_at:
            try:
                canceled_at_datetime = datetime.fromtimestamp(canceled_at, tz=timezone.utc)
                self.supabase.table("profiles").update({
                    "subscription_canceled_at": canceled_at_datetime.isoformat()
                }).eq("id", user_id).execute()
                
                logger.info(f"Updated subscription_canceled_at for user {user_id[:8]} to {canceled_at_datetime.isoformat()}")
                
                # Invalidate cache again since we updated canceled_at
                try:
                    asyncio.create_task(invalidate_user_tier_cache(user_id))
                except Exception as cache_error:
                    logger.warning(f"Failed to invalidate cache after canceled_at update: {cache_error}")
                    
            except Exception as e:
                logger.error(f"Failed to update subscription_canceled_at for user {user_id[:8]}: {e}")
    
    async def handle_subscription_deleted(self, subscription: dict) -> None:
        """
        Handle customer.subscription.deleted webhook event.
        
        Args:
            subscription: Stripe Subscription object
        """
        user_id = subscription.get("metadata", {}).get("user_id")
        if not user_id:
            logger.warning(f"No user_id in subscription {subscription.get('id')}, skipping deletion")
            return
        
        canceled_at = subscription.get("canceled_at", int(datetime.now(timezone.utc).timestamp()))
        
        logger.info(f"Subscription deleted: {subscription.get('id')} for user {user_id[:8]}")
        
        await self.cancel_subscription(
            user_id=user_id,
            subscription_id=subscription.get("id"),
            canceled_at_timestamp=canceled_at
        )
    
    async def handle_invoice_paid(self, invoice: dict) -> None:
        """
        Handle invoice.paid webhook event.
        
        Args:
            invoice: Stripe Invoice object
        """
        subscription_id = invoice.get("subscription")
        if not subscription_id:
            logger.info(f"Invoice {invoice.get('id')} not associated with subscription")
            return
        
        # Fetch subscription to get metadata
        subscription = stripe.Subscription.retrieve(subscription_id)
        user_id = subscription.get("metadata", {}).get("user_id")
        
        if not user_id:
            logger.warning(f"No user_id in subscription {subscription_id}, skipping invoice handling")
            return
        
        logger.info(f"Invoice paid: {invoice.get('id')} for user {user_id[:8]}")
        
        # Update subscription status to active (in case it was past_due)
        items = subscription.get("items")
        if items and items.get("data"):
            first_item = items.get("data")[0]
            price_id = first_item.get("price", {}).get("id")
            
            await self.provision_subscription(
                user_id=user_id,
                customer_id=subscription.get("customer"),
                subscription_id=subscription_id,
                subscription_status=STATUS_ACTIVE,
                price_id=price_id,
                current_period_start=subscription.get("current_period_start"),
                current_period_end=subscription.get("current_period_end")
            )
    
    async def handle_invoice_payment_failed(self, invoice: dict) -> None:
        """
        Handle invoice.payment_failed webhook event.
        
        Args:
            invoice: Stripe Invoice object
        """
        subscription_id = invoice.get("subscription")
        if not subscription_id:
            logger.info(f"Invoice {invoice.get('id')} not associated with subscription")
            return
        
        # Fetch subscription to get metadata
        subscription = stripe.Subscription.retrieve(subscription_id)
        user_id = subscription.get("metadata", {}).get("user_id")
        
        if not user_id:
            logger.warning(f"No user_id in subscription {subscription_id}, skipping invoice handling")
            return
        
        logger.warning(f"Invoice payment failed: {invoice.get('id')} for user {user_id[:8]}")
        
        # Update subscription status to past_due
        try:
            self.supabase.table("profiles").update({
                "subscription_status": STATUS_PAST_DUE
            }).eq("id", user_id).execute()
            
            logger.info(f"Updated user {user_id[:8]} subscription status to past_due")
            
            # Invalidate cache
            try:
                asyncio.create_task(invalidate_user_tier_cache(user_id))
            except Exception as cache_error:
                logger.warning(f"Failed to invalidate cache: {cache_error}")
                
        except Exception as e:
            logger.error(f"Error updating subscription to past_due: {e}")
    
    # ========================================================================
    # Subscription Status Query
    # ========================================================================
    
    async def get_subscription_status(self, user_id: str) -> dict:
        """
        Get the user's current subscription and billing status.
        
        Args:
            user_id: Supabase user UUID
            
        Returns:
            dict with subscription status including:
                - account_tier: str (free, basic, pro)
                - subscription_status: Optional[str] (active, canceled, past_due, etc.)
                - stripe_customer_id: Optional[str]
                - stripe_subscription_id: Optional[str]
                - current_period_start: Optional[str] (ISO timestamp)
                - current_period_end: Optional[str] (ISO timestamp)
                - subscription_canceled_at: Optional[str] (ISO timestamp)
                - quota_limit: int
                - current_quiz_count: int
                - quota_exceeded: bool
                
        Epic 5: Subscription status query IMPLEMENTED
        """
        try:
            # Query user_tier_info view for comprehensive status
            response = self.supabase.table("user_tier_info").select("*").eq("id", user_id).execute()
            
            if not response.data:
                logger.warning(f"No tier info found for user {user_id[:8]}")
                raise HTTPException(status_code=404, detail="User not found")
            
            user_data = response.data[0]
            
            # Calculate billing status
            billing_status = self._calculate_billing_status(user_data)
            
            return {
                "account_tier": user_data.get("account_tier", "free"),
                "subscription_status": user_data.get("subscription_status"),
                "billing_status": billing_status,
                "stripe_customer_id": user_data.get("stripe_customer_id"),
                "stripe_subscription_id": user_data.get("stripe_subscription_id"),
                "current_period_start": user_data.get("current_period_start"),
                "current_period_end": user_data.get("current_period_end"),
                "subscription_canceled_at": user_data.get("subscription_canceled_at"),
                "quota_limit": user_data.get("quota_limit", 0),
                "current_quiz_count": user_data.get("current_quiz_count", 0),
                "quota_exceeded": user_data.get("quota_exceeded", False)
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting subscription status: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to get subscription status: {str(e)}")
    
    def _calculate_billing_status(self, user_data: dict) -> str:
        """
        Calculate billing status based on subscription data.
        
        Args:
            user_data: User data from user_tier_info view
            
        Returns:
            str: Billing status (no_subscription, active, grace_period, past_due, expired)
        """
        subscription_status = user_data.get("subscription_status")
        
        if not subscription_status:
            return "no_subscription"
        
        if subscription_status == STATUS_ACTIVE:
            return "active"
        
        if subscription_status == STATUS_CANCELED:
            # Check if still in grace period
            current_period_end = user_data.get("current_period_end")
            if current_period_end:
                try:
                    period_end = datetime.fromisoformat(current_period_end.replace("Z", "+00:00"))
                    if datetime.now(timezone.utc) < period_end:
                        return "grace_period"
                    else:
                        return "expired"
                except Exception:
                    return "expired"
            return "expired"
        
        if subscription_status == STATUS_PAST_DUE:
            return "past_due"
        
        return subscription_status
