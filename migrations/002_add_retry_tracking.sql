-- Migration: Add retry tracking for video processing
-- Date: 2025-10-25
-- Purpose: Track retry attempts to prevent infinite retry loops and identify stuck videos

-- Add retry_count column to track processing attempts
ALTER TABLE videos ADD COLUMN retry_count INTEGER DEFAULT 0;

-- Create index for efficient queries on retry count
CREATE INDEX IF NOT EXISTS idx_retry_count ON videos(retry_count);

-- Update any existing videos in 'processing' state to have retry_count = 1
-- This ensures consistency for videos that might be mid-processing
UPDATE videos
SET retry_count = 1
WHERE processing_status = 'processing';

-- Note: The retry_count will be incremented each time processing starts
-- Maximum retry limit of 3 attempts will be enforced in application code