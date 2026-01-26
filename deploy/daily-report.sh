#!/bin/bash

# Daily health report - run via cron for 4-month monitoring
# Add to crontab: 0 9 * * * /path/to/deploy/daily-report.sh
#
# Sends a Telegram summary if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTANCES_DIR="$SCRIPT_DIR/instances"

# Try to load Telegram credentials from first instance
for instance_dir in "$INSTANCES_DIR"/*/; do
    if [[ -f "$instance_dir/.env" ]]; then
        source "$instance_dir/.env"
        break
    fi
done

generate_report() {
    echo "Daily ProtonMail Forwarder Report"
    echo "=================================="
    echo "Date: $(date '+%Y-%m-%d %H:%M:%S')"
    echo ""

    total_forwarded=0
    total_errors=0
    unhealthy_instances=""

    for instance_dir in "$INSTANCES_DIR"/*/; do
        if [[ -f "$instance_dir/docker-compose.yml" ]]; then
            instance_name=$(basename "$instance_dir")

            # Load instance env
            if [[ -f "$instance_dir/.env" ]]; then
                source "$instance_dir/.env"
            fi

            hydroxide_status=$(docker inspect --format='{{.State.Health.Status}}' "${instance_name}-hydroxide" 2>/dev/null || echo "not running")
            forwarder_status=$(docker inspect --format='{{.State.Health.Status}}' "${instance_name}-forwarder" 2>/dev/null || echo "not running")

            # Get stats from health endpoint
            forward_count=0
            error_count=0
            if [[ "$forwarder_status" == "healthy" ]] && [[ -n "$HEALTH_CHECK_PORT" ]]; then
                health_data=$(curl -s "http://localhost:$HEALTH_CHECK_PORT/health" 2>/dev/null)
                forward_count=$(echo "$health_data" | grep -o '"forward_count":[0-9]*' | cut -d: -f2 || echo 0)
                error_count=$(echo "$health_data" | grep -o '"error_count":[0-9]*' | cut -d: -f2 || echo 0)
            fi

            total_forwarded=$((total_forwarded + forward_count))
            total_errors=$((total_errors + error_count))

            status_icon="✅"
            if [[ "$hydroxide_status" != "healthy" ]] || [[ "$forwarder_status" != "healthy" ]]; then
                status_icon="❌"
                unhealthy_instances="$unhealthy_instances $instance_name"
            fi

            echo "$status_icon $instance_name: forwarded=$forward_count errors=$error_count (hydroxide=$hydroxide_status, forwarder=$forwarder_status)"
        fi
    done

    echo ""
    echo "TOTALS: $total_forwarded emails forwarded, $total_errors errors"

    if [[ -n "$unhealthy_instances" ]]; then
        echo ""
        echo "⚠️  ATTENTION: Unhealthy instances:$unhealthy_instances"
    fi
}

# Generate report
REPORT=$(generate_report)
echo "$REPORT"

# Send to Telegram if configured
if [[ -n "$TELEGRAM_BOT_TOKEN" ]] && [[ -n "$TELEGRAM_CHAT_ID" ]]; then
    # Escape special characters for Telegram
    ESCAPED_REPORT=$(echo "$REPORT" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g')

    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d "chat_id=${TELEGRAM_CHAT_ID}" \
        -d "text=<pre>${ESCAPED_REPORT}</pre>" \
        -d "parse_mode=HTML" > /dev/null

    echo ""
    echo "(Report sent to Telegram)"
fi
