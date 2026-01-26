import os
import logging
from dataclasses import dataclass
from typing import Optional

@dataclass
class Config:
    """Configuration for email forwarder service"""
    
    # ProtonMail IMAP settings (via Hydroxide)
    imap_host: str = os.getenv('IMAP_HOST', 'hydroxide')
    imap_port: int = int(os.getenv('IMAP_PORT', '1143'))
    imap_username: str = os.getenv('PROTONMAIL_USERNAME', '')
    imap_password: str = os.getenv('BRIDGE_PASSWORD', '')  # This is the bridge password from hydroxide
    imap_use_ssl: bool = os.getenv('IMAP_USE_SSL', 'false').lower() == 'true'
    
    # External SMTP settings for forwarding
    smtp_host: str = os.getenv('SMTP_HOST', 'smtp.gmail.com')
    smtp_port: int = int(os.getenv('SMTP_PORT', '587'))
    smtp_username: str = os.getenv('SMTP_USERNAME', '')
    smtp_password: str = os.getenv('SMTP_PASSWORD', '')
    smtp_use_tls: bool = os.getenv('SMTP_USE_TLS', 'true').lower() == 'true'
    smtp_use_ssl: bool = os.getenv('SMTP_USE_SSL', 'false').lower() == 'true'
    
    # Forwarding configuration
    forward_to: str = os.getenv('FORWARD_TO', '')
    forward_from: Optional[str] = os.getenv('FORWARD_FROM', None)  # Override sender if needed
    check_interval: int = int(os.getenv('CHECK_INTERVAL', '30'))  # seconds
    max_emails_per_batch: int = int(os.getenv('MAX_EMAILS_PER_BATCH', '10'))
    mark_as_read: bool = os.getenv('MARK_AS_READ', 'true').lower() == 'true'
    delete_after_forward: bool = os.getenv('DELETE_AFTER_FORWARD', 'false').lower() == 'true'
    
    # Processing options
    forward_attachments: bool = os.getenv('FORWARD_ATTACHMENTS', 'true').lower() == 'true'
    max_attachment_size: int = int(os.getenv('MAX_ATTACHMENT_SIZE', '25')) * 1024 * 1024  # MB to bytes
    preserve_headers: bool = os.getenv('PRESERVE_HEADERS', 'true').lower() == 'true'
    add_forward_header: bool = os.getenv('ADD_FORWARD_HEADER', 'true').lower() == 'true'
    
    # Retry configuration
    max_retries: int = int(os.getenv('MAX_RETRIES', '3'))
    retry_delay: int = int(os.getenv('RETRY_DELAY', '30'))  # seconds
    
    # Logging
    log_level: str = os.getenv('LOG_LEVEL', 'INFO')
    log_format: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Health check
    health_check_port: int = int(os.getenv('HEALTH_CHECK_PORT', '8080'))
    enable_health_check: bool = os.getenv('ENABLE_HEALTH_CHECK', 'true').lower() == 'true'

    # Telegram alerting
    telegram_bot_token: str = os.getenv('TELEGRAM_BOT_TOKEN', '')
    telegram_chat_id: str = os.getenv('TELEGRAM_CHAT_ID', '')

    # Database for tracking forwarded emails (prevents duplicates)
    db_path: str = os.getenv('DB_PATH', '/data/forwarded.db')
    
    def validate(self) -> bool:
        """Validate configuration"""
        errors = []
        
        if not self.imap_username:
            errors.append("PROTONMAIL_USERNAME is required")
        # Bridge password will be loaded from file, not required in env
        # if not self.imap_password:
        #     errors.append("BRIDGE_PASSWORD is required")
        if not self.smtp_host:
            errors.append("SMTP_HOST is required")
        if not self.smtp_username:
            errors.append("SMTP_USERNAME is required")
        if not self.smtp_password:
            errors.append("SMTP_PASSWORD is required")
        if not self.forward_to:
            errors.append("FORWARD_TO email address is required")
        
        if errors:
            for error in errors:
                logging.error(f"Config validation error: {error}")
            return False
        
        return True
    
    def setup_logging(self):
        """Setup logging configuration"""
        logging.basicConfig(
            level=getattr(logging, self.log_level.upper()),
            format=self.log_format
        )
        
        # Reduce noise from some libraries
        logging.getLogger('asyncio').setLevel(logging.WARNING)

# Global config instance
config = Config()