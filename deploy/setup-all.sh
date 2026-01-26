#!/bin/bash
set -e

# Setup all 4 instances with staggered intervals and unique ports
# Intervals are prime-ish to avoid synchronization

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Setting up 4 ProtonMail forwarder instances..."
echo ""

# Instance 1: port 8081, captcha 5801, 30s interval
"$SCRIPT_DIR/setup-instance.sh" proton1 8081 5801 30

# Instance 2: port 8082, captcha 5802, 37s interval
"$SCRIPT_DIR/setup-instance.sh" proton2 8082 5802 37

# Instance 3: port 8083, captcha 5803, 43s interval
"$SCRIPT_DIR/setup-instance.sh" proton3 8083 5803 43

# Instance 4: port 8084, captcha 5804, 51s interval
"$SCRIPT_DIR/setup-instance.sh" proton4 8084 5804 51

echo ""
echo "========================================"
echo "All instances created!"
echo "========================================"
echo ""
echo "Instance directories:"
echo "  $SCRIPT_DIR/instances/proton1  (health: 8081, captcha: 5801, interval: 30s)"
echo "  $SCRIPT_DIR/instances/proton2  (health: 8082, captcha: 5802, interval: 37s)"
echo "  $SCRIPT_DIR/instances/proton3  (health: 8083, captcha: 5803, interval: 43s)"
echo "  $SCRIPT_DIR/instances/proton4  (health: 8084, captcha: 5804, interval: 51s)"
echo ""
echo "Next steps:"
echo "  1. Edit .env in each instance directory"
echo "  2. Run: ./start-all.sh"
echo ""
echo "IMPORTANT: Stagger initial authentication!"
echo "  - Start proton1, wait 5-10 minutes"
echo "  - Start proton2, wait 5-10 minutes"
echo "  - etc."
echo ""
