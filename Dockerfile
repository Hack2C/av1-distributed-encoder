# Build stage
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies and FFmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Runtime stage - use python slim (distroless doesn't include FFmpeg easily)
FROM python:3.12-slim

WORKDIR /app

# Install FFmpeg and clean up
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY lib/ ./lib/
COPY web/ ./web/
COPY *.py ./
COPY *.json ./

# Set Python path
ENV PYTHONPATH=/root/.local/lib/python3.12/site-packages
ENV PATH=/root/.local/bin:$PATH

# Expose web port
EXPOSE 8090

# Default command (can be overridden in docker-compose)
CMD ["python3", "transcode.py"]
