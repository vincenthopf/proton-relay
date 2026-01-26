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

# Header
gum style \
    --foreground 212 --border-foreground 212 --border double \
    --align center --width 50 --margin "1 2" --padding "1 2" \
    'Proton Relay' 'Multi-Account Setup'

echo ""
gum style --foreground 240 "This will create 4 forwarder instances with staggered intervals."
echo ""

# Confirm
gum confirm "Create 4 ProtonMail forwarder instances?" || exit 0

echo ""

# Instance configs: name, health_port, captcha_port, interval
instances=(
    "proton1:8081:5801:30"
    "proton2:8082:5802:37"
    "proton3:8083:5803:43"
    "proton4:8084:5804:51"
)

for instance in "${instances[@]}"; do
    IFS=':' read -r name health_port captcha_port interval <<< "$instance"

    gum spin --spinner dot --title "Creating $name..." -- \
        "$SCRIPT_DIR/setup-instance.sh" "$name" "$health_port" "$captcha_port" "$interval"

    gum style --foreground 42 "✓ $name created (health: $health_port, interval: ${interval}s)"
done

echo ""
gum style \
    --foreground 42 --border-foreground 42 --border rounded \
    --align left --width 60 --padding "1 2" \
    "All instances created!

Next steps:
  1. Edit .env in each instance directory
  2. Run: ./start-all.sh

Instance directories:
  $SCRIPT_DIR/instances/"

echo ""
gum style --foreground 214 --bold "⚠  IMPORTANT: Stagger initial authentication!"
gum style --foreground 240 "   Start instances one at a time, 5-10 min apart."
echo ""
