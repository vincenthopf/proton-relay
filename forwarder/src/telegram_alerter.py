import logging
import time
import urllib.parse
import urllib.request
from typing import Dict

logger = logging.getLogger(__name__)

# Rate limit: one alert per error_type per 10 minutes
RATE_LIMIT_SECONDS = 600


class TelegramAlerter:
    """Sends alert messages via Telegram Bot API.

    If bot_token or chat_id are empty/None, all calls are silent no-ops.
    Rate-limited to one alert per error_type per 10 minutes.
    """

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._bot_token = bot_token or ""
        self._chat_id = chat_id or ""
        self._last_alert: Dict[str, float] = {}
        self._enabled = bool(self._bot_token and self._chat_id)

        if not self._enabled:
            logger.info("Telegram alerter disabled (bot_token or chat_id not configured)")

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def send_alert(self, error_type: str, message: str) -> None:
        """Send an alert message to Telegram.

        Args:
            error_type: Category of the error (used for rate limiting).
            message: Human-readable alert text.
        """
        if not self._enabled:
            return

        now = time.monotonic()
        last = self._last_alert.get(error_type)

        if last is not None and (now - last) < RATE_LIMIT_SECONDS:
            logger.debug(
                "Telegram alert rate-limited for error_type=%s (%.0fs remaining)",
                error_type,
                RATE_LIMIT_SECONDS - (now - last),
            )
            return

        try:
            self._post_message(error_type, message)
            self._last_alert[error_type] = now
            logger.info("Telegram alert sent for error_type=%s", error_type)
        except Exception:
            logger.exception("Failed to send Telegram alert for error_type=%s", error_type)

    def _post_message(self, error_type: str, message: str) -> None:
        """Post a message to the Telegram Bot API (blocking I/O)."""
        text = f"[{error_type}] {message}"
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "HTML",
        }).encode("utf-8")

        request = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(request, timeout=10) as response:
            if response.status != 200:
                logger.warning(
                    "Telegram API returned status %d", response.status
                )
