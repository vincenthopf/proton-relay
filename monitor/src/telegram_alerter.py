"""Telegram alerter for hydroxide monitor."""

import asyncio
import logging
import time
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)


class TelegramAlerter:
    """Send alerts via Telegram bot."""

    def __init__(self, bot_token: str, chat_id: str, instance_name: str = "unknown", cooldown: int = 600):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.instance_name = instance_name
        self.cooldown = cooldown
        self._last_alert: dict[str, float] = {}
        self._enabled = bool(bot_token and chat_id)

        if not self._enabled:
            logger.warning("Telegram alerts disabled (missing bot token or chat ID)")

    async def send_alert(self, error_type: str, message: str) -> bool:
        """Send alert if not in cooldown period."""
        if not self._enabled:
            return False

        # Check cooldown
        now = time.time()
        last = self._last_alert.get(error_type, 0)
        if now - last < self.cooldown:
            logger.debug("Alert %s suppressed (cooldown)", error_type)
            return False

        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": f"[{self.instance_name}] {message}",
                "parse_mode": "HTML",
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=10) as resp:
                    if resp.status == 200:
                        self._last_alert[error_type] = now
                        logger.info("Telegram alert sent for error_type=%s", error_type)
                        return True
                    else:
                        text = await resp.text()
                        logger.error("Telegram API error: %s %s", resp.status, text)
                        return False

        except Exception as e:
            logger.error("Failed to send Telegram alert: %s", e)
            return False

    async def send_status(self, message: str) -> bool:
        """Send status report (bypasses cooldown)."""
        if not self._enabled:
            return False

        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": f"[{self.instance_name}] {message}",
                "parse_mode": "HTML",
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=10) as resp:
                    if resp.status == 200:
                        logger.info("Telegram status report sent")
                        return True
                    else:
                        text = await resp.text()
                        logger.error("Telegram API error: %s %s", resp.status, text)
                        return False

        except Exception as e:
            logger.error("Failed to send Telegram status: %s", e)
            return False
