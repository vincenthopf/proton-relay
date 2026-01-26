#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTANCES_DIR="$SCRIPT_DIR/instances"

# Check for gum
if ! command -v gum &> /dev/null; then
    echo "gum not found. Install: https://github.com/charmbracelet/gum"
    exit 1
fi

# Load Proton colors
source "$SCRIPT_DIR/lib/colors.sh"

# Header
proton_header "Proton Relay" "Status Dashboard"

echo ""

# Collect status for all instances
has_instances=false

for instance_dir in "$INSTANCES_DIR"/*/; do
    [ -d "$instance_dir" ] || continue
    [[ -f "$instance_dir/docker-compose.yml" ]] || continue

    has_instances=true
    name=$(basename "$instance_dir")

    # Load env for ports
    health_port=""
    if [[ -f "$instance_dir/.env" ]]; then
        health_port=$(grep -E '^HEALTH_CHECK_PORT=' "$instance_dir/.env" 2>/dev/null | cut -d= -f2)
    fi

    # Get container status
    hydroxide_status=$(docker inspect --format='{{.State.Health.Status}}' "${name}-hydroxide" 2>/dev/null || echo "stopped")
    forwarder_status=$(docker inspect --format='{{.State.Health.Status}}' "${name}-forwarder" 2>/dev/null || echo "stopped")

    # Get stats from health endpoint
    forward_count="-"
    error_count="-"
    if [[ -n "$health_port" ]] && [[ "$forwarder_status" == "healthy" ]]; then
        health_data=$(curl -s --connect-timeout 2 "http://localhost:$health_port/health" 2>/dev/null || echo "{}")
        forward_count=$(echo "$health_data" | grep -o '"forward_count":[0-9]*' | cut -d: -f2)
        error_count=$(echo "$health_data" | grep -o '"error_count":[0-9]*' | cut -d: -f2)
        [[ -z "$forward_count" ]] && forward_count="-"
        [[ -z "$error_count" ]] && error_count="-"
    fi

    # Status colors (using Proton palette)
    h_color="$COLOR_ERROR"
    f_color="$COLOR_ERROR"
    [[ "$hydroxide_status" == "healthy" ]] && h_color="$COLOR_SUCCESS"
    [[ "$hydroxide_status" == "starting" ]] && h_color="$COLOR_WARNING"
    [[ "$forwarder_status" == "healthy" ]] && f_color="$COLOR_SUCCESS"
    [[ "$forwarder_status" == "starting" ]] && f_color="$COLOR_WARNING"

    # Overall status
    if [[ "$hydroxide_status" == "healthy" ]] && [[ "$forwarder_status" == "healthy" ]]; then
        status_icon="✓"
        status_color="$COLOR_SUCCESS"
    elif [[ "$hydroxide_status" == "stopped" ]] && [[ "$forwarder_status" == "stopped" ]]; then
        status_icon="○"
        status_color="$COLOR_MUTED"
    else
        status_icon="!"
        status_color="$COLOR_WARNING"
    fi

    # Format status strings with color
    h_status_str=$(gum style --foreground "$h_color" "$hydroxide_status")
    f_status_str=$(gum style --foreground "$f_color" "$forwarder_status")
    name_str=$(gum style --foreground "$status_color" --bold "$status_icon $name")

    # Build instance box content
    box_content="$name_str

  hydroxide:  $h_status_str
  forwarder:  $f_status_str

  $(gum style --foreground "$COLOR_MUTED" "forwarded:") $forward_count    $(gum style --foreground "$COLOR_MUTED" "errors:") $error_count
  $(gum style --foreground "$COLOR_MUTED" "health:") http://localhost:${health_port:-????}/health"

    gum style --border rounded --border-foreground "$status_color" --padding "0 1" --width 58 "$box_content"
    echo ""
done

if [[ "$has_instances" == false ]]; then
    proton_muted "No instances found. Run ./setup-all.sh first."
fi

# Legend
legend="Legend: $(gum style --foreground "$COLOR_SUCCESS" '✓ healthy')  $(gum style --foreground "$COLOR_WARNING" '! degraded')  $(gum style --foreground "$COLOR_MUTED" '○ stopped')"
proton_muted "$legend"
echo ""
