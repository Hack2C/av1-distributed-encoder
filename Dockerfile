# Build stage
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies and FFmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies system-wide
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Runtime stage - use python slim
FROM python:3.12-slim

WORKDIR /app

# Install FFmpeg, CIFS utilities, and gosu for user switching
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    cifs-utils \
    fuse \
    gosu \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy Python packages from builder (installed system-wide)
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY lib/ ./lib/
COPY web/ ./web/
COPY *.py ./
COPY *.json ./
COPY docker-entrypoint.sh /usr/local/bin/

# Make entrypoint executable
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Expose web port
EXPOSE 8090

# Use entrypoint for SMB mounting
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# Default command (can be overridden in docker-compose)
CMD ["python3", "transcode.py"]
