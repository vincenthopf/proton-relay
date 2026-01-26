#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Check for gum
if ! command -v gum &> /dev/null; then
    echo "Installing gum for beautiful terminal UI..."
    if command -v brew &> /dev/null; then
        brew install gum
    elif command -v apt-get &> /dev/null; then
        sudo mkdir -p /etc/apt/keyrings
        curl -fsSL https://repo.charm.sh/apt/gpg.key | sudo gpg --dearmor -o /etc/apt/keyrings/charm.gpg
        echo "deb [signed-by=/etc/apt/keyrings/charm.gpg] https://repo.charm.sh/apt/ * *" | sudo tee /etc/apt/sources.list.d/charm.list
        sudo apt update && sudo apt install gum
    else
        echo "Please install gum: https://github.com/charmbracelet/gum#installation"
        exit 1
    fi
fi

# Load Proton colors
source "$SCRIPT_DIR/lib/colors.sh"

# Header
proton_header "Proton Relay" "Multi-Account Setup"
echo ""

# Get number of instances
proton_muted "How many ProtonMail accounts do you want to forward?"
echo ""

count=$(gum input \
    --placeholder "Number of instances (1-10)" \
    --prompt "> " \
    --prompt.foreground "$PROTON_PURPLE" \
    --width 30)

# Validate input
if ! [[ "$count" =~ ^[0-9]+$ ]] || [[ "$count" -lt 1 ]] || [[ "$count" -gt 10 ]]; then
    proton_error "Please enter a number between 1 and 10"
    exit 1
fi

echo ""

# Show what will be created
proton_muted "This will create $count forwarder instance(s) with staggered intervals:"
echo ""

# Generate instance configs dynamically
# Base ports: health starts at 8081, captcha at 5801
# Intervals: staggered using primes to avoid synchronization (30, 37, 43, 47, 53, 59, 61, 67, 71, 73)
intervals=(30 37 43 47 53 59 61 67 71 73)

instances=()
for ((i=1; i<=count; i++)); do
    health_port=$((8080 + i))
    captcha_port=$((5800 + i))
    interval=${intervals[$((i-1))]}
    instances+=("proton${i}:${health_port}:${captcha_port}:${interval}")

    gum style --foreground "$PROTON_MAIL" "  proton${i}: health=$health_port, captcha=$captcha_port, interval=${interval}s"
done

echo ""

# Confirm
gum confirm --prompt.foreground "$PROTON_PURPLE" "Create these $count instance(s)?" || exit 0

echo ""

# Create instances
for instance in "${instances[@]}"; do
    IFS=':' read -r name health_port captcha_port interval <<< "$instance"

    gum spin --spinner dot --spinner.foreground "$PROTON_PURPLE" --title "Creating $name..." -- \
        "$SCRIPT_DIR/setup-instance.sh" "$name" "$health_port" "$captcha_port" "$interval"

    proton_success "$name created (health: $health_port, interval: ${interval}s)"
done

echo ""
gum style \
    --foreground "$COLOR_SUCCESS" --border-foreground "$COLOR_SUCCESS" --border rounded \
    --align left --width 60 --padding "1 2" \
    "All $count instance(s) created!

Next steps:
  1. Edit .env in each instance directory
  2. Run: ./start-all.sh

Instance directories:
  $SCRIPT_DIR/instances/"

echo ""
if [[ "$count" -gt 1 ]]; then
    proton_warning "IMPORTANT: Stagger initial authentication!"
    proton_muted "   Start instances one at a time, 5-10 min apart."
else
    proton_muted "Run ./start-all.sh when ready."
fi
echo ""
