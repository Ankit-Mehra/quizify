-- Migration 037: Fix new user period fields initialization
--
-- Problem:
-- Some environments have a version of public.handle_new_user() that does not
-- initialize profiles.current_period_start / profiles.current_period_end,
-- resulting in NULL values for newly created profiles.
--
-- Fix (minimal / non-regressive):
-- 1) Replace public.handle_new_user() to always set current_period_*.
-- 2) Backfill existing profiles with NULL period fields.

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  v_display_name TEXT;
  v_avatar_url TEXT;
BEGIN
  v_display_name := COALESCE(
    NEW.raw_user_meta_data->>'full_name',
    NEW.raw_user_meta_data->>'name',
    NULL
  );

  v_avatar_url := COALESCE(
    NEW.raw_user_meta_data->>'avatar_url',
    NEW.raw_user_meta_data->>'picture',
    NULL
  );

  INSERT INTO public.profiles (
    id,
    account_tier,
    billing_plan,
    current_period_start,
    current_period_end,
    display_name,
    avatar_url,
    created_at,
    updated_at
  )
  VALUES (
    NEW.id,
    'free',
    'free',
    date_trunc('month', now()),
    date_trunc('month', now()) + interval '1 month',
    v_display_name,
    v_avatar_url,
    COALESCE(NEW.created_at, now()),
    now()
  )
  ON CONFLICT (id) DO UPDATE
  SET
    -- Keep profile enrichment idempotent (don’t overwrite existing values)
    display_name = COALESCE(EXCLUDED.display_name, public.profiles.display_name),
    avatar_url = COALESCE(EXCLUDED.avatar_url, public.profiles.avatar_url),

    -- Ensure required billing window exists
    current_period_start = COALESCE(public.profiles.current_period_start, EXCLUDED.current_period_start),
    current_period_end = COALESCE(public.profiles.current_period_end, EXCLUDED.current_period_end),

    updated_at = now();

  RETURN NEW;
EXCEPTION
  WHEN others THEN
    -- Never block auth signup.
    RAISE WARNING 'Failed to create/update profile for user %: %', NEW.id, SQLERRM;
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION public.handle_new_user IS
'Creates/updates profiles row on auth.users INSERT, ensuring billing period boundaries are always initialized.';

-- ============================================================================
-- Backfill NULL period fields for existing profiles
-- ============================================================================

UPDATE public.profiles
SET
  current_period_start = COALESCE(current_period_start, date_trunc('month', now())),
  current_period_end = COALESCE(current_period_end, date_trunc('month', now()) + interval '1 month'),
  updated_at = NOW()
WHERE current_period_start IS NULL OR current_period_end IS NULL;
