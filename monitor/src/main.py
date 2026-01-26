#!/usr/bin/env python3
"""Hydroxide container monitor - standalone service."""

import asyncio
import logging
import os
import sys

from config import config
from hydroxide_monitor import HydroxideMonitor
from telegram_alerter import TelegramAlerter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def main():
    logger.info("=" * 50)
    logger.info("Hydroxide Monitor Starting")
    logger.info("=" * 50)

    # Determine container name
    container_name = config.container_name
    if not container_name:
        project = os.environ.get("COMPOSE_PROJECT_NAME", "")
        if project:
            container_name = f"{project}-hydroxide"
        else:
            logger.error("CONTAINER_NAME or COMPOSE_PROJECT_NAME must be set")
            sys.exit(1)

    logger.info("Instance: %s", config.instance_name)
    logger.info("Monitoring container: %s", container_name)
    logger.info("Check interval: %d seconds", config.check_interval)
    logger.info("Status report interval: %d seconds (%d minutes)", config.status_interval, config.status_interval // 60)
    logger.info("Alert cooldown: %d seconds", config.alert_cooldown)

    # Initialize alerter
    alerter = TelegramAlerter(
        bot_token=config.telegram_bot_token,
        chat_id=config.telegram_chat_id,
        instance_name=config.instance_name,
        cooldown=config.alert_cooldown,
    )

    if config.telegram_bot_token and config.telegram_chat_id:
        logger.info("Telegram alerts: enabled")
    else:
        logger.warning("Telegram alerts: disabled (missing credentials)")

    # Initialize monitor
    monitor = HydroxideMonitor(container_name)

    # Run monitor loop
    logger.info("=" * 50)
    await monitor.monitor_loop(
        alerter,
        interval=config.check_interval,
        status_interval=config.status_interval,
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
