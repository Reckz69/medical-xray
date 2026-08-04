# Worker image — build from the backend root (deploy/../ is the context).
#   docker build -f worker/Dockerfile -t denoise-worker ..
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY gateway ./gateway
COPY worker ./worker

CMD ["python", "-m", "worker.main"]
