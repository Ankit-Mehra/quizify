-- Migration: 024 - Fix llm_calls INSERT policy security
-- Date: 2025-12-03
-- Purpose: Remove overly permissive INSERT policy on llm_calls table
-- 
-- Security Issue: The previous policy "Service can insert llm_calls" with 
-- WITH CHECK (TRUE) allowed any authenticated user to insert rows.
-- This could allow attackers to pollute analytics or impersonate other users.
--
-- Fix: Remove the INSERT policy entirely. The service role bypasses RLS
-- anyway, so only backend code using the service role can insert llm_calls.
-- Regular authenticated users cannot insert into llm_calls.

-- Remove the overly permissive INSERT policy
DROP POLICY IF EXISTS "Service can insert llm_calls" ON public.llm_calls;

-- Verify: After this migration, only the service role can insert into llm_calls.
-- The SELECT policy "Users can view own llm_calls" remains for users to view their own data.

-- Add a comment documenting the security decision
COMMENT ON TABLE public.llm_calls IS 'LLM call analytics for internal tracking. INSERT restricted to service role only (via RLS bypass). Users can only SELECT their own records.';
