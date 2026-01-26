#!/bin/bash
set -e

# Usage: ./setup-instance.sh <instance-name> <health-port> <check-interval>
# Example: ./setup-instance.sh proton1 8081 30

INSTANCE_NAME="${1:?Usage: $0 <instance-name> <health-port> <check-interval>}"
HEALTH_PORT="${2:?Specify health check port}"
CHECK_INTERVAL="${3:-30}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTANCE_DIR="$SCRIPT_DIR/instances/$INSTANCE_NAME"

# Create instance directory
mkdir -p "$INSTANCE_DIR"

# Create docker-compose.yml for this instance (no captcha browser - that's shared)
# Paths are relative to instances/<name>/ so need ../../../ to reach repo root
cat > "$INSTANCE_DIR/docker-compose.yml" << 'COMPOSE_EOF'
services:
  hydroxide:
    build:
      context: ../../../hydroxide-container
      dockerfile: Dockerfile
    container_name: ${COMPOSE_PROJECT_NAME}-hydroxide
    restart: unless-stopped
    environment:
      - PROTONMAIL_USERNAME=${PROTONMAIL_USERNAME}
      - PROTONMAIL_PASSWORD=${PROTONMAIL_PASSWORD}
    volumes:
      - ./auth:/home/hydroxide/.config/hydroxide
      - bridge-password:/bridge-password
    networks:
      - proton-relay-network
    expose:
      - "1143"
    healthcheck:
      test: ["CMD", "nc", "-z", "localhost", "1143"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

  forwarder:
    build:
      context: ../../../forwarder
      dockerfile: Dockerfile
    container_name: ${COMPOSE_PROJECT_NAME}-forwarder
    restart: unless-stopped
    depends_on:
      hydroxide:
        condition: service_healthy
    environment:
      - IMAP_HOST=hydroxide
      - IMAP_PORT=1143
      - IMAP_USE_SSL=false
      - PROTONMAIL_USERNAME=${PROTONMAIL_USERNAME}
      - BRIDGE_PASSWORD=${BRIDGE_PASSWORD:-}
      - SMTP_HOST=${SMTP_HOST}
      - SMTP_PORT=${SMTP_PORT}
      - SMTP_USERNAME=${SMTP_USERNAME}
      - SMTP_PASSWORD=${SMTP_PASSWORD}
      - SMTP_USE_TLS=${SMTP_USE_TLS:-true}
      - SMTP_USE_SSL=${SMTP_USE_SSL:-false}
      - FORWARD_TO=${FORWARD_TO}
      - FORWARD_FROM=${FORWARD_FROM:-}
      - CHECK_INTERVAL=${CHECK_INTERVAL}
      - MAX_EMAILS_PER_BATCH=${MAX_EMAILS_PER_BATCH:-10}
      - MARK_AS_READ=${MARK_AS_READ:-true}
      - DELETE_AFTER_FORWARD=${DELETE_AFTER_FORWARD:-false}
      - FORWARD_ATTACHMENTS=${FORWARD_ATTACHMENTS:-true}
      - MAX_ATTACHMENT_SIZE=${MAX_ATTACHMENT_SIZE:-25}
      - PRESERVE_HEADERS=${PRESERVE_HEADERS:-true}
      - ADD_FORWARD_HEADER=${ADD_FORWARD_HEADER:-true}
      - MAX_RETRIES=${MAX_RETRIES:-3}
      - RETRY_DELAY=${RETRY_DELAY:-30}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN:-}
      - TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID:-}
      - HEALTH_CHECK_PORT=8080
      - ENABLE_HEALTH_CHECK=true
    volumes:
      - forwarder-data:/data
      - bridge-password:/bridge-password:ro
      - /var/run/docker.sock:/var/run/docker.sock:ro
    networks:
      - proton-relay-network
    ports:
      - "${HEALTH_CHECK_PORT}:8080"
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/health').read()"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s

networks:
  proton-relay-network:
    name: proton-relay-network
    external: true

volumes:
  bridge-password:
    driver: local
  forwarder-data:
    driver: local
COMPOSE_EOF

# Create .env file that sources shared config
cat > "$INSTANCE_DIR/.env" << ENV_EOF
# Instance: $INSTANCE_NAME
COMPOSE_PROJECT_NAME=$INSTANCE_NAME

# Instance-specific settings
CHECK_INTERVAL=$CHECK_INTERVAL
HEALTH_CHECK_PORT=$HEALTH_PORT

# ============================================
# PROTONMAIL CREDENTIALS (unique per instance)
# ============================================
PROTONMAIL_USERNAME=
PROTONMAIL_PASSWORD=

# ============================================
# SHARED SETTINGS (loaded from ../shared.env)
# ============================================
# These are loaded automatically by start.sh
# Edit ../shared.env to change SMTP, Telegram, etc.
ENV_EOF

# Create auth directory
mkdir -p "$INSTANCE_DIR/auth"

# Create helper scripts that load shared config
cat > "$INSTANCE_DIR/start.sh" << 'SCRIPT_EOF'
#!/bin/bash
cd "$(dirname "$0")"

# Ensure shared network exists
docker network create proton-relay-network 2>/dev/null || true

# Load shared config first, then instance config (instance overrides shared)
# shared.env is in deploy/, instance is in deploy/instances/<name>/
set -a
[ -f ../../shared.env ] && source ../../shared.env
source .env
set +a

docker compose up -d
SCRIPT_EOF
chmod +x "$INSTANCE_DIR/start.sh"

cat > "$INSTANCE_DIR/stop.sh" << 'SCRIPT_EOF'
#!/bin/bash
cd "$(dirname "$0")"
docker compose down
SCRIPT_EOF
chmod +x "$INSTANCE_DIR/stop.sh"

cat > "$INSTANCE_DIR/logs.sh" << 'SCRIPT_EOF'
#!/bin/bash
cd "$(dirname "$0")"
docker compose logs -f "${1:-forwarder}"
SCRIPT_EOF
chmod +x "$INSTANCE_DIR/logs.sh"
