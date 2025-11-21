-- ============================================================================
-- Migration 018: Remove Educator Tier from Database Constraint
-- ============================================================================
-- Purpose: Update account_tier CHECK constraint to only allow: free, basic, pro
-- Created: 2025-11-21
-- 
-- Background:
-- - "educator" tier was replaced by "pro" tier in Migration 016
-- - Current database constraint still allows "educator" (legacy)
-- - No users currently have "educator" tier (verified via query)
-- - This migration enforces the new tier system at the database level
-- ============================================================================

-- 1. Drop old constraint
ALTER TABLE public.profiles 
DROP CONSTRAINT IF EXISTS profiles_account_tier_check;

-- 2. Add new constraint with only current tiers
ALTER TABLE public.profiles 
ADD CONSTRAINT profiles_account_tier_check 
CHECK (account_tier IN ('free', 'basic', 'pro'));

-- 3. Verify no users are affected
DO $$
DECLARE
    educator_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO educator_count 
    FROM public.profiles 
    WHERE account_tier = 'educator';
    
    IF educator_count > 0 THEN
        RAISE EXCEPTION 'Cannot apply migration: % users still have educator tier. Migrate them to pro first.', educator_count;
    END IF;
    
    RAISE NOTICE 'Migration 018 completed successfully';
    RAISE NOTICE 'Database constraint now enforces: free, basic, pro only';
END $$;

-- ============================================================================
-- Notes
-- ============================================================================
-- This migration is safe because:
-- 1. No users currently have "educator" tier (verified)
-- 2. All views already use "free", "basic", "pro" logic (from Migration 017)
-- 3. Application code (schemas/user.py) uses Literal["free", "basic", "pro"]
-- 4. Database and application are now fully aligned
-- ============================================================================
