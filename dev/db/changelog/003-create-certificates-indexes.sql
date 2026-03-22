CREATE INDEX idx_certificates_status ON certificates(status);
CREATE INDEX idx_certificates_created_at ON certificates(created_at DESC);
CREATE INDEX idx_certificates_student_id ON certificates(student_id);
CREATE INDEX idx_certificates_status_created ON certificates(status, created_at DESC);
