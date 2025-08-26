# docker/backend/Dockerfile
FROM python:3.11-slim

# Set Working directory
WORKDIR /app/backend

# System deps (for psycopg2 & boto3)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (better caching)
COPY app/backend/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY app/backend/ ./

# Expose FastAPI port
EXPOSE 8000

# Default command
CMD ["python", "main.py"]
