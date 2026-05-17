import imaplib
import email
import re
import time
from loguru import logger
from email.header import decode_header

def get_latest_otp(email_address, app_password, sender_keyword, regex_pattern=r'(\d{6})', max_wait_time=60):
    """
    Connects to Gmail IMAP, waits for a new email matching the sender_keyword, 
    and extracts the OTP using regex_pattern.
    """
    logger.info(f"📧 Connecting to IMAP for {email_address} to wait for OTP...")
    
    imap_server = "imap.gmail.com"
    try:
        mail = imaplib.IMAP4_SSL(imap_server)
        mail.login(email_address, app_password)
    except Exception as e:
        logger.error(f"❌ Failed to connect to IMAP. Ensure App Passwords are enabled: {e}")
        return None

    mail.select('inbox')
    
    start_time = time.time()
    while time.time() - start_time < max_wait_time:
        # Search for unseen emails. 
        # Note: sometimes emails are instantly marked read by other clients, so we just check recent emails
        status, messages = mail.search(None, 'ALL')
        
        if status == 'OK':
            email_ids = messages[0].split()
            # Look at the last 5 emails
            for email_id in reversed(email_ids[-5:]):
                status, msg_data = mail.fetch(email_id, '(RFC822)')
                
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        
                        sender = msg.get("From", "")
                        if sender_keyword.lower() not in sender.lower():
                            continue
                            
                        subject, encoding = decode_header(msg.get("Subject", ""))[0]
                        if isinstance(subject, bytes):
                            subject = subject.decode(encoding if encoding else 'utf-8')
                            
                        logger.info(f"📬 Analyzing recent email from {sender}: {subject}")
                        
                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                content_type = part.get_content_type()
                                if "text/plain" in content_type or "text/html" in content_type:
                                    try:
                                        body += part.get_payload(decode=True).decode()
                                    except:
                                        pass
                        else:
                            try:
                                body = msg.get_payload(decode=True).decode()
                            except:
                                pass
                                
                        # Extract OTP
                        match = re.search(regex_pattern, body)
                        if not match:
                            match = re.search(regex_pattern, subject)
                            
                        if match:
                            otp = match.group(1) if len(match.groups()) > 0 else match.group(0)
                            logger.info(f"🔑 Successfully extracted OTP: {otp}")
                            mail.logout()
                            return otp
                
        logger.info("⏳ Waiting for OTP email to arrive...")
        time.sleep(5)
        
    logger.warning("⏱️ Timed out waiting for OTP email.")
    mail.logout()
    return None

def get_latest_magic_link(email_address, app_password, sender_keyword, max_wait_time=60):
    """
    Connects to Gmail IMAP, waits for a new email, and extracts the magic sign-in link.
    """
    logger.info(f"🔗 Connecting to IMAP for {email_address} to wait for Magic Link...")
    
    imap_server = "imap.gmail.com"
    try:
        mail = imaplib.IMAP4_SSL(imap_server)
        mail.login(email_address, app_password)
    except Exception as e:
        logger.error(f"❌ Failed to connect to IMAP: {e}")
        return None

    mail.select('inbox')
    
    start_time = time.time()
    while time.time() - start_time < max_wait_time:
        status, messages = mail.search(None, 'ALL')
        if status == 'OK':
            email_ids = messages[0].split()
            for email_id in reversed(email_ids[-5:]):
                status, msg_data = mail.fetch(email_id, '(RFC822)')
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        sender = msg.get("From", "")
                        if sender_keyword.lower() not in sender.lower():
                            continue
                        
                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                content_type = part.get_content_type()
                                if "text/html" in content_type or "text/plain" in content_type:
                                    try:
                                        body += part.get_payload(decode=True).decode()
                                    except:
                                        pass
                        else:
                            try:
                                body = msg.get_payload(decode=True).decode()
                            except:
                                pass
                                
                        # Extract Magic Link (URL containing linkedin.com and some auth token)
                        # We look for a URL that looks like a sign-in link
                        links = re.findall(r'(https://www\.linkedin\.com/[^\s"\'<>]+)', body)
                        for link in links:
                            if 'e/v2' in link or 'uas/login' in link or 'pin' in link or 'verify' in link or 'sign-in' in link or 'cookie' not in link:
                                # A heuristic to find the primary action link. Often it contains e/v2 or similar tracking
                                if 'help' not in link and 'legal' not in link and 'unsubscribe' not in link:
                                    logger.info(f"🔗 Extracted Magic Link: {link}")
                                    mail.logout()
                                    return link
                
        logger.info("⏳ Waiting for Magic Link email to arrive...")
        time.sleep(5)
        
    logger.warning("⏱️ Timed out waiting for Magic Link email.")
    mail.logout()
    return None
