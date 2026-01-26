"""Configuration for hydroxide monitor."""

import os
from dataclasses import dataclass


@dataclass
class Config:
    # Container to monitor (derived from COMPOSE_PROJECT_NAME)
    container_name: str = os.getenv('CONTAINER_NAME', '')
    instance_name: str = os.getenv('COMPOSE_PROJECT_NAME', 'unknown')

    # Telegram settings
    telegram_bot_token: str = os.getenv('TELEGRAM_BOT_TOKEN', '')
    telegram_chat_id: str = os.getenv('TELEGRAM_CHAT_ID', '')

    # Monitor settings
    check_interval: int = int(os.getenv('CHECK_INTERVAL', '60'))  # Health check interval (seconds)
    alert_cooldown: int = int(os.getenv('ALERT_COOLDOWN', '600'))  # Error alert cooldown (10 min)
    status_interval: int = int(os.getenv('STATUS_INTERVAL', '3600'))  # Status report interval (60 min)


config = Config()
