# Gateway image — build from the backend root (deploy/../ is the context).
#   docker build -f gateway/Dockerfile -t denoise-gateway ..
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY gateway ./gateway
COPY db ./db
COPY alembic.ini .

# Apply pending migrations on start (idempotent), then serve the API.
CMD ["sh", "-c", "alembic upgrade head && python -m uvicorn gateway.main:app --host 0.0.0.0 --port 8000"]
