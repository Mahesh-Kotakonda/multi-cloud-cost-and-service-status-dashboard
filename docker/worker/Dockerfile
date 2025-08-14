FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY app/worker/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# copy entire app so worker can import app.database
COPY app /app/app

# default envs (override in prod)
ENV WORKER_INTERVAL=60 \
    RESOURCE_NAME=demo-resource

CMD ["python", "app/worker/worker.py"]
