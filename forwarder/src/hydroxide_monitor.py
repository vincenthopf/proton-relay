"""Monitor hydroxide container for auth errors and health issues."""

import asyncio
import logging
import re
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


class HydroxideMonitor:
    """Monitor hydroxide container for auth errors via Docker logs."""

    CONTAINER_NAME = "hydroxide-bridge"

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

    def __init__(self):
        self._last_log_check = 0
        self._logs_since = "1m"  # Check logs from last minute

    def _run_docker_command(self, args: list[str]) -> tuple[bool, str]:
        """Run a docker command and return (success, output)."""
        try:
            result = subprocess.run(
                ["docker"] + args,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except Exception as e:
            return False, str(e)

    async def check_health(self) -> tuple[bool, Optional[str]]:
        """Check if hydroxide container is healthy.

        Returns:
            (is_healthy, error_message_if_unhealthy)
        """
        # Run in thread to avoid blocking
        loop = asyncio.get_event_loop()
        success, output = await loop.run_in_executor(
            None,
            lambda: self._run_docker_command([
                "inspect",
                "--format",
                "{{.State.Health.Status}}",
                self.CONTAINER_NAME,
            ]),
        )

        if not success:
            # Container might not exist or docker not available
            if "No such object" in output:
                return False, "Container not found"
            return False, f"Docker inspect failed: {output}"

        health_status = output.strip().lower()

        if health_status == "healthy":
            return True, None
        elif health_status == "starting":
            return True, None  # Still starting, not an error yet
        elif health_status == "unhealthy":
            return False, "Container healthcheck failing"
        else:
            return False, f"Unknown health status: {health_status}"

    async def check_logs_for_errors(self) -> list[tuple[str, str]]:
        """Scan recent container logs for error patterns.

        Returns:
            List of (error_type, matched_line) tuples
        """
        loop = asyncio.get_event_loop()
        success, output = await loop.run_in_executor(
            None,
            lambda: self._run_docker_command([
                "logs",
                "--since",
                self._logs_since,
                self.CONTAINER_NAME,
            ]),
        )

        if not success:
            logger.debug("Failed to get container logs: %s", output)
            return []

        errors_found = []
        lines = output.lower().split("\n")

        for error_type, patterns in self.ERROR_PATTERNS.items():
            for pattern in patterns:
                regex = re.compile(pattern, re.IGNORECASE)
                for line in lines:
                    if regex.search(line):
                        errors_found.append((error_type, line.strip()))
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
        logger.info("Hydroxide monitor started (interval=%ds)", interval)

        while True:
            try:
                # Check container health
                is_healthy, error_msg = await self.check_health()

                if not is_healthy:
                    logger.warning("Hydroxide unhealthy: %s", error_msg)
                    await alerter.send_alert(
                        "hydroxide_unhealthy",
                        self.ALERT_MESSAGES["hydroxide_unhealthy"],
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
