# Database Migrations

This directory contains SQL migration files for the Quizify database schema.

## Migration Files

### 001_add_missing_features.sql
**Date**: 2025-10-03  
**Status**: ✅ Applied to production

**Purpose**: Add tier management, content source tracking, file size validation, and search indexes

**Changes**:
- Verified profiles table with `account_tier` column
- Added `content_source_type` and `content_source_reference` to quizzes
- Added `file_size_bytes` to user_files
- Created search indexes for quiz titles (trigram + GIN)
- Created `user_quiz_counts` view (real-time count per user)
- Created `user_tier_info` view (combines users + profiles + quotas)
- Added row-level security policies

---

### 002_auto_create_profiles.sql
**Date**: 2025-10-08  
**Status**: ⏳ Pending deployment

**Purpose**: Ensure every new user automatically gets a profiles record with default 'free' tier

**Changes**:
- Created `handle_new_user()` trigger function
- Created `on_auth_user_created` trigger on auth.users table
- Backfills profiles for existing users without records
- Verifies all users have profiles after migration

**Why this is needed**:
- Prevents issues where new users don't have profiles
- Ensures `user_tier_info` view always returns data
- Eliminates race conditions in profile creation
- Guarantees all users start with 'free' tier

---

## How to Apply Migrations

### Method 1: Supabase Dashboard (Recommended)

1. Open your Supabase project dashboard
2. Go to **SQL Editor**
3. Click **New Query**
4. Copy the entire contents of the migration file
5. Paste into the query editor
6. Click **Run** (or press Cmd+Enter / Ctrl+Enter)
7. Check the **Results** tab for success messages and logs

### Method 2: Supabase CLI

```bash
# Install Supabase CLI if not already installed
npm install -g supabase

# Login to Supabase
supabase login

# Link to your project
supabase link --project-ref YOUR_PROJECT_REF

# Run migration (replace with actual filename)
supabase db push migrations/002_auto_create_profiles.sql
```

### Method 3: Direct psql Connection

```bash
# Get connection string from Supabase Dashboard -> Settings -> Database
psql "postgresql://postgres:[YOUR-PASSWORD]@[YOUR-HOST].supabase.co:5432/postgres"

# Run migration
\i migrations/002_auto_create_profiles.sql
```

---

## Verification After Migration

After applying a migration, verify it worked:

```sql
-- Check if trigger exists
SELECT tgname, tgenabled 
FROM pg_trigger 
WHERE tgname = 'on_auth_user_created';

-- Check if function exists
SELECT proname, prosrc 
FROM pg_proc 
WHERE proname = 'handle_new_user';

-- Verify all users have profiles
SELECT 
    COUNT(u.id) as total_users,
    COUNT(p.id) as total_profiles,
    COUNT(u.id) - COUNT(p.id) as missing_profiles
FROM auth.users u
LEFT JOIN public.profiles p ON u.id = p.id;

-- Test the user_tier_info view
SELECT * FROM user_tier_info LIMIT 5;
```

---

## Testing the Profile Trigger

To test if the trigger works without creating a real user:

```sql
-- This will simulate what happens when a user signs up
-- (Don't run in production - for testing only)

BEGIN;
-- Create a test user in auth.users
INSERT INTO auth.users (id, email, encrypted_password, email_confirmed_at, created_at, updated_at)
VALUES (
    gen_random_uuid(),
    'test-trigger@example.com',
    'test-encrypted-password',
    NOW(),
    NOW(),
    NOW()
);

-- Check if profile was auto-created
SELECT * FROM public.profiles WHERE email = 'test-trigger@example.com';

-- Rollback to clean up test data
ROLLBACK;
```

---

## Migration Ordering

Migrations must be applied in order:
1. `001_add_missing_features.sql` (base schema)
2. `002_auto_create_profiles.sql` (trigger setup)

---

## Rollback Instructions

### Rollback 002_auto_create_profiles.sql

```sql
-- Remove trigger
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;

-- Remove function
DROP FUNCTION IF EXISTS public.handle_new_user() CASCADE;

-- Note: We don't delete profiles created during backfill
-- as they contain important user data
```

### Rollback 001_add_missing_features.sql

```sql
-- Remove views
DROP VIEW IF EXISTS user_tier_info CASCADE;
DROP VIEW IF EXISTS user_quiz_counts CASCADE;

-- Remove columns (careful - this deletes data!)
ALTER TABLE quizzes DROP COLUMN IF EXISTS content_source_type;
ALTER TABLE quizzes DROP COLUMN IF EXISTS content_source_reference;
ALTER TABLE user_files DROP COLUMN IF EXISTS file_size_bytes;

-- Remove indexes
DROP INDEX IF EXISTS idx_quizzes_title_search;
DROP INDEX IF EXISTS idx_quizzes_title_trgm;
DROP INDEX IF EXISTS idx_quizzes_source_type;

-- Note: We keep the profiles.account_tier column as it's part of base schema
```

---

## Notes

- **Always backup your database before running migrations**
- Test migrations in a development environment first
- Check Supabase logs after applying migrations
- Migrations are idempotent (can be run multiple times safely)
- Use `IF EXISTS` / `IF NOT EXISTS` clauses to prevent errors on re-runs
