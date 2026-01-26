#!/bin/bash
# Proton Brand Colors for Terminal UI
# Based on https://proton.me/blog/new-visual-universe

# Primary brand colors (hex for gum)
PROTON_PURPLE="#6d4aff"      # Primary Proton brand purple
PROTON_MAIL="#6d629b"        # Proton Mail accent (muted purple)
PROTON_PURPLE_LIGHT="#9b8aff" # Lighter purple for secondary text

# Status colors (accessible contrast)
COLOR_SUCCESS="#1f9f9c"      # Teal (based on VPN green, brightened for visibility)
COLOR_WARNING="#e5a34d"      # Amber/gold for warnings
COLOR_ERROR="#d64a6a"        # Magenta/pink (based on Drive, brightened)
COLOR_MUTED="#8a8a9b"        # Muted text (grey-purple)

# Semantic aliases
COLOR_HEALTHY="$COLOR_SUCCESS"
COLOR_DEGRADED="$COLOR_WARNING"
COLOR_STOPPED="$COLOR_ERROR"
COLOR_INACTIVE="$COLOR_MUTED"

# Header styling helper
proton_header() {
    local title="$1"
    local subtitle="${2:-}"

    if [[ -n "$subtitle" ]]; then
        gum style \
            --foreground "$PROTON_PURPLE" --border-foreground "$PROTON_PURPLE" --border double \
            --align center --width 50 --margin "1 2" --padding "1 2" \
            "$title" "$subtitle"
    else
        gum style \
            --foreground "$PROTON_PURPLE" --border-foreground "$PROTON_PURPLE" --border double \
            --align center --width 50 --margin "1 2" --padding "1 2" \
            "$title"
    fi
}

# Success message
proton_success() {
    gum style --foreground "$COLOR_SUCCESS" "✓ $1"
}

# Warning message
proton_warning() {
    gum style --foreground "$COLOR_WARNING" --bold "⚠ $1"
}

# Error message
proton_error() {
    gum style --foreground "$COLOR_ERROR" "✗ $1"
}

# Muted/secondary text
proton_muted() {
    gum style --foreground "$COLOR_MUTED" "$1"
}

# Info box
proton_box() {
    local color="${2:-$PROTON_MAIL}"
    gum style --border rounded --border-foreground "$color" --padding "1 2" "$1"
}
