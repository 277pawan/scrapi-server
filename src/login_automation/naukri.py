from loguru import logger
import asyncio

async def login_to_naukri(page, username, password):
    logger.info(f"🤖 Automating Naukri login for {username}...")
    try:
        # Navigate to Naukri login
        await page.goto("https://login.naukri.com/nLogin/Login.php", wait_until="domcontentloaded")

        # Fill credentials using their specific input IDs
        await page.wait_for_selector('input#usernameField', timeout=10000)
        await page.fill('input#usernameField', username)
        await asyncio.sleep(0.5)
        await page.fill('input#passwordField', password)
        await asyncio.sleep(0.5)
        
        await page.click('button[type="submit"]')
        
        try:
            await page.wait_for_url(lambda u: 'login' not in u.lower(), timeout=15000)
            logger.info("✅ Successfully logged into Naukri.")
            return True
        except Exception as e:
            logger.warning(f"🚨 Login blocked! We likely hit a CAPTCHA or OTP checkpoint on Naukri: {page.url}")
            return False

    except Exception as e:
        logger.error(f"❌ Failed to automate Naukri login: {e}")
        return False
