#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTANCES_DIR="$SCRIPT_DIR/instances"

echo "Stopping all instances..."
echo ""

for instance_dir in "$INSTANCES_DIR"/*/; do
    if [[ -f "$instance_dir/docker-compose.yml" ]]; then
        instance_name=$(basename "$instance_dir")
        echo "Stopping $instance_name..."
        (cd "$instance_dir" && docker compose down)
    fi
done

echo ""
echo "All instances stopped."
