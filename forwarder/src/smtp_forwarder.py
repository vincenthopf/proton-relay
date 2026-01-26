import asyncio
import logging
import smtplib
import ssl
import email
import threading
import time

logger = logging.getLogger(__name__)


class SMTPForwarder:
    """Forward emails via external SMTP server"""

    def __init__(self, config, alerter=None):
        self.config = config
        self.alerter = alerter
        self.smtp_connection = None
        self.last_connect_time = 0
        self.connection_lifetime = 300  # Reuse connection for 5 minutes
        self._lock = threading.Lock()  # Protect concurrent access
    
    def connect(self) -> bool:
        """Connect to SMTP server (thread-safe)"""
        with self._lock:
            return self._connect_internal()

    def _connect_internal(self) -> bool:
        """Internal connect method - must be called with lock held"""
        try:
            # Close existing connection if it's old
            if self.smtp_connection and (time.time() - self.last_connect_time > self.connection_lifetime):
                logger.debug("Closing old SMTP connection")
                self._disconnect_internal()

            # Reuse existing connection if available
            if self.smtp_connection:
                try:
                    self.smtp_connection.noop()
                    logger.debug("Reusing existing SMTP connection")
                    return True
                except:
                    logger.debug("Existing SMTP connection is dead, reconnecting")
                    self.smtp_connection = None

            logger.info(f"🔌 Connecting to SMTP server {self.config.smtp_host}:{self.config.smtp_port}")

            if self.config.smtp_use_ssl:
                # SSL connection (port 465)
                context = ssl.create_default_context()
                self.smtp_connection = smtplib.SMTP_SSL(
                    self.config.smtp_host,
                    self.config.smtp_port,
                    context=context
                )
            else:
                # Regular connection, optionally upgrade to TLS
                self.smtp_connection = smtplib.SMTP(
                    self.config.smtp_host,
                    self.config.smtp_port,
                    timeout=30
                )

                if self.config.smtp_use_tls:
                    # STARTTLS (port 587)
                    context = ssl.create_default_context()
                    self.smtp_connection.starttls(context=context)

            # Login
            self.smtp_connection.login(
                self.config.smtp_username,
                self.config.smtp_password
            )

            self.last_connect_time = time.time()
            logger.info("✅ Successfully connected to SMTP server")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to connect to SMTP server: {e}")

            # Provide helpful error messages
            if 'authentication' in str(e).lower() or '535' in str(e):
                logger.error("Authentication failed. Please check:")
                logger.error("  - SMTP username and password are correct")
                logger.error("  - For Gmail: use an App Password, not your regular password")
                logger.error("  - For other providers: check if app-specific passwords are required")
            elif 'connection refused' in str(e).lower():
                logger.error("Connection refused. Please check:")
                logger.error(f"  - SMTP host '{self.config.smtp_host}' is correct")
                logger.error(f"  - Port {self.config.smtp_port} is correct")
                logger.error("  - Firewall/network allows outbound SMTP connections")
            elif 'timeout' in str(e).lower():
                logger.error("Connection timeout. Please check:")
                logger.error("  - Network connectivity to SMTP server")
                logger.error("  - SMTP port is correct (587 for TLS, 465 for SSL, 25 for plain)")
            elif 'ssl' in str(e).lower() or 'tls' in str(e).lower():
                logger.error("SSL/TLS error. Please check:")
                logger.error(f"  - TLS setting: {self.config.smtp_use_tls}")
                logger.error(f"  - SSL setting: {self.config.smtp_use_ssl}")
                logger.error("  - These match your SMTP provider's requirements")

            self.smtp_connection = None
            return False
    
    def disconnect(self):
        """Disconnect from SMTP server (thread-safe)"""
        with self._lock:
            self._disconnect_internal()

    def _disconnect_internal(self):
        """Internal disconnect - must be called with lock held"""
        try:
            if self.smtp_connection:
                self.smtp_connection.quit()
        except:
            pass
        finally:
            self.smtp_connection = None
    
    def create_forward_message(self, original_msg: email.message.Message) -> email.message.Message:
        """Forward original message intact, just updating envelope headers"""
        import copy
        forward_msg = copy.deepcopy(original_msg)

        # Replace delivery headers
        del forward_msg['To']
        del forward_msg['Delivered-To']
        del forward_msg['Return-Path']
        forward_msg['To'] = self.config.forward_to

        # Set From to our SMTP sender (required for SMTP auth)
        original_from = forward_msg.get('From', '')
        del forward_msg['From']
        forward_msg['From'] = self.config.forward_from or self.config.smtp_username

        # Prefix subject
        original_subject = forward_msg.get('Subject', 'No Subject')
        if not str(original_subject).startswith('Fwd:'):
            del forward_msg['Subject']
            forward_msg['Subject'] = f"Fwd: {original_subject}"

        # Add forwarding info headers
        if self.config.add_forward_header:
            forward_msg['X-Forwarded-For'] = original_from
            forward_msg['X-Forwarded-Date'] = original_msg.get('Date', 'Unknown')
            forward_msg['X-Original-To'] = original_msg.get('To', 'Unknown')

        # Add Reply-To pointing to original sender
        if not forward_msg.get('Reply-To'):
            forward_msg['Reply-To'] = original_from

        return forward_msg
    
    async def forward_email(self, original_msg: email.message.Message) -> bool:
        """Forward an email"""
        retry_count = 0
        subject = original_msg.get('Subject', 'No Subject')
        if isinstance(subject, email.header.Header):
            subject = str(subject)
        
        while retry_count <= self.config.max_retries:
            try:
                # Connect to SMTP server
                if not self.connect():
                    raise Exception("Failed to connect to SMTP server")
                
                # Create forward message
                logger.debug(f"Creating forward message for: {subject}")
                forward_msg = self.create_forward_message(original_msg)
                
                # Send email
                logger.debug(f"Sending email via SMTP to {self.config.forward_to}")
                self.smtp_connection.send_message(forward_msg)
                
                logger.info(f"✅ Successfully forwarded '{subject}' to {self.config.forward_to}")
                return True
                
            except Exception as e:
                retry_count += 1
                
                if retry_count <= self.config.max_retries:
                    logger.warning(f"⚠️ Forward attempt {retry_count}/{self.config.max_retries + 1} failed: {e}")
                    logger.info(f"Retrying in {self.config.retry_delay} seconds...")
                    
                    # Disconnect and wait before retry
                    self.disconnect()
                    await asyncio.sleep(self.config.retry_delay)
                else:
                    logger.error(f"❌ Failed to forward '{subject}' after {retry_count} attempts")
                    logger.error(f"Final error: {e}")
                    if self.alerter:
                        await self.alerter.send_alert("smtp_forward_failure", f"Failed to forward '{subject}' after {retry_count} attempts. Last error: {e}")
                    return False
        
        return False
    
    def cleanup(self):
        """Cleanup resources"""
        self.disconnect()