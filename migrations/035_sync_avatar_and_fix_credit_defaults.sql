-- Migration 035: Sync avatar URLs and fix credit defaults for free users
-- 
-- Issues Fixed:
-- 1. Existing users missing avatar_url in profiles (trigger only ran on INSERT)
-- 2. Free users incorrectly getting subscription credits (defaults were wrong)
--
-- Run Date: 2025-12-13

-- ============================================================================
-- PART 1: Sync avatar_url from auth.users to profiles for existing users
-- ============================================================================
-- The handle_new_user trigger syncs avatar on INSERT, but existing users
-- who signed up before the trigger was updated are missing their avatars.

UPDATE profiles p
SET 
    avatar_url = COALESCE(
        u.raw_user_meta_data->>'avatar_url',
        u.raw_user_meta_data->>'picture'
    ),
    updated_at = NOW()
FROM auth.users u
WHERE p.id = u.id
  AND p.avatar_url IS NULL
  AND (u.raw_user_meta_data->>'avatar_url' IS NOT NULL 
       OR u.raw_user_meta_data->>'picture' IS NOT NULL);

-- ============================================================================
-- PART 2: Fix credit defaults - subscription credits should only be for Pro
-- ============================================================================
-- Previously, column defaults gave ALL users subscription credits (credit_units_remaining=6)
-- Free users should only have free_credit_units, not subscription credits.

-- 2a. Change defaults for new users
ALTER TABLE profiles 
ALTER COLUMN credit_units_remaining SET DEFAULT 0;

ALTER TABLE profiles 
ALTER COLUMN credit_units_monthly SET DEFAULT 0;

-- 2b. Fix existing free users who incorrectly have subscription credits
UPDATE profiles 
SET 
    credit_units_remaining = 0,
    credit_units_monthly = 0
WHERE billing_plan = 'free' 
  AND (credit_units_remaining > 0 OR credit_units_monthly > 0);

-- ============================================================================
-- PART 3: Add documentation comments
-- ============================================================================
COMMENT ON COLUMN profiles.credit_units_remaining IS 'Subscription credits (Pro plan only). Default 0 for free users.';
COMMENT ON COLUMN profiles.credit_units_monthly IS 'Monthly subscription credit quota (Pro plan only). Default 0 for free users.';
COMMENT ON COLUMN profiles.free_credit_units_remaining IS 'Free tier credits available to ALL users (including Pro). Resets monthly.';
COMMENT ON COLUMN profiles.free_credit_units_monthly IS 'Monthly free credit quota for all users. Default 6 units = 3 credits.';
COMMENT ON COLUMN profiles.avatar_url IS 'User avatar URL from OAuth providers (Google, etc). Synced from auth.users on signup.';
