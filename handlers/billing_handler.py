"""
Billing Handler - Business Logic for checkout session verification
"""

import asyncio
from typing import Dict
import stripe
from fastapi import HTTPException
from services.logger import app_logger as logger
from services.billing_service import BillingService, _short_stripe_id
from services.db_services.supabase_quiz import get_supabase


async def verify_checkout_session(
    session_id: str, 
    user_id: str,
    billing_service: BillingService
) -> Dict:
    """
    Verify checkout session and return subscription details.
    
    This endpoint is called by the frontend after the user returns from Stripe Checkout.
    It verifies the session belongs to the user and that payment was successful.
    
    IMPORTANT: This endpoint does NOT provision the subscription. Provisioning is handled
    exclusively by Stripe webhooks (checkout.session.completed) to ensure:
    1. Single source of truth for subscription state
    2. No race conditions between sync verification and async webhooks
    3. Consistent behavior even if user closes browser before returning
    
    If the webhook hasn't processed yet, this returns status="pending" and the frontend
    should poll /subscription-status until the tier is updated.
    
    Args:
        session_id: Stripe Checkout Session ID
        user_id: Quizify user ID (for verification)
        billing_service: Injected BillingService instance
        
    Returns:
        Dict with subscription details and provisioning status
        
    Raises:
        HTTPException: If session invalid or user mismatch
    """
    try:
        # Retrieve session from Stripe (wrapped to avoid blocking event loop)
        session = await asyncio.to_thread(
            stripe.checkout.Session.retrieve,
            session_id,
            expand=["subscription"]
        )
        
        # Verify session belongs to user
        session_user_id = session.metadata.get("user_id")
        if session_user_id != user_id:
            safe_session_user_id = session_user_id[:8] if session_user_id else "None"
            logger.warning(
                f"Session {_short_stripe_id(session_id)} user mismatch: "
                f"expected {user_id[:8]}, got {safe_session_user_id}"
            )
            raise HTTPException(
                status_code=403,
                detail="Session does not belong to this user"
            )
        
        # Verify payment status
        if session.payment_status != "paid":
            logger.warning(
                f"Session {_short_stripe_id(session_id)} payment not complete: "
                f"status={session.payment_status}"
            )
            raise HTTPException(
                status_code=400,
                detail=f"Payment not complete: {session.payment_status}"
            )
        
        # Extract subscription details
        subscription_id = session.subscription
        if hasattr(subscription_id, 'id'):
            subscription_id = subscription_id.id
        
        # Fetch fresh subscription with all fields
        subscription = await asyncio.to_thread(
            stripe.Subscription.retrieve,
            subscription_id
        )
        
        tier = session.metadata.get("tier", "free")
        
        # Check if subscription is already provisioned in database
        # This handles the case where webhook processed before user returned
        supabase = get_supabase()
        profile = supabase.table("profiles").select(
            "stripe_subscription_id", "billing_plan", "subscription_status"
        ).eq("id", user_id).single().execute()
        
        provisioned = False
        if profile.data:
            db_subscription_id = profile.data.get("stripe_subscription_id")
            db_billing_plan = profile.data.get("billing_plan")
            
            # Check if webhook has already provisioned this subscription
            if db_subscription_id == subscription_id and db_billing_plan == "pro":
                provisioned = True
                logger.info(
                    f"Session {_short_stripe_id(session_id)} already provisioned by webhook"
                )
        
        # Extract period end from subscription items
        current_period_end = None
        items = subscription.get("items", {})
        item_data = items.get("data", []) if isinstance(items, dict) else getattr(items, "data", [])
        if item_data:
            first_item = item_data[0]
            current_period_end = (
                first_item.get("current_period_end") 
                if isinstance(first_item, dict) 
                else getattr(first_item, "current_period_end", None)
            )
        
        return {
            "session_id": session.id,
            "customer_id": session.customer,
            "subscription_id": subscription_id,
            "tier": tier,
            "status": subscription.status,
            "current_period_end": current_period_end,
            "payment_status": session.payment_status,
            # New field: indicates if frontend should poll for subscription status
            "provisioned": provisioned,
            "message": (
                "Subscription active" if provisioned 
                else "Payment successful. Your subscription is being activated..."
            )
        }
        
    except stripe.InvalidRequestError as e:
        logger.error(f"Invalid session ID {_short_stripe_id(session_id)}: {e}")
        raise HTTPException(
            status_code=404,
            detail="Checkout session not found"
        )
    except stripe.StripeError as e:
        logger.error(f"Stripe error verifying session {_short_stripe_id(session_id)}: {e}")
        raise HTTPException(
            status_code=502,
            detail="Failed to verify checkout session with Stripe"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error verifying session {_short_stripe_id(session_id)}: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )
