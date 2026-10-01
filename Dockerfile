# Multi-stage lightweight Python Dockerfile
FROM python:3.12-slim AS builder

WORKDIR /app

# Install system dependencies needed for compiling C-extensions if any
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies in wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Final runtime image
FROM python:3.12-slim

WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source code
COPY . .

# Create volume mount point for database persistence
RUN mkdir -p /app/data

# Run bot
CMD ["python", "main.py"]
