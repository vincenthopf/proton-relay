#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTANCES_DIR="$SCRIPT_DIR/instances"

# Check for gum
if ! command -v gum &> /dev/null; then
    echo "gum not found. Install: https://github.com/charmbracelet/gum"
    exit 1
fi

# Header
gum style \
    --foreground 196 --border-foreground 196 --border double \
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
    gum style --foreground 240 "No running instances found."
    exit 0
fi

gum style --foreground 214 "Running instances: ${running[*]}"
echo ""

gum confirm "Stop all ${#running[@]} instance(s)?" || exit 0
echo ""

for name in "${running[@]}"; do
    instance_dir="$INSTANCES_DIR/$name"

    gum spin --spinner dot --title "Stopping $name..." -- \
        bash -c "cd '$instance_dir' && docker compose down 2>&1"

    gum style --foreground 42 "✓ $name stopped"
done

echo ""
gum style --foreground 42 "All instances stopped."
echo ""
