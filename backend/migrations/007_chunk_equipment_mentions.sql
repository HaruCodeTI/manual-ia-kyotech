ALTER TABLE chunks
ADD COLUMN IF NOT EXISTS equipment_mentions jsonb NOT NULL DEFAULT '[]';

CREATE INDEX IF NOT EXISTS idx_chunks_equipment_mentions
ON chunks USING gin(equipment_mentions);
