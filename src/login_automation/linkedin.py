from loguru import logger
import asyncio
from .email_otp import get_latest_otp, get_latest_magic_link

async def login_to_linkedin(page, username, password, email_app_password=None):
    logger.info(f"🤖 Automating LinkedIn login for {username}...")
    try:
        # Check if already logged in by looking for a common authenticated element
        if await page.query_selector('input.search-global-typeahead__input'):
            logger.info("✅ Already logged into LinkedIn.")
            return True

        # Navigate to the official login page
        await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")

        # Wait for the username field to ensure page has loaded
        await page.wait_for_selector('input#username', timeout=10000)
        
        # Simulate human-like typing
        await page.fill('input#username', username)
        await asyncio.sleep(0.5)
        await page.fill('input#password', password)
        await asyncio.sleep(0.5)
        
        # Click the sign-in button
        await page.click('button[type="submit"]')
        
        # Wait to see if we navigate away from the login page successfully
        try:
            # Wait for either successful login OR a checkpoint page
            await page.wait_for_url(lambda u: 'login' not in u.lower(), timeout=15000)
            
            if 'checkpoint' in page.url.lower():
                logger.warning(f"🚨 LinkedIn Checkpoint detected: {page.url}")
                
                page_text = await page.content()
                
                # Check if it's an email PIN verification
                pin_input = await page.query_selector('input[name="pin"], input#input__email_verification_pin')
                
                if pin_input:
                    logger.info("📧 LinkedIn is asking for an Email PIN.")
                    if email_app_password:
                        logger.info("Fetching OTP from Gmail...")
                        otp = get_latest_otp(username, email_app_password, "linkedin")
                        
                        if otp:
                            await pin_input.fill(otp)
                            submit_btn = await page.query_selector('button[type="submit"], button#email-pin-submit-button')
                            if submit_btn:
                                await submit_btn.click()
                            await page.wait_for_load_state("networkidle")
                            logger.info("✅ Submitted LinkedIn OTP.")
                        else:
                            logger.error("❌ Could not get OTP from email.")
                            return False
                    else:
                        logger.error("❌ Email app password missing. Cannot automatically fetch OTP.")
                        return False
                        
                elif "one-time link" in page_text.lower() or "emailed a link" in page_text.lower():
                    logger.info("🔗 LinkedIn sent a Magic Sign-In Link to email.")
                    if email_app_password:
                        logger.info("Fetching Magic Link from Gmail...")
                        magic_link = get_latest_magic_link(username, email_app_password, "linkedin")
                        
                        if magic_link:
                            logger.info("Navigating to Magic Link...")
                            await page.goto(magic_link, wait_until="domcontentloaded")
                            await page.wait_for_load_state("networkidle")
                            logger.info("✅ Navigated to Magic Link.")
                        else:
                            logger.error("❌ Could not get Magic Link from email.")
                            return False
                    else:
                        logger.error("❌ Email app password missing.")
                        return False
                else:
                    logger.warning("🚨 Unknown checkpoint type. Could be CAPTCHA.")
                    return False
            
            # Final check if we reached the feed or search page
            await page.wait_for_url(lambda u: 'checkpoint' not in u.lower() and 'login' not in u.lower(), timeout=15000)
            logger.info("✅ Successfully logged into LinkedIn.")
            return True
        except Exception as e:
            logger.warning(f"🚨 Login blocked or timed out on LinkedIn: {page.url}. Error: {e}")
            return False

    except Exception as e:
        logger.error(f"❌ Failed to automate LinkedIn login: {e}")
        return False
