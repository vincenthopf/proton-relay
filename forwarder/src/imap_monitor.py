import asyncio
import logging
import imaplib
import email
from email.header import decode_header
from typing import List, Optional, Set, Tuple
import time
import sqlite3
from datetime import datetime
import hashlib

logger = logging.getLogger(__name__)


class IMAPMonitor:
    """Monitor IMAP mailbox for new emails"""
    
    def __init__(self, config):
        self.config = config
        self.connection = None
        self.processed_uids: Set[str] = set()
        self.db_conn = None
        self.init_database()
        
    def init_database(self):
        """Initialize SQLite database for tracking forwarded emails"""
        try:
            self.db_conn = sqlite3.connect(self.config.db_path)
            cursor = self.db_conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS forwarded_emails (
                    message_id TEXT PRIMARY KEY,
                    uid TEXT,
                    subject TEXT,
                    sender TEXT,
                    forwarded_at TIMESTAMP,
                    hash TEXT UNIQUE
                )
            ''')
            self.db_conn.commit()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    def connect(self) -> bool:
        """Connect to IMAP server"""
        try:
            if self.connection:
                try:
                    self.connection.close()
                    self.connection.logout()
                except:
                    pass
            
            logger.info(f"🔌 Connecting to IMAP server {self.config.imap_host}:{self.config.imap_port}")
            
            if self.config.imap_use_ssl:
                self.connection = imaplib.IMAP4_SSL(
                    self.config.imap_host, 
                    self.config.imap_port
                )
            else:
                self.connection = imaplib.IMAP4(
                    self.config.imap_host, 
                    self.config.imap_port
                )
            
            # Login
            logger.info(f"Authenticating as {self.config.imap_username}")
            logger.debug(f"Using bridge password (length: {len(self.config.imap_password)} chars)")
            
            try:
                self.connection.login(self.config.imap_username, self.config.imap_password)
            except imaplib.IMAP4.error as e:
                if 'AUTHENTICATIONFAILED' in str(e).upper():
                    logger.error("❌ Authentication failed - check bridge password")
                    logger.error("The bridge password may have changed. Try restarting containers.")
                else:
                    logger.error(f"❌ IMAP login error: {e}")
                return False
            
            # Select inbox
            status, data = self.connection.select('INBOX')
            if status != 'OK':
                logger.error(f"❌ Failed to select INBOX: {data}")
                return False
            
            logger.info("✅ Successfully connected to IMAP server")
            
            # Get mailbox status
            status, data = self.connection.status('INBOX', '(MESSAGES UNSEEN)')
            if status == 'OK':
                # Parse response like: INBOX (MESSAGES 10 UNSEEN 5)
                import re
                match = re.search(r'MESSAGES (\d+) UNSEEN (\d+)', data[0].decode())
                if match:
                    total = match.group(1)
                    unseen = match.group(2)
                    logger.info(f"📧 Mailbox status: {total} total messages, {unseen} unread")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to IMAP server: {e}")
            if 'connection refused' in str(e).lower():
                logger.error("Connection refused - is hydroxide container running?")
            elif 'timeout' in str(e).lower():
                logger.error("Connection timeout - check network configuration")
            self.connection = None
            return False
    
    def ensure_connected(self) -> bool:
        """Ensure IMAP connection is active"""
        try:
            if self.connection:
                # Test connection with NOOP command
                self.connection.noop()
                return True
        except:
            pass
        
        # Reconnect
        return self.connect()
    
    def decode_header_value(self, value: str) -> str:
        """Decode email header value"""
        if not value:
            return ""
        
        decoded_parts = []
        for part, encoding in decode_header(value):
            if isinstance(part, bytes):
                try:
                    decoded_parts.append(part.decode(encoding or 'utf-8'))
                except:
                    decoded_parts.append(part.decode('utf-8', errors='ignore'))
            else:
                decoded_parts.append(str(part))
        
        return ' '.join(decoded_parts)
    
    def get_email_hash(self, msg: email.message.Message) -> str:
        """Generate unique hash for email to prevent duplicates"""
        hash_parts = []
        
        # Use message ID if available
        message_id = msg.get('Message-ID', '')
        if message_id:
            hash_parts.append(message_id)
        
        # Add date, from, subject
        hash_parts.append(msg.get('Date', ''))
        hash_parts.append(msg.get('From', ''))
        hash_parts.append(msg.get('Subject', ''))
        
        # Add first part of body
        body = self.get_email_body(msg)[:1000] if msg.is_multipart() else str(msg)[:1000]
        hash_parts.append(body)
        
        hash_string = '|'.join(hash_parts)
        return hashlib.sha256(hash_string.encode()).hexdigest()
    
    def is_already_forwarded(self, msg: email.message.Message) -> bool:
        """Check if email was already forwarded"""
        email_hash = self.get_email_hash(msg)
        
        cursor = self.db_conn.cursor()
        cursor.execute('SELECT 1 FROM forwarded_emails WHERE hash = ?', (email_hash,))
        result = cursor.fetchone()
        
        return result is not None
    
    def mark_as_forwarded(self, msg: email.message.Message, uid: str):
        """Mark email as forwarded in database"""
        try:
            email_hash = self.get_email_hash(msg)
            message_id = msg.get('Message-ID', email_hash)
            subject = self.decode_header_value(msg.get('Subject', 'No Subject'))
            sender = self.decode_header_value(msg.get('From', 'Unknown'))
            
            cursor = self.db_conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO forwarded_emails 
                (message_id, uid, subject, sender, forwarded_at, hash)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (message_id, uid, subject, sender, datetime.now(), email_hash))
            self.db_conn.commit()
            
        except Exception as e:
            logger.error(f"Failed to mark email as forwarded: {e}")
    
    def get_email_body(self, msg: email.message.Message) -> str:
        """Extract email body from message"""
        body = ""
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))
                
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    payload = part.get_payload(decode=True)
                    if payload:
                        try:
                            body = payload.decode('utf-8', errors='ignore')
                        except:
                            body = str(payload)
                        break
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                try:
                    body = payload.decode('utf-8', errors='ignore')
                except:
                    body = str(payload)
        
        return body
    
    def fetch_unread_emails(self) -> List[Tuple[str, email.message.Message]]:
        """Fetch unread emails from IMAP server"""
        emails = []
        
        try:
            if not self.ensure_connected():
                logger.warning("Not connected to IMAP server, skipping fetch")
                return emails
            
            # Search for unread emails
            search_criteria = 'UNSEEN' if self.config.mark_as_read else 'ALL'
            logger.debug(f"Searching for emails with criteria: {search_criteria}")
            
            status, data = self.connection.search(None, search_criteria)
            
            if status != 'OK':
                logger.error(f"❌ Failed to search emails: {status}")
                return emails
            
            email_ids = data[0].split()
            
            if not email_ids:
                logger.debug("📥 No new emails found")
                return emails
            
            # Limit batch size
            total_found = len(email_ids)
            email_ids = email_ids[:self.config.max_emails_per_batch]
            
            if total_found > len(email_ids):
                logger.info(f"📨 Found {total_found} new email(s), processing batch of {len(email_ids)}")
            else:
                logger.info(f"📨 Found {len(email_ids)} new email(s) to process")
            
            for email_id in email_ids:
                try:
                    # Fetch email
                    status, data = self.connection.fetch(email_id, '(RFC822)')
                    
                    if status != 'OK':
                        logger.error(f"Failed to fetch email {email_id}")
                        continue
                    
                    # Parse email
                    raw_email = data[0][1]
                    msg = email.message_from_bytes(raw_email)
                    
                    # Get email details for logging
                    subject = self.decode_header_value(msg.get('Subject', 'No Subject'))
                    sender = self.decode_header_value(msg.get('From', 'Unknown'))
                    date = msg.get('Date', 'Unknown')
                    
                    # Check if already forwarded
                    if self.is_already_forwarded(msg):
                        logger.info(f"🔄 Already forwarded: '{subject}' from {sender}")
                        if self.config.mark_as_read:
                            self.connection.store(email_id, '+FLAGS', '\\Seen')
                        continue
                    
                    logger.info(f"📧 New email: '{subject}' from {sender} ({date})")
                    emails.append((email_id.decode() if isinstance(email_id, bytes) else str(email_id), msg))
                    
                except Exception as e:
                    logger.error(f"❌ Error processing email {email_id}: {e}")
                    continue
            
            if emails:
                logger.info(f"📤 Ready to forward {len(emails)} email(s)")
            else:
                logger.debug("No new emails to forward after filtering")
            
        except Exception as e:
            logger.error(f"Error fetching emails: {e}")
            self.connection = None
        
        return emails
    
    def mark_as_read(self, email_id: str):
        """Mark email as read"""
        try:
            if self.connection and self.config.mark_as_read:
                self.connection.store(email_id.encode(), '+FLAGS', '\\Seen')
                logger.debug(f"Marked email {email_id} as read")
        except Exception as e:
            logger.error(f"Failed to mark email as read: {e}")
    
    def delete_email(self, email_id: str):
        """Delete email from server"""
        try:
            if self.connection and self.config.delete_after_forward:
                self.connection.store(email_id.encode(), '+FLAGS', '\\Deleted')
                self.connection.expunge()
                logger.debug(f"Deleted email {email_id}")
        except Exception as e:
            logger.error(f"Failed to delete email: {e}")
    
    async def monitor_loop(self, forward_callback, alerter=None):
        """Main monitoring loop"""
        logger.info("🎯 Starting IMAP monitoring loop")
        consecutive_errors = 0
        check_count = 0
        
        while True:
            try:
                check_count += 1
                if check_count % 12 == 1:  # Log every hour (assuming 5 min intervals)
                    logger.info(f"🔍 Performing email check #{check_count}")
                else:
                    logger.debug(f"Checking for new emails (check #{check_count})")
                
                # Fetch unread emails
                emails = self.fetch_unread_emails()
                
                # Forward emails
                forwarded_count = 0
                failed_count = 0
                
                for email_id, msg in emails:
                    try:
                        subject = self.decode_header_value(msg.get('Subject', 'No Subject'))
                        sender = self.decode_header_value(msg.get('From', 'Unknown'))
                        
                        logger.info(f"📨 Forwarding: '{subject}' from {sender}")
                        success = await forward_callback(msg)
                        
                        if success:
                            # Mark as forwarded in database
                            self.mark_as_forwarded(msg, email_id)
                            
                            # Mark as read
                            self.mark_as_read(email_id)
                            
                            # Delete if configured
                            self.delete_email(email_id)
                            
                            logger.info(f"✅ Successfully forwarded: '{subject}'")
                            forwarded_count += 1
                        else:
                            logger.error(f"❌ Failed to forward: '{subject}'")
                            failed_count += 1
                    
                    except Exception as e:
                        logger.error(f"❌ Error forwarding email {email_id}: {e}", exc_info=True)
                        failed_count += 1
                
                # Log summary if emails were processed
                if forwarded_count > 0 or failed_count > 0:
                    logger.info(f"📊 Batch complete: {forwarded_count} forwarded, {failed_count} failed")
                
                # Reset error counter on successful check
                consecutive_errors = 0
                
                # Wait before next check
                logger.debug(f"Waiting {self.config.check_interval} seconds before next check...")
                await asyncio.sleep(self.config.check_interval)
                
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"❌ Error in monitor loop (consecutive errors: {consecutive_errors}): {e}")

                if consecutive_errors >= 3 and alerter:
                    await alerter.send_alert("imap_prolonged_disconnect", f"IMAP monitor: {consecutive_errors} consecutive failures. Last error: {e}")

                # Exponential backoff for consecutive errors
                wait_time = min(30 * (2 ** (consecutive_errors - 1)), 300)  # Max 5 minutes
                logger.info(f"Waiting {wait_time} seconds before retry...")
                await asyncio.sleep(wait_time)
    
    def cleanup(self):
        """Cleanup resources"""
        try:
            if self.connection:
                self.connection.close()
                self.connection.logout()
            if self.db_conn:
                self.db_conn.close()
        except:
            pass