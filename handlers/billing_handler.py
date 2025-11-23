"""
Billing Handler - Business Logic
Author: GitHub Copilot
Date: 2025-11-19
"""

from typing import Dict, Optional
import stripe
from fastapi import HTTPException
from config import config
from services.logger import app_logger as logger
from services.billing_service import BillingService

async def verify_checkout_session(
    session_id: str, 
    user_id: str,
    billing_service: BillingService
) -> Dict:
    """
    Verify checkout session and return subscription details
    
    Args:
        session_id: Stripe Checkout Session ID
        user_id: Quizify user ID (for verification)
        billing_service: Injected BillingService instance
        
    Returns:
        Dict with subscription details
        
    Raises:
        HTTPException: If session invalid or user mismatch
    """
    try:
        # Note: stripe.api_key is set by the injected billing_service instance (BillingService.__init__)
        
        # Retrieve session from Stripe
        session = stripe.checkout.Session.retrieve(
            session_id,
            expand=["subscription"]
        )
        
        # Verify session belongs to user
        session_user_id = session.metadata.get("user_id")
        if session_user_id != user_id:
            safe_session_user_id = session_user_id[:8] if session_user_id else "None"
            logger.warning(
                f"Session {session_id} user mismatch: "
                f"expected {user_id[:8]}, got {safe_session_user_id}"
            )
            raise HTTPException(
                status_code=403,
                detail="Session does not belong to this user"
            )
        
        # Verify payment status
        if session.payment_status != "paid":
            logger.warning(
                f"Session {session_id} payment not complete: "
                f"status={session.payment_status}"
            )
            raise HTTPException(
                status_code=400,
                detail=f"Payment not complete: {session.payment_status}"
            )
        
        # Extract subscription details
        subscription = session.subscription
        if isinstance(subscription, str):
            # Subscription not expanded, fetch it
            subscription = stripe.Subscription.retrieve(subscription)
        
        tier = session.metadata.get("tier", "free")
        
        # ------------------------------------------------------------------
        # PROVISIONING (Temporary Bridge for Epic 2 Testing)
        # ------------------------------------------------------------------
        # In a full production setup (Epic 3), this is handled by webhooks.
        # However, to make the "Upgrade" flow testable immediately without
        # waiting for async webhooks, we provision the user here synchronously.
        # This is safe because we verified payment_status="paid" above.
        # ------------------------------------------------------------------
        try:
            # Get price ID from subscription items using shared helper
            price_id = billing_service._extract_price_id_from_subscription(
                subscription,
                context=f"session {session_id} for user {user_id[:8]}"
            )
            
            if not price_id:
                raise HTTPException(
                    status_code=500,
                    detail="Price ID missing in subscription"
                )
            
            # Extract billing period dates from subscription object
            current_period_start = subscription.get("current_period_start")
            current_period_end = subscription.get("current_period_end")
            
            await billing_service.provision_subscription(
                user_id=user_id,
                customer_id=session.customer,
                subscription_id=subscription.id,
                subscription_status=subscription.status,
                price_id=price_id,
                current_period_start=current_period_start,
                current_period_end=current_period_end
            )
            logger.info(f"Synchronously provisioned subscription for user {user_id[:8]}")
            
        except Exception as e:
            # Log as CRITICAL because until Epic 3 (Webhooks) is implemented, this failure means
            # the user paid but didn't get the upgrade.
            logger.critical(f"Failed to synchronously provision subscription for user {user_id}: {e}")
            # Raise 500 to inform frontend and trigger retry/support contact
            raise HTTPException(
                status_code=500,
                detail="Payment succeeded but failed to provision subscription. Please contact support."
            )
        
        return {
            "session_id": session.id,
            "customer_id": session.customer,
            "subscription_id": subscription.id,
            "tier": tier,
            "status": subscription.status,
            "current_period_end": current_period_end,
            "payment_status": session.payment_status
        }
        
    except stripe.InvalidRequestError as e:
        logger.error(f"Invalid session ID {session_id}: {e}")
        raise HTTPException(
            status_code=404,
            detail="Checkout session not found"
        )
    except stripe.StripeError as e:
        logger.error(f"Stripe error verifying session {session_id}: {e}")
        raise HTTPException(
            status_code=502,
            detail="Failed to verify checkout session with Stripe"
        )
    except HTTPException:
        # Re-raise HTTPExceptions
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error verifying session {session_id}: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )
