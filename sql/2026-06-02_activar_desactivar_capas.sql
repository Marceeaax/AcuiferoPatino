ALTER TABLE patino
ADD COLUMN IF NOT EXISTS activo boolean NOT NULL DEFAULT true;

ALTER TABLE capa_raster
ADD COLUMN IF NOT EXISTS activo boolean NOT NULL DEFAULT true;

CREATE INDEX IF NOT EXISTS idx_patino_activo ON patino (activo);
CREATE INDEX IF NOT EXISTS idx_capa_raster_activo ON capa_raster (activo);
