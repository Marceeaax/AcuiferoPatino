# Deploy base para Render / Docker

Este proyecto usa dependencias GIS reales:

- PostGIS como backend de Django
- GDAL / OGR para TIFF y Shapefile
- GEOS / PROJ para geometrias y reproyeccion

Por eso, para deploy, Docker es la opcion mas segura y reproducible.

## Variables de entorno recomendadas

Definir al menos:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG=false`
- `DJANGO_ALLOWED_HOSTS=tu-servicio.onrender.com`
- `DATABASE_URL=postgis://usuario:password@host:5432/base`

Opcionales:

- `USE_WHITENOISE=true`
- `DJANGO_TIME_ZONE=America/Asuncion`
- `GDAL_LIBRARY_PATH`
- `PROJ_LIB`

## Archivos preparados

- `requirements.txt`
- `build.sh`
- `Dockerfile`
- `start.sh`
- `render.yaml`
- `.env.example`
- `RENDER_DB_MIGRATION.md`

## Observaciones importantes

1. `muestreo` y `patino` no quedan totalmente reproducidos desde cero solo con `migrate`.
   El esquema real actual necesita una estrategia de bootstrap adicional
   si se despliega sobre una base nueva de Render.

2. Si usas Render, verifica que tu base soporte PostGIS.
   En este proyecto conviene usar PostgreSQL 16 para quedar alineados con tu entorno local.

3. El flujo TIFF y Shapefile depende de binarios del sistema:
   - `gdalinfo`
   - `gdalwarp`
   - `gdaldem`
   - `gdal_translate`
   - `ogr2ogr`

4. `MEDIA_ROOT` debe vivir en un disco persistente.
   El blueprint `render.yaml` ya monta `/app/media` como persistent disk.

5. Para este proyecto, la forma mas segura de poblar la base en Render no es empezar desde cero, sino restaurar un dump de la base local actual.

## Siguiente paso sugerido

Antes de un deploy real:

1. Crear el servicio desde `render.yaml`.
2. Confirmar que la base tenga `postgis` activa.
3. Restaurar la base local con la guia de `RENDER_DB_MIGRATION.md`.
4. Probar localmente con Docker cuando tengas Docker disponible.
5. Recien despues compartir la URL publica.
