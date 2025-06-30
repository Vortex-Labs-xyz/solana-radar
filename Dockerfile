# Multi-stage Dockerfile for Python application
FROM python:3.11-slim as base

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Development stage
FROM base as development
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "ingest"]

# Production stage
FROM base as production
COPY . .
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "ingest"] 