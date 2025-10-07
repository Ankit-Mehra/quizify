#!/usr/bin/env python3
"""
One-time script to add account_tier column to auth.users table.
This requires the SERVICE_ROLE_KEY (not the anon key) which has admin privileges.

WARNING: Keep your service role key secure and never commit it to git!
"""

import os
from supabase import create_client, Client

# You need the SERVICE_ROLE_KEY for this (not the anon key)
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://dqxzzyoqwaegdnwijgqn.supabase.co")
SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")  # Get from Supabase Dashboard > Settings > API

if not SERVICE_ROLE_KEY:
    print("❌ ERROR: SUPABASE_SERVICE_ROLE_KEY environment variable not set")
    print("\nTo get your service role key:")
    print("1. Go to https://app.supabase.com")
    print("2. Select your project")
    print("3. Go to Settings > API")
    print("4. Copy the 'service_role' key (not the anon key!)")
    print("\nThen run:")
    print("export SUPABASE_SERVICE_ROLE_KEY='your-service-role-key-here'")
    print("python scripts/add_account_tier.py")
    exit(1)

try:
    # Create Supabase client with service role key
    supabase: Client = create_client(SUPABASE_URL, SERVICE_ROLE_KEY)
    
    print("🔄 Attempting to add account_tier column to auth.users...")
    
    # Execute SQL to add column
    sql = """
    -- Add account_tier column
    ALTER TABLE auth.users 
    ADD COLUMN IF NOT EXISTS account_tier TEXT DEFAULT 'free' 
    CHECK (account_tier IN ('free', 'basic', 'educator'));
    
    -- Add comment
    COMMENT ON COLUMN auth.users.account_tier IS 'User subscription tier: free (5 quizzes), basic (100 quizzes), educator (500 quizzes)';
    
    -- Create index
    CREATE INDEX IF NOT EXISTS idx_users_tier ON auth.users(account_tier);
    """
    
    result = supabase.rpc('exec_sql', {'sql': sql}).execute()
    
    print("✅ Successfully added account_tier column!")
    print("\nVerifying...")
    
    # Verify by checking if we can query the column
    verify_sql = """
    SELECT COUNT(*) as user_count, account_tier 
    FROM auth.users 
    GROUP BY account_tier;
    """
    
    verify_result = supabase.rpc('exec_sql', {'sql': verify_sql}).execute()
    print(f"✅ Verification successful: {verify_result.data}")
    
except Exception as e:
    print(f"❌ Error: {e}")
    print("\nNote: This operation requires service_role key privileges.")
    print("If you're getting permission errors, use the Supabase Dashboard SQL Editor instead.")

