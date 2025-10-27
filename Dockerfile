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

# Runtime stage - use python slim
FROM python:3.12-slim

WORKDIR /app

# Install FFmpeg and CIFS utilities for network shares
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    cifs-utils \
    fuse \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY lib/ ./lib/
COPY web/ ./web/
COPY *.py ./
COPY *.json ./
COPY docker-entrypoint.sh /usr/local/bin/

# Set Python path
ENV PYTHONPATH=/root/.local/lib/python3.12/site-packages
ENV PATH=/root/.local/bin:$PATH

# Make entrypoint executable
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Expose web port
EXPOSE 8090

# Use entrypoint for SMB mounting
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# Default command (can be overridden in docker-compose)
CMD ["python3", "transcode.py"]
