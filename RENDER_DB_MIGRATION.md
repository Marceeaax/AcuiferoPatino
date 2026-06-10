# Migracion de base local a Render

Este proyecto depende de **PostGIS** y ademas usa tablas geoespaciales (`muestreo`, `patino`) cuyo estado real actual no queda descrito por completo solo con `python manage.py migrate`.

Por eso, para una demo en Render, el camino recomendado es:

1. crear la base PostgreSQL en Render;
2. usar una version compatible con PostGIS y, de preferencia, **PostgreSQL 16** para quedar alineados con la base local;
3. exportar la base local completa;
4. restaurar ese dump en la base de Render;
5. recien despues levantar el web service Docker.

## Punto importante

No conviene dejar que Render cree una base vacia y confiar solo en `migrate`, porque:

- `mapas.models.Muestreo` y `mapas.models.Capa` estan marcados como `managed = False`;
- la tabla `muestreo` real tiene muchas mas columnas que la migracion inicial;
- hay ajustes manuales en `sql/2026-05-18_auditoria_muestreo_patino.sql` y `sql/2026-06-02_activar_desactivar_capas.sql`.

## Estado local actual verificado

- Base usada localmente: `tesisdb`
- Tamano aproximado: `18 MB`
- Version local de PostgreSQL: `16.4`
- Extension local: `PostGIS 3.5`

## 1. Crear la base en Render

El archivo [render.yaml](./render.yaml) ya fija:

- servicio web Docker;
- disco persistente para `MEDIA_ROOT`;
- base PostgreSQL;
- `postgresMajorVersion: "16"`.

Render soporta PostGIS en versiones modernas de PostgreSQL, asi que la recomendacion aqui es **mantener PostgreSQL 16** para reducir friccion entre el entorno local y el remoto.

## 2. Exportar la base local

### Opcion simple: SQL plano

```powershell
$env:PGPASSWORD='TU_PASSWORD_LOCAL'
powershell -ExecutionPolicy Bypass -File .\scripts\export_render_db.ps1 -DbName tesisdb -DbUser postgres -DbHost localhost -DbPort 5432 -Format plain
```

Eso va a dejar un archivo en `backups/`.

### Opcion alternativa: custom dump

```powershell
$env:PGPASSWORD='TU_PASSWORD_LOCAL'
powershell -ExecutionPolicy Bypass -File .\scripts\export_render_db.ps1 -DbName tesisdb -DbUser postgres -DbHost localhost -DbPort 5432 -Format custom
```

## 3. Obtener la URL externa de Render Postgres

En Render:

1. entra a la base `acuifero-patino-db`;
2. abre la seccion **Connections**;
3. copia la **External Database URL**.

Debe verse como:

```text
postgres://USER:PASSWORD@HOST:PORT/DBNAME
```

## 4. Restaurar el dump en Render

### Si exportaste `.sql`

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\restore_render_db.ps1 -DatabaseUrl "postgres://USER:PASSWORD@HOST:PORT/DBNAME" -DumpPath ".\backups\tesisdb_render_YYYY-MM-DD_HH-mm-ss.sql"
```

### Si exportaste `.dump`

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\restore_render_db.ps1 -DatabaseUrl "postgres://USER:PASSWORD@HOST:PORT/DBNAME" -DumpPath ".\backups\tesisdb_render_YYYY-MM-DD_HH-mm-ss.dump"
```

## 5. Verificaciones recomendadas despues de restaurar

Conectate con `psql` a la base de Render y verifica:

```sql
SELECT version();
SELECT PostGIS_Version();
SELECT count(*) FROM muestreo;
SELECT count(*) FROM patino;
SELECT count(*) FROM capa_raster;
SELECT count(*) FROM auth_user;
```

## 6. Despues si desplegar el servicio web

Cuando la base ya tenga los datos:

1. crea el Blueprint en Render desde `render.yaml`;
2. deja que el contenedor arranque;
3. el `start.sh` ya ejecuta:
   - espera a la base,
   - verifica `CREATE EXTENSION IF NOT EXISTS postgis`,
   - corre `migrate`,
   - y levanta `gunicorn`.

## Si la restauracion falla

El caso mas probable seria por:

- diferencias de extensiones o configuracion entre tu Postgres local y el Postgres de Render;
- algun objeto generado manualmente fuera de Django;
- o rutas/privilegios incompatibles en el dump.

Si pasa eso, el siguiente plan seria:

1. exportar en formato `custom`;
2. restaurar primero solo esquema;
3. luego restaurar datos;
4. o reconstruir especificamente `muestreo`, `patino` y `capa_raster` en una base intermedia compatible.

Pero por el tamano y simplicidad actual del proyecto, lo razonable es **probar primero con dump completo**.
