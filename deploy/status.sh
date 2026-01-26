#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTANCES_DIR="$SCRIPT_DIR/instances"

echo "ProtonMail Forwarder Status"
echo "============================"
echo ""

for instance_dir in "$INSTANCES_DIR"/*/; do
    if [[ -f "$instance_dir/docker-compose.yml" ]]; then
        instance_name=$(basename "$instance_dir")

        # Load env to get ports
        if [[ -f "$instance_dir/.env" ]]; then
            source "$instance_dir/.env"
        fi

        echo "[$instance_name]"

        # Check hydroxide container
        hydroxide_status=$(docker inspect --format='{{.State.Health.Status}}' "${instance_name}-hydroxide" 2>/dev/null || echo "not running")
        forwarder_status=$(docker inspect --format='{{.State.Health.Status}}' "${instance_name}-forwarder" 2>/dev/null || echo "not running")

        # Get forward count from health endpoint
        forward_count="N/A"
        if [[ "$forwarder_status" == "healthy" ]] && [[ -n "$HEALTH_CHECK_PORT" ]]; then
            stats=$(curl -s "http://localhost:$HEALTH_CHECK_PORT/health" 2>/dev/null | grep -o '"forward_count":[0-9]*' | cut -d: -f2)
            if [[ -n "$stats" ]]; then
                forward_count="$stats"
            fi
        fi

        printf "  %-12s %s\n" "Hydroxide:" "$hydroxide_status"
        printf "  %-12s %s\n" "Forwarder:" "$forwarder_status"
        printf "  %-12s %s\n" "Forwarded:" "$forward_count emails"
        printf "  %-12s %s\n" "Health:" "http://localhost:${HEALTH_CHECK_PORT:-8080}/health"
        echo ""
    fi
done
