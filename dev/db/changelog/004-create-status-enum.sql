DO $$ BEGIN
    CREATE TYPE certificate_status AS ENUM (
        'pending',
        'ocr_processing',
        'ocr_completed',
        'ocr_error',
        'llm_processing',
        'completed',
        'error'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;
