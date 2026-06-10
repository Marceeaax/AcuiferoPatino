FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    DJANGO_DEBUG=false \
    USE_WHITENOISE=true \
    STATIC_ROOT=/app/staticfiles \
    MEDIA_ROOT=/app/media \
    GDAL_DATA=/usr/share/gdal \
    PROJ_LIB=/usr/share/proj

RUN apt-get update && apt-get install -y --no-install-recommends \
    binutils \
    gcc \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libpq-dev \
    libproj-dev \
    proj-bin \
    proj-data \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./

RUN python -m pip install --upgrade pip \
    && pip install -r requirements.txt

COPY . .

RUN chmod +x /app/build.sh /app/start.sh \
    && mkdir -p /app/media /app/staticfiles \
    && python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["/app/start.sh"]
