FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    binutils \
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
    && python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["/app/start.sh"]
