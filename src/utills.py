from loguru import logger
import re
from bs4 import BeautifulSoup
import html2text
from requests.compat import urljoin

def is_dynamic_framework(html_text: str) -> bool:
    """
    Detect if a website requires JavaScript rendering (client-side rendered SPA).
    Returns True only for sites that truly need JS rendering, excluding SSR sites.
    Uses specific patterns to avoid false positives.
    """
    html_lower = html_text.lower()
    logger.debug(f"is_dynamic_framework: Analyzing HTML ({len(html_text)} chars)")
    
    # Step 1: Exclude SSR platforms (very specific patterns only)
    ssr_patterns = {
        'shopify': [r'cdn\.shopify\.com', r'shopify\.theme', r'data-shopify', r'shopify\.com/s/'],
        'wordpress': [r'/wp-content/', r'/wp-includes/', r'/wp-admin/', r'wp\.json'],
        'magento': [r'/magento/', r'Magento_', r'data-mage-init', r'/pub/static/.*/mage/'],
        'drupal': [r'drupal\.js', r'Drupal\.', r'misc/drupal'],
        'joomla': [r'/joomla/', r'com_joomla', r'/components/com_joomla']
    }
    for platform, patterns in ssr_patterns.items():
        for pattern in patterns:
            if re.search(pattern, html_text, re.IGNORECASE):
                logger.debug(f"is_dynamic_framework: Detected {platform} pattern '{pattern}', returning False")
                return False
    
    # Step 2: Strong SPA indicators (definitive patterns)
    strong_indicators = ['__next', '__nuxt', 'reactroot', 'data-reactroot', '__react_props',
                        '__REACT_DEVTOOLS_GLOBAL_HOOK__', '<app-root', 'astro-island']
    for indicator in strong_indicators:
        if indicator in html_lower:
            logger.debug(f"is_dynamic_framework: Found strong SPA indicator '{indicator}', returning True")
            return True
    
    # Step 3: React/Vue/Angular in script tags (specific patterns only)
    script_patterns = [
        r'<script[^>]*src=["\'][^"\']*react[^"\']*\.js',  # React in script src
        r'<script[^>]*src=["\'][^"\']*react-dom[^"\']*\.js',  # ReactDOM in script src
        r'<script[^>]*>.*?(react|react-dom|@angular|vue\.js|vue\.runtime)',  # In script content
        r'createRoot\(',  # React 18
        r'ReactDOM\.render\(',  # React render
    ]
    for pattern in script_patterns:
        if re.search(pattern, html_text, re.IGNORECASE | re.DOTALL):
            logger.debug(f"is_dynamic_framework: Found script framework pattern '{pattern}', returning True")
            return True
    
    # Step 4: Root containers with React indicators (specific checks)
    root_patterns = [r'id=["\']root["\']', r'id=["\']app["\']', r'id=["\']__next["\']', r'id=["\']react-root["\']']
    has_root = any(re.search(pattern, html_text, re.IGNORECASE) for pattern in root_patterns)
    
    if has_root:
        # Check for React terms in script context (not just anywhere in HTML)
        react_in_script = re.search(r'<script[^>]*>.*?(react|react-dom|createroot|reactdom)', html_text, re.IGNORECASE | re.DOTALL)
        if react_in_script:
            logger.debug(f"is_dynamic_framework: Found root container with React in script, returning True")
            return True
        # Check for empty root container (definitive SPA)
        if re.search(r'<div[^>]*id=["\'](root|app|__next|react-root)["\'][^>]*>\s*</div>', html_text, re.IGNORECASE):
            logger.debug(f"is_dynamic_framework: Found empty root container, returning True")
            return True
        # Check for ES6 modules (modern frameworks)
        if re.search(r'<script[^>]*type=["\']module["\']', html_text, re.IGNORECASE):
            logger.debug(f"is_dynamic_framework: Found root container with ES6 modules, returning True")
            return True
    
    # Step 5: Vue.js specific patterns
    vue_patterns = [r'v-if=', r'v-for=', r'v-model=', r'@click=', 'vue-loader', 'vue-router', '__vue__']
    for pattern in vue_patterns:
        if isinstance(pattern, str):
            if pattern in html_lower:
                logger.debug(f"is_dynamic_framework: Found Vue pattern '{pattern}', returning True")
                return True
        elif re.search(pattern, html_text, re.IGNORECASE):
            logger.debug(f"is_dynamic_framework: Found Vue pattern '{pattern}', returning True")
            return True
    
    # Step 6: Vite (specific patterns only)
    if any(pattern in html_lower for pattern in ['vite/client', '/@vite/', 'import.meta.env']):
        logger.debug(f"is_dynamic_framework: Found Vite pattern, returning True")
        return True
    
    # Step 7: Webpack with SPA framework (not Shopify)
    if 'webpack' in html_lower and 'shopify' not in html_lower:
        if re.search(r'<script[^>]*>.*?webpack.*?(react|vue|angular|svelte)', html_text, re.IGNORECASE | re.DOTALL):
            logger.debug(f"is_dynamic_framework: Found webpack SPA pattern, returning True")
            return True
    
    logger.debug(f"is_dynamic_framework: No dynamic framework patterns found, returning False")
    return False

def html_to_markdown_with_readability(html_content):
    markdown_converter = html2text.HTML2Text()
    markdown_converter.ignore_links = False
    markdown_converter.ignore_images = False
    markdown_converter.body_width = 0
    markdown_converter.ignore_emphasis = False
    markdown_content = markdown_converter.handle(html_content)
    return markdown_content

def _extract_text_from_soup(soup):
    """Extract meaningful text from soup, handling various content containers"""
    # Remove script, style, and noisy navigational/footer elements
    noisy_tags = ["script", "style", "noscript", "nav", "footer", "aside", "header"]
    for tag in soup(noisy_tags):
        tag.decompose()
    
    # Remove common filter sections by class name (heuristics)
    for filter_div in soup.find_all("div", class_=lambda c: c and "filter" in c.lower()):
        filter_div.decompose()
        
    clean_html = soup.decode_contents(formatter="html")
    markdown_text = html_to_markdown_with_readability(clean_html)
    return markdown_text

async def fetch_static_content(response,url):
        if hasattr(response, "text"):
            html = response.text
        elif isinstance(response, bytes):
            html = response.decode("utf-8", errors="replace")
        else:
            html = str(response)
        soup = BeautifulSoup(html, 'html.parser')
        
        urls = set()
        for link in soup.find_all("a", href=True):
            absolute_url = urljoin(url, link["href"])
            urls.add(absolute_url)

        text = _extract_text_from_soup(soup)

        return {
            "markdown": text,
            "links": list(urls)
        }