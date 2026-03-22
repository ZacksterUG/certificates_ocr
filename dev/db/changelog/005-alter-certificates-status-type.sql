ALTER TABLE certificates
ALTER COLUMN status TYPE certificate_status
USING status::certificate_status;
