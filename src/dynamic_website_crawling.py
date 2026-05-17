from playwright.async_api import async_playwright
import asyncio
import time
from loguru import logger

from src.utills import fetch_static_content
from src.linkedin_scraper import scroll_linkedin_job_list, extract_linkedin_jobs, clean_with_gemini

GEMINI_API_KEY = "AIzaSyBz4lZ9DVlYZ1Ylx7pFgkD0GcUOxxxFPp8"
JOB_PLATFORMS = ["linkedin.com", "naukri.com", "foundit.in", "wellfound.com",
                 "internshala.com", "instahyre.com", "upwork.com", "indeed.com"]


async def auto_scroll(page, max_scrolls=10):
    """
    Pure scroll engine - handles ONLY scrolling to load lazy/infinite content.
    Navigation buttons (Load More, Next, etc.) are handled by the pagination loop.
    """
    logger.info("🔄 Auto-scrolling to load dynamic content...")
    
    items_before = await page.evaluate("() => document.querySelectorAll('a[href]').length")
    
    for scroll_num in range(max_scrolls):
        logger.info(f"📜 Scroll pass {scroll_num + 1}/{max_scrolls}...")
        
        # METHOD 1: Standard scrollTo bottom
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1)
        
        # METHOD 2: Keyboard End key (works for LinkedIn's virtual DOM scroll)
        await page.keyboard.press("End")
        await asyncio.sleep(1)
        
        # METHOD 3: Smooth incremental scroll (triggers IntersectionObserver on LinkedIn)
        current_pos = await page.evaluate("() => window.scrollY")
        total_height = await page.evaluate("() => document.body.scrollHeight")
        step = max(200, int((total_height - current_pos) // 5))
        pos = int(current_pos)
        while pos < int(total_height):
            await page.evaluate(f"window.scrollTo(0, {pos})")
            await asyncio.sleep(0.1)
            pos += step
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

        # Wait for network to settle after scroll triggers new API calls
        try:
            await page.wait_for_load_state("networkidle", timeout=4000)
        except Exception:
            pass
        
        items_after = await page.evaluate("() => document.querySelectorAll('a[href]').length")
        logger.info(f"   📊 Content growth: {items_before} → {items_after} links on page")
        items_before = items_after
        
    logger.info("✅ Auto-scroll complete.")



async def scrape_comprehensive(browser_context, url, wait_time=5):
    """
    Intelligently scrape a page by waiting for network idle and DOM stability.
    Replaces fixed waits with adaptive detection.
    """
    page = await browser_context.new_page()
    
    # --- JS Stealth Injection ---
    # Attempt to bypass Cloudflare/Bot-detection by masking WebDriver properties
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.navigator.chrome = { runtime: {} };
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        
        // Mock permissions API
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            originalQuery(parameters)
        );
    """)
    
    start_time = time.time()

    try:
        logger.info(f"🌐 Loading: {url}")
        logger.info(f"⏱️  Crawl started at: {time.strftime('%H:%M:%S', time.localtime(start_time))}")

        # Step 1: Load page and wait for DOM to be ready
        await page.goto(url=url, wait_until="domcontentloaded", timeout=30000.0)
        logger.info("✅ DOM content loaded")

        # CHECK FOR LOGIN REDIRECTION
        current_url = page.url.lower()
        if any(kw in current_url for kw in ['login', 'signup', 'auth', 'session_redirect', 'signin']):
            logger.warning(f"🚨 Login screen detected! ({page.url})")
            
            # --- PHASE 1 AUTOMATED LOGIN ---
            # Try to load local auth_vault
            import json
            import os
            from src.login_automation import handle_login_if_needed
            
            auth_vault = {}
            if os.path.exists("auth.json"):
                with open("auth.json", "r") as f:
                    auth_vault = json.load(f)
            
            # Attempt automated login
            login_success = await handle_login_if_needed(page, url, auth_vault)
            
            if login_success:
                # Re-navigate to the original target URL after successful login
                await page.goto(url=url, wait_until="domcontentloaded", timeout=30000.0)
            else:
                # Fallback to manual pause if automation fails or credentials don't exist
                logger.error("❌ Automated login failed and manual intervention is disabled. Aborting crawl for this URL.")
                return {"text": {"visible": ""}, "links": {"all_links": set()}, "raw_html": "", "framework_detection": {}, "error": "Login failed"}


        # Step 2: CRITICAL - Wait for network to be idle
        # This replaces the blind sleep(5) - waits until no network activity for 500ms
        try:
            logger.info("⏳ Waiting for network idle (API calls to finish)...")
            await page.wait_for_load_state("networkidle", timeout=15000)
            logger.info("✅ Network is idle - all API calls completed")
            
            # CRITICAL: Wait for React to render the API data into DOM
            # Network idle = HTTP response finished, but React needs time to:
            # 1. Parse JSON, 2. Update state, 3. Re-render, 4. Paint to DOM
            logger.info("⏳ Waiting 2s for React rendering...")
            await asyncio.sleep(2)
            logger.info("✅ React rendering time complete")
        except Exception as e:
            logger.warning(f"⚠ Network idle timeout (continuing anyway): {e}")

        # Step 3: Wait for meaningful content to appear
        try:
            await page.wait_for_function("""
                () => {
                    const body = document.body;
                    const textContent = body.innerText || body.textContent || '';
                    return textContent.length > 200;
                }
            """, timeout=10000)
            logger.info("✅ Found substantial text content")
        except:
            logger.warning("⚠ No substantial text content detected")

        # --- PAGINATION & EXTRACTION LOOP ---
        MAX_PAGES = 5
        accumulated_markdown = ""
        accumulated_links = set()
        final_raw_html = ""
        last_link_count = 0
        
        for current_page in range(1, MAX_PAGES + 1):
            logger.info(f"📄 Processing Page {current_page} of up to {MAX_PAGES}...")
            
            # Step 4: Auto Scroll (Forced for all websites)
            logger.info("🔄 Performing auto-scroll to trigger any infinite-scroll or lazy-loading (like LinkedIn)...")
            links_before_scroll = len(accumulated_links)
            await auto_scroll(page, max_scrolls=5) 
            await page.evaluate("window.scrollTo(0, 0)")  # Scroll back to top
                
            await asyncio.sleep(0.5)

            # ── EXTRACTION BLOCK ──────────────────────────────────────────
            current_url = page.url
            is_linkedin = "linkedin.com" in current_url

            if is_linkedin:
                # LinkedIn: use left-panel scroller + structured DOM extractor
                logger.info("🔗 LinkedIn detected — using left-panel scroll + DOM extractor")
                await scroll_linkedin_job_list(page, max_scrolls=5)
                page_markdown = await extract_linkedin_jobs(page)

                # Also collect links
                links_method = await page.evaluate("""
                    () => Array.from(document.querySelectorAll('a[href*="/jobs/view/"]')).map(a => a.href)
                """)
                for href in links_method:
                    accumulated_links.add(href)
            else:
                # All other sites: generic scroll + fetch_static_content
                logger.info("🔗 Generic extraction path")

                # Extract Links
                logger.info(f"🔗 Extracting links from Page {current_page}...")
                links_method = await page.evaluate("""
                    () => {
                        const links = Array.from(document.querySelectorAll('a[href]'));
                        return links.map(link => link.href);
                    }
                """)
                for href in links_method:
                    accumulated_links.add(href)

                links_gained_from_scroll = len(accumulated_links) - links_before_scroll
                logger.info(f"📊 Scroll yielded {links_gained_from_scroll} new links on Page {current_page}")

                raw_html = await page.content()
                final_raw_html = raw_html
                page_data = await fetch_static_content(raw_html, page.url)

                if isinstance(page_data, dict) and "markdown" in page_data:
                    page_markdown = page_data["markdown"]
                elif isinstance(page_data, str):
                    page_markdown = page_data
                else:
                    page_markdown = ""

            accumulated_markdown += f"\n\n--- PAGE {current_page} ---\n\n" + page_markdown
                
            if current_page == MAX_PAGES:
                logger.info(f"🛑 Reached maximum pagination limit ({MAX_PAGES}).")
                break

            # --- SMART NAVIGATION FALLBACK ---
            # Try multiple strategies to move to the next batch of content.
            # Priority: Next Arrow → Next Button → Numbered Pages → Load More
            
            nav_clicked = False
            
            # Strategy 1 (Highest Priority): Previous/Next arrow buttons (LinkedIn, specific paginations)
            if not nav_clicked:
                arrow_selectors = [
                    '.artdeco-pagination__button--next',  # LinkedIn specific
                    '[aria-label*="next" i]', '[aria-label*="forward" i]',
                    'button[aria-label*="next" i]', 'a[aria-label*="next" i]',
                    'button.pagination-next',
                ]
                for selector in arrow_selectors:
                    try:
                        elements = await page.query_selector_all(selector)
                        for el in elements:
                            if await el.is_visible():
                                is_disabled = await el.get_attribute("disabled")
                                if is_disabled is None:
                                    logger.info(f"⏭️ [Navigation] Found 'Next Arrow' button, clicking...")
                                    await el.click()
                                    nav_clicked = True
                                    break
                    except Exception:
                        pass
                    if nav_clicked:
                        break

            # Strategy 2: "Next" button / link (Naukri, Internshala, Instahyre)
            if not nav_clicked:
                next_selectors = [
                    'a:has-text("Next")', 'button:has-text("Next")',
                    '[aria-label="Next"]', '[aria-label="Next page"]',
                    '.next', 'a.next-page', 'button.next-page',
                    '[class*="pagination"] a:last-child',
                    'button:has-text("Next Page")',
                ]
                for selector in next_selectors:
                    try:
                        elements = await page.query_selector_all(selector)
                        for el in elements:
                            if await el.is_visible():
                                logger.info(f"➡️ [Navigation] Found 'Next' button, clicking to go to Page {current_page + 1}...")
                                await el.click()
                                nav_clicked = True
                                break
                    except Exception:
                        pass
                    if nav_clicked:
                        break
                        
            # Strategy 3: Numbered pagination - click the next page number
            if not nav_clicked:
                try:
                    next_page_num = current_page + 1
                    num_selectors = [
                        f'button:has-text("{next_page_num}")',
                        f'a:has-text("{next_page_num}")',
                        f'[aria-label="Page {next_page_num}"]',
                    ]
                    for selector in num_selectors:
                        elements = await page.query_selector_all(selector)
                        for el in elements:
                            if await el.is_visible():
                                logger.info(f"🔢 [Navigation] Found numbered page button '{next_page_num}', clicking...")
                                await el.click()
                                nav_clicked = True
                                break
                        if nav_clicked:
                            break
                except Exception:
                    pass

            # Strategy 4 (Lowest Priority): "Load More" / "Show More" button (Foundit, Wellfound)
            # This is lowest priority because "Show more" is often used for expanding text blocks!
            if not nav_clicked:
                load_more_selectors = [
                    'button:has-text("Load more")', 'button:has-text("Show more")',
                    'button:has-text("Load More")', 'button:has-text("Show More")',
                    'button:has-text("See more")', 'a:has-text("Load More")',
                    'button:has-text("View more")'
                ]
                for selector in load_more_selectors:
                    try:
                        elements = await page.query_selector_all(selector)
                        for el in elements:
                            if await el.is_visible():
                                logger.info(f"🖱️ [Navigation] Found 'Load More' button, clicking...")
                                await el.click()
                                nav_clicked = True
                                break
                    except Exception:
                        pass
                    if nav_clicked:
                        break
                    
            if not nav_clicked:
                logger.info("⏹️ No navigation button found (Next/Load More/Arrows/Numbers). Extraction complete.")
                break
                
            # Verify navigation actually changed the page before waiting
            url_before_nav = page.url
            # Wait for next page to load
            try:
                logger.info("⏳ Waiting for next page to load...")
                await page.wait_for_load_state("networkidle", timeout=10000)
                await asyncio.sleep(2) # Give React time to re-render DOM
            except:
                logger.warning("⚠ Timeout waiting for next page, continuing extraction anyway...")
            
            url_after_nav = page.url
            if url_before_nav == url_after_nav:
                logger.info(f"⚠ URL did not change after clicking navigation ({url_before_nav}). Page may be using AJAX loading.")
            else:
                logger.info(f"✅ Navigated to new page: {url_after_nav}")
                
        # --- END PAGINATION LOOP ---


        spa_patterns = await page.evaluate("""
            () => {
                const html = document.documentElement.outerHTML;
                return {
                    hasReact: html.includes('react') || html.includes('React'),
                    hasNext: html.includes('_next') || html.includes('__NEXT'),
                    hasVue: html.includes('vue') || html.includes('Vue'),
                    hasAngular: html.includes('angular') || html.includes('ng-'),
                    hasRouter: html.includes('router') || html.includes('Router')
                }
            }
        """)
        
        # ── FINAL: Gemini AI cleaning for job platforms ──────────────────
        current_url = page.url
        is_job_platform = any(p in current_url for p in JOB_PLATFORMS)
        is_linkedin = "linkedin.com" in current_url
        
        if is_job_platform and not is_linkedin and accumulated_markdown.strip():
            logger.info("✨ Applying Gemini AI content cleaning to remove noise...")
            accumulated_markdown = await clean_with_gemini(accumulated_markdown, GEMINI_API_KEY)
        elif is_linkedin:
            logger.info("✅ Skipping Gemini cleaning for LinkedIn (data is already perfectly structured).")

        visible_text = accumulated_markdown
        all_links = accumulated_links
        raw_html = final_raw_html
        
        logger.info(f"\n🕵️‍♂️ Framework Detection:", spa_patterns)

        print(f"all_links: {all_links}")
        print(f"spa_patterns: {spa_patterns}")
        
        # Calculate and log total time
        end_time = time.time()
        total_duration = end_time - start_time
        logger.info(f"⏱️  Crawl ended at: {time.strftime('%H:%M:%S', time.localtime(end_time))}")
        logger.info(f"⏱️  Total crawl duration: {total_duration:.2f} seconds")
        
        return {

            'text': {
                'visible': visible_text,
            },
            'links': {
                'all_links':all_links,
            },
            'raw_html': raw_html,
            'framework_detection': spa_patterns,
        }

    except Exception as e:
        logger.info(f"❌ Error during scraping: {e}")
        import traceback
        traceback.print_exc()
        raise e
    finally:
            await page.close()
