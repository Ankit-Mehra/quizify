-- ============================================================================
-- Migration 014: Add Stripe Integration to Profiles
-- ============================================================================
-- Purpose: Add Stripe customer and subscription tracking to profiles table
-- Created: 2025-01-XX (Epic 1: Infrastructure Setup)
-- 
-- This migration adds the necessary columns to track Stripe customers and
-- subscriptions, enabling subscription billing for Basic and Educator tiers.
-- ============================================================================

-- Add Stripe customer ID column
-- This is the Stripe customer ID (cus_XXXXXXXXX) created when user subscribes
ALTER TABLE public.profiles
ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT UNIQUE;

-- Add Stripe subscription ID column
-- This is the active subscription ID (sub_XXXXXXXXX) for the user
ALTER TABLE public.profiles
ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT;

-- Add subscription status column
-- Values: null (free tier), "active", "past_due", "canceled", "incomplete", "trialing"
-- See: https://stripe.com/docs/api/subscriptions/object#subscription_object-status
ALTER TABLE public.profiles
ADD COLUMN IF NOT EXISTS subscription_status TEXT;

-- Add subscription cancellation timestamp
-- Records when subscription was canceled (for grace period handling)
ALTER TABLE public.profiles
ADD COLUMN IF NOT EXISTS subscription_canceled_at TIMESTAMPTZ;

-- ============================================================================
-- Indexes for Performance
-- ============================================================================

-- Index on stripe_customer_id for fast Stripe webhook lookups
CREATE INDEX IF NOT EXISTS idx_profiles_stripe_customer_id 
ON public.profiles(stripe_customer_id) 
WHERE stripe_customer_id IS NOT NULL;

-- Index on stripe_subscription_id for subscription queries
CREATE INDEX IF NOT EXISTS idx_profiles_stripe_subscription_id 
ON public.profiles(stripe_subscription_id) 
WHERE stripe_subscription_id IS NOT NULL;

-- Index on subscription_status for billing queries
CREATE INDEX IF NOT EXISTS idx_profiles_subscription_status 
ON public.profiles(subscription_status) 
WHERE subscription_status IS NOT NULL;

-- ============================================================================
-- Row Level Security (RLS) Policies
-- ============================================================================

-- Drop policy if exists to avoid error on recreation
DROP POLICY IF EXISTS "Users can view own Stripe data" ON public.profiles;

-- Users can view their own Stripe data (needed for billing page)
CREATE POLICY "Users can view own Stripe data"
ON public.profiles
FOR SELECT
USING (auth.uid() = id);

-- Users cannot directly modify Stripe data (only backend via service role)
-- No INSERT/UPDATE/DELETE policies for Stripe columns
-- Backend uses service_role key to update these fields via webhooks

-- ============================================================================
-- Comments for Documentation
-- ============================================================================

COMMENT ON COLUMN public.profiles.stripe_customer_id IS 
'Stripe customer ID (cus_XXXXXXXXX) - created on first subscription purchase';

COMMENT ON COLUMN public.profiles.stripe_subscription_id IS 
'Stripe subscription ID (sub_XXXXXXXXX) - null for free tier, set for active subscriptions';

COMMENT ON COLUMN public.profiles.subscription_status IS 
'Stripe subscription status: null (free), active, past_due, canceled, incomplete, trialing';

COMMENT ON COLUMN public.profiles.subscription_canceled_at IS 
'Timestamp when subscription was canceled - used for grace period calculations';

-- ============================================================================
-- Verification Queries (Run these to verify migration success)
-- ============================================================================

-- Check that columns were added
-- SELECT column_name, data_type, is_nullable 
-- FROM information_schema.columns 
-- WHERE table_schema = 'public' 
-- AND table_name = 'profiles' 
-- AND column_name IN ('stripe_customer_id', 'stripe_subscription_id', 'subscription_status', 'subscription_canceled_at');

-- Check that indexes were created
-- SELECT indexname, indexdef 
-- FROM pg_indexes 
-- WHERE schemaname = 'public' 
-- AND tablename = 'profiles' 
-- AND indexname LIKE 'idx_profiles_stripe%';

-- Check that policies exist
-- SELECT policyname, cmd, qual 
-- FROM pg_policies 
-- WHERE schemaname = 'public' 
-- AND tablename = 'profiles' 
-- AND policyname LIKE '%Stripe%';
