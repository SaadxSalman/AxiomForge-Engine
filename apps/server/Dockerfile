# apps/server/Dockerfile — FastAPI + Celery worker image.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

COPY apps/server/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/server/app ./app

EXPOSE 8000

# Default: run the API.  docker-compose overrides the command for the
# Celery worker / Flower services.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
