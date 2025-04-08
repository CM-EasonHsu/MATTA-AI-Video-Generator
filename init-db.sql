-- Create the ENUM type for submission statuses
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'submission_status') THEN
        CREATE TYPE submission_status AS ENUM (
            'PENDING_PHOTO_APPROVAL', -- Initial state after upload
            'PHOTO_REJECTED',         -- Moderator rejected the photo
            'PHOTO_APPROVED',         -- Moderator approved photo, ready for queue
            'QUEUED_FOR_GENERATION',  -- Task sent to queue
            'GENERATING_VIDEO',       -- Worker picked up the task
            'GENERATION_FAILED',      -- Video generation failed
            'PENDING_VIDEO_APPROVAL', -- Video generated, awaiting moderator approval
            'VIDEO_REJECTED',         -- Moderator rejected the video
            'VIDEO_APPROVED'          -- Final approved state, visible to user
        );
        RAISE NOTICE 'Created ENUM type submission_status.';
    ELSE
        RAISE NOTICE 'ENUM type submission_status already exists.';
    END IF;
END$$;


-- Create the main table for tracking submissions
CREATE TABLE IF NOT EXISTS submissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),      -- Internal unique ID
    submission_code VARCHAR(10) UNIQUE NOT NULL,      -- Shorter, user-facing code
    status submission_status NOT NULL DEFAULT 'PENDING_PHOTO_APPROVAL',

    -- Input details
    uploaded_photo_gcs_path VARCHAR(1024) NOT NULL,    -- GCS path like 'pending_photos/<code>.jpg'
    user_prompt TEXT,                                  -- Optional text from user

    -- Output details
    generated_video_gcs_path VARCHAR(1024),            -- GCS path like 'generated_videos/<code>.mp4'

    -- Timestamps (use TIMESTAMPTZ for time zone awareness)
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Moderation details
    photo_moderated_at TIMESTAMPTZ,
    video_moderated_at TIMESTAMPTZ,

    -- Error details
    error_message TEXT
);

RAISE NOTICE 'Checked/Created table submissions.';

-- Create Indexes for efficient querying
-- Note: UNIQUE constraint on submission_code automatically creates an index
CREATE INDEX IF NOT EXISTS idx_submissions_status ON submissions(status);
CREATE INDEX IF NOT EXISTS idx_submissions_created_at ON submissions(created_at);

RAISE NOTICE 'Checked/Created indexes on submissions table.';

-- Create Trigger function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION trigger_set_timestamp()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

RAISE NOTICE 'Checked/Created function trigger_set_timestamp.';

-- Create Trigger to call the function before any update on the submissions table
-- Drop existing trigger first to ensure idempotency if script is run multiple times (though entrypoint prevents this)
DROP TRIGGER IF EXISTS set_timestamp ON submissions;
CREATE TRIGGER set_timestamp
BEFORE UPDATE ON submissions
FOR EACH ROW
EXECUTE FUNCTION trigger_set_timestamp();

RAISE NOTICE 'Checked/Created trigger set_timestamp on submissions table.';

-- Grant permissions (adjust user if necessary, though entrypoint usually runs as POSTGRES_USER)
-- The user defined by POSTGRES_USER in .env will own the objects by default
-- Granting explicit permissions can be useful in more complex setups.
-- GRANT ALL PRIVILEGES ON TABLE submissions TO your_app_user;
-- GRANT USAGE, SELECT ON SEQUENCE IF EXISTS submissions_id_seq TO your_app_user; -- If using SERIAL instead of UUID

RAISE NOTICE 'Database initialization script completed successfully.';