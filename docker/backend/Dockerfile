# Use lightweight Python image
FROM python:3.11-slim

# Set working directory inside container
WORKDIR /app

# Install system dependencies for psycopg2 & boto3
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY ./requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files (from repo root into container)
COPY . .

# Expose FastAPI port
EXPOSE 8000

# Default command (can be overridden by docker run)
CMD ["python", "main.py"]
