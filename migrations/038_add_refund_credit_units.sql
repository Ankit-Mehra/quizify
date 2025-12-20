-- Migration: 038 - Add Refund Credit Units Function
-- Description: RPC function for refunding credits on failed quiz generation
-- Date: 2025-12-19
-- 
-- SECURITY: This function is restricted to service_role only.
-- It should only be called from the backend with the service role key.
--
-- PURPOSE: Enables atomic credit reservation pattern to prevent TOCTOU race conditions:
-- 1. Consume credits BEFORE quiz generation (atomic)
-- 2. If generation fails, refund credits (this function)
-- This prevents concurrent requests from bypassing credit limits.

-- ============================================================================
-- SECTION 1: Atomic refund_credit_units function
-- ============================================================================

-- Atomically refund credit units after failed quiz generation
-- Adds units back to free_credit_units_remaining (simplest approach)
-- SECURITY: Only callable by service_role (backend)
CREATE OR REPLACE FUNCTION public.refund_credit_units(
    p_user_id UUID,
    p_units INT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_caller_role TEXT;
    v_is_service_role BOOLEAN;
BEGIN
    -- Validate input
    IF p_units <= 0 THEN
        RAISE EXCEPTION 'Invalid refund amount: %. Units must be positive.', p_units;
    END IF;
    
    -- Prevent integer overflow/abuse (max 1 million units = 500k credits)
    IF p_units > 1000000 THEN
        RAISE EXCEPTION 'Refund amount too large: %. Max allowed is 1,000,000 units.', p_units;
    END IF;

    -- Check current balance to prevent overflow (max 10 million units)
    IF EXISTS (
        SELECT 1 FROM public.profiles 
        WHERE id = p_user_id 
        AND (COALESCE(free_credit_units_remaining, 0) + p_units) > 10000000
    ) THEN
        RAISE EXCEPTION 'Refund would exceed maximum credit balance limit (10,000,000 units).';
    END IF;

    -- ========================================================================
    -- SECURITY CHECK: Verify caller is service_role (backend only)
    -- ========================================================================
    v_caller_role := current_setting('request.jwt.claim.role', true);
    v_is_service_role := (
        v_caller_role = 'service_role' OR
        current_user = 'service_role' OR
        session_user IN ('postgres', 'service_role')
    );
    
    IF NOT v_is_service_role THEN
        RAISE EXCEPTION 'Access denied: this function requires service_role privileges (got role=%, user=%)', 
            COALESCE(v_caller_role, 'NULL'), current_user;
    END IF;

    -- ========================================================================
    -- ATOMIC INCREMENT: Add units back to free bucket with overflow protection
    -- ========================================================================
    -- Note: We always refund to free_credit_units_remaining for simplicity.
    -- This is slightly favorable to users (they get free credits back even if
    -- they originally paid), but it's fair given they didn't get a quiz.
    -- 
    -- SECURITY: Cap refunds to prevent integer overflow or abuse.
    -- Max free_credit_units_remaining is capped at monthly allocation (6 for free, 80 for pro)
    -- plus a reasonable buffer. 100 units should cover any legitimate case.
    UPDATE public.profiles
    SET 
        free_credit_units_remaining = LEAST(
            COALESCE(free_credit_units_remaining, 0) + p_units,
            100  -- Cap at 100 units to prevent overflow/abuse
        ),
        updated_at = now()
    WHERE id = p_user_id;
    
    -- If no rows updated, user doesn't exist
    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;
    
    RETURN TRUE;
END;
$$;

COMMENT ON FUNCTION public.refund_credit_units IS 
'Atomically refund credit units after failed quiz generation. Part of atomic reservation pattern to prevent TOCTOU race conditions.';


-- ============================================================================
-- SECTION 2: Security - Grant permissions to service_role ONLY
-- ============================================================================

-- This function can modify ANY user's credits, so must be restricted to backend
REVOKE ALL ON FUNCTION public.refund_credit_units(UUID, INT) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.refund_credit_units(UUID, INT) FROM authenticated;
REVOKE ALL ON FUNCTION public.refund_credit_units(UUID, INT) FROM anon;
GRANT EXECUTE ON FUNCTION public.refund_credit_units(UUID, INT) TO service_role;
