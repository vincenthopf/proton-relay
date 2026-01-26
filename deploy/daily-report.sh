#!/bin/bash

# Daily health report - run via cron for 4-month monitoring
# Add to crontab: 0 9 * * * /path/to/deploy/daily-report.sh
#
# Sends a Telegram summary if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set
# Note: This script works without gum for cron compatibility

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTANCES_DIR="$SCRIPT_DIR/instances"

# Try to load Telegram credentials from first instance
for instance_dir in "$INSTANCES_DIR"/*/; do
    if [[ -f "$instance_dir/.env" ]]; then
        source "$instance_dir/.env"
        break
    fi
done

# Check if running interactively (has gum)
INTERACTIVE=false
if command -v gum &> /dev/null && [[ -t 1 ]]; then
    INTERACTIVE=true
fi

generate_report() {
    local total_forwarded=0
    local total_errors=0
    local unhealthy_instances=""
    local report=""

    report+="Proton Relay Daily Report\n"
    report+="══════════════════════════\n"
    report+="Date: $(date '+%Y-%m-%d %H:%M:%S')\n\n"

    for instance_dir in "$INSTANCES_DIR"/*/; do
        [[ -f "$instance_dir/docker-compose.yml" ]] || continue
        instance_name=$(basename "$instance_dir")

        # Load instance env
        local HEALTH_CHECK_PORT=""
        if [[ -f "$instance_dir/.env" ]]; then
            HEALTH_CHECK_PORT=$(grep -E '^HEALTH_CHECK_PORT=' "$instance_dir/.env" 2>/dev/null | cut -d= -f2)
        fi

        hydroxide_status=$(docker inspect --format='{{.State.Health.Status}}' "${instance_name}-hydroxide" 2>/dev/null || echo "stopped")
        forwarder_status=$(docker inspect --format='{{.State.Health.Status}}' "${instance_name}-forwarder" 2>/dev/null || echo "stopped")

        # Get stats from health endpoint
        forward_count=0
        error_count=0
        if [[ "$forwarder_status" == "healthy" ]] && [[ -n "$HEALTH_CHECK_PORT" ]]; then
            health_data=$(curl -s --connect-timeout 2 "http://localhost:$HEALTH_CHECK_PORT/health" 2>/dev/null)
            forward_count=$(echo "$health_data" | grep -o '"forward_count":[0-9]*' | cut -d: -f2)
            error_count=$(echo "$health_data" | grep -o '"error_count":[0-9]*' | cut -d: -f2)
            [[ -z "$forward_count" ]] && forward_count=0
            [[ -z "$error_count" ]] && error_count=0
        fi

        total_forwarded=$((total_forwarded + forward_count))
        total_errors=$((total_errors + error_count))

        status_icon="✓"
        if [[ "$hydroxide_status" != "healthy" ]] || [[ "$forwarder_status" != "healthy" ]]; then
            status_icon="✗"
            unhealthy_instances="$unhealthy_instances $instance_name"
        fi

        report+="$status_icon $instance_name\n"
        report+="  forwarded: $forward_count  errors: $error_count\n"
        report+="  hydroxide: $hydroxide_status  forwarder: $forwarder_status\n\n"
    done

    report+="──────────────────────────\n"
    report+="TOTAL: $total_forwarded forwarded, $total_errors errors\n"

    if [[ -n "$unhealthy_instances" ]]; then
        report+="\n⚠ UNHEALTHY:$unhealthy_instances\n"
    fi

    echo -e "$report"
}

# Generate report
REPORT=$(generate_report)

# Display report
if [[ "$INTERACTIVE" == true ]]; then
    gum style \
        --foreground 212 --border-foreground 212 --border double \
        --align center --width 50 --margin "1 2" --padding "1 2" \
        'Proton Relay' 'Daily Report'
    echo ""
    echo -e "$REPORT"
else
    echo -e "$REPORT"
fi

# Send to Telegram if configured
if [[ -n "$TELEGRAM_BOT_TOKEN" ]] && [[ -n "$TELEGRAM_CHAT_ID" ]]; then
    # Escape special characters for Telegram
    ESCAPED_REPORT=$(echo -e "$REPORT" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g')

    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d "chat_id=${TELEGRAM_CHAT_ID}" \
        -d "text=<pre>${ESCAPED_REPORT}</pre>" \
        -d "parse_mode=HTML" > /dev/null

    if [[ "$INTERACTIVE" == true ]]; then
        echo ""
        gum style --foreground 42 "Report sent to Telegram"
    else
        echo "(Report sent to Telegram)"
    fi
fi
