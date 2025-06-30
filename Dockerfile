# Multi-stage Dockerfile for solana-radar

# Base stage with common dependencies
FROM python:3.12-slim AS base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Create app directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Development stage
FROM base AS development

# Copy requirements files
COPY requirements.txt requirements-dev.txt ./

# Install all dependencies including dev
RUN pip install --no-cache-dir -r requirements.txt -r requirements-dev.txt

# Copy application code
COPY . .

# Compile proto files
RUN python scripts/compile_proto.py

# Default command for development
CMD ["python", "-m", "ingest"]

# Production stage
FROM base AS production

# Copy only production requirements
COPY requirements.txt ./

# Install production dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy proto files and compile them
COPY proto ./proto
COPY scripts/compile_proto.py ./scripts/
RUN python scripts/compile_proto.py

# Copy application code
COPY ingest ./ingest
COPY core ./core
COPY alerts ./alerts

# Create non-root user
RUN useradd -m -u 1000 radar && chown -R radar:radar /app

# Switch to non-root user
USER radar

# Default command for production
CMD ["python", "-m", "ingest"] 