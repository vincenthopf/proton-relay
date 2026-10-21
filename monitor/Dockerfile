# Hydroxide monitor container - runs as root for Docker socket access
FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends --only-upgrade ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ /app/

# Run as root to access Docker socket
CMD ["python", "-u", "main.py"]
