-- Migration: 004 - Add Role-Based Access Control (RBAC)
-- Date: 2025-10-09
-- Purpose: Replace UUID-based admin authorization with proper role-based system

-- ============================================================================
-- 1. Add role column to profiles table
-- ============================================================================

-- Add role column with CHECK constraint
-- Valid roles: 'user' (default), 'admin', 'moderator'
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'user' 
CHECK (role IN ('user', 'admin', 'moderator'));

-- Add index for role queries (performance optimization)
CREATE INDEX IF NOT EXISTS idx_profiles_role ON public.profiles(role);

-- Add comment for documentation
COMMENT ON COLUMN public.profiles.role IS 
'User role for access control: user (default), admin (full access), moderator (limited admin access)';

-- ============================================================================
-- 2. Set default role for existing users without role
-- ============================================================================

-- Ensure all existing profiles have 'user' role if role is NULL
UPDATE public.profiles 
SET role = 'user' 
WHERE role IS NULL;

-- ============================================================================
-- 3. Promote initial admin(s) based on environment variable
-- ============================================================================

-- IMPORTANT: After running this migration, you need to manually promote 
-- your first admin user by running one of these commands:
--
-- Option 1: Promote by email
-- UPDATE public.profiles 
-- SET role = 'admin' 
-- WHERE id = (SELECT id FROM auth.users WHERE email = 'your-admin@example.com');
--
-- Option 2: Promote by user ID (if you know it)
-- UPDATE public.profiles 
-- SET role = 'admin' 
-- WHERE id = 'YOUR-USER-UUID-HERE';
--
-- Option 3: Promote multiple admins
-- UPDATE public.profiles 
-- SET role = 'admin' 
-- WHERE id IN (
--   SELECT id FROM auth.users 
--   WHERE email IN ('admin1@example.com', 'admin2@example.com')
-- );

-- ============================================================================
-- 4. Update user_tier_info view to include role
-- ============================================================================

-- Drop existing view
DROP VIEW IF EXISTS user_tier_info;

-- Recreate with role column
CREATE OR REPLACE VIEW user_tier_info AS
SELECT 
    u.id,
    u.email,
    COALESCE(p.account_tier, 'free') AS account_tier,
    COALESCE(p.role, 'user') AS role,  -- NEW: Include role
    COALESCE(q.quiz_count, 0) AS current_quiz_count,
    CASE 
        WHEN COALESCE(p.account_tier, 'free') = 'free' THEN 5
        WHEN COALESCE(p.account_tier, 'free') = 'basic' THEN 100
        WHEN COALESCE(p.account_tier, 'free') = 'educator' THEN 500
        ELSE 5
    END AS quota_limit,
    CASE 
        WHEN COALESCE(p.account_tier, 'free') = 'free' THEN COALESCE(q.quiz_count, 0) >= 5
        WHEN COALESCE(p.account_tier, 'free') = 'basic' THEN COALESCE(q.quiz_count, 0) >= 100
        WHEN COALESCE(p.account_tier, 'free') = 'educator' THEN COALESCE(q.quiz_count, 0) >= 500
        ELSE true
    END AS quota_exceeded,
    p.created_at,
    p.updated_at
FROM auth.users u
LEFT JOIN public.profiles p ON u.id = p.id
LEFT JOIN user_quiz_counts q ON u.id = q.user_id;

COMMENT ON VIEW user_tier_info IS 
'User tier and role information with quota status for enforcement and admin panel';

-- ============================================================================
-- 5. Create helper function to check if user is admin
-- ============================================================================

-- Function to check if a user has admin role
CREATE OR REPLACE FUNCTION public.is_user_admin(user_uuid UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    user_role TEXT;
BEGIN
    SELECT role INTO user_role
    FROM public.profiles
    WHERE id = user_uuid;
    
    RETURN COALESCE(user_role, 'user') = 'admin';
END;
$$;

COMMENT ON FUNCTION public.is_user_admin(UUID) IS 
'Check if a user has admin role - useful for RLS policies';

-- ============================================================================
-- 6. Add audit log for role changes (optional but recommended)
-- ============================================================================

-- Create audit table for tracking role changes
CREATE TABLE IF NOT EXISTS public.role_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    old_role TEXT,
    new_role TEXT NOT NULL,
    changed_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    reason TEXT,
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Add constraint to ensure valid roles
    CHECK (old_role IN ('user', 'admin', 'moderator') OR old_role IS NULL),
    CHECK (new_role IN ('user', 'admin', 'moderator'))
);

-- Add index for audit queries
CREATE INDEX IF NOT EXISTS idx_role_audit_user ON public.role_audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_role_audit_changed_by ON public.role_audit_log(changed_by);
CREATE INDEX IF NOT EXISTS idx_role_audit_changed_at ON public.role_audit_log(changed_at DESC);

COMMENT ON TABLE public.role_audit_log IS 
'Audit trail for role changes - tracks who changed roles and when';

-- Enable RLS on audit log
ALTER TABLE public.role_audit_log ENABLE ROW LEVEL SECURITY;

-- Policy: Only admins can view audit log
DROP POLICY IF EXISTS audit_log_admin_policy ON public.role_audit_log;
CREATE POLICY audit_log_admin_policy 
ON public.role_audit_log FOR ALL 
USING (public.is_user_admin(auth.uid()));

-- ============================================================================
-- Migration Complete
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Migration 004 completed successfully';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Added: role column to profiles table';
    RAISE NOTICE 'Updated: user_tier_info view includes role';
    RAISE NOTICE 'Created: is_user_admin() helper function';
    RAISE NOTICE 'Created: role_audit_log table for tracking changes';
    RAISE NOTICE '';
    RAISE NOTICE 'NEXT STEPS:';
    RAISE NOTICE '1. Promote your first admin user:';
    RAISE NOTICE '   UPDATE profiles SET role = ''admin'' WHERE id = (SELECT id FROM auth.users WHERE email = ''your-email@example.com'');';
    RAISE NOTICE '';
    RAISE NOTICE '2. Verify role was set:';
    RAISE NOTICE '   SELECT email, role FROM user_tier_info WHERE role = ''admin'';';
    RAISE NOTICE '';
    RAISE NOTICE '3. Deploy updated application code';
    RAISE NOTICE '4. Remove ADMIN_USER_IDS environment variable (no longer needed)';
    RAISE NOTICE '========================================';
END $$;
