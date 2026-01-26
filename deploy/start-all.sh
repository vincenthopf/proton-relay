#!/bin/bash

# Start all instances with staggered delays to avoid auth rate limits
# Use --no-delay flag to skip delays (for restarts after initial auth)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTANCES_DIR="$SCRIPT_DIR/instances"
DELAY_SECONDS=300  # 5 minutes between starts

if [[ "$1" == "--no-delay" ]]; then
    DELAY_SECONDS=5
    echo "Starting all instances with minimal delay..."
else
    echo "Starting all instances with ${DELAY_SECONDS}s delay between each..."
    echo "(Use --no-delay flag for restarts after initial auth)"
fi
echo ""

FIRST=true
for instance_dir in "$INSTANCES_DIR"/*/; do
    if [[ -f "$instance_dir/docker-compose.yml" ]] && [[ -f "$instance_dir/.env" ]]; then
        instance_name=$(basename "$instance_dir")

        if [[ "$FIRST" != true ]]; then
            echo "Waiting ${DELAY_SECONDS}s before starting next instance..."
            sleep "$DELAY_SECONDS"
        fi
        FIRST=false

        echo "Starting $instance_name..."
        (cd "$instance_dir" && docker compose up -d)
        echo "$instance_name started."
        echo ""
    else
        instance_name=$(basename "$instance_dir")
        if [[ ! -f "$instance_dir/.env" ]]; then
            echo "SKIPPING $instance_name - no .env file (copy from .env.example)"
        fi
    fi
done

echo "All configured instances started."
echo ""
echo "Check status: ./status.sh"
