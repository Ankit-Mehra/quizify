-- Migration: 041_fix_quiz_metadata_varchar_limits.sql
-- Date: 2026-01-28
-- Purpose: Expand file_type and content_type columns to accommodate long MIME types
-- 
-- Background:
-- The file_type column was VARCHAR(50) but DOCX MIME type is 71 characters:
-- "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
-- This caused "value too long for type character varying(50)" errors during quiz generation
-- ============================================================================

-- Alter file_type to TEXT to accommodate any MIME type
ALTER TABLE public.quiz_metadata 
ALTER COLUMN file_type TYPE TEXT;

-- Alter content_type to TEXT for consistency (was also VARCHAR(50))
ALTER TABLE public.quiz_metadata 
ALTER COLUMN content_type TYPE TEXT;

-- Add comments explaining the columns
COMMENT ON COLUMN public.quiz_metadata.file_type IS 'MIME type of the uploaded file (e.g., application/pdf, application/vnd.openxmlformats-officedocument.wordprocessingml.document)';
COMMENT ON COLUMN public.quiz_metadata.content_type IS 'Content source type: file, text, url, or MIME type for legacy records';
