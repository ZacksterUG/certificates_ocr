CREATE TABLE certificates (
    id uuid PRIMARY KEY NOT NULL,
    image_data bytea NOT NULL,
    image_filename varchar(255) NOT NULL,
    image_mime_type varchar(50) NOT NULL,
    image_size_bytes bigint NOT NULL,
    raw_text text,
    structured_data jsonb,
    status varchar(50) NOT NULL,
    error_message text,
    student_id varchar(100),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    completed_at timestamp with time zone
);
