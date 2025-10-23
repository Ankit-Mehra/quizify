-- Migration: 009 - Add name to profiles table and update trigger
-- Date: 2025-10-23
-- Purpose: Store user's display name in profiles table from signup

-- ============================================================================
-- Step 1: Add name column to profiles table
-- ============================================================================

ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS display_name TEXT;

COMMENT ON COLUMN public.profiles.display_name IS 
'User display name extracted from auth.users.raw_user_meta_data during signup';

-- ============================================================================
-- Step 2: Update trigger function to extract and save name
-- ============================================================================

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
  -- Extract name from raw_user_meta_data if present
  INSERT INTO public.profiles (id, account_tier, display_name, created_at, updated_at)
  VALUES (
    NEW.id, 
    'free',
    COALESCE(NEW.raw_user_meta_data->>'name', NULL),  -- Extract 'name' from metadata
    COALESCE(NEW.created_at, NOW()),
    NOW()
  )
  ON CONFLICT (id) DO UPDATE
  SET 
    display_name = COALESCE(EXCLUDED.display_name, public.profiles.display_name),
    updated_at = NOW();
  
  RETURN NEW;
EXCEPTION
  WHEN others THEN
    -- Log error but don't fail user signup
    RAISE WARNING 'Failed to create/update profile for user %: %', NEW.id, SQLERRM;
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION public.handle_new_user() IS 
'Trigger function that auto-creates profile with free tier and extracts display name from user metadata on signup';

-- ============================================================================
-- Step 3: Backfill existing users' names from auth.users metadata
-- ============================================================================

DO $$
DECLARE
    updated_count INTEGER;
BEGIN
    -- Update existing profiles with names from auth.users metadata
    WITH name_updates AS (
        UPDATE public.profiles p
        SET display_name = u.raw_user_meta_data->>'name'
        FROM auth.users u
        WHERE p.id = u.id 
        AND p.display_name IS NULL  -- Only update if not already set
        AND u.raw_user_meta_data->>'name' IS NOT NULL  -- Only if name exists in metadata
        RETURNING p.id
    )
    SELECT COUNT(*) INTO updated_count FROM name_updates;
    
    RAISE NOTICE 'Backfilled % user names from metadata to profiles', updated_count;
END $$;

-- ============================================================================
-- Step 4: Verification
-- ============================================================================

-- Check profiles table structure
SELECT 
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' 
AND table_name = 'profiles'
ORDER BY ordinal_position;

-- Sample: Show first 5 profiles with names
SELECT 
    p.id,
    p.display_name,
    p.account_tier,
    u.email,
    u.raw_user_meta_data->>'name' as metadata_name
FROM public.profiles p
LEFT JOIN auth.users u ON p.id = u.id
LIMIT 5;

-- ============================================================================
-- Notes
-- ============================================================================
-- After this migration:
-- 1. New signups will automatically have their name saved to profiles.display_name
-- 2. Existing users' names will be backfilled from auth.users.raw_user_meta_data
-- 3. The name field is optional (NULL allowed) in case signup doesn't provide it
-- ============================================================================
