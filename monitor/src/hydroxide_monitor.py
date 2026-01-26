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

    def __init__(self, container_name: str):
        self._container_name = container_name
        self._docker_available = os.path.exists(DOCKER_SOCKET)

        if not self._docker_available:
            logger.error("Docker socket not available at %s", DOCKER_SOCKET)

    def _parse_chunked_body(self, body: str) -> str:
        """Parse HTTP chunked transfer encoding."""
        result = []
        remaining = body

        while remaining:
            # Find the chunk size line
            if "\r\n" not in remaining:
                break

            size_line, remaining = remaining.split("\r\n", 1)

            # Parse hex chunk size (ignore extensions after semicolon)
            try:
                chunk_size = int(size_line.split(";")[0].strip(), 16)
            except ValueError:
                # Not a valid chunk size, might be the actual content
                result.append(size_line)
                if remaining:
                    result.append(remaining)
                break

            if chunk_size == 0:
                break  # Final chunk

            # Extract the chunk data
            chunk_data = remaining[:chunk_size]
            result.append(chunk_data)

            # Skip past chunk data and trailing CRLF
            remaining = remaining[chunk_size:]
            if remaining.startswith("\r\n"):
                remaining = remaining[2:]

        return "".join(result)

    def _docker_api_request(self, method: str, path: str, timeout: float = 5.0) -> tuple[bool, str]:
        """Make a request to Docker API via Unix socket."""
        if not self._docker_available:
            return False, "Docker socket not available"

        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect(DOCKER_SOCKET)

            request = f"{method} {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n"
            sock.sendall(request.encode())

            response = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk

            sock.close()

            response_str = response.decode('utf-8', errors='ignore')

            if "\r\n\r\n" in response_str:
                headers, body = response_str.split("\r\n\r\n", 1)
            else:
                headers, body = response_str, ""

            # Check for chunked transfer encoding
            if "transfer-encoding: chunked" in headers.lower():
                body = self._parse_chunked_body(body)

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
        """Check if hydroxide container is healthy."""
        if not self._docker_available:
            return False, "Docker socket not available"

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

            if not state.get("Running", False):
                return False, "Container not running"

            health = state.get("Health", {})
            if health:
                status = health.get("Status", "").lower()
                if status == "healthy":
                    return True, None
                elif status == "starting":
                    return True, None
                elif status == "unhealthy":
                    return False, "Container healthcheck failing"

            return True, None

        except json.JSONDecodeError as e:
            return False, f"Failed to parse Docker response: {e}"

    async def check_logs_for_errors(self) -> list[tuple[str, str]]:
        """Scan recent container logs for error patterns."""
        if not self._docker_available:
            return []

        loop = asyncio.get_event_loop()
        encoded_name = urllib.parse.quote(self._container_name, safe='')

        import time
        since = int(time.time()) - 120  # Last 2 minutes

        success, response = await loop.run_in_executor(
            None,
            lambda: self._docker_api_request(
                "GET",
                f"/containers/{encoded_name}/logs?stdout=1&stderr=1&since={since}&tail=100",
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
                        errors_found.append((error_type, line.strip()[:200]))
                        break
                else:
                    continue
                break

        return errors_found

    async def monitor_loop(self, alerter, interval: int = 60, status_interval: int = 3600):
        """Main monitoring loop.

        Args:
            alerter: TelegramAlerter instance
            interval: Seconds between health checks (default 60)
            status_interval: Seconds between status reports (default 3600 = 1 hour)
        """
        if not self._docker_available:
            logger.error("Cannot start monitor - Docker socket not available")
            await alerter.send_alert("monitor_error", f"Monitor failed to start - Docker socket not available (container: {self._container_name})")
            return

        logger.info(
            "Hydroxide monitor started (container=%s, check_interval=%ds, status_interval=%ds)",
            self._container_name,
            interval,
            status_interval,
        )

        check_count = 0
        checks_per_status = max(1, status_interval // interval)

        while True:
            try:
                check_count += 1
                is_healthy, error_msg = await self.check_health()

                if is_healthy:
                    logger.debug("Hydroxide container healthy")

                    # Check logs for auth errors even when container appears healthy
                    errors = await self.check_logs_for_errors()

                    for error_type, matched_line in errors:
                        logger.warning(
                            "Hydroxide error detected [%s]: %s",
                            error_type,
                            matched_line,
                        )
                        await alerter.send_alert(
                            error_type,
                            f"{self.ALERT_MESSAGES.get(error_type, 'Error detected')} (container: {self._container_name})",
                        )

                    # Send periodic status report
                    if check_count >= checks_per_status:
                        check_count = 0
                        await alerter.send_status(f"Status OK - {self._container_name} healthy")
                        logger.info("Sent hourly status report")

                else:
                    logger.warning("Hydroxide unhealthy: %s", error_msg)
                    await alerter.send_alert(
                        "hydroxide_unhealthy",
                        f"{self.ALERT_MESSAGES['hydroxide_unhealthy']} (container: {self._container_name}, error: {error_msg})",
                    )

            except Exception as e:
                logger.error("Error in hydroxide monitor: %s", e)
                await alerter.send_alert(
                    "monitor_error",
                    f"Monitor error (container: {self._container_name}): {e}",
                )

            await asyncio.sleep(interval)
