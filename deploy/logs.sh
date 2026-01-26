#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTANCES_DIR="$SCRIPT_DIR/instances"

# Check for gum
if ! command -v gum &> /dev/null; then
    echo "gum not found. Install: https://github.com/charmbracelet/gum"
    exit 1
fi

# If arguments provided, use them directly
if [[ -n "$1" ]]; then
    INSTANCE="$1"
    SERVICE="${2:-forwarder}"

    if [[ -d "$INSTANCES_DIR/$INSTANCE" ]]; then
        gum style --foreground 212 "Tailing $SERVICE logs for $INSTANCE..."
        echo ""
        cd "$INSTANCES_DIR/$INSTANCE"
        docker compose logs -f "$SERVICE"
    else
        gum style --foreground 196 "Instance not found: $INSTANCE"
        exit 1
    fi
    exit 0
fi

# Interactive mode - show selection
gum style \
    --foreground 212 --border-foreground 212 --border double \
    --align center --width 50 --margin "1 2" --padding "1 2" \
    'Proton Relay' 'View Logs'

echo ""

# Get available instances
instances=()
for instance_dir in "$INSTANCES_DIR"/*/; do
    [ -d "$instance_dir" ] || continue
    [[ -f "$instance_dir/docker-compose.yml" ]] || continue
    instances+=("$(basename "$instance_dir")")
done

if [[ ${#instances[@]} -eq 0 ]]; then
    gum style --foreground 240 "No instances found."
    exit 1
fi

# Add "all" option
options=("All instances (recent)" "${instances[@]}")

# Select instance
gum style --foreground 240 "Select instance:"
SELECTION=$(gum choose "${options[@]}")

if [[ "$SELECTION" == "All instances (recent)" ]]; then
    # Show recent logs from all
    gum style --foreground 212 "Recent logs from all instances:"
    echo ""

    for name in "${instances[@]}"; do
        instance_dir="$INSTANCES_DIR/$name"

        gum style --foreground 214 --bold "━━━ $name ━━━"
        (cd "$instance_dir" && docker compose logs --tail=15 forwarder 2>/dev/null) || echo "  (not running)"
        echo ""
    done
else
    # Select service
    gum style --foreground 240 "Select service:"
    SERVICE=$(gum choose "forwarder" "hydroxide")

    gum style --foreground 212 "Tailing $SERVICE logs for $SELECTION..."
    gum style --foreground 240 "(Ctrl+C to exit)"
    echo ""

    cd "$INSTANCES_DIR/$SELECTION"
    docker compose logs -f "$SERVICE"
fi
