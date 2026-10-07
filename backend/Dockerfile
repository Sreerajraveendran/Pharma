FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY app/ ./app/

RUN useradd --system --uid 10001 --no-create-home app
USER app

EXPOSE 8000

# Migrate the schema to the latest revision, then serve. The API is only reachable through
# the nginx frontend (or localhost), so trust its X-Forwarded-For header for the client IP
# recorded in the auth audit log.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips '*'"]
