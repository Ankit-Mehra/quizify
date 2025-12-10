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
from hashlib import sha256
from typing import Optional
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from config import Config
from supabase import Client
from services.logger import app_logger as logger
from services.db_services.supabase_quiz import invalidate_user_tier_cache
from services.db_services.supabase_quiz import get_authed_supabase_client
from schemas.billing import UserBillingState

# Subscription status constants
STATUS_ACTIVE = "active"
STATUS_CANCELED = "canceled"
STATUS_PAST_DUE = "past_due"
STATUS_TRIALING = "trialing"
STATUS_INCOMPLETE = "incomplete"
STATUS_INCOMPLETE_EXPIRED = "incomplete_expired"
STATUS_UNPAID = "unpaid"

# Checkout session retry configuration
# Stripe caches idempotent responses for 24 hours, but checkout sessions become
# invalid after completion. We try multiple idempotency keys to find a valid session.
# 5 attempts balances retry coverage with API performance and covers typical cache edge cases
MAX_CHECKOUT_SESSION_ATTEMPTS = 5

# Tier hierarchy for upgrade/downgrade detection
# Higher number = higher tier. Used to determine if plan change is upgrade or downgrade.
# Note: 'premium' is legacy (kept for backward compatibility), treated same as 'pro'
TIER_ORDER = {"free": 0, "premium": 2, "pro": 2}

# Credit unit constants (Epic 2.1)
STANDARD_UNITS = 1   # Standard quiz = 1 unit
ENHANCED_UNITS = 2   # Enhanced quiz = 2 units

FREE_MONTHLY_UNITS = 6     # 3 credits = 6 units
PRO_MONTHLY_UNITS = 60     # 30 credits = 60 units

# Credit pack configuration
# Pack sizes are by CREDITS (not price). Price is set in Stripe.
# Mapping: pack_size (credits) -> units (1 credit = 2 units)
CREDIT_PACK_UNITS = {
    "5": 10,    # $5  - 5 credits = 10 units (5 standard or 2-3 enhanced quizzes)
    "10": 20,   # $10 - 10 credits = 20 units (10 standard or 5 enhanced quizzes)
    "15": 30,   # $15 - 15 credits = 30 units (15 standard or 7-8 enhanced quizzes)
}

# Conversion for display (1 credit = 2 units)
def units_to_credits(units: int) -> float:
    return units / 2.0

def credits_to_units(credits: float) -> int:
    return int(credits * 2)

def quiz_unit_cost(quiz_type: str) -> int:
    """
    Get the unit cost for a quiz type.
    
    Args:
        quiz_type: "standard" or "enhanced"
        
    Returns:
        Number of units required (1 for standard, 2 for enhanced)
        
    Raises:
        ValueError: If unknown quiz_type
    """
    if quiz_type == "standard":
        return STANDARD_UNITS
    elif quiz_type == "enhanced":
        return ENHANCED_UNITS
    raise ValueError(f"Unknown quiz_type: {quiz_type}")


async def get_billing_state(user_id: str) -> UserBillingState:
    """Fetch user's current billing state from profiles table."""
    # Use service role client to ensure we can read billing data
    from services.db_services.supabase_quiz import get_supabase
    supabase = get_supabase()
    
    response = supabase.table("profiles").select("*").eq("id", user_id).single().execute()
    
    if not response.data:
        # Should not happen if profile exists, but handle gracefully
        raise HTTPException(status_code=404, detail="User profile not found")
        
    data = response.data
    
    # Handle potential nulls if backfill hasn't run or race condition
    plan = data.get("billing_plan") or "free"
    # Map legacy tiers if needed (though we did backfill)
    if plan not in ["free", "pro"]:
        plan = "pro" if data.get("account_tier") in ["basic", "premium", "pro"] else "free"
        
    free_monthly = data.get("free_credit_units_monthly", FREE_MONTHLY_UNITS)
    free_remaining = data.get("free_credit_units_remaining")
    # If new free bucket is missing (older rows), derive it from total remaining
    if free_remaining is None:
        total_remaining = data.get("credit_units_remaining", FREE_MONTHLY_UNITS)
        free_remaining = min(total_remaining, free_monthly)
    
    subscription_remaining = data.get("credit_units_remaining", 0)
    
    return UserBillingState(
        user_id=user_id,
        plan=plan,
        credit_units_monthly=data.get("credit_units_monthly", 6),
        credit_units_remaining=subscription_remaining,
        credit_units_purchased=data.get("credit_units_purchased", 0),
        free_credit_units_monthly=free_monthly,
        free_credit_units_remaining=free_remaining,
        period_start=data.get("current_period_start"),
        period_end=data.get("current_period_end")
    )


async def consume_units(user_id: str, quiz_type: str) -> bool:
    """
    Attempt to consume units for quiz generation.
    
    Priority order: purchased → free → subscription
    (Use purchased first, then free allowance, preserve subscription credits longest)
    
    Uses atomic SQL to prevent race conditions on concurrent quiz starts.
    Returns True if successful, False if insufficient units.
    """
    needed = quiz_unit_cost(quiz_type)
    
    from services.db_services.supabase_quiz import get_supabase
    supabase = get_supabase()
    
    # Use atomic RPC to debit units safely
    # This prevents double-spending under concurrent load
    try:
        result = supabase.rpc("consume_credit_units", {
            "p_user_id": user_id,
            "p_units_needed": needed
        }).execute()
        
        # PostgREST scalar function returns: {"data": true/false}
        # supabase-py parses to: result.data = True/False (Python bool)
        # 
        # IMPORTANT: For scalar RPC functions, result.data is the direct value,
        # NOT wrapped in a list. This is different from table-returning functions.
        data = result.data
        
        # Debug logging to catch unexpected formats in production
        logger.debug(f"consume_credit_units RPC returned: type={type(data).__name__}, value={data!r}")
        
        # Direct boolean check (most common case for scalar BOOLEAN RPC)
        if data is True or data is False:
            return data
        
        # Fallback: Handle potential edge cases from different Supabase versions
        # Some versions might wrap scalar in a list
        if isinstance(data, list):
            if len(data) == 1:
                return bool(data[0])
            elif len(data) == 0:
                logger.warning(f"consume_credit_units returned empty list for user {user_id[:8]}")
                return False
        
        # String fallback (shouldn't happen but defensive)
        if isinstance(data, str):
            return data.lower() in ("true", "1", "t", "yes")
        
        # Integer fallback
        if isinstance(data, int):
            return data > 0
        
        # Last resort: log and coerce to bool
        logger.warning(f"Unexpected RPC return format for consume_credit_units: type={type(data).__name__}, value={data!r}")
        return bool(data)
        
    except Exception as e:
        logger.error(f"Failed to consume units for user {user_id[:8]}: {e}")
        return False


async def add_purchased_units(user_id: str, units: int) -> bool:
    """
    Add purchased units to user's credit balance.
    
    Called when a credit pack purchase is completed via Stripe webhook.
    Uses atomic SQL increment to prevent race conditions.
    
    Args:
        user_id: User ID
        units: Number of units to add (e.g., 20, 60, 200 for 10/30/100 credit packs)
        
    Returns:
        True if successful
    """
    from services.db_services.supabase_quiz import get_supabase
    supabase = get_supabase()
    
    # Use atomic RPC to add units safely (prevents race conditions)
    try:
        supabase.rpc("add_purchased_credit_units", {
            "p_user_id": user_id,
            "p_units": units
        }).execute()
        
        logger.info(f"Added {units} units ({units/2} credits) to user {user_id[:8]}")
        return True
    except Exception as e:
        logger.error(f"Failed to add purchased units for user {user_id[:8]}: {e}")
        return False


async def reset_monthly_credits_for_user(user_id: str) -> bool:
    """
    Reset monthly free credits for a single user.
    
    Called by:
    1. Monthly cron job (free allowance)
    2. Fallback handler if we need to manually top-up free allowance
    
    Args:
        user_id: User ID
        
    Returns:
        True if successful
    """
    from services.db_services.supabase_quiz import get_supabase
    from datetime import datetime, timezone
    from dateutil.relativedelta import relativedelta
    
    supabase = get_supabase()
    state = await get_billing_state(user_id)
    
    now = datetime.now(timezone.utc)
    # Use calendar month boundaries for consistency
    period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    period_end = period_start + relativedelta(months=1)
    
    # Reset only the free bucket; paid/subscription handled separately (Stripe)
    supabase.table("profiles").update({
        "free_credit_units_remaining": state.free_credit_units_monthly,
        "current_period_start": period_start.isoformat(),
        "current_period_end": period_end.isoformat()
    }).eq("id", user_id).execute()
    
    logger.info(f"Reset monthly free credits for user {user_id[:8]} to {state.free_credit_units_monthly} units")
    return True


async def reset_expired_monthly_credits() -> dict:
    """
    Reset monthly free credits for all users whose period has expired.
    
    Called by cron job endpoint. Paid/subscription credits are handled separately
    via Stripe webhooks; this only touches the free allowance bucket.
    
    Returns:
        Dict with reset_count and any errors
    """
    from services.db_services.supabase_quiz import get_supabase
    from datetime import datetime, timezone
    from dateutil.relativedelta import relativedelta
    
    supabase = get_supabase()
    now = datetime.now(timezone.utc)
    
    # Use calendar month boundaries for consistency with Stripe billing cycles
    # Period starts at beginning of current month, ends at beginning of next month
    period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    period_end = period_start + relativedelta(months=1)
    
    # Find FREE users only with expired periods (include rows with null period_end)
    # Pro users have their periods managed by Stripe webhooks - we must not touch them
    # to avoid desyncing from Stripe billing cycles
    response = supabase.table("profiles").select(
        "id, billing_plan, free_credit_units_monthly, current_period_end, subscription_status"
    ).or_(f"current_period_end.is.null,current_period_end.lt.{now.isoformat()}").execute()
    
    # Filter to only process free users (no active subscription)
    # Pro users with active/trialing subscriptions are handled by Stripe webhooks
    free_profiles = [
        p for p in (response.data or [])
        if p.get("billing_plan") != "pro" or p.get("subscription_status") not in ["active", "trialing"]
    ]
    
    reset_count = 0
    errors = []
    skipped_pro = len(response.data or []) - len(free_profiles)
    if skipped_pro > 0:
        logger.info(f"Skipping {skipped_pro} Pro users with active subscriptions (managed by Stripe)")
    
    for profile in free_profiles:
        try:
            user_id = profile["id"]
            monthly_units = profile.get("free_credit_units_monthly", FREE_MONTHLY_UNITS)
            
            # Update credits and period using calendar month boundaries
            supabase.table("profiles").update({
                "free_credit_units_remaining": monthly_units,
                "current_period_start": period_start.isoformat(),
                "current_period_end": period_end.isoformat()
            }).eq("id", user_id).execute()
            
            reset_count += 1
            
        except Exception as e:
            errors.append({"user_id": profile.get("id", "unknown")[:8], "error": str(e)})
            logger.error(f"Failed to reset credits for user {profile.get('id', 'unknown')[:8]}: {e}")
    
    logger.info(f"Monthly credit reset complete: {reset_count} users reset, {len(errors)} errors")
    
    return {
        "reset_count": reset_count,
        "error_count": len(errors),
        "errors": errors[:10]  # Return first 10 errors for debugging
    }


def _short_stripe_id(stripe_id: str, max_len: int = 12) -> str:
    """
    Truncate Stripe IDs for logging to reduce verbosity.
    
    Stripe IDs are prefixed (e.g., sub_, cus_, cs_) followed by a long random string.
    This keeps the prefix and first few characters for debugging while reducing log noise.
    
    Args:
        stripe_id: Full Stripe ID (e.g., sub_1aBcDeFgHiJkLmNoP)
        max_len: Maximum length of truncated ID
        
    Returns:
        Truncated ID (e.g., sub_1aBcDe...)
    """
    if not stripe_id:
        return "N/A"
    if len(stripe_id) <= max_len:
        return stripe_id
    return f"{stripe_id[:max_len]}..."


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
        logger.info("Stripe API initialized successfully")
    
    # ========================================================================
    # Helper Methods
    # ========================================================================
    
    @staticmethod
    def _get_attr(obj, key, default=None):
        """
        Unified accessor for both dict and Stripe API objects.
        
        Stripe objects from API calls (e.g., stripe.Subscription.retrieve()) use
        attribute access (obj.key), while webhook event data comes as dicts (obj["key"]).
        This helper handles both cases transparently.
        
        Args:
            obj: Dict or Stripe API object
            key: Attribute/key name to access
            default: Default value if not found
            
        Returns:
            The value or default
        """
        if obj is None:
            return default
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)
    
    def _extract_price_id_from_subscription(self, subscription, context: str = "") -> Optional[str]:
        """
        Extract price_id from Stripe subscription items.
        
        This helper eliminates duplicated price_id extraction logic across webhook handlers
        and verification endpoints.
        
        Handles both dict (from webhook events) and Stripe API objects (from API calls)
        using a unified access pattern. Avoids deprecated methods like to_dict().
        
        Args:
            subscription: Stripe Subscription object (dict or Stripe API object)
            context: Context for logging (e.g., "invoice inv_xxx", "subscription sub_xxx")
            
        Returns:
            str: Price ID if found, None otherwise
        """
        # Use unified accessor for both dict and Stripe objects
        _get = self._get_attr
        
        items = _get(subscription, "items")
        if not items:
            logger.error(f"No items in subscription{' for ' + context if context else ''}")
            return None
        
        data = _get(items, "data")
        if not data or not isinstance(data, list) or len(data) == 0:
            logger.error(f"Subscription items data missing or empty{' for ' + context if context else ''}")
            return None
        
        first_item = data[0]
        price = _get(first_item, "price")
        price_id = _get(price, "id")
        
        if not price_id:
            logger.error(f"No price_id found in subscription item{' for ' + context if context else ''}")
            return None
        
        return price_id
    
    def _extract_period_dates_from_subscription(self, subscription, context: str = "") -> tuple[Optional[int], Optional[int]]:
        """
        Extract current_period_start and current_period_end from Stripe subscription.
        
        IMPORTANT: Per Stripe API documentation, the billing period dates are stored on
        subscription ITEMS (items.data[].current_period_start/end), NOT on the subscription
        object itself. This is a common source of confusion.
        
        Args:
            subscription: Stripe Subscription object (dict or Stripe API object)
            context: Context for logging
            
        Returns:
            tuple: (current_period_start, current_period_end) as Unix timestamps, or (None, None)
        """
        _get = self._get_attr
        
        items = _get(subscription, "items")
        if not items:
            logger.error(f"No items in subscription{' for ' + context if context else ''}, cannot extract period dates")
            return None, None
        
        data = _get(items, "data")
        if not data or not isinstance(data, list) or len(data) == 0:
            logger.error(f"Subscription items data missing or empty{' for ' + context if context else ''}")
            return None, None
        
        # Get period dates from the first subscription item
        first_item = data[0]
        current_period_start = _get(first_item, "current_period_start")
        current_period_end = _get(first_item, "current_period_end")
        
        return current_period_start, current_period_end
    
    async def _validate_webhook_user_authorization(
        self, 
        user_id: str, 
        customer_id: str, 
        context: str = ""
    ) -> bool:
        """
        Validate that a user_id from webhook metadata matches the database mapping.
        
        This is a critical security check to prevent spoofed metadata attacks.
        Even though Stripe signature verification ensures the webhook is legitimate,
        the metadata could be set incorrectly or maliciously by API misuse.
        
        Args:
            user_id: User ID from Stripe metadata
            customer_id: Stripe customer ID from the webhook event
            context: Context for logging (e.g., "checkout session cs_xxx")
            
        Returns:
            bool: True if validation passes, False otherwise
        """
        if not user_id or not customer_id:
            logger.error(f"Missing user_id or customer_id for validation{' in ' + context if context else ''}")
            return False
        
        try:
            # Query database for the user's stripe_customer_id
            response = self.supabase.table("profiles").select("stripe_customer_id").eq("id", user_id).execute()
            
            if not response.data or len(response.data) == 0:
                # User doesn't exist - could be a race condition or attack
                logger.warning(f"User {user_id[:8]} not found during webhook validation{' for ' + context if context else ''}")
                return False
            
            db_customer_id = response.data[0].get("stripe_customer_id")
            
            # If user has no stored customer_id, this might be the first checkout
            # In that case, we allow it (the checkout handler will store the customer_id)
            if not db_customer_id:
                # MONITORING: Log first-time customer mapping for audit trail
                # This is expected for new subscribers but should be monitored
                # for unusual patterns (e.g., same user_id with different customer_ids)
                logger.info(
                    f"BILLING_AUDIT: First-time customer mapping - "
                    f"user={user_id[:8]} customer={_short_stripe_id(customer_id)} "
                    f"context={context or 'unknown'}"
                )
                return True
            
            # Validate customer_id matches
            if db_customer_id != customer_id:
                logger.error(
                    f"SECURITY: Customer ID mismatch for user {user_id[:8]}: "
                    f"webhook has {_short_stripe_id(customer_id)}, database has {_short_stripe_id(db_customer_id)}"
                    f"{' in ' + context if context else ''}"
                )
                return False
            
            logger.debug(f"Webhook user authorization validated for user {user_id[:8]}")
            return True
            
        except Exception as e:
            logger.error(f"Error validating webhook user authorization: {e}", exc_info=True)
            return False

    # ========================================================================
    # Customer Management
    # ========================================================================
    
    async def get_or_create_customer(self, user_id: str, user_token: str, email: str) -> str:
        """
        Get existing Stripe customer ID or create a new customer.
        
        This method checks if the user already has a Stripe customer ID in the database.
        If not, it creates a new Stripe customer and stores the ID.
        
        Args:
            user_id: Supabase user UUID
            user_token: User's JWT token for authenticated Supabase access
            email: User's email address
            
        Returns:
            str: Stripe customer ID (cus_XXXXXXXXX)
            
        Raises:
            HTTPException: If customer creation fails
        """
        try:
            logger.info(f"Getting or creating Stripe customer for user {user_id[:8]}")
            
            # Use authenticated Supabase client to comply with RLS policies
            authed_supabase = get_authed_supabase_client(user_token)
            
            # 1. Check if user already has a customer ID
            response = authed_supabase.table("profiles").select("stripe_customer_id").eq("id", user_id).execute()
            
            # Check if profile exists and has a customer ID
            if response.data and len(response.data) > 0 and response.data[0].get("stripe_customer_id"):
                customer_id = response.data[0]["stripe_customer_id"]
                logger.info(f"Found existing Stripe customer: {_short_stripe_id(customer_id)}")
                return customer_id
            
            logger.info(f"Creating new Stripe customer for email: {email}")
            
            # 2. Create new customer in Stripe
            # Run synchronous Stripe API call in thread pool to avoid blocking event loop
            customer = await asyncio.to_thread(
                stripe.Customer.create,
                email=email,
                metadata={
                    "user_id": user_id,
                    "environment": "production" if not self.config.is_testing() else "test"
                }
            )
            
            logger.info(f"Stripe customer created: {customer.id}")
            
            # 3. Update user profile with customer ID using authenticated client
            response = authed_supabase.table("profiles").update({
                "stripe_customer_id": customer.id
            }).eq("id", user_id).execute()
            
            # Verify database update succeeded
            if not response.data:
                logger.error(f"No profile found for user {user_id[:8]} when storing Stripe customer ID")
                raise HTTPException(status_code=404, detail="User profile not found")
            
            logger.info(f"Updated profile with Stripe customer ID for user {user_id[:8]}")
            
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
    
    async def get_active_subscription(self, customer_id: str) -> Optional[stripe.Subscription]:
        """
        Get the user's active or trialing subscription from Stripe.
        
        Args:
            customer_id: Stripe customer ID
            
        Returns:
            stripe.Subscription if user has an active or trialing subscription, None otherwise
        """
        try:
            # Make both API calls concurrently to reduce latency
            active_subs, trialing_subs = await asyncio.gather(
                asyncio.to_thread(
                    stripe.Subscription.list,
                    customer=customer_id,
                    status="active",
                    limit=1
                ),
                asyncio.to_thread(
                    stripe.Subscription.list,
                    customer=customer_id,
                    status="trialing",
                    limit=1
                )
            )
            
            # Prefer active over trialing
            if active_subs.data:
                return active_subs.data[0]
            
            if trialing_subs.data:
                return trialing_subs.data[0]
            
            return None
            
        except stripe.StripeError as e:
            logger.error(f"Error fetching subscriptions: {e}")
            return None
    
    async def upgrade_subscription(
        self,
        subscription_id: str,
        new_price_id: str,
        user_id: str,
        tier: str
    ) -> dict:
        """
        Upgrade an existing subscription to a new price/tier.
        
        This modifies the subscription immediately with proration,
        rather than creating a duplicate subscription.
        
        Args:
            subscription_id: Existing Stripe subscription ID
            new_price_id: New price ID to switch to
            user_id: User ID for metadata
            tier: New tier name
            
        Returns:
            dict with subscription details
        """
        try:
            # Get current subscription to find the subscription item ID
            subscription = await asyncio.to_thread(
                stripe.Subscription.retrieve,
                subscription_id
            )
            
            # Get the first (and typically only) subscription item using _get_attr helper
            # for consistent access regardless of whether it's a dict or Stripe object
            items = self._get_attr(subscription, "items")
            items_data = self._get_attr(items, "data", [])
            if not items_data:
                raise HTTPException(status_code=500, detail="Subscription has no items")
            
            first_item = items_data[0]
            subscription_item_id = self._get_attr(first_item, "id")
            item_price = self._get_attr(first_item, "price")
            current_price_id = self._get_attr(item_price, "id")
            
            # Check if already on this price
            if current_price_id == new_price_id:
                logger.info(f"User {user_id[:8]} already on {tier}, no upgrade needed")
                return {
                    "status": "already_subscribed",
                    "message": f"You are already subscribed to {tier}",
                    "subscription_id": subscription_id
                }
            
            # Determine if this is an upgrade or downgrade based on tier hierarchy
            # Only include tiers that have Stripe price IDs configured
            current_tier = self.config.get_tier_from_price_id(current_price_id) or "unknown"
            is_upgrade = TIER_ORDER.get(tier, 0) > TIER_ORDER.get(current_tier, 0)
            action = "upgrade" if is_upgrade else "downgrade"
            
            logger.info(
                f"{action.capitalize()}ing subscription {_short_stripe_id(subscription_id)} "
                f"from {current_tier} ({_short_stripe_id(current_price_id)}) to {tier} ({_short_stripe_id(new_price_id)})"
            )
            
            # Update the subscription with the new price
            # For upgrades: "create_prorations" charges the difference immediately
            # For downgrades: "none" takes effect at next billing cycle (prevents partial refunds)
            proration_behavior = "create_prorations" if is_upgrade else "none"
            
            updated_subscription = await asyncio.to_thread(
                stripe.Subscription.modify,
                subscription_id,
                items=[{
                    "id": subscription_item_id,
                    "price": new_price_id,
                }],
                proration_behavior=proration_behavior,
                metadata={
                    "user_id": user_id,
                    "tier": tier,
                    "upgraded_at" if is_upgrade else "downgraded_at": datetime.now(timezone.utc).isoformat()
                }
            )
            
            status = "upgraded" if is_upgrade else "downgraded"
            logger.info(f"Subscription {status} successfully for user {user_id[:8]} to {tier}")
            
            # Sync database immediately so user sees updated tier without waiting for webhook
            # The webhook will also fire but this ensures immediate consistency
            try:
                await self.provision_subscription(
                    user_id=user_id,
                    customer_id=self._get_attr(updated_subscription, "customer"),
                    subscription_id=updated_subscription.id,
                    subscription_status=self._get_attr(updated_subscription, "status"),
                    price_id=new_price_id,
                    current_period_start=self._get_attr(updated_subscription, "current_period_start"),
                    current_period_end=self._get_attr(updated_subscription, "current_period_end")
                )
                logger.info(f"Database synced immediately after {action} for user {user_id[:8]}")
            except Exception as db_error:
                # Log but don't fail - webhook will eventually sync
                logger.warning(f"Failed to sync database immediately, webhook will sync: {db_error}")
            return {
                "status": status,
                "message": f"Successfully {status} to {tier}" + ("" if is_upgrade else " (effective next billing cycle)"),
                "subscription_id": updated_subscription.id
            }
            
        except stripe.StripeError as e:
            logger.error(f"Stripe error upgrading subscription: {e}")
            raise HTTPException(status_code=502, detail=f"Stripe error: {str(e)}")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error upgrading subscription: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to upgrade subscription: {str(e)}")

    async def preview_upgrade(
        self,
        user_id: str,
        user_token: str,
        tier: str
    ) -> dict:
        """
        Preview the cost of upgrading/downgrading a subscription.
        
        Uses Stripe's Invoice.create_preview API to calculate the exact proration
        amount without actually modifying the subscription. This allows showing
        the user what they'll be charged before they confirm.
        
        Args:
            user_id: User ID
            user_token: User's JWT token for authenticated Supabase access
            tier: Target tier to preview (premium or pro)
            
        Returns:
            dict with proration details including amounts, card info, and billing date
            
        Raises:
            HTTPException: If user has no active subscription or preview fails
        """
        logger.info(f"Previewing upgrade to {tier} for user {user_id[:8]}")
        
        # Validate tier and get price ID
        new_price_id = self.config.get_price_id_from_tier(tier)
        if not new_price_id:
            raise HTTPException(status_code=400, detail=f"Invalid tier: {tier}")
        
        try:
            # Get customer ID from profile
            from services.db_services.supabase_quiz import get_authed_supabase_client
            supabase = get_authed_supabase_client(user_token)
            
            result = supabase.table("profiles").select(
                "stripe_customer_id"
            ).eq("id", user_id).single().execute()
            
            if not result.data or not result.data.get("stripe_customer_id"):
                raise HTTPException(
                    status_code=400, 
                    detail="No subscription found. Please subscribe first."
                )
            
            customer_id = result.data["stripe_customer_id"]
            
            # Get active subscription
            subscription = await self.get_active_subscription(customer_id)
            if not subscription:
                raise HTTPException(
                    status_code=400,
                    detail="No active subscription found. Please subscribe first."
                )
            
            # Get current subscription item and price
            items = self._get_attr(subscription, "items")
            items_data = self._get_attr(items, "data", [])
            if not items_data:
                raise HTTPException(status_code=500, detail="Subscription has no items")
            
            first_item = items_data[0]
            subscription_item_id = self._get_attr(first_item, "id")
            item_price = self._get_attr(first_item, "price")
            current_price_id = self._get_attr(item_price, "id")
            
            # Check if already on this tier
            current_tier = self.config.get_tier_from_price_id(current_price_id) or "unknown"
            if current_price_id == new_price_id:
                raise HTTPException(
                    status_code=400,
                    detail=f"You are already subscribed to {tier}"
                )
            
            # Determine if upgrade or downgrade using module-level tier hierarchy
            is_upgrade = TIER_ORDER.get(tier, 0) > TIER_ORDER.get(current_tier, 0)
            
            # Create preview invoice using Stripe's API
            # This calculates the proration without actually modifying the subscription
            preview_invoice = await asyncio.to_thread(
                stripe.Invoice.create_preview,
                customer=customer_id,
                subscription=subscription.id,
                subscription_details={
                    "items": [{
                        "id": subscription_item_id,
                        "price": new_price_id,
                    }],
                    "proration_behavior": "create_prorations" if is_upgrade else "none"
                }
            )
            
            # Parse invoice line items to find proration amounts
            credit_amount = 0  # Credit for unused time (negative line item)
            debit_amount = 0   # Charge for new plan time (positive line item)
            
            for line in preview_invoice.lines.data:
                # Check if this is a proration line item
                # Stripe marks prorations with discountable=False OR type contains proration info
                # For subscription updates, prorations appear as line items with amounts
                # Negative amounts = credits for unused time on old plan
                # Positive amounts = charges for new plan time
                is_proration = getattr(line, 'proration', False) or not getattr(line, 'discountable', True)
                
                if is_proration:
                    if line.amount < 0:
                        credit_amount += abs(line.amount)  # Store as positive
                    else:
                        debit_amount += line.amount
            
            # Net proration (what user pays today)
            proration_amount = debit_amount - credit_amount
            
            # Get next billing info
            # current_period_end should always exist on subscription objects per Stripe API docs
            # Using _get_attr for defensive access in case of API inconsistencies
            current_period_end = self._get_attr(subscription, "current_period_end")
            if current_period_end:
                next_billing_date = datetime.fromtimestamp(
                    current_period_end, tz=timezone.utc
                )
            else:
                # Fallback: estimate next billing as 30 days from now
                # Log warning as this shouldn't happen with valid subscriptions
                logger.warning(
                    f"Subscription {subscription.id} missing current_period_end field. "
                    f"Using 30-day fallback estimate."
                )
                next_billing_date = datetime.now(tz=timezone.utc) + timedelta(days=30)
            
            # Get the new plan's monthly price
            new_price = await asyncio.to_thread(stripe.Price.retrieve, new_price_id)
            next_billing_amount = new_price.unit_amount or 0
            
            # Get card info for display
            card_last4 = None
            card_brand = None
            
            try:
                customer = await asyncio.to_thread(
                    stripe.Customer.retrieve,
                    customer_id,
                    expand=["default_source", "invoice_settings.default_payment_method"]
                )
                
                # Try to get card from default payment method first
                payment_method = self._get_attr(
                    self._get_attr(customer, "invoice_settings"), 
                    "default_payment_method"
                )
                if payment_method:
                    card = self._get_attr(payment_method, "card")
                    if card:
                        card_last4 = self._get_attr(card, "last4")
                        card_brand = self._get_attr(card, "brand")
                
                # Fallback to default source
                if not card_last4:
                    default_source = self._get_attr(customer, "default_source")
                    if default_source:
                        card_last4 = self._get_attr(default_source, "last4")
                        card_brand = self._get_attr(default_source, "brand")
            except Exception as e:
                logger.warning(f"Failed to get card info: {e}")
            
            # Format amounts for display
            def format_amount(cents: int) -> str:
                """Format cents as dollar string."""
                dollars = cents / 100
                return f"${dollars:,.2f}"
            
            # Build user message based on upgrade/downgrade and proration amount
            if is_upgrade:
                if proration_amount > 0:
                    message = (
                        f"You'll be charged {format_amount(proration_amount)} today (prorated). "
                        f"Then {format_amount(next_billing_amount)}/month starting "
                        f"{next_billing_date.strftime('%b %d')}."
                    )
                elif proration_amount == 0:
                    # Edge case: exact proration balance (unlikely but possible)
                    message = (
                        f"No charge today - your credit exactly covers the upgrade. "
                        f"Then {format_amount(next_billing_amount)}/month starting "
                        f"{next_billing_date.strftime('%b %d')}."
                    )
                else:
                    # Negative proration: user gets a credit (rare for upgrades)
                    message = (
                        f"You'll receive a {format_amount(abs(proration_amount))} credit. "
                        f"Then {format_amount(next_billing_amount)}/month starting "
                        f"{next_billing_date.strftime('%b %d')}."
                    )
            else:
                # Downgrade: no proration, change takes effect at next billing cycle
                # Note: proration fields will be $0.00 for downgrades since proration_behavior="none"
                message = (
                    f"Your plan will change to {tier} on {next_billing_date.strftime('%b %d')}. "
                    f"You'll keep {current_tier} until then. "
                    f"Next billing: {format_amount(next_billing_amount)}/month."
                )
            
            logger.info(
                f"Upgrade preview for user {user_id[:8]}: {current_tier} → {tier}, "
                f"proration: {format_amount(proration_amount)}"
            )
            
            return {
                "current_tier": current_tier,
                "target_tier": tier,
                "is_upgrade": is_upgrade,
                "proration_amount": proration_amount,
                "proration_amount_formatted": format_amount(proration_amount) if proration_amount >= 0 else f"-{format_amount(abs(proration_amount))}",
                "credit_amount": credit_amount,
                "credit_amount_formatted": format_amount(credit_amount),
                "debit_amount": debit_amount,
                "debit_amount_formatted": format_amount(debit_amount),
                "next_billing_amount": next_billing_amount,
                "next_billing_amount_formatted": f"{format_amount(next_billing_amount)}/month",
                "next_billing_date": next_billing_date,
                "card_last4": card_last4,
                "card_brand": card_brand,
                "message": message
            }
            
        except stripe.StripeError as e:
            logger.error(f"Stripe error previewing upgrade: {e}")
            raise HTTPException(status_code=502, detail=f"Stripe error: {str(e)}")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error previewing upgrade: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to preview upgrade: {str(e)}")

    async def create_checkout_session(
        self, 
        user_id: str, 
        user_token: str,
        email: str, 
        tier: str
    ) -> dict:
        """
        Create a Stripe Checkout session for subscription purchase.
        
        This method creates a Stripe Checkout session that allows the user to
        enter payment information and complete the subscription purchase.
        
        Args:
            user_id: Supabase user UUID
            user_token: User's JWT token for authenticated Supabase access
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
        
        logger.info(f"Using Stripe price ID: {_short_stripe_id(price_id)}")
        
        # Validate success/cancel URLs are configured and point to our frontend
        success_url = self.config.STRIPE_SUCCESS_URL
        cancel_url = self.config.STRIPE_CANCEL_URL
        frontend_url = self.config.FRONTEND_URL
        
        if not success_url or not cancel_url:
            logger.error("STRIPE_SUCCESS_URL or STRIPE_CANCEL_URL not configured")
            raise HTTPException(status_code=500, detail="Checkout URLs not properly configured")
        
        # Security: Validate URLs are on the allowed domain
        if frontend_url:
            from urllib.parse import urlparse
            frontend_domain = urlparse(frontend_url).netloc
            success_domain = urlparse(success_url).netloc
            cancel_domain = urlparse(cancel_url).netloc
            
            # Explicitly check all domains are non-empty to prevent bypass
            if not frontend_domain or not success_domain or not cancel_domain:
                logger.error(
                    f"SECURITY: URL parsing failed - empty domain detected. "
                    f"Frontend: '{frontend_domain}', Success: '{success_domain}', Cancel: '{cancel_domain}'"
                )
                raise HTTPException(status_code=500, detail="Checkout URL configuration error")
            
            if success_domain != frontend_domain or cancel_domain != frontend_domain:
                logger.error(
                    f"SECURITY: Checkout URLs must match frontend domain. "
                    f"Frontend: {frontend_domain}, Success: {success_domain}, Cancel: {cancel_domain}"
                )
                raise HTTPException(status_code=500, detail="Checkout URL configuration error")
            
        try:
            # 2. Get or create customer
            customer_id = await self.get_or_create_customer(user_id, user_token, email)
            
            # 3. Check if user already has an active subscription
            # If they do, upgrade it instead of creating a new one
            existing_subscription = await self.get_active_subscription(customer_id)
            
            if existing_subscription:
                logger.info(
                    f"User {user_id[:8]} has existing subscription "
                    f"{_short_stripe_id(existing_subscription.id)}, upgrading instead of creating new"
                )
                # Upgrade the existing subscription to the new tier
                return await self.upgrade_subscription(
                    subscription_id=existing_subscription.id,
                    new_price_id=price_id,
                    user_id=user_id,
                    tier=tier
                )
            
            # 4. No existing subscription, create Checkout Session for new subscription
            # 
            # IDEMPOTENCY KEY STRATEGY:
            # Stripe caches idempotent API responses for 24 hours. However, checkout sessions
            # become invalid after use (status changes from "open" to "complete"/"expired").
            # 
            # Problem: Same idempotency key → returns cached (potentially stale) session
            # Solution: Try different idempotency keys until we find an "open" session
            # 
            # Each attempt uses a unique key: hash(user:tier:hour:attempt:N)
            # - Attempt 0: May return cached session from earlier in the hour
            # - Attempt 1-4: Each creates/retrieves a different session
            # 
            # Double-click protection is maintained because rapid clicks within the same
            # attempt number will get the same idempotency key → same session.
            #
            hourly_bucket = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H")
            base_key = f"{user_id}:{tier}:{hourly_bucket}"
            
            # Initialize current_session before loop for explicit scope
            current_session = None
            
            for attempt in range(MAX_CHECKOUT_SESSION_ATTEMPTS):
                # Generate idempotency key for this attempt
                # Each attempt gets a unique key to bypass cached stale sessions
                # while still protecting against double-clicks within the same attempt
                idempotency_key = sha256(f"{base_key}:attempt:{attempt}".encode()).hexdigest()[:32]
                
                # Run synchronous Stripe API call in thread pool to avoid blocking event loop
                session = await asyncio.to_thread(
                    stripe.checkout.Session.create,
                    customer=customer_id,
                    payment_method_types=["card"],
                    line_items=[{
                        "price": price_id,
                        "quantity": 1,
                    }],
                    mode="subscription",
                    success_url=f"{success_url.rstrip('/')}?session_id={{CHECKOUT_SESSION_ID}}",
                    cancel_url=cancel_url.rstrip('/'),
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
                    allow_promotion_codes=True,
                    idempotency_key=idempotency_key
                )
                
                # CRITICAL: When Stripe returns a cached session via idempotency key,
                # the status reflects the ORIGINAL response (always "open" at creation).
                # We must re-fetch the session to get its CURRENT status.
                # This handles the case where user completed checkout, canceled subscription,
                # and is now trying to re-subscribe within the same hour.
                current_session = await asyncio.to_thread(
                    stripe.checkout.Session.retrieve,
                    session.id
                )
                
                # Check if session is still valid (status = "open")
                if current_session.status == "open":
                    if attempt > 0:
                        logger.info(
                            f"Found valid session {_short_stripe_id(current_session.id)} on attempt {attempt + 1} "
                            f"for user {user_id[:8]}"
                        )
                    else:
                        logger.debug(f"Checkout session {_short_stripe_id(current_session.id)} created/retrieved")
                    break
                else:
                    logger.debug(
                        f"Attempt {attempt + 1}: Session {_short_stripe_id(current_session.id)} has status "
                        f"'{current_session.status}', trying next attempt..."
                    )
            
            # After all attempts, check if we have a valid session
            # Note: current_session should not be None here since MAX_CHECKOUT_SESSION_ATTEMPTS is > 0
            # and it's assigned in every loop iteration, but we check status to ensure we got a valid "open" session
            if not current_session or current_session.status != "open":
                logger.error(
                    f"Failed to get valid checkout session after {MAX_CHECKOUT_SESSION_ATTEMPTS} attempts "
                    f"for user {user_id[:8]}. Last session status: {current_session.status if current_session else 'None'}"
                )
                raise HTTPException(
                    status_code=503,
                    detail="Unable to create checkout session. Please contact support if this persists."
                )
            
            # Return the current session's URL (not the cached one from create)
            # current_session is from Session.retrieve, so it has real-time data
            return {
                "checkout_url": current_session.url,
                "session_id": current_session.id
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
    
    async def create_portal_session(self, user_id: str, user_token: str) -> str:
        """
        Create a Stripe Customer Portal session.
        
        The Customer Portal allows users to manage their subscription:
        - View invoices and payment history
        - Update payment method
        - Cancel subscription
        
        Args:
            user_id: Supabase user UUID
            user_token: User's JWT token for authenticated Supabase access
            
        Returns:
            str: Customer Portal URL to redirect user to
            
        Raises:
            HTTPException: If user has no Stripe customer ID or portal creation fails
            
        Epic 4: Customer Portal session creation IMPLEMENTED
        """
        try:
            # 1. Get stripe_customer_id from profiles using authenticated client
            # This ensures RLS policies are properly enforced for the authenticated user
            authed_supabase = get_authed_supabase_client(user_token)
            response = authed_supabase.table("profiles").select("stripe_customer_id").eq("id", user_id).execute()
            
            # Debug logging to diagnose cache vs database mismatch
            has_customer_id = bool(response.data and response.data[0].get("stripe_customer_id"))
            logger.info(f"Portal session query result for user {user_id[:8]}: has_customer_id={has_customer_id}")
            
            if not response.data or len(response.data) == 0 or not response.data[0].get("stripe_customer_id"):
                logger.warning(
                    f"User {user_id[:8]} has no Stripe customer ID - data_present: {bool(response.data)}, data_length: {len(response.data) if response.data else 0}"
                )
                raise HTTPException(
                    status_code=404,
                    detail="No subscription found. Please subscribe first."
                )
            
            customer_id = response.data[0]["stripe_customer_id"]
            logger.info(f"Creating portal session for customer {_short_stripe_id(customer_id)}")
            
            # 2. Create portal session with return URL
            # Run synchronous Stripe API call in thread pool to avoid blocking event loop
            portal_session = await asyncio.to_thread(
                stripe.billing_portal.Session.create,
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
        current_period_end: Optional[int] = None,
        reset_credits: bool = False
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
            reset_credits: Whether to reset credit allowance (e.g. on new sub or renewal)
            
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
        
        # Map tier to plan (Epic 1/3)
        plan = "pro" if tier in ["basic", "premium", "pro"] else "free"

        try:
            # 2. Prepare update data
            update_data = {
                "stripe_customer_id": customer_id,
                "stripe_subscription_id": subscription_id,
                "subscription_status": subscription_status,
                "account_tier": tier,
                "billing_plan": plan,
                # Clear any stale cancellation timestamp when provisioning a new/active subscription
                "subscription_canceled_at": None
            }

            # Handle credit reset for Pro plan (Epic 3.4)
            if reset_credits and plan == "pro" and subscription_status in [STATUS_ACTIVE, STATUS_TRIALING]:
                update_data["credit_units_monthly"] = PRO_MONTHLY_UNITS
                update_data["credit_units_remaining"] = PRO_MONTHLY_UNITS
                # Also reset free credits bucket on subscription renewal
                update_data["free_credit_units_remaining"] = FREE_MONTHLY_UNITS
            
            # Update billing period for quota tracking (Migration 017)
            if current_period_start:
                update_data["current_period_start"] = datetime.fromtimestamp(current_period_start, tz=timezone.utc).isoformat()
            
            if current_period_end:
                update_data["current_period_end"] = datetime.fromtimestamp(current_period_end, tz=timezone.utc).isoformat()
            
            # 3. Update profiles table
            # We use the service role client (self.supabase) which bypasses RLS
            # This is safe because this method is called by trusted internal handlers
            response = self.supabase.table("profiles").update(update_data).eq("id", user_id).execute()
            
            # Verify database update succeeded
            if not response.data:
                logger.error(f"No profile found for user {user_id[:8]} during provisioning")
                raise HTTPException(status_code=404, detail="User profile not found")
            
            logger.info(f"Successfully provisioned subscription {_short_stripe_id(subscription_id)} for user {user_id[:8]}")
            
            # 4. Invalidate user tier cache after successful provisioning
            # This ensures the next API call fetches fresh data showing the upgraded tier
            try:
                # Run cache invalidation asynchronously
                asyncio.create_task(invalidate_user_tier_cache(user_id))
                logger.info(f"Invalidated tier cache for user {user_id[:8]} after provisioning")
            except Exception as cache_error:
                # Cache invalidation failure should not break provisioning
                logger.warning(f"Failed to invalidate cache for user {user_id[:8]}: {cache_error}")
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to provision subscription: {str(e)}")
    

    
    async def cancel_subscription(
        self, 
        user_id: str, 
        subscription_id: str,
        canceled_at_timestamp: int
    ) -> None:
        """
        Cancel a subscription (from webhook).
        
        This method is called by the webhook handler when customer.subscription.deleted
        fires. IMPORTANT: Stripe sends this event AFTER the subscription period ends,
        not when the user requests cancellation. The grace period is automatically
        handled by Stripe - users retain access until their paid period expires,
        and only then does this webhook fire to downgrade them.
        
        Flow:
        1. User cancels in Customer Portal → subscription.updated (cancel_at_period_end=True)
        2. User retains Pro access until period ends (Stripe handles this)
        3. Period ends → subscription.deleted fires → this method downgrades to free
        
        Args:
            user_id: Supabase user UUID
            subscription_id: Stripe subscription ID (sub_XXXXXXXXX)
            canceled_at_timestamp: Unix timestamp when subscription was canceled
            
        Epic 3: Subscription cancellation IMPLEMENTED
        """
        try:
            canceled_at = datetime.fromtimestamp(canceled_at_timestamp, tz=timezone.utc)
            
            # Update subscription status to canceled AND downgrade tier to free
            # When subscription.deleted fires, the subscription has truly ended
            # (either immediately or after the grace period expired)
            response = self.supabase.table("profiles").update({
                "subscription_status": STATUS_CANCELED,
                "subscription_canceled_at": canceled_at.isoformat(),
                "account_tier": "free",  # Downgrade to free tier
                "billing_plan": "free",  # Downgrade plan (Epic 3.5)
                "credit_units_monthly": FREE_MONTHLY_UNITS,  # Legacy compatibility
                "credit_units_remaining": 0,  # Drop any recurring subscription credits
                "free_credit_units_monthly": FREE_MONTHLY_UNITS,
                "free_credit_units_remaining": FREE_MONTHLY_UNITS
                # Note: credit_units_purchased is preserved (Epic 3.5)
            }).eq("id", user_id).execute()
            
            # Verify database update succeeded
            if not response.data:
                logger.error(f"No profile found for user {user_id[:8]} during cancellation")
                raise HTTPException(status_code=404, detail="User profile not found")
            
            logger.info(f"Subscription {_short_stripe_id(subscription_id)} canceled for user {user_id[:8]}")
            
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
            logger.error(f"No user_id in checkout session {_short_stripe_id(session.get('id'))}")
            return
        
        customer_id = session.get("customer")
        
        # Security: Validate user_id matches customer_id in database
        # This prevents spoofed metadata attacks
        if not await self._validate_webhook_user_authorization(
            user_id=user_id,
            customer_id=customer_id,
            context=f"checkout session {_short_stripe_id(session.get('id'))}"
        ):
            logger.error(f"SECURITY: Webhook authorization failed for checkout {_short_stripe_id(session.get('id'))}")
            return
        
        # Handle Credit Pack Purchase (One-time payment) (Epic 3.3)
        if session.get("mode") == "payment":
            logger.info(f"Processing credit pack purchase for user {user_id[:8]}")
            
            # Extract units from metadata (assuming set during checkout creation)
            units = session.get("metadata", {}).get("units")
            if units:
                try:
                    units = int(units)
                    # Update DB
                    from services.db_services.supabase_quiz import get_supabase
                    supabase = get_supabase()
                    
                    # Fetch current
                    resp = supabase.table("profiles").select("credit_units_purchased").eq("id", user_id).single().execute()
                    current = resp.data.get("credit_units_purchased", 0)
                    
                    supabase.table("profiles").update({
                        "credit_units_purchased": current + units
                    }).eq("id", user_id).execute()
                    
                    logger.info(f"Added {units} units to user {user_id[:8]}")
                except Exception as e:
                    logger.error(f"Failed to add credits: {e}")
            else:
                logger.warning("No 'units' in metadata for credit pack purchase")
            return
        
        # Get subscription details
        subscription_id = session.get("subscription")
        if not subscription_id:
            logger.warning(f"No subscription in checkout session {_short_stripe_id(session.get('id'))}")
            return
        
        # Fetch full subscription details
        # Run synchronous Stripe API call in thread pool to avoid blocking event loop
        subscription = await asyncio.to_thread(
            stripe.Subscription.retrieve, subscription_id
        )
        
        # Extract price_id from subscription items
        price_id = self._extract_price_id_from_subscription(
            subscription, 
            context=f"subscription {subscription_id}, user {user_id[:8]}"
        )
        if not price_id:
            return
        
        logger.info(f"Checkout completed for user {user_id[:8]}, subscription {_short_stripe_id(subscription_id)}")
        
        # Extract period dates from subscription items (NOT from subscription object itself)
        current_period_start, current_period_end = self._extract_period_dates_from_subscription(
            subscription, context=f"checkout session for user {user_id[:8]}"
        )
        
        # Provision subscription
        await self.provision_subscription(
            user_id=user_id,
            customer_id=customer_id,
            subscription_id=subscription_id,
            subscription_status=self._get_attr(subscription, "status"),
            price_id=price_id,
            current_period_start=current_period_start,
            current_period_end=current_period_end,
            reset_credits=True  # Reset credits for new subscription
        )
    
    async def handle_subscription_created(self, subscription: dict) -> None:
        """
        Handle customer.subscription.created webhook event.
        
        Args:
            subscription: Stripe Subscription object
        """
        user_id = subscription.get("metadata", {}).get("user_id")
        if not user_id:
            logger.error(f"No user_id in subscription {_short_stripe_id(subscription.get('id'))}")
            return
        
        customer_id = subscription.get("customer")
        
        # Security: Validate user_id matches customer_id in database
        if not await self._validate_webhook_user_authorization(
            user_id=user_id,
            customer_id=customer_id,
            context=f"subscription created {_short_stripe_id(subscription.get('id'))}"
        ):
            logger.error(f"SECURITY: Webhook authorization failed for subscription {_short_stripe_id(subscription.get('id'))}")
            return
        
        # Extract price_id from subscription items
        price_id = self._extract_price_id_from_subscription(
            subscription,
            context=f"subscription {_short_stripe_id(subscription.get('id'))}"
        )
        if not price_id:
            return
        
        logger.info(f"Subscription created: {_short_stripe_id(subscription.get('id'))} for user {user_id[:8]}")
        
        # Extract period dates from subscription items (NOT from subscription object itself)
        current_period_start, current_period_end = self._extract_period_dates_from_subscription(
            subscription, context=f"subscription {_short_stripe_id(subscription.get('id'))}"
        )
        
        # Provision subscription
        await self.provision_subscription(
            user_id=user_id,
            customer_id=customer_id,
            subscription_id=subscription.get("id"),
            subscription_status=subscription.get("status"),
            price_id=price_id,
            current_period_start=current_period_start,
            current_period_end=current_period_end
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
            logger.warning(f"No user_id in subscription {_short_stripe_id(subscription.get('id'))}, skipping update")
            return
        
        customer_id = subscription.get("customer")
        
        # Security: Validate user_id matches customer_id in database
        if not await self._validate_webhook_user_authorization(
            user_id=user_id,
            customer_id=customer_id,
            context=f"subscription updated {_short_stripe_id(subscription.get('id'))}"
        ):
            logger.error(f"SECURITY: Webhook authorization failed for subscription {_short_stripe_id(subscription.get('id'))}")
            return
        
        # Extract price_id from subscription items
        price_id = self._extract_price_id_from_subscription(
            subscription,
            context=f"subscription {_short_stripe_id(subscription.get('id'))} for user {user_id[:8]}"
        )
        if not price_id:
            logger.error(f"Cannot provision subscription {_short_stripe_id(subscription.get('id'))} without price_id")
            return
        
        subscription_status = subscription.get("status")
        canceled_at = subscription.get("canceled_at")
        cancel_at = subscription.get("cancel_at")  # Scheduled cancellation date (cancel at period end)
        
        logger.info(f"Subscription updated: {_short_stripe_id(subscription.get('id'))} for user {user_id[:8]} - status: {subscription_status}, canceled_at: {canceled_at}, cancel_at: {cancel_at}")
        
        # Extract period dates from subscription items (NOT from subscription object itself)
        current_period_start, current_period_end = self._extract_period_dates_from_subscription(
            subscription, context=f"subscription {_short_stripe_id(subscription.get('id'))} for user {user_id[:8]}"
        )
        
        # Update subscription details
        await self.provision_subscription(
            user_id=user_id,
            customer_id=customer_id,
            subscription_id=subscription.get("id"),
            subscription_status=subscription_status,
            price_id=price_id,
            current_period_start=current_period_start,
            current_period_end=current_period_end
        )
        
        # Handle cancellation timestamps
        # - canceled_at: When subscription was actually canceled (immediate cancellation)
        # - cancel_at: Scheduled future cancellation date (cancel at period end)
        # We use whichever is set to track the cancellation
        cancellation_timestamp = canceled_at or cancel_at
        
        if cancellation_timestamp:
            # Subscription has pending or completed cancellation
            canceled_at_datetime = datetime.fromtimestamp(cancellation_timestamp, tz=timezone.utc)
            response = self.supabase.table("profiles").update({
                "subscription_canceled_at": canceled_at_datetime.isoformat()
            }).eq("id", user_id).execute()
            
            # Verify database update succeeded - critical for grace period logic
            if not response.data:
                logger.warning(f"Attempted to update subscription_canceled_at for user {user_id[:8]}, but no profile was updated (user may not exist)")
                # Do not raise exception - provisioning already succeeded above
            else:
                logger.info(f"Updated subscription_canceled_at for user {user_id[:8]} to {canceled_at_datetime.isoformat()}")
            
            # Invalidate cache again since we updated canceled_at
            try:
                asyncio.create_task(invalidate_user_tier_cache(user_id))
            except Exception as cache_error:
                logger.warning(f"Failed to invalidate cache after canceled_at update: {cache_error}")
        else:
            # No cancellation pending - clear any stale subscription_canceled_at
            # This handles reactivation scenarios where a previously canceled subscription
            # is reactivated (e.g., user "undoes" cancellation before period end)
            if subscription_status == STATUS_ACTIVE:
                response = self.supabase.table("profiles").update({
                    "subscription_canceled_at": None
                }).eq("id", user_id).execute()
                
                if response.data:
                    logger.info(f"Cleared subscription_canceled_at for reactivated subscription for user {user_id[:8]}")
                
                try:
                    asyncio.create_task(invalidate_user_tier_cache(user_id))
                except Exception as cache_error:
                    logger.warning(f"Failed to invalidate cache after reactivation: {cache_error}")
    
    async def handle_subscription_deleted(self, subscription: dict) -> None:
        """
        Handle customer.subscription.deleted webhook event.
        
        Args:
            subscription: Stripe Subscription object
        """
        user_id = subscription.get("metadata", {}).get("user_id")
        if not user_id:
            logger.warning(f"No user_id in subscription {_short_stripe_id(subscription.get('id'))}, skipping deletion")
            return
        
        customer_id = subscription.get("customer")
        
        # Security: Validate user_id matches customer_id in database
        if not await self._validate_webhook_user_authorization(
            user_id=user_id,
            customer_id=customer_id,
            context=f"subscription deleted {_short_stripe_id(subscription.get('id'))}"
        ):
            logger.error(f"SECURITY: Webhook authorization failed for subscription {_short_stripe_id(subscription.get('id'))}")
            return
        
        canceled_at = subscription.get("canceled_at", int(datetime.now(timezone.utc).timestamp()))
        
        logger.info(f"Subscription deleted: {_short_stripe_id(subscription.get('id'))} for user {user_id[:8]}")
        
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
            logger.info(f"Invoice {_short_stripe_id(invoice.get('id'))} not associated with subscription")
            return
        
        # Fetch subscription to get metadata
        # Run synchronous Stripe API call in thread pool to avoid blocking event loop
        subscription = await asyncio.to_thread(
            stripe.Subscription.retrieve, subscription_id
        )
        # Use _get_attr for Stripe API objects (supports both dict and object access)
        metadata = self._get_attr(subscription, "metadata", {})
        user_id = self._get_attr(metadata, "user_id")
        
        if not user_id:
            logger.warning(f"No user_id in subscription {_short_stripe_id(subscription_id)}, skipping invoice handling")
            return
        
        customer_id = self._get_attr(subscription, "customer")
        
        # Security: Validate user_id matches customer_id in database
        if not await self._validate_webhook_user_authorization(
            user_id=user_id,
            customer_id=customer_id,
            context=f"invoice paid {_short_stripe_id(invoice.get('id'))}"
        ):
            logger.error(f"SECURITY: Webhook authorization failed for invoice {_short_stripe_id(invoice.get('id'))}")
            return
        
        logger.info(f"Invoice paid: {_short_stripe_id(invoice.get('id'))} for user {user_id[:8]}")
        
        # Update subscription status to active (in case it was past_due)
        price_id = self._extract_price_id_from_subscription(
            subscription,
            context=f"invoice {_short_stripe_id(invoice.get('id'))} (subscription {_short_stripe_id(subscription_id)})"
        )
        if not price_id:
            return
        
        # Extract period dates from subscription items (NOT from subscription object itself)
        current_period_start, current_period_end = self._extract_period_dates_from_subscription(
            subscription, context=f"invoice {_short_stripe_id(invoice.get('id'))} for user {user_id[:8]}"
        )
        
        await self.provision_subscription(
            user_id=user_id,
            customer_id=customer_id,
            subscription_id=subscription_id,
            subscription_status=STATUS_ACTIVE,
            price_id=price_id,
            current_period_start=current_period_start,
            current_period_end=current_period_end,
            reset_credits=True  # Reset credits on successful invoice payment (renewal)
        )
    
    async def handle_invoice_payment_failed(self, invoice: dict) -> None:
        """
        Handle invoice.payment_failed webhook event.
        
        Args:
            invoice: Stripe Invoice object
        """
        subscription_id = invoice.get("subscription")
        if not subscription_id:
            logger.info(f"Invoice {_short_stripe_id(invoice.get('id'))} not associated with subscription")
            return
        
        # Fetch subscription to get metadata
        # Run synchronous Stripe API call in thread pool to avoid blocking event loop
        subscription = await asyncio.to_thread(
            stripe.Subscription.retrieve, subscription_id
        )
        # Use _get_attr for Stripe API objects (supports both dict and object access)
        metadata = self._get_attr(subscription, "metadata", {})
        user_id = self._get_attr(metadata, "user_id")
        
        if not user_id:
            logger.warning(f"No user_id in subscription {_short_stripe_id(subscription_id)}, skipping invoice handling")
            return
        
        customer_id = self._get_attr(subscription, "customer")
        
        # Security: Validate user_id matches customer_id in database
        if not await self._validate_webhook_user_authorization(
            user_id=user_id,
            customer_id=customer_id,
            context=f"invoice payment failed {_short_stripe_id(invoice.get('id'))}"
        ):
            logger.error(f"SECURITY: Webhook authorization failed for invoice {_short_stripe_id(invoice.get('id'))}")
            return
        
        logger.warning(f"Invoice payment failed: {_short_stripe_id(invoice.get('id'))} for user {user_id[:8]}")
        
        # Update subscription status to past_due
        try:
            response = self.supabase.table("profiles").update({
                "subscription_status": STATUS_PAST_DUE
            }).eq("id", user_id).execute()
            
            if not response.data:
                logger.error(f"No profile found for user {user_id[:8]} during payment failure handling")
            else:
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
            str: Billing status (no_subscription, active, canceling, grace_period, past_due, expired)
        """
        subscription_status = user_data.get("subscription_status")
        subscription_canceled_at = user_data.get("subscription_canceled_at")
        
        if not subscription_status:
            return "no_subscription"
        
        if subscription_status == STATUS_ACTIVE:
            # Check if subscription is scheduled for cancellation (cancel at period end)
            if subscription_canceled_at:
                return "canceling"  # Active but will cancel at period end
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
                except ValueError as e:
                    # Invalid timestamp format - log and treat as expired
                    logger.warning(f"Invalid timestamp format for current_period_end: {current_period_end} - {e}")
                    return "expired"
                except Exception as e:
                    # Unexpected error - log with full context for debugging
                    logger.error(f"Unexpected error parsing period_end timestamp: {e}", exc_info=True)
                    return "expired"
            return "expired"
        
        if subscription_status == STATUS_PAST_DUE:
            return "past_due"
        
        return subscription_status
