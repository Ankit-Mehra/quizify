-- Migration: 031 - Fix user_tier_info view missing quizzes_attempted
-- Description: Adds back the quizzes_attempted field that was lost in migration 029
-- Date: 2025-12-10
-- 
-- ISSUE: Migration 029 recreated user_tier_info view without quizzes_attempted,
--        causing Pydantic validation errors in the UserTierInfo schema.

-- ============================================================================
-- SECTION 1: Recreate user_tier_info view with ALL required fields
-- ============================================================================

DROP VIEW IF EXISTS user_tier_info;

CREATE OR REPLACE VIEW user_tier_info AS
SELECT 
    u.id,
    u.email,
    p.display_name,
    
    -- Map billing_plan to account_tier for backward compatibility
    COALESCE(p.billing_plan, 'free') AS account_tier,
    COALESCE(p.role, 'user') AS role,
    
    -- Credit fields (3-bucket system: subscription + free + purchased)
    (COALESCE(p.credit_units_remaining, 0) + 
     COALESCE(p.credit_units_purchased, 0) + 
     COALESCE(p.free_credit_units_remaining, 0)) AS available_units,
    
    (COALESCE(p.credit_units_remaining, 0) + 
     COALESCE(p.credit_units_purchased, 0) + 
     COALESCE(p.free_credit_units_remaining, 0)) / 2.0 AS available_credits,
    
    -- Monthly allowance: Pro gets subscription (60) + free (6), Free users get just free (6)
    CASE 
        WHEN COALESCE(p.billing_plan, 'free') = 'pro' 
        THEN (COALESCE(p.credit_units_monthly, 60) + COALESCE(p.free_credit_units_monthly, 6)) / 2.0
        ELSE COALESCE(p.free_credit_units_monthly, 6) / 2.0
    END AS monthly_credits,
    
    COALESCE(p.credit_units_purchased, 0) / 2.0 AS purchased_credits,
    
    -- Individual bucket visibility (for debugging/admin)
    COALESCE(p.credit_units_remaining, 0) AS subscription_units_remaining,
    COALESCE(p.free_credit_units_remaining, 0) AS free_units_remaining,
    COALESCE(p.credit_units_purchased, 0) AS purchased_units,
    
    -- Period info
    p.current_period_start,
    p.current_period_end AS period_end,
    
    -- Stripe info
    p.stripe_customer_id,
    p.stripe_subscription_id,
    p.subscription_status,
    p.billing_plan,
    
    -- Quiz count fields (REQUIRED by UserTierInfo schema)
    (SELECT count(*) FROM quizzes q WHERE q.created_by = u.id)::INTEGER AS current_quiz_count,
    
    -- Quizzes attempted (submissions) - WAS MISSING IN 029!
    (SELECT count(*) FROM submissions s WHERE s.user_id = u.id)::INTEGER AS quizzes_attempted,
    
    -- Quota limit (legacy): 5 for free, -1 (unlimited) for pro
    CASE 
        WHEN COALESCE(p.billing_plan, 'free') = 'pro' THEN -1
        ELSE 5
    END AS quota_limit,
    
    -- Quota exceeded: Check if total credits <= 0
    ((COALESCE(p.credit_units_remaining, 0) + 
      COALESCE(p.credit_units_purchased, 0) + 
      COALESCE(p.free_credit_units_remaining, 0)) <= 0) AS quota_exceeded,
    
    p.created_at,
    p.updated_at

FROM auth.users u
LEFT JOIN public.profiles p ON u.id = p.id;

COMMENT ON VIEW user_tier_info IS 
'User billing info with 3-bucket credit status and quiz statistics. Includes quizzes_attempted for submission tracking.';
