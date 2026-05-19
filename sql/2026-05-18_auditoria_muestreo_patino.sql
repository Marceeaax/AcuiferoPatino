-- Auditoria y trazabilidad para tablas no gestionadas por Django.
-- Ejecutar en PostgreSQL antes de usar los nuevos campos desde la app.

BEGIN;

ALTER TABLE muestreo
    ADD COLUMN IF NOT EXISTS lote_carga varchar(64),
    ADD COLUMN IF NOT EXISTS archivo_origen varchar(255),
    ADD COLUMN IF NOT EXISTS srid_origen integer,
    ADD COLUMN IF NOT EXISTS fec_insercion timestamp with time zone,
    ADD COLUMN IF NOT EXISTS usu_insercion integer,
    ADD COLUMN IF NOT EXISTS fec_modificacion timestamp with time zone,
    ADD COLUMN IF NOT EXISTS usu_modificacion integer;

ALTER TABLE patino
    ADD COLUMN IF NOT EXISTS fec_insercion timestamp with time zone,
    ADD COLUMN IF NOT EXISTS usu_insercion integer,
    ADD COLUMN IF NOT EXISTS fec_modificacion timestamp with time zone,
    ADD COLUMN IF NOT EXISTS usu_modificacion integer;

UPDATE muestreo
SET
    srid_origen = COALESCE(srid_origen, 4326),
    fec_insercion = COALESCE(fec_insercion, NOW()),
    fec_modificacion = COALESCE(fec_modificacion, NOW()),
    usu_insercion = COALESCE(usu_insercion, user_id),
    usu_modificacion = COALESCE(usu_modificacion, user_id)
WHERE
    srid_origen IS NULL
    OR fec_insercion IS NULL
    OR fec_modificacion IS NULL
    OR usu_insercion IS NULL
    OR usu_modificacion IS NULL;

UPDATE patino
SET
    fec_insercion = COALESCE(fec_insercion, fecha_subida, NOW()),
    fec_modificacion = COALESCE(fec_modificacion, fecha_subida, NOW()),
    usu_insercion = COALESCE(usu_insercion, user_id),
    usu_modificacion = COALESCE(usu_modificacion, user_id)
WHERE
    fec_insercion IS NULL
    OR fec_modificacion IS NULL
    OR usu_insercion IS NULL
    OR usu_modificacion IS NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_muestreo_usu_insercion'
    ) THEN
        ALTER TABLE muestreo
            ADD CONSTRAINT fk_muestreo_usu_insercion
            FOREIGN KEY (usu_insercion) REFERENCES auth_user(id) ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_muestreo_usu_modificacion'
    ) THEN
        ALTER TABLE muestreo
            ADD CONSTRAINT fk_muestreo_usu_modificacion
            FOREIGN KEY (usu_modificacion) REFERENCES auth_user(id) ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_patino_usu_insercion'
    ) THEN
        ALTER TABLE patino
            ADD CONSTRAINT fk_patino_usu_insercion
            FOREIGN KEY (usu_insercion) REFERENCES auth_user(id) ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_patino_usu_modificacion'
    ) THEN
        ALTER TABLE patino
            ADD CONSTRAINT fk_patino_usu_modificacion
            FOREIGN KEY (usu_modificacion) REFERENCES auth_user(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_muestreo_lote_carga ON muestreo (lote_carga);
CREATE INDEX IF NOT EXISTS idx_muestreo_archivo_origen ON muestreo (archivo_origen);
CREATE INDEX IF NOT EXISTS idx_muestreo_usu_insercion ON muestreo (usu_insercion);
CREATE INDEX IF NOT EXISTS idx_muestreo_usu_modificacion ON muestreo (usu_modificacion);
CREATE INDEX IF NOT EXISTS idx_patino_usu_insercion ON patino (usu_insercion);
CREATE INDEX IF NOT EXISTS idx_patino_usu_modificacion ON patino (usu_modificacion);

COMMIT;
