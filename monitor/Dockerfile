# Hydroxide monitor container - runs as root for Docker socket access
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ /app/

# Run as root to access Docker socket
CMD ["python", "-u", "main.py"]
