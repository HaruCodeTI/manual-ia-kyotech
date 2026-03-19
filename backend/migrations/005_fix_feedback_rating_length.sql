-- Kyotech AI — Fix: ampliar coluna rating para acomodar 'thumbs_down' (11 chars)
-- VARCHAR(10) rejeitava 'thumbs_down' com StringDataRightTruncationError
ALTER TABLE message_feedback ALTER COLUMN rating TYPE VARCHAR(12);
