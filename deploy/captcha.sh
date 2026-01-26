#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Load colors if available
if [[ -f "$SCRIPT_DIR/lib/colors.sh" ]] && command -v gum &> /dev/null; then
    source "$SCRIPT_DIR/lib/colors.sh"
    HAS_GUM=true
else
    HAS_GUM=false
fi

case "${1:-start}" in
    start)
        # Ensure network exists
        docker network create proton-relay-network 2>/dev/null || true

        # Start browser
        docker compose -f "$SCRIPT_DIR/docker-compose.yml" --profile captcha up -d

        if [[ "$HAS_GUM" == true ]]; then
            echo ""
            proton_success "CAPTCHA browser started"
            echo ""
            gum style --foreground "$PROTON_PURPLE" --bold "Open in your browser:"
            gum style --foreground "$COLOR_MUTED" "  http://localhost:5800"
            echo ""
            proton_muted "Log into any ProtonMail account to clear CAPTCHA flags."
            proton_muted "Run './captcha.sh stop' when done."
        else
            echo "CAPTCHA browser started at: http://localhost:5800"
            echo "Run './captcha.sh stop' when done."
        fi
        ;;
    stop)
        docker compose -f "$SCRIPT_DIR/docker-compose.yml" --profile captcha down
        if [[ "$HAS_GUM" == true ]]; then
            proton_success "CAPTCHA browser stopped"
        else
            echo "CAPTCHA browser stopped."
        fi
        ;;
    *)
        echo "Usage: $0 [start|stop]"
        exit 1
        ;;
esac
