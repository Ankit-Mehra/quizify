-- Migration: Add indexes for quiz search and filtering
-- Purpose: Optimize queries for title search and date range filtering
-- Date: 2025-10-13

-- Index for case-insensitive title search
-- This allows efficient ILIKE queries on quiz titles
CREATE INDEX IF NOT EXISTS idx_quizzes_title_lower 
ON quizzes (LOWER(title));

-- Composite index for filtered queries
-- This optimizes queries that filter by user and order by creation date
CREATE INDEX IF NOT EXISTS idx_quizzes_user_created 
ON quizzes (created_by, created_at DESC);

-- Note: The combination of these indexes will significantly improve
-- query performance for the /api/quiz/my-quizzes endpoint with filters
