from loguru import logger
import asyncio

async def generic_login(page, username, password, domain):
    logger.info(f"🤖 Attempting Generic Automated Login for {domain}...")
    try:
        # Give page a moment to fully render login fields
        await asyncio.sleep(2)
        
        # Check if redirected to Google Auth
        if "accounts.google.com" in page.url:
            logger.info("🌐 Detected Google OAuth login screen. Attempting automated Google Auth...")
            try:
                email_input = await page.wait_for_selector('input[type="email"]', timeout=10000)
                await email_input.fill(username)
                await page.click('#identifierNext')
                
                await asyncio.sleep(4) # Wait for password transition
                
                pass_input = await page.wait_for_selector('input[type="password"]', timeout=10000)
                await pass_input.fill(password)
                await page.click('#passwordNext')
                
                await asyncio.sleep(5)
                # Check if Google threw the "Browser not secure" error
                page_text = await page.content()
                if "couldn't sign you in" in page_text.lower() or "not secure" in page_text.lower():
                    logger.error("❌ Google blocked the automated login due to security heuristics.")
                    return False
                    
                await page.wait_for_url(lambda u: 'accounts.google.com' not in u.lower(), timeout=15000)
                logger.info("✅ Successfully bypassed Google Auth!")
                return True
            except Exception as e:
                logger.error(f"❌ Failed to automate Google Auth: {e}")
                return False
        
        # 1. Find and fill the Email/Username field
        email_selectors = [
            'input[type="email"]', 
            'input[name="email"]', 
            'input[id="email"]',
            'input[name="username"]',
            'input[id="username"]',
            'input[id="login_email"]',
            'input[placeholder*="Email"]'
        ]
        
        email_filled = False
        for selector in email_selectors:
            elements = await page.query_selector_all(selector)
            for el in elements:
                if await el.is_visible():
                    await el.fill(username)
                    email_filled = True
                    break
            if email_filled:
                break
                
        if not email_filled:
            logger.warning(f"⚠ Could not find a visible email/username input on {domain}.")
            return False

        # 2. Find and fill the Password field
        password_selectors = [
            'input[type="password"]',
            'input[name="password"]',
            'input[id="password"]',
            'input[placeholder*="Password"]'
        ]
        
        pass_filled = False
        for selector in password_selectors:
            elements = await page.query_selector_all(selector)
            for el in elements:
                if await el.is_visible():
                    await el.fill(password)
                    pass_filled = True
                    break
            if pass_filled:
                break
                
        if not pass_filled:
            # Some sites (like Upwork) have a 2-step login. They ask for email, click next, THEN ask for password.
            logger.info("⏳ Password field not visible immediately. Trying to click 'Next' or 'Continue' first...")
            next_buttons = await page.query_selector_all('button, input[type="submit"]')
            for btn in next_buttons:
                text = await btn.inner_text()
                if any(word in text.lower() for word in ['next', 'continue', 'proceed']):
                    await btn.click()
                    await asyncio.sleep(2) # wait for password field to appear
                    break
            
            # Try finding password again
            for selector in password_selectors:
                elements = await page.query_selector_all(selector)
                for el in elements:
                    if await el.is_visible():
                        await el.fill(password)
                        pass_filled = True
                        break
                if pass_filled:
                    break
            
            if not pass_filled:
                logger.warning(f"⚠ Could not find a visible password input on {domain}.")
                return False

        # 3. Find and click the Submit/Login button
        await asyncio.sleep(0.5)
        submit_selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Log In")',
            'button:has-text("Sign In")',
            'button:has-text("Login")'
        ]
        
        clicked = False
        for selector in submit_selectors:
            elements = await page.query_selector_all(selector)
            for el in elements:
                if await el.is_visible():
                    await el.click()
                    clicked = True
                    break
            if clicked:
                break

        if clicked:
            logger.info(f"✅ Clicked login button on {domain}. Waiting for redirect...")
            try:
                # Wait for navigation away from login
                await page.wait_for_url(lambda u: 'login' not in u.lower() and 'signin' not in u.lower(), timeout=15000)
                logger.info(f"✅ Successfully logged into {domain} via generic automation.")
                return True
            except:
                logger.warning(f"🚨 Generic login on {domain} may have hit a CAPTCHA or OTP checkpoint.")
                return False
        else:
            logger.warning(f"⚠ Could not find the submit button on {domain}.")
            return False

    except Exception as e:
        logger.error(f"❌ Failed to automate generic login on {domain}: {e}")
        return False
