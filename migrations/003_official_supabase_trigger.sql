-- Migration: 007 - Official Supabase Pattern for Auto-Creating Profiles
-- Source: https://supabase.com/docs/guides/auth/managing-user-data
-- Date: 2025-10-09

-- ============================================================================
-- This is the OFFICIAL Supabase pattern from their documentation
-- ============================================================================

-- Step 1: Drop any existing function and trigger
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
DROP FUNCTION IF EXISTS public.handle_new_user() CASCADE;
DROP FUNCTION IF EXISTS public.handle_new_user(jsonb) CASCADE;

-- Step 2: Create the trigger function (OFFICIAL pattern from Supabase docs)
-- Key differences from what we tried:
-- 1. RETURNS trigger (not jsonb) - because it's a TRIGGER function
-- 2. SET search_path = '' - security best practice
-- 3. Uses NEW.id directly (not from jsonb parameter)

CREATE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
  INSERT INTO public.profiles (id, account_tier)
  VALUES (NEW.id, 'free')
  ON CONFLICT (id) DO NOTHING;
  
  RETURN NEW;
END;
$$;

-- Step 3: Create trigger on auth.users table
-- This might fail with permission error in some Supabase setups
-- If it fails, we'll need to contact Supabase support or use app-level solution

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW
  EXECUTE PROCEDURE public.handle_new_user();

-- ============================================================================
-- Verification
-- ============================================================================

-- Check if trigger was created
SELECT 
    tgname as trigger_name,
    tgenabled as is_enabled,
    tgrelid::regclass as table_name
FROM pg_trigger
WHERE tgname = 'on_auth_user_created';

-- Check if function exists
SELECT 
    p.proname as function_name,
    pg_get_function_result(p.oid) as return_type
FROM pg_proc p
WHERE p.proname = 'handle_new_user';

-- ============================================================================
-- Notes
-- ============================================================================
-- If you get an error like:
-- "ERROR: permission denied to create trigger on table users"
--
-- This means your Supabase project doesn't allow triggers on auth.users.
-- In that case, you have two options:
--
-- Option A: Contact Supabase support to enable it
-- Option B: Use application-level profile creation (more reliable anyway)
-- ============================================================================
