# docker/worker/Dockerfile
FROM python:3.11-slim

# System deps (for SSL, timezone, tini)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates tzdata curl tini && \
    rm -rf /var/lib/apt/lists/*

# Workdir
WORKDIR /app/worker

# Copy requirements first (better layer caching)
COPY app/worker/requirements.txt .

# Install Python deps
RUN pip install --no-cache-dir -r requirements.txt

# Copy all worker code (worker.py + aws_module.py + azure_module.py + gcp_module.py + README.md, etc.)
COPY app/worker/*.py .
COPY app/worker/README.md .

# Create non-root user
RUN useradd -m appuser
USER appuser

# Environment defaults (can be overridden at run time)
ENV AWS_REGION=us-east-1 \
    SSM_PARAM_NAME=myapp_database_credentials \
    DB_NAME=appdb \
    POLL_INTERVAL_SECONDS=600 \
    PYTHONUNBUFFERED=1

# Use tini as init for proper signal handling
ENTRYPOINT ["/usr/bin/tini", "--"]

# Healthcheck (simple ping to the process every 30s)
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD pgrep -f worker.py || exit 1

# Run the worker
CMD ["python", "worker.py"]
