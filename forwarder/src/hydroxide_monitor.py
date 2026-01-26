"""Monitor hydroxide container for auth errors and health issues."""

import asyncio
import json
import logging
import os
import re
import socket
import urllib.parse
from typing import Optional

logger = logging.getLogger(__name__)

# Docker socket path
DOCKER_SOCKET = "/var/run/docker.sock"


class HydroxideMonitor:
    """Monitor hydroxide container for auth errors via Docker API."""

    # Error patterns to detect in logs
    ERROR_PATTERNS = {
        "hydroxide_captcha": [
            r"captcha",
            r"human verification",
            r"hv_required",
        ],
        "hydroxide_credentials": [
            r"invalid credentials",
            r"incorrect password",
            r"authentication failed",
            r"401",
        ],
        "hydroxide_rate_limit": [
            r"rate limit",
            r"429",
            r"too many requests",
        ],
        "hydroxide_2fa": [
            r"two.?factor",
            r"2fa",
            r"totp",
            r"verification code",
        ],
        "hydroxide_session": [
            r"token expired",
            r"session expired",
            r"re-?authenticate",
            r"refresh token",
        ],
    }

    # Alert messages for each error type
    ALERT_MESSAGES = {
        "hydroxide_captcha": "ProtonMail requires CAPTCHA. Log in via web to clear.",
        "hydroxide_credentials": "ProtonMail credentials invalid. Check username/password.",
        "hydroxide_rate_limit": "ProtonMail rate limited. Wait before retry.",
        "hydroxide_2fa": "2FA issue detected. Check TOTP setup.",
        "hydroxide_session": "ProtonMail session expired. Re-authentication required.",
        "hydroxide_unhealthy": "Hydroxide container is unhealthy or stopped.",
    }

    def __init__(self, container_name: Optional[str] = None):
        # Container name from env or derive from COMPOSE_PROJECT_NAME
        if container_name:
            self._container_name = container_name
        else:
            project = os.environ.get("COMPOSE_PROJECT_NAME", "")
            if project:
                self._container_name = f"{project}-hydroxide"
            else:
                # Fallback - try to detect from PROTONMAIL_USERNAME
                username = os.environ.get("PROTONMAIL_USERNAME", "")
                if username and "@" in username:
                    name = username.split("@")[0].lower()
                    name = re.sub(r'[^a-z0-9-]', '-', name)
                    self._container_name = f"{name}-hydroxide"
                else:
                    self._container_name = "hydroxide"

        self._docker_available = os.path.exists(DOCKER_SOCKET) and os.access(DOCKER_SOCKET, os.R_OK)
        if not os.path.exists(DOCKER_SOCKET):
            logger.warning("Docker socket not available at %s - hydroxide monitoring disabled", DOCKER_SOCKET)
        elif not os.access(DOCKER_SOCKET, os.R_OK):
            logger.warning("Docker socket not readable (permission denied) - hydroxide monitoring disabled")
            logger.info("To enable monitoring, add docker group to forwarder container or run as root")

    def _docker_api_request(self, method: str, path: str, timeout: float = 5.0) -> tuple[bool, str]:
        """Make a request to Docker API via Unix socket.

        Returns:
            (success, response_body)
        """
        if not self._docker_available:
            return False, "Docker socket not available"

        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect(DOCKER_SOCKET)

            # Build HTTP request
            request = f"{method} {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n"
            sock.sendall(request.encode())

            # Read response
            response = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk

            sock.close()

            # Parse response
            response_str = response.decode('utf-8', errors='ignore')

            # Split headers and body
            if "\r\n\r\n" in response_str:
                headers, body = response_str.split("\r\n\r\n", 1)
            else:
                headers, body = response_str, ""

            # Check status code
            first_line = headers.split("\r\n")[0]
            if "200" in first_line or "304" in first_line:
                return True, body
            elif "404" in first_line:
                return False, "Container not found"
            else:
                return False, f"HTTP error: {first_line}"

        except socket.timeout:
            return False, "Request timed out"
        except Exception as e:
            return False, str(e)

    async def check_health(self) -> tuple[bool, Optional[str]]:
        """Check if hydroxide container is healthy.

        Returns:
            (is_healthy, error_message_if_unhealthy)
        """
        if not self._docker_available:
            return True, None  # Assume healthy if we can't check

        loop = asyncio.get_event_loop()
        encoded_name = urllib.parse.quote(self._container_name, safe='')
        success, response = await loop.run_in_executor(
            None,
            lambda: self._docker_api_request("GET", f"/containers/{encoded_name}/json"),
        )

        if not success:
            if "not found" in response.lower():
                return False, f"Container '{self._container_name}' not found"
            return False, f"Docker API error: {response}"

        try:
            data = json.loads(response)
            state = data.get("State", {})

            # Check if running
            if not state.get("Running", False):
                return False, "Container not running"

            # Check health if available
            health = state.get("Health", {})
            if health:
                status = health.get("Status", "").lower()
                if status == "healthy":
                    return True, None
                elif status == "starting":
                    return True, None  # Still starting, not an error
                elif status == "unhealthy":
                    return False, "Container healthcheck failing"
                else:
                    return True, None  # No health status = assume OK

            return True, None

        except json.JSONDecodeError as e:
            return False, f"Failed to parse Docker response: {e}"

    async def check_logs_for_errors(self) -> list[tuple[str, str]]:
        """Scan recent container logs for error patterns.

        Returns:
            List of (error_type, matched_line) tuples
        """
        if not self._docker_available:
            return []

        loop = asyncio.get_event_loop()
        encoded_name = urllib.parse.quote(self._container_name, safe='')
        # Get logs from last 60 seconds
        success, response = await loop.run_in_executor(
            None,
            lambda: self._docker_api_request(
                "GET",
                f"/containers/{encoded_name}/logs?stdout=1&stderr=1&since={int(asyncio.get_event_loop().time()) - 60}&tail=100",
                timeout=10.0,
            ),
        )

        if not success:
            logger.debug("Failed to get container logs: %s", response)
            return []

        errors_found = []
        lines = response.lower().split("\n")

        for error_type, patterns in self.ERROR_PATTERNS.items():
            for pattern in patterns:
                regex = re.compile(pattern, re.IGNORECASE)
                for line in lines:
                    if regex.search(line):
                        errors_found.append((error_type, line.strip()[:200]))  # Limit line length
                        break  # Only report first match per error type
                else:
                    continue
                break  # Found this error type, move to next

        return errors_found

    async def monitor_loop(self, alerter, interval: int = 60):
        """Main monitoring loop.

        Args:
            alerter: TelegramAlerter instance for sending alerts
            interval: Seconds between checks
        """
        if not self._docker_available:
            logger.info("Hydroxide monitor disabled (Docker socket not available)")
            return  # Exit loop - no point running without Docker

        logger.info("Hydroxide monitor started (container=%s, interval=%ds)", self._container_name, interval)

        while True:
            try:
                # Check container health
                is_healthy, error_msg = await self.check_health()

                if not is_healthy:
                    logger.warning("Hydroxide unhealthy: %s", error_msg)
                    await alerter.send_alert(
                        "hydroxide_unhealthy",
                        f"{self.ALERT_MESSAGES['hydroxide_unhealthy']} ({error_msg})",
                    )
                else:
                    # Check logs for auth errors
                    errors = await self.check_logs_for_errors()

                    for error_type, matched_line in errors:
                        logger.warning(
                            "Hydroxide error detected [%s]: %s",
                            error_type,
                            matched_line,
                        )
                        await alerter.send_alert(
                            error_type,
                            self.ALERT_MESSAGES.get(
                                error_type,
                                f"Hydroxide error: {matched_line}",
                            ),
                        )

            except Exception as e:
                logger.error("Error in hydroxide monitor: %s", e)

            await asyncio.sleep(interval)
