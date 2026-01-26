#!/bin/bash
set -e

# Configuration
AUTH_FILE="/home/hydroxide/.config/hydroxide/auth.json"
HYDROXIDE_CMD="/usr/local/bin/hydroxide"

# Color codes for logging
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_debug() {
    echo -e "${BLUE}[DEBUG]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# Function to handle authentication
authenticate() {
    log_info "Starting hydroxide authentication process..."
    
    if [ -z "$PROTONMAIL_USERNAME" ] || [ -z "$PROTONMAIL_PASSWORD" ]; then
        log_error "PROTONMAIL_USERNAME and PROTONMAIL_PASSWORD must be set in environment variables"
        exit 1
    fi
    
    log_info "Username: $PROTONMAIL_USERNAME"
    
    # Check if already authenticated (bridge password stored alongside auth file for persistence)
    BRIDGE_PASS_FILE="/home/hydroxide/.config/hydroxide/bridge_password"
    if [ -f "$AUTH_FILE" ] && [ -f "$BRIDGE_PASS_FILE" ]; then
        BRIDGE_PASSWORD=$(cat "$BRIDGE_PASS_FILE")
        if [ -n "$BRIDGE_PASSWORD" ]; then
            log_info "Found existing authentication and bridge password"

            # Share with forwarder container
            if [ -d "/bridge-password" ]; then
                if echo "$BRIDGE_PASSWORD" > /bridge-password/password.txt 2>/dev/null; then
                    chmod 644 /bridge-password/password.txt
                    log_info "Bridge password copied to shared volume"
                fi
            fi

            export HYDROXIDE_BRIDGE_PASS="$BRIDGE_PASSWORD"
            return 0
        fi
    fi

    # Clean up partial state
    if [ -f "$AUTH_FILE" ] && [ ! -f "$BRIDGE_PASS_FILE" ]; then
        log_warn "Auth file exists but no bridge password - re-authenticating"
        rm -f "$AUTH_FILE"
    fi
    
    # Authenticate if needed
    if [ ! -f "$AUTH_FILE" ]; then
        log_info "No valid authentication found - authenticating with ProtonMail..."
        
        # Run auth command with password via environment variable (patched hydroxide)
        log_debug "Running: hydroxide auth [username] (password via environment)"
        
        # Set password in environment variable for our patched hydroxide
        export HYDROXIDE_AUTH_PASS="$PROTONMAIL_PASSWORD"
        
        # Run auth command - patched hydroxide will read from HYDROXIDE_AUTH_PASS
        set +e
        AUTH_OUTPUT=$($HYDROXIDE_CMD auth "$PROTONMAIL_USERNAME" 2>&1)
        AUTH_EXIT_CODE=$?
        set -e
        
        if [ $AUTH_EXIT_CODE -ne 0 ]; then
            log_error "Authentication command failed with exit code: $AUTH_EXIT_CODE"
            log_error "$AUTH_OUTPUT"
            log_error "Waiting 60 seconds before exit to avoid rate-limiting..."
            sleep 60
            exit 1
        fi
        
        # Check if authentication was successful
        if echo "$AUTH_OUTPUT" | grep -q "Bridge password:"; then
            # Extract bridge password from output
            BRIDGE_PASSWORD=$(echo "$AUTH_OUTPUT" | grep "Bridge password:" | sed 's/Bridge password: //' | tr -d '[:space:]')
            
            if [ -z "$BRIDGE_PASSWORD" ]; then
                log_error "Failed to extract bridge password from output"
                log_error "Output was: $AUTH_OUTPUT"
                exit 1
            fi
            
            log_info "✅ Authentication successful!"
            log_info "Bridge password has been generated (hidden for security)"
            log_debug "Bridge password length: ${#BRIDGE_PASSWORD} characters"
            
            # Save to persistent volume (same location as auth.json)
            echo "$BRIDGE_PASSWORD" > "$BRIDGE_PASS_FILE"
            chmod 600 "$BRIDGE_PASS_FILE"
            log_info "Bridge password saved to persistent storage"
            
            # Also save in a shared volume location for the forwarder
            if [ -d "/bridge-password" ]; then
                if echo "$BRIDGE_PASSWORD" > /bridge-password/password.txt 2>/dev/null; then
                    chmod 644 /bridge-password/password.txt
                    log_info "Bridge password saved to shared volume for forwarder"
                else
                    log_warn "Could not write to /bridge-password - forwarder will read from container storage"
                fi
            else
                log_warn "/bridge-password directory not mounted - forwarder may not get password automatically"
            fi
            
            export HYDROXIDE_BRIDGE_PASS="$BRIDGE_PASSWORD"
            
            # Verify authentication worked
            log_info "Verifying authentication..."
            if [ -f "$AUTH_FILE" ]; then
                log_info "✅ Authentication file created successfully"
            else
                log_error "Authentication file was not created - something went wrong"
                exit 1
            fi
            
        else
            log_error "Authentication failed - no bridge password in output"
            log_error "Output: $AUTH_OUTPUT"
            
            # Check for common errors
            if echo "$AUTH_OUTPUT" | grep -qi "incorrect password\|invalid credentials\|401"; then
                log_error "Invalid ProtonMail credentials. Please check your username and password."
            elif echo "$AUTH_OUTPUT" | grep -qi "two.factor\|2fa"; then
                log_error "Two-factor authentication is enabled. Please disable 2FA temporarily for initial setup."
            elif echo "$AUTH_OUTPUT" | grep -qi "rate limit\|429"; then
                log_error "Rate limited by ProtonMail. Please wait a few minutes and try again."
            fi
            
            exit 1
        fi
    fi
}

# Function to test IMAP connectivity
test_imap_connection() {
    log_info "Testing IMAP service connectivity..."
    
    # Try to connect to IMAP port
    if nc -z localhost 1143 2>/dev/null; then
        log_info "✅ IMAP port 1143 is accessible"
        return 0
    else
        log_warn "IMAP port 1143 not yet accessible"
        return 1
    fi
}

# Function to start services
start_services() {
    local mode="${1:-serve}"

    case "$mode" in
        serve)
            log_info "Starting hydroxide in serve mode..."
            log_info "  - IMAP will be available on port 1143"
            log_info "  - SMTP will be available on port 1025"
            log_info "  - CardDAV will be available on port 8080"
            exec $HYDROXIDE_CMD -imap-host 0.0.0.0 -smtp-host 0.0.0.0 -carddav-host 0.0.0.0 serve
            ;;
        imap)
            log_info "Starting hydroxide IMAP service on port 1143..."
            exec $HYDROXIDE_CMD -imap-host 0.0.0.0 imap
            ;;
        smtp)
            log_info "Starting hydroxide SMTP service on port 1025..."
            exec $HYDROXIDE_CMD smtp
            ;;
        carddav)
            log_info "Starting hydroxide CardDAV service on port 8080..."
            exec $HYDROXIDE_CMD carddav
            ;;
        *)
            log_error "Unknown mode: $mode. Use serve, imap, smtp, or carddav"
            exit 1
            ;;
    esac
}

# Main execution
main() {
    log_info "======================================"
    log_info "Hydroxide Bridge Container Starting"
    log_info "======================================"
    log_info "Version: Hydroxide Bridge"
    log_info "Mode: ${1:-serve}"
    
    # Authenticate
    authenticate
    
    log_info "Preparing to start services..."
    
    # Give a moment for everything to settle
    sleep 2
    
    # Start service based on command
    start_services "$@"
}

# Trap signals for graceful shutdown
trap 'log_info "Received shutdown signal - cleaning up..."; exit 0' SIGTERM SIGINT

# Run main function
main "$@"