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
- `.env.example`

## Observaciones importantes

1. `muestreo` y `patino` siguen siendo tablas no gestionadas por Django.
   Si desplegas una base nueva, esas tablas no se crean solas con `migrate`.

2. Si usas Render, verifica que tu base soporte PostGIS.
   Si no, necesitas una base PostgreSQL externa con la extension PostGIS activa.

3. El flujo TIFF y Shapefile depende de binarios del sistema:
   - `gdalinfo`
   - `gdalwarp`
   - `gdaldem`
   - `gdal_translate`
   - `ogr2ogr`

## Siguiente paso sugerido

Antes de un deploy real:

1. Crear una base de datos con PostGIS disponible.
2. Confirmar variables de entorno.
3. Probar localmente con Docker.
4. Recien despues conectar Render.
