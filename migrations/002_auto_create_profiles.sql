-- Migration: 002 - Auto-create Profiles on User Signup
-- Date: 2025-10-08
-- Purpose: Ensure every new user automatically gets a profiles record with default 'free' tier

-- ============================================================================
-- IMPORTANT: Supabase Security Note
-- ============================================================================
-- Creating triggers on auth.users requires superuser privileges in Supabase.
-- There are two ways to implement this:
--
-- Option A (RECOMMENDED): Use Supabase Dashboard Webhooks
--   1. Go to Authentication > Hooks in Supabase Dashboard
--   2. Enable "New user signup" hook
--   3. Point to an Edge Function that creates the profile
--
-- Option B (SQL - May require manual execution by Supabase support): 
--   Run this migration as shown below
--   If you get "must be owner of relation users" error, contact Supabase support
--   or use Option A instead
-- ============================================================================

-- ============================================================================
-- 1. Create trigger function to auto-create profiles
-- ============================================================================

-- Drop existing function if it exists (for re-running migration)
DROP FUNCTION IF EXISTS public.handle_new_user() CASCADE;

-- Create function that runs when a new user signs up
-- SECURITY DEFINER allows the function to run with elevated privileges
-- This is necessary because auth.users is in a different schema
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER 
SECURITY DEFINER
SET search_path = public
LANGUAGE plpgsql
AS $$
BEGIN
    -- Insert a new profile for the user with default 'free' tier
    -- ON CONFLICT DO NOTHING prevents errors if profile already exists
    -- Note: profiles table only has (id, account_tier, created_at, updated_at)
    INSERT INTO public.profiles (id, account_tier, created_at, updated_at)
    VALUES (
        NEW.id,
        'free',  -- Default tier for all new users
        COALESCE(NEW.created_at, NOW()),
        NOW()
    )
    ON CONFLICT (id) DO NOTHING;
    
    RETURN NEW;
EXCEPTION
    WHEN others THEN
        -- Log error but don't fail user signup
        RAISE WARNING 'Failed to create profile for user %: %', NEW.id, SQLERRM;
        RETURN NEW;
END;
$$;

COMMENT ON FUNCTION public.handle_new_user() IS 
'Automatically creates a profile record with free tier when a new user signs up via Supabase Auth';

-- ============================================================================
-- 2. Create trigger on auth.users table
-- ============================================================================
-- NOTE: This requires elevated privileges. If it fails, see alternative below.

-- Drop existing trigger if it exists (for re-running migration)
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;

-- Attempt to create trigger (may fail with permission error in some Supabase setups)
-- If this fails, use Supabase Auth Hooks instead (see top of file)
DO $$
BEGIN
    CREATE TRIGGER on_auth_user_created
        AFTER INSERT ON auth.users
        FOR EACH ROW
        EXECUTE FUNCTION public.handle_new_user();
    
    RAISE NOTICE 'Successfully created trigger on auth.users';
EXCEPTION
    WHEN insufficient_privilege THEN
        RAISE NOTICE '========================================';
        RAISE NOTICE 'TRIGGER CREATION FAILED - INSUFFICIENT PRIVILEGES';
        RAISE NOTICE '========================================';
        RAISE NOTICE 'Cannot create trigger on auth.users due to permissions.';
        RAISE NOTICE 'ALTERNATIVE SOLUTION:';
        RAISE NOTICE '1. Go to Supabase Dashboard > Authentication > Hooks';
        RAISE NOTICE '2. Enable "New user signup" hook';
        RAISE NOTICE '3. Create an Edge Function with this code:';
        RAISE NOTICE '';
        RAISE NOTICE 'import { createClient } from "@supabase/supabase-js"';
        RAISE NOTICE '';
        RAISE NOTICE 'Deno.serve(async (req) => {';
        RAISE NOTICE '  const supabase = createClient(env.SUPABASE_URL, env.SERVICE_ROLE_KEY)';
        RAISE NOTICE '  const { user } = await req.json()';
        RAISE NOTICE '  await supabase.from("profiles").insert({';
        RAISE NOTICE '    id: user.id,';
        RAISE NOTICE '    email: user.email,';
        RAISE NOTICE '    account_tier: "free"';
        RAISE NOTICE '  })';
        RAISE NOTICE '  return new Response("OK")';
        RAISE NOTICE '})';
        RAISE NOTICE '';
        RAISE NOTICE '========================================';
END;
$$;

-- ============================================================================
-- 3. Backfill existing users without profiles (if any)
-- ============================================================================
-- This works regardless of whether the trigger was successfully created

DO $$
DECLARE
    backfilled_count INTEGER;
    total_users INTEGER;
    total_profiles INTEGER;
    users_without_profiles INTEGER;
BEGIN
    -- Backfill: Create profiles for existing users without them
    INSERT INTO public.profiles (id, account_tier, created_at, updated_at)
    SELECT 
        u.id,
        'free' AS account_tier,
        u.created_at,
        NOW() AS updated_at
    FROM auth.users u
    LEFT JOIN public.profiles p ON u.id = p.id
    WHERE p.id IS NULL  -- Only insert for users without profiles
    ON CONFLICT (id) DO NOTHING;
    
    GET DIAGNOSTICS backfilled_count = ROW_COUNT;
    RAISE NOTICE 'Backfill completed - created % profiles for existing users', backfilled_count;
    
    -- ============================================================================
    -- 4. Verify migration success
    -- ============================================================================
    
    -- Count users and profiles
    SELECT COUNT(*) INTO total_users FROM auth.users;
    SELECT COUNT(*) INTO total_profiles FROM public.profiles;
    
    -- Check for users without profiles
    SELECT COUNT(*) INTO users_without_profiles 
    FROM auth.users u
    LEFT JOIN public.profiles p ON u.id = p.id
    WHERE p.id IS NULL;
    
    -- Report results
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Migration 002 Status';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Total users in auth.users: %', total_users;
    RAISE NOTICE 'Total profiles in public.profiles: %', total_profiles;
    RAISE NOTICE 'Users without profiles: %', users_without_profiles;
    RAISE NOTICE '';
    
    IF users_without_profiles > 0 THEN
        RAISE WARNING 'Found % users without profiles. This should not happen after backfill.', users_without_profiles;
    ELSE
        RAISE NOTICE '✓ All users have profiles';
    END IF;
    
    RAISE NOTICE '';
    RAISE NOTICE 'NEXT STEPS:';
    RAISE NOTICE '1. Set up Database Webhook for automatic profile creation';
    RAISE NOTICE '2. See migrations/SUPABASE_AUTH_HOOKS_GUIDE.md for instructions';
    RAISE NOTICE '========================================';
END $$;
