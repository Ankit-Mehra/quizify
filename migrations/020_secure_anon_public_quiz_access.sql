-- Migration: 020 - Secure Anonymous Public Quiz Access
-- Date: 2025-11-26
-- Purpose: Replace direct anon policies with sanitized views (security fix)
-- Note: This migration fixes a security issue where anon users could see created_by field

-- ============================================================================
-- 1. Remove insecure direct anon policies
-- ============================================================================

DROP POLICY IF EXISTS quizzes_anon_public_policy ON quizzes;
DROP POLICY IF EXISTS questions_anon_public_policy ON questions;

-- ============================================================================
-- 2. Create sanitized view for public quizzes (no user identifiers)
-- ============================================================================

DROP VIEW IF EXISTS public_quizzes;

CREATE VIEW public_quizzes AS
SELECT 
    id,
    title,
    public_slug,
    shared_at,
    created_at
FROM quizzes
WHERE is_public = TRUE AND public_slug IS NOT NULL;

COMMENT ON VIEW public_quizzes IS 'Sanitized view for anonymous access - excludes user identifiers';

GRANT SELECT ON public_quizzes TO anon;

-- ============================================================================
-- 3. Create sanitized view for public quiz questions
-- ============================================================================

DROP VIEW IF EXISTS public_quiz_questions;

CREATE VIEW public_quiz_questions AS
SELECT 
    q.id,
    q.quiz_id,
    q.type,
    q.question,
    q.options,
    q."left",
    q."right",
    q.explanation
FROM questions q
INNER JOIN quizzes qz ON q.quiz_id = qz.id
WHERE qz.is_public = TRUE AND qz.public_slug IS NOT NULL;

COMMENT ON VIEW public_quiz_questions IS 'Sanitized questions view for anonymous access - excludes correct answers';

GRANT SELECT ON public_quiz_questions TO anon;

-- ============================================================================
-- Migration Complete
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE 'Migration 020 completed successfully';
    RAISE NOTICE 'Removed: Direct anon policies on quizzes/questions tables';
    RAISE NOTICE 'Created: public_quizzes view (sanitized, no created_by)';
    RAISE NOTICE 'Created: public_quiz_questions view (sanitized, no correct_answer)';
    RAISE NOTICE 'Security: Anonymous users can no longer see user identifiers';
END $$;
