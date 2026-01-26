#!/bin/bash
set -e

# Usage: ./setup-instance.sh <instance-name> <health-port> <captcha-port> <check-interval>
# Example: ./setup-instance.sh account1 8081 5801 30

INSTANCE_NAME="${1:?Usage: $0 <instance-name> <health-port> <captcha-port> <check-interval>}"
HEALTH_PORT="${2:?Specify health check port}"
CAPTCHA_PORT="${3:?Specify captcha browser port}"
CHECK_INTERVAL="${4:-30}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
INSTANCE_DIR="$SCRIPT_DIR/instances/$INSTANCE_NAME"

echo "Setting up instance: $INSTANCE_NAME"
echo "  Health port: $HEALTH_PORT"
echo "  Captcha port: $CAPTCHA_PORT"
echo "  Check interval: ${CHECK_INTERVAL}s"
echo ""

# Create instance directory
mkdir -p "$INSTANCE_DIR"

# Create docker-compose.yml for this instance
cat > "$INSTANCE_DIR/docker-compose.yml" << 'COMPOSE_EOF'
services:
  hydroxide:
    build:
      context: ../../hydroxide-container
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
      - email-network
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
      context: ../../forwarder
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
      - CHECK_INTERVAL=${CHECK_INTERVAL:-30}
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
      - email-network
    ports:
      - "${HEALTH_CHECK_PORT:-8080}:8080"
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/health').read()"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s

  captcha-browser:
    image: jlesage/firefox
    container_name: ${COMPOSE_PROJECT_NAME}-captcha
    profiles: [captcha]
    ports:
      - "${CAPTCHA_PORT:-5800}:5800"
    environment:
      - DISPLAY_WIDTH=1280
      - DISPLAY_HEIGHT=900
      - KEEP_APP_RUNNING=1
      - FF_OPEN_URL=https://account.proton.me/login
    shm_size: 2gb
    networks:
      - email-network

networks:
  email-network:
    driver: bridge

volumes:
  bridge-password:
    driver: local
  forwarder-data:
    driver: local
COMPOSE_EOF

# Create .env template
cat > "$INSTANCE_DIR/.env.example" << ENV_EOF
# Instance: $INSTANCE_NAME
COMPOSE_PROJECT_NAME=$INSTANCE_NAME

# ProtonMail credentials
PROTONMAIL_USERNAME=your-email@protonmail.com
PROTONMAIL_PASSWORD=your-protonmail-password

# External SMTP (destination)
SMTP_HOST=smtp.fastmail.com
SMTP_PORT=587
SMTP_USERNAME=your-smtp-username
SMTP_PASSWORD=your-smtp-password

# Forwarding
FORWARD_TO=destination@example.com

# Instance-specific settings
CHECK_INTERVAL=$CHECK_INTERVAL
HEALTH_CHECK_PORT=$HEALTH_PORT
CAPTCHA_PORT=$CAPTCHA_PORT

# Telegram alerts (shared across instances is fine)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Optional
LOG_LEVEL=INFO
ENV_EOF

# Create auth directory
mkdir -p "$INSTANCE_DIR/auth"

# Create helper scripts
cat > "$INSTANCE_DIR/start.sh" << 'SCRIPT_EOF'
#!/bin/bash
cd "$(dirname "$0")"
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

cat > "$INSTANCE_DIR/captcha.sh" << 'SCRIPT_EOF'
#!/bin/bash
cd "$(dirname "$0")"
case "${1:-start}" in
  start)
    docker compose --profile captcha up -d captcha-browser
    source .env 2>/dev/null
    echo "Browser available at: http://localhost:${CAPTCHA_PORT:-5800}"
    ;;
  stop)
    docker compose --profile captcha down
    ;;
  *)
    echo "Usage: $0 [start|stop]"
    ;;
esac
SCRIPT_EOF
chmod +x "$INSTANCE_DIR/captcha.sh"

echo ""
echo "Instance created at: $INSTANCE_DIR"
echo ""
echo "Next steps:"
echo "  1. cp $INSTANCE_DIR/.env.example $INSTANCE_DIR/.env"
echo "  2. Edit $INSTANCE_DIR/.env with your credentials"
echo "  3. cd $INSTANCE_DIR && ./start.sh"
echo ""
