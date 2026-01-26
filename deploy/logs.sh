#!/bin/bash

# View logs for a specific instance or all instances
# Usage: ./logs.sh [instance-name] [service]
# Examples:
#   ./logs.sh              # All forwarder logs
#   ./logs.sh proton1      # proton1 forwarder logs
#   ./logs.sh proton1 hydroxide  # proton1 hydroxide logs

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTANCES_DIR="$SCRIPT_DIR/instances"

INSTANCE="${1:-}"
SERVICE="${2:-forwarder}"

if [[ -n "$INSTANCE" ]]; then
    # Specific instance
    if [[ -d "$INSTANCES_DIR/$INSTANCE" ]]; then
        cd "$INSTANCES_DIR/$INSTANCE"
        docker compose logs -f "$SERVICE"
    else
        echo "Instance not found: $INSTANCE"
        echo "Available: $(ls "$INSTANCES_DIR")"
        exit 1
    fi
else
    # All instances - show recent logs from all forwarders
    echo "Recent logs from all forwarders (use './logs.sh <instance>' for specific):"
    echo ""
    for instance_dir in "$INSTANCES_DIR"/*/; do
        if [[ -f "$instance_dir/docker-compose.yml" ]]; then
            instance_name=$(basename "$instance_dir")
            echo "=== $instance_name ==="
            (cd "$instance_dir" && docker compose logs --tail=10 "$SERVICE" 2>/dev/null)
            echo ""
        fi
    done
fi
