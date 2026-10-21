# Python email forwarder container
FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends --only-upgrade ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r forwarder && useradd -r -g forwarder forwarder

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ /app/

# Create data directory for SQLite database
RUN mkdir -p /data && chown -R forwarder:forwarder /data

# Switch to non-root user
USER forwarder

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health').read()" || exit 1

# Expose health check port
EXPOSE 8080

# Run the application
CMD ["python", "-u", "main.py"]