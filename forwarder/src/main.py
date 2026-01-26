#!/usr/bin/env python3

import asyncio
import logging
import signal
import sys
import os
from aiohttp import web
from typing import Optional

from config import config
from imap_monitor import IMAPMonitor
from smtp_forwarder import SMTPForwarder
from telegram_alerter import TelegramAlerter
from hydroxide_monitor import HydroxideMonitor

logger = logging.getLogger(__name__)


class EmailForwarderService:
    """Main email forwarder service"""
    
    def __init__(self):
        self.config = config
        self.imap_monitor: Optional[IMAPMonitor] = None
        self.smtp_forwarder: Optional[SMTPForwarder] = None
        self.health_check_app: Optional[web.Application] = None
        self.health_check_runner: Optional[web.AppRunner] = None
        self.is_healthy = True
        self.last_forward_time = None
        self.forward_count = 0
        self.error_count = 0
        self.shutdown_event = asyncio.Event()
        self.hydroxide_monitor: Optional[HydroxideMonitor] = None
    
    async def setup(self):
        """Setup service components"""
        # Setup logging
        self.config.setup_logging()
        
        logger.info("======================================")
        logger.info("ProtonMail Email Forwarder Starting")
        logger.info("======================================")
        
        # Validate configuration
        if not self.config.validate():
            logger.error("❌ Invalid configuration. Exiting.")
            sys.exit(1)
        
        # Log configuration (without sensitive data)
        logger.info("📋 Configuration:")
        logger.info(f"  IMAP Server: {self.config.imap_host}:{self.config.imap_port}")
        logger.info(f"  SMTP Server: {self.config.smtp_host}:{self.config.smtp_port}")
        logger.info(f"  Forward To: {self.config.forward_to}")
        logger.info(f"  Check Interval: {self.config.check_interval} seconds")
        logger.info(f"  Max Emails Per Batch: {self.config.max_emails_per_batch}")
        logger.info(f"  Mark as Read: {self.config.mark_as_read}")
        logger.info(f"  Delete After Forward: {self.config.delete_after_forward}")
        
        # Initialize alerter (before wait_for_bridge_password so it can alert on timeout)
        self.alerter = TelegramAlerter(self.config.telegram_bot_token, self.config.telegram_chat_id)

        # Initialize hydroxide monitor
        self.hydroxide_monitor = HydroxideMonitor()

        # Wait for bridge password file if needed
        await self.wait_for_bridge_password()

        # Initialize components
        logger.info("🔧 Initializing components...")
        self.imap_monitor = IMAPMonitor(self.config)
        self.smtp_forwarder = SMTPForwarder(self.config, self.alerter)
        
        # Test connections on startup
        await self.test_connections()
        
        # Setup health check endpoint
        if self.config.enable_health_check:
            await self.setup_health_check()
        
        logger.info("✅ Service setup complete and ready!")
    
    async def wait_for_bridge_password(self):
        """Wait for bridge password to be available"""
        if not self.config.imap_password:
            # Try to read from shared volume first, then fallback to container location
            password_files = [
                '/bridge-password/password.txt',  # Shared volume location
                '/home/hydroxide/.bridge_password'  # Container location
            ]
            
            logger.info("🔐 Waiting for bridge password from hydroxide...")
            logger.info(f"Checking locations: {password_files}")
            
            for attempt in range(60):  # Wait up to 5 minutes
                # Try each file location
                for password_file in password_files:
                    if os.path.exists(password_file):
                        try:
                            with open(password_file, 'r') as f:
                                password_content = f.read().strip()
                            if password_content:
                                self.config.imap_password = password_content
                                logger.info(f"✅ Bridge password loaded from {password_file}")
                                logger.debug(f"Bridge password length: {len(self.config.imap_password)} characters")
                                return
                        except Exception as e:
                            logger.warning(f"Failed to read {password_file}: {e}")
                
                # Check environment variable as fallback
                if os.getenv('BRIDGE_PASSWORD'):
                    self.config.imap_password = os.getenv('BRIDGE_PASSWORD')
                    logger.info("✅ Bridge password loaded from BRIDGE_PASSWORD environment variable")
                    return
                
                if attempt % 12 == 0:  # Log every minute
                    logger.info(f"Still waiting for bridge password... (attempt {attempt+1}/60)")
                
                await asyncio.sleep(5)
            
            logger.error("❌ Bridge password not available after 5 minutes timeout")
            logger.error("Please check that hydroxide container is running and authenticated")
            await self.alerter.send_alert("bridge_password_timeout", "Bridge password not available after 5 minutes. Hydroxide container may not be running or authenticated.")
            sys.exit(1)
    
    async def test_connections(self):
        """Test IMAP and SMTP connections on startup"""
        logger.info("🔍 Testing connections...")
        
        # Test IMAP connection to hydroxide
        logger.info("Testing IMAP connection to hydroxide...")
        max_retries = 5
        for attempt in range(max_retries):
            if self.imap_monitor.connect():
                logger.info("✅ IMAP connection successful")
                logger.info(f"  Connected to: {self.config.imap_host}:{self.config.imap_port}")
                logger.info(f"  Username: {self.config.imap_username}")
                break
            else:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 5
                    logger.warning(f"IMAP connection failed, retrying in {wait_time} seconds... (attempt {attempt+1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error("❌ Failed to connect to IMAP after all retries")
                    logger.error("Please check:")
                    logger.error("  1. Hydroxide container is running")
                    logger.error("  2. Hydroxide is authenticated")
                    logger.error("  3. Bridge password is correct")
                    await self.alerter.send_alert("imap_auth_failure", "Failed to connect to IMAP after all retries. Check hydroxide status and bridge password.")
                    sys.exit(1)
        
        # Test SMTP connection
        logger.info("Testing SMTP connection to external server...")
        if self.smtp_forwarder.connect():
            logger.info("✅ SMTP connection successful")
            logger.info(f"  Connected to: {self.config.smtp_host}:{self.config.smtp_port}")
            logger.info(f"  Username: {self.config.smtp_username}")
            logger.info(f"  TLS: {self.config.smtp_use_tls}, SSL: {self.config.smtp_use_ssl}")
            
            # Optionally send test email
            if os.getenv('SEND_TEST_EMAIL', 'false').lower() == 'true':
                await self.send_test_email()
        else:
            logger.error("❌ Failed to connect to SMTP server")
            logger.error("Please check:")
            logger.error("  1. SMTP host and port are correct")
            logger.error("  2. SMTP username and password are correct")
            logger.error("  3. Network connectivity to SMTP server")
            await self.alerter.send_alert("smtp_test_failure", f"SMTP connection test failed to {self.config.smtp_host}:{self.config.smtp_port}")
            sys.exit(1)
        
        logger.info("✅ All connections tested successfully")
    
    async def send_test_email(self):
        """Send a test email on startup"""
        logger.info("📧 Sending test email...")
        try:
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            import datetime
            
            msg = MIMEMultipart()
            msg['From'] = self.config.smtp_username
            msg['To'] = self.config.forward_to
            msg['Subject'] = f"ProtonMail Forwarder Started - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            body = f"""
            ProtonMail Email Forwarder has started successfully!
            
            Configuration:
            - ProtonMail Account: {self.config.imap_username}
            - Forward To: {self.config.forward_to}
            - Check Interval: {self.config.check_interval} seconds
            - SMTP Server: {self.config.smtp_host}
            
            This is a test email to confirm the forwarder is working.
            """
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Create a test message object that mimics the structure expected
            class TestMessage:
                def __init__(self, msg):
                    self._msg = msg
                def get(self, key, default=None):
                    return self._msg.get(key, default)
                def __getitem__(self, key):
                    return self._msg[key]
                def is_multipart(self):
                    return False
                def get_payload(self, decode=False):
                    return body.encode() if not decode else body
            
            test_msg = TestMessage(msg)
            success = await self.smtp_forwarder.forward_email(test_msg)
            
            if success:
                logger.info("✅ Test email sent successfully")
            else:
                logger.warning("⚠️ Failed to send test email")
        except Exception as e:
            logger.warning(f"⚠️ Could not send test email: {e}")
    
    async def setup_health_check(self):
        """Setup health check HTTP endpoint"""
        self.health_check_app = web.Application()
        self.health_check_app.router.add_get('/health', self.health_check_handler)
        self.health_check_app.router.add_get('/metrics', self.metrics_handler)
        
        self.health_check_runner = web.AppRunner(self.health_check_app)
        await self.health_check_runner.setup()
        
        site = web.TCPSite(
            self.health_check_runner,
            '0.0.0.0',
            self.config.health_check_port
        )
        await site.start()
        
        logger.info(f"Health check endpoint available at http://0.0.0.0:{self.config.health_check_port}/health")
    
    async def health_check_handler(self, request):
        """Handle health check requests - non-blocking, uses cached status"""
        imap_connected = False
        smtp_connected = False

        try:
            imap_connected = await asyncio.wait_for(
                asyncio.to_thread(self.imap_monitor.ensure_connected),
                timeout=5
            ) if self.imap_monitor else False
        except (asyncio.TimeoutError, Exception):
            pass

        try:
            smtp_connected = await asyncio.wait_for(
                asyncio.to_thread(self.smtp_forwarder.connect),
                timeout=5
            ) if self.smtp_forwarder else False
        except (asyncio.TimeoutError, Exception):
            pass

        overall_healthy = self.is_healthy and (imap_connected or smtp_connected)
        status = "healthy" if overall_healthy else "unhealthy"

        data = {
            "status": status,
            "connections": {
                "imap": "connected" if imap_connected else "disconnected",
                "smtp": "connected" if smtp_connected else "disconnected"
            },
            "statistics": {
                "forward_count": self.forward_count,
                "error_count": self.error_count,
                "last_forward": str(self.last_forward_time) if self.last_forward_time else None
            },
            "configuration": {
                "forward_to": self.config.forward_to,
                "check_interval": self.config.check_interval,
                "username": self.config.imap_username
            }
        }

        return web.json_response(
            data,
            status=200 if overall_healthy else 503
        )
    
    async def metrics_handler(self, request):
        """Handle metrics requests (Prometheus format)"""
        metrics = []
        metrics.append(f"# HELP email_forwarder_up Service status (1=up, 0=down)")
        metrics.append(f"# TYPE email_forwarder_up gauge")
        metrics.append(f"email_forwarder_up {1 if self.is_healthy else 0}")
        
        metrics.append(f"# HELP email_forwarder_forwarded_total Total emails forwarded")
        metrics.append(f"# TYPE email_forwarder_forwarded_total counter")
        metrics.append(f"email_forwarder_forwarded_total {self.forward_count}")
        
        metrics.append(f"# HELP email_forwarder_errors_total Total errors encountered")
        metrics.append(f"# TYPE email_forwarder_errors_total counter")
        metrics.append(f"email_forwarder_errors_total {self.error_count}")
        
        return web.Response(text="\n".join(metrics), content_type="text/plain")
    
    async def forward_email_callback(self, msg) -> bool:
        """Callback for forwarding emails"""
        try:
            success = await self.smtp_forwarder.forward_email(msg)
            
            if success:
                self.forward_count += 1
                self.last_forward_time = asyncio.get_event_loop().time()
            else:
                self.error_count += 1
            
            return success
            
        except Exception as e:
            logger.error(f"Error in forward callback: {e}")
            self.error_count += 1
            return False
    
    async def run(self):
        """Run the service"""
        try:
            await self.setup()
            
            # Start monitoring
            logger.info("🚀 Starting email monitoring...")
            logger.info("="*50)
            logger.info("Service is now running and monitoring for emails")
            logger.info(f"Checking every {self.config.check_interval} seconds")
            logger.info("="*50)
            
            # Run monitor loop
            monitor_task = asyncio.create_task(
                self.imap_monitor.monitor_loop(self.forward_email_callback, self.alerter)
            )

            # Log periodic status
            status_task = asyncio.create_task(self.log_status_periodically())

            # Start hydroxide container monitor
            hydroxide_task = asyncio.create_task(
                self.hydroxide_monitor.monitor_loop(self.alerter)
            )

            # Wait for shutdown
            await self.shutdown_event.wait()

            # Cancel tasks
            monitor_task.cancel()
            status_task.cancel()
            hydroxide_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
            try:
                await status_task
            except asyncio.CancelledError:
                pass
            try:
                await hydroxide_task
            except asyncio.CancelledError:
                pass
            
        except Exception as e:
            logger.error(f"❌ Service error: {e}", exc_info=True)
            self.is_healthy = False
            raise
        finally:
            await self.cleanup()
    
    async def log_status_periodically(self):
        """Log status periodically"""
        while True:
            await asyncio.sleep(300)  # Every 5 minutes
            logger.info(f"📊 Status: Forwarded={self.forward_count}, Errors={self.error_count}, Uptime={int(asyncio.get_event_loop().time())}s")
    
    async def cleanup(self):
        """Cleanup resources"""
        logger.info("Cleaning up resources...")
        
        if self.imap_monitor:
            self.imap_monitor.cleanup()
        
        if self.smtp_forwarder:
            self.smtp_forwarder.cleanup()
        
        if self.health_check_runner:
            await self.health_check_runner.cleanup()
    
    def handle_signal(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, shutting down...")
        self.shutdown_event.set()


def main():
    """Main entry point"""
    # Create service
    service = EmailForwarderService()
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, service.handle_signal)
    signal.signal(signal.SIGTERM, service.handle_signal)
    
    # Run service
    try:
        asyncio.run(service.run())
    except KeyboardInterrupt:
        logger.info("Service interrupted by user")
    except Exception as e:
        logger.error(f"Service failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()