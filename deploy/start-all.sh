#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTANCES_DIR="$SCRIPT_DIR/instances"

# Check for gum
if ! command -v gum &> /dev/null; then
    echo "gum not found. Run ./setup-all.sh first or install: https://github.com/charmbracelet/gum"
    exit 1
fi

# Load Proton colors
source "$SCRIPT_DIR/lib/colors.sh"

# Header
proton_header "Proton Relay" "Start Instances"

echo ""

# Check which instances are configured
configured=()
unconfigured=()

for instance_dir in "$INSTANCES_DIR"/*/; do
    [ -d "$instance_dir" ] || continue
    name=$(basename "$instance_dir")
    if [[ -f "$instance_dir/.env" ]]; then
        configured+=("$name")
    else
        unconfigured+=("$name")
    fi
done

if [[ ${#configured[@]} -eq 0 ]]; then
    proton_error "No configured instances found."
    proton_muted "Copy .env.example to .env in each instance directory."
    exit 1
fi

# Show status
proton_success "Configured: ${configured[*]}"
[[ ${#unconfigured[@]} -gt 0 ]] && gum style --foreground "$COLOR_WARNING" "Unconfigured (skipping): ${unconfigured[*]}"
echo ""

# Ask about delay
if gum confirm --prompt.foreground "$PROTON_PURPLE" "First time starting? (adds 5 min delay between instances for auth)"; then
    DELAY_SECONDS=300
    proton_muted "Using 5 minute delay between starts."
else
    DELAY_SECONDS=5
    proton_muted "Using minimal delay (restart mode)."
fi

echo ""
gum confirm --prompt.foreground "$PROTON_PURPLE" "Start ${#configured[@]} instance(s)?" || exit 0
echo ""

# Start instances
FIRST=true
for name in "${configured[@]}"; do
    instance_dir="$INSTANCES_DIR/$name"

    if [[ "$FIRST" != true ]] && [[ $DELAY_SECONDS -gt 5 ]]; then
        proton_muted "Waiting ${DELAY_SECONDS}s before next instance..."

        # Show countdown with spinner
        for ((i=DELAY_SECONDS; i>0; i-=10)); do
            remaining=$((i < 10 ? i : 10))
            gum spin --spinner dot --spinner.foreground "$PROTON_PURPLE" --title "Next start in ${i}s..." -- sleep $remaining
        done
    fi
    FIRST=false

    gum spin --spinner dot --spinner.foreground "$PROTON_PURPLE" --title "Starting $name..." -- \
        bash -c "cd '$instance_dir' && docker compose up -d 2>&1"

    proton_success "$name started"
done

echo ""
gum style \
    --foreground "$COLOR_SUCCESS" --border-foreground "$COLOR_SUCCESS" --border rounded \
    --padding "1 2" \
    "All instances started! Run ./status.sh to check health."
echo ""
