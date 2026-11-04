# Same image in dev and production (SPEC 3.1).
FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN useradd --create-home --uid 10001 engine
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY seed_data ./seed_data
COPY scripts/start.sh ./scripts/start.sh
# File storage (STORAGE_URL empty -> /app/storage). Ephemeral on Render (D46): dummy data only.
RUN mkdir -p /app/storage && chown engine:engine /app/storage
USER engine
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import os,urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:%s/v1/health' % os.environ.get('PORT','8000')).status==200 else 1)"
# Runs `alembic upgrade head` when DATABASE_URL is set, then uvicorn on $PORT (scripts/start.sh).
CMD ["sh", "scripts/start.sh"]
