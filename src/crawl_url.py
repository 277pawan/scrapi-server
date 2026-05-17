import aiohttp
from loguru import logger
from playwright.async_api import async_playwright
from src.dynamic_website_crawling import scrape_comprehensive
from src.utills import fetch_static_content, is_dynamic_framework
from fastapi import WebSocket
from urllib.parse import urlparse
import os

CRAWLER_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

# Optional: Add your Proxy URL here (e.g., "http://username:password@proxyserver:port")
# If None, proxies will not be used.
PROXY_URL = None 

USER_DATA_DIR = os.path.join(os.getcwd(), "browser_data")

def normalize_url(u: str) -> str:
    try:
        parsed = urlparse(u)
        path = parsed.path.rstrip('/')
        if not path:
            path = '/'
        query = f"?{parsed.query}" if parsed.query else ""
        return f"{parsed.scheme}://{parsed.netloc}{path}{query}"
    except Exception:
        return u

async def fetch_js_rendered_content(url, return_metadata: bool = False):
    async with async_playwright() as p:
        
        # Configure proxy for Playwright if provided
        proxy_config = None
        if PROXY_URL:
            proxy_config = {"server": PROXY_URL}

        # Use a persistent context to save cookies, localStorage, and login sessions
        context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False,
            user_agent=CRAWLER_USER_AGENT,
            viewport={'width': 1280, 'height': 720},
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-setuid-sandbox',
                '--window-size=1280,720'
            ],  # Helps avoid bot detection
            proxy=proxy_config
        )
        
        result = await scrape_comprehensive(context, url)
        logger.info("✅ Comprehensive scrape completed. Closing browser context...")
        try:
            import asyncio
            await asyncio.wait_for(context.close(), timeout=5.0)
            logger.info("✅ Browser context closed successfully.")
        except Exception as e:
            logger.warning(f"⚠ Timeout or error closing Playwright context: {e}")

    logger.info("⏳ Processing extracted data payload...")
    text_value = None
    if result and result.get("text", {}).get("visible"):
        candidate = result["text"]["visible"]
        # Handle both dict (old behavior) and string (new pagination behavior)
        if isinstance(candidate, dict):
            candidate = candidate.get("markdown", "")
        if isinstance(candidate, str):
            candidate = candidate.strip()
            text_value = candidate if len(candidate) > 50 else None

    if return_metadata:
        return {
            "markdown": text_value,
            "raw_html": result.get("raw_html") if result else None,
            "links": result.get("links") if result else None,
        }

    return text_value

async def crawl_url(urls, websocket: WebSocket):
    async with aiohttp.ClientSession() as session:
        for start_url in urls:
            if not start_url:
                continue
                
            try:
                parsed_start = urlparse(start_url)
                domain = parsed_start.netloc
            except Exception:
                continue

            if not domain:
                continue

            queue = [start_url]
            visited = set()

            while queue:
                url = queue.pop(0)
                clean_url = normalize_url(url)
                
                if clean_url in visited:
                    continue
                    
                visited.add(clean_url)
                
                try:
                    logger.info(f"🔍 Fetching {url}...")
                    
                    # Optional: Add proxy to aiohttp
                    request_kwargs = {"headers": {"User-Agent": CRAWLER_USER_AGENT}, "timeout": 15}
                    if PROXY_URL:
                        request_kwargs["proxy"] = PROXY_URL
                        
                    auth_domains = ["linkedin.com", "naukri.com", "foundit.in", "wellfound.com", "internshala.com", "instahyre.com", "upwork.com", "indeed.com"]
                    is_auth_domain = any(d in domain for d in auth_domains)
                    
                    if is_auth_domain:
                        logger.info(f"⚙️ Known auth-required platform detected for {url}, skipping aiohttp and using Playwright directly")
                        content = await fetch_js_rendered_content(url, return_metadata=True)
                        markdown_content = content.get("markdown") if content else None
                        new_urls = content["links"]["all_links"] if content and content.get("links") else []
                    else:
                        async with session.get(url, **request_kwargs) as response:
                            content_type = response.headers.get('Content-Type', '')
                            if 'text/html' not in content_type:
                                logger.info(f"⏭️ Skipping non-HTML content at {url}")
                                continue

                            html_text = await response.text()

                            if is_dynamic_framework(html_text):
                                logger.info(f"⚙️ Detected dynamic site for {url}, using Playwright")
                                content = await fetch_js_rendered_content(url, return_metadata=True)
                                markdown_content = content.get("markdown") if content else None
                                new_urls = content["links"]["all_links"] if content and content.get("links") else []
                            else:
                                content = await fetch_static_content(html_text, url)
                                markdown_content = content.get("markdown") if content else None
                                new_urls = content.get("links", []) if content else []

                    # ✅ FIXED: Send response to UI for ALL domains (auth + non-auth)
                    if content:
                        logger.info(f"✅ Successfully crawled {url}")
                        try:
                            await websocket.send_json({
                                "url": url,
                                "markdown": markdown_content
                            })
                            logger.info(f"📡 Successfully sent {len(str(markdown_content))} bytes of markdown to UI WebSocket.")
                        except Exception as ws_err:
                            logger.error(f"❌ Failed to send payload to UI WebSocket: {ws_err}")

                except Exception as e:
                    logger.error(f"❌ Error crawling {url}: {e}")

async def scrape_urls_api(urls: list[str]) -> dict:
    """
    API version of crawl_url that doesn't use websockets and returns a dictionary of results.
    """
    results = {}
    async with aiohttp.ClientSession() as session:
        for url in urls:
            if not url:
                continue
                
            try:
                parsed_start = urlparse(url)
                domain = parsed_start.netloc
            except Exception:
                continue

            if not domain:
                continue
            
            clean_url = normalize_url(url)
            
            try:
                logger.info(f"🔍 API Fetching {url}...")
                
                request_kwargs = {"headers": {"User-Agent": CRAWLER_USER_AGENT}, "timeout": 15}
                if PROXY_URL:
                    request_kwargs["proxy"] = PROXY_URL
                    
                auth_domains = ["linkedin.com", "naukri.com", "foundit.in", "wellfound.com", "internshala.com", "instahyre.com", "upwork.com", "indeed.com"]
                is_auth_domain = any(d in domain for d in auth_domains)
                
                content = None
                markdown_content = None
                
                if is_auth_domain:
                    logger.info(f"⚙️ Known auth-required platform detected for {url}, using Playwright directly")
                    content = await fetch_js_rendered_content(url, return_metadata=True)
                    markdown_content = content.get("markdown") if content else None
                else:
                    async with session.get(url, **request_kwargs) as response:
                        content_type = response.headers.get('Content-Type', '')
                        if 'text/html' not in content_type:
                            logger.info(f"⏭️ Skipping non-HTML content at {url}")
                            results[url] = {"error": "Non-HTML content"}
                            continue

                        html_text = await response.text()

                        if is_dynamic_framework(html_text):
                            logger.info(f"⚙️ Detected dynamic site for {url}, using Playwright")
                            content = await fetch_js_rendered_content(url, return_metadata=True)
                            markdown_content = content.get("markdown") if content else None
                        else:
                            content = await fetch_static_content(html_text, url)
                            markdown_content = content.get("markdown") if content else None
                
                if content:
                    logger.info(f"✅ Successfully scraped {url} via API")
                    results[url] = {
                        "markdown": markdown_content
                    }
                else:
                    results[url] = {"error": "Failed to extract content"}

            except Exception as e:
                logger.error(f"❌ Error scraping {url} via API: {e}")
                results[url] = {"error": str(e)}

    return results

