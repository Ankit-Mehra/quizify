-- Migration: 008 - Clean up redundant RLS policies
-- Date: 2025-10-17
-- Purpose: Remove conflicting public policies and keep only authenticated policies

-- ============================================================================
-- Profiles Table - Remove redundant public policies
-- ============================================================================

-- Drop the old public policies (they conflict with authenticated policies)
DROP POLICY IF EXISTS profiles_select_policy ON profiles;
DROP POLICY IF EXISTS profiles_update_policy ON profiles;
DROP POLICY IF EXISTS profiles_insert_policy ON profiles;

-- Keep these policies:
-- ✅ profiles_user_policy (authenticated, ALL) - Users manage their own profiles
-- ✅ profiles_admin_policy (authenticated, SELECT) - Admins view all profiles
-- ✅ "Allow auth admin to insert profiles" (supabase_auth_admin, INSERT) - System trigger

COMMENT ON TABLE profiles IS 
'User profiles - RLS enforced: users can manage their own profile, admins can view all profiles';

-- ============================================================================
-- Role Audit Log - Fix policy role from public to authenticated
-- ============================================================================

-- The audit_log_admin_policy should be for authenticated users, not public
DROP POLICY IF EXISTS audit_log_admin_policy ON role_audit_log;

-- Recreate with correct role (authenticated, not public)
CREATE POLICY audit_log_admin_policy 
ON role_audit_log FOR ALL 
TO authenticated  -- Changed from 'public' to 'authenticated'
USING (public.is_user_admin(auth.uid()));

COMMENT ON POLICY audit_log_admin_policy ON role_audit_log IS 
'Only admins can view and manage role audit logs (authenticated users only)';

-- ============================================================================
-- Verification
-- ============================================================================

DO $$
DECLARE
    profiles_policy_count INTEGER;
    profiles_public_policies INTEGER;
    audit_log_policy_role TEXT;
BEGIN
    -- Count profiles policies
    SELECT COUNT(*) INTO profiles_policy_count
    FROM pg_policies 
    WHERE tablename = 'profiles';
    
    -- Count profiles policies that use 'public' role (should be 1 or 0)
    SELECT COUNT(*) INTO profiles_public_policies
    FROM pg_policies 
    WHERE tablename = 'profiles' 
    AND 'public' = ANY(roles);
    
    -- Check audit log policy role
    SELECT ARRAY_TO_STRING(roles, ',') INTO audit_log_policy_role
    FROM pg_policies 
    WHERE tablename = 'role_audit_log' 
    AND policyname = 'audit_log_admin_policy';
    
    RAISE NOTICE '============================================';
    RAISE NOTICE 'Policy Cleanup Summary:';
    RAISE NOTICE '============================================';
    RAISE NOTICE 'Profiles table:';
    RAISE NOTICE '  Total policies: %', profiles_policy_count;
    RAISE NOTICE '  Public role policies: %', profiles_public_policies;
    
    IF profiles_public_policies <= 1 THEN
        -- 0 or 1 is OK (1 would be the supabase_auth_admin policy)
        RAISE NOTICE '  ✅ No conflicting public policies';
    ELSE
        RAISE WARNING '  ⚠️  Still has % public policies (expected 0-1)', profiles_public_policies;
    END IF;
    
    RAISE NOTICE '';
    RAISE NOTICE 'Role audit log:';
    RAISE NOTICE '  audit_log_admin_policy role: %', COALESCE(audit_log_policy_role, 'NOT FOUND');
    
    IF audit_log_policy_role = 'authenticated' THEN
        RAISE NOTICE '  ✅ Correctly set to authenticated';
    ELSE
        RAISE WARNING '  ⚠️  Expected "authenticated", got "%"', audit_log_policy_role;
    END IF;
    
    RAISE NOTICE '============================================';
    RAISE NOTICE 'Migration 008 completed!';
    RAISE NOTICE '============================================';
END $$;

-- Show final clean policy list
SELECT 
    tablename,
    policyname,
    roles,
    cmd,
    CASE 
        WHEN policyname LIKE '%admin%' THEN '👤 Admin'
        WHEN policyname LIKE '%user%' THEN '👥 User'
        WHEN 'supabase_auth_admin' = ANY(roles) THEN '🔧 System'
        ELSE '❓ Other'
    END as policy_type
FROM pg_policies 
WHERE schemaname = 'public' 
AND tablename IN ('profiles', 'role_audit_log')
ORDER BY tablename, policyname;
