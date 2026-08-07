# Scheduler image — build from the backend root (deploy/../ is the context).
#   docker build -f scheduler/Dockerfile -t denoise-scheduler ..
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY gateway ./gateway
COPY scheduler ./scheduler

CMD ["python", "-m", "scheduler.main"]
