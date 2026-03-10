-- Migration: Add content_source_type and content_source_reference to quiz_metadata
-- Purpose: Track the source of quiz content (file, url, text) in metadata table
-- Date: 2025-12-04

-- Add content_source_type and content_source_reference columns to quiz_metadata
ALTER TABLE quiz_metadata 
ADD COLUMN IF NOT EXISTS content_source_type TEXT,
ADD COLUMN IF NOT EXISTS content_source_reference TEXT;

-- Backfill data from quizzes table
UPDATE quiz_metadata qm
SET 
    content_source_type = q.content_source_type,
    content_source_reference = q.content_source_reference
FROM quizzes q
WHERE qm.quiz_id = q.id
AND (qm.content_source_type IS NULL OR qm.content_source_reference IS NULL);

-- Add comments for documentation
COMMENT ON COLUMN quiz_metadata.content_source_type IS 'Source type: file, url, or text';
COMMENT ON COLUMN quiz_metadata.content_source_reference IS 'Reference to source: file_id for files, URL for urls, NULL for text';
