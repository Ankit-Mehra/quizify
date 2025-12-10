-- Migration: 030 - Atomic Credit Operations
-- Description: RPC functions for race-safe credit consumption and addition
-- Date: 2025-12-09
-- 
-- SECURITY: These functions are restricted to service_role only.
-- They should only be called from the backend with the service role key.
-- Authenticated users cannot call these directly.
--
-- PURPOSE: Prevents race conditions where concurrent quiz starts could 
-- double-spend credits by using FOR UPDATE row locking.

-- ============================================================================
-- SECTION 1: Atomic consume_credit_units function
-- ============================================================================

-- Atomically consume credit units with priority: purchased → free → subscription
-- Returns TRUE if units were successfully consumed, FALSE if insufficient units
-- SECURITY: Only callable by service_role (backend)
CREATE OR REPLACE FUNCTION public.consume_credit_units(
    p_user_id UUID,
    p_units_needed INT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_purchased INT;
    v_free INT;
    v_subscription INT;
    v_total INT;
    v_remaining INT;
    v_take_purchased INT;
    v_take_free INT;
    v_take_subscription INT;
    v_caller_role TEXT;
    v_is_service_role BOOLEAN;
BEGIN
    -- ========================================================================
    -- SECURITY CHECK: Verify caller is service_role (backend only)
    -- ========================================================================
    -- Check JWT claim (PostgREST), current_user (direct), and session_user
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
    -- ATOMIC OPERATION: Lock row and check balances
    -- ========================================================================
    -- FOR UPDATE prevents concurrent modifications (race condition fix)
    SELECT 
        COALESCE(credit_units_purchased, 0),
        COALESCE(free_credit_units_remaining, 0),
        COALESCE(credit_units_remaining, 0)
    INTO v_purchased, v_free, v_subscription
    FROM public.profiles
    WHERE id = p_user_id
    FOR UPDATE;
    
    -- Check if user exists
    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;
    
    -- Calculate total available across all buckets
    v_total := v_purchased + v_free + v_subscription;
    
    -- Check if sufficient units
    IF v_total < p_units_needed THEN
        RETURN FALSE;
    END IF;
    
    -- ========================================================================
    -- CONSUMPTION: Priority order purchased → free → subscription
    -- ========================================================================
    -- Rationale: Use purchased first (already paid), then free allowance,
    --            preserve subscription credits longest (monthly value)
    v_remaining := p_units_needed;
    
    -- 1. Take from purchased first (one-time purchases, use first)
    v_take_purchased := LEAST(v_purchased, v_remaining);
    v_remaining := v_remaining - v_take_purchased;
    
    -- 2. Take from free second (monthly free allowance)
    v_take_free := LEAST(v_free, v_remaining);
    v_remaining := v_remaining - v_take_free;
    
    -- 3. Take from subscription last (preserve paid subscription credits)
    v_take_subscription := v_remaining;  -- Whatever is left
    
    -- ========================================================================
    -- UPDATE: Atomically update all three buckets
    -- ========================================================================
    UPDATE public.profiles
    SET 
        credit_units_purchased = credit_units_purchased - v_take_purchased,
        free_credit_units_remaining = free_credit_units_remaining - v_take_free,
        credit_units_remaining = credit_units_remaining - v_take_subscription,
        updated_at = now()
    WHERE id = p_user_id;
    
    RETURN TRUE;
END;
$$;

COMMENT ON FUNCTION public.consume_credit_units IS 
'Atomically consume credit units for quiz generation. Priority: purchased → free → subscription. Returns FALSE if insufficient credits.';


-- ============================================================================
-- SECTION 2: Atomic add_purchased_credit_units function
-- ============================================================================

-- Safely increments purchased credits without race conditions
-- SECURITY: Only callable by service_role (backend)
CREATE OR REPLACE FUNCTION public.add_purchased_credit_units(
    p_user_id UUID,
    p_units INT
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_caller_role TEXT;
    v_is_service_role BOOLEAN;
BEGIN
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
    -- ATOMIC INCREMENT: Add units to purchased bucket
    -- ========================================================================
    UPDATE public.profiles
    SET 
        credit_units_purchased = COALESCE(credit_units_purchased, 0) + p_units,
        updated_at = now()
    WHERE id = p_user_id;
    
    -- If no rows updated, user doesn't exist
    IF NOT FOUND THEN
        RAISE EXCEPTION 'User % not found', p_user_id;
    END IF;
END;
$$;

COMMENT ON FUNCTION public.add_purchased_credit_units IS 
'Atomically add purchased credit units to a user profile. Called after successful credit pack purchase.';


-- ============================================================================
-- SECTION 3: Security - Grant permissions to service_role ONLY
-- ============================================================================

-- These functions can modify ANY user's credits, so must be restricted to backend
-- Defense in depth: Function checks role internally + database permission restriction

-- consume_credit_units: Revoke from everyone, grant only to service_role
REVOKE ALL ON FUNCTION public.consume_credit_units(UUID, INT) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.consume_credit_units(UUID, INT) FROM authenticated;
REVOKE ALL ON FUNCTION public.consume_credit_units(UUID, INT) FROM anon;
GRANT EXECUTE ON FUNCTION public.consume_credit_units(UUID, INT) TO service_role;

-- add_purchased_credit_units: Revoke from everyone, grant only to service_role
REVOKE ALL ON FUNCTION public.add_purchased_credit_units(UUID, INT) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.add_purchased_credit_units(UUID, INT) FROM authenticated;
REVOKE ALL ON FUNCTION public.add_purchased_credit_units(UUID, INT) FROM anon;
GRANT EXECUTE ON FUNCTION public.add_purchased_credit_units(UUID, INT) TO service_role;
