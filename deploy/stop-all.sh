#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTANCES_DIR="$SCRIPT_DIR/instances"

# Check for gum
if ! command -v gum &> /dev/null; then
    echo "gum not found. Install: https://github.com/charmbracelet/gum"
    exit 1
fi

# Load Proton colors
source "$SCRIPT_DIR/lib/colors.sh"

# Header (red-ish for stop action)
gum style \
    --foreground "$COLOR_ERROR" --border-foreground "$COLOR_ERROR" --border double \
    --align center --width 50 --margin "1 2" --padding "1 2" \
    'Proton Relay' 'Stop Instances'

echo ""

# Find running instances
running=()
for instance_dir in "$INSTANCES_DIR"/*/; do
    [ -d "$instance_dir" ] || continue
    name=$(basename "$instance_dir")
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${name}-"; then
        running+=("$name")
    fi
done

if [[ ${#running[@]} -eq 0 ]]; then
    proton_muted "No running instances found."
    exit 0
fi

gum style --foreground "$COLOR_WARNING" "Running instances: ${running[*]}"
echo ""

gum confirm --prompt.foreground "$COLOR_ERROR" "Stop all ${#running[@]} instance(s)?" || exit 0
echo ""

for name in "${running[@]}"; do
    instance_dir="$INSTANCES_DIR/$name"

    gum spin --spinner dot --spinner.foreground "$PROTON_PURPLE" --title "Stopping $name..." -- \
        bash -c "cd '$instance_dir' && docker compose down 2>&1"

    proton_success "$name stopped"
done

echo ""
proton_success "All instances stopped."
echo ""
