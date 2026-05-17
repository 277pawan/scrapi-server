"""
Dedicated LinkedIn scraper.
Handles LinkedIn's two-panel layout correctly by scrolling the LEFT job-list panel
and extracting structured job data from job cards.
"""
import asyncio
import json
import re
from loguru import logger


# ── Gemini AI cleaner ────────────────────────────────────────────────────────

async def clean_with_gemini(raw_text: str, api_key: str) -> str:
    """
    Use Gemini Flash to strip noise and return only clean job listings.
    Falls back to raw text if API call fails.
    """
    if not api_key or not raw_text:
        return raw_text

    try:
        import aiohttp
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        prompt = f"""You are a job data extraction assistant.
From the raw scraped text below, extract ONLY the job listings.
For each job, output a highly detailed markdown block like:

**Job Title** at **Company Name**
- Location: ...
- Posted By / Hiring Manager: [Name and title of the person who posted it, if available]
- Requirements & Details: 
  - [Extract the core skills required]
  - [Extract the years of experience]
  - [Extract any other critical requirements or responsibilities]

Do NOT truncate the requirements. Be comprehensive but remove corporate fluff.
Ignore all navigation menus, ads, footer text, login prompts, recommended connections, 
premium upsells, and any UI chrome. Output ONLY the job listings. If no jobs found, say "No jobs found."

RAW TEXT:
{raw_text[:20000]}
"""
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 8192}
        }
        
        import aiohttp
        async with aiohttp.ClientSession() as session:
            for attempt in range(3):
                try:
                    async with session.post(url, json=payload, timeout=45) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            cleaned = data["candidates"][0]["content"]["parts"][0]["text"]
                            logger.info(f"✨ Gemini cleaned content: {len(raw_text)} → {len(cleaned)} chars")
                            return cleaned
                        elif resp.status in [429, 500, 502, 503]:
                            logger.warning(f"⚠ Gemini API {resp.status} (attempt {attempt+1}/3). Retrying in 5s...")
                            await asyncio.sleep(5)
                        else:
                            logger.warning(f"⚠ Gemini API returned {resp.status}, using raw text")
                            return raw_text
                except asyncio.TimeoutError:
                    logger.warning(f"⚠ Gemini API timeout (attempt {attempt+1}/3). Retrying...")
                    await asyncio.sleep(2)
            
            logger.error("❌ Gemini API failed after 3 attempts. Falling back to raw text.")
            return raw_text
            
    except Exception as e:
        logger.warning(f"⚠ Gemini cleaning completely failed: {e}. Falling back to raw text.")
        return raw_text


# ── LinkedIn left-panel scroller ─────────────────────────────────────────────

async def scroll_linkedin_job_list(page, max_scrolls: int = 15) -> int:
    """
    Scroll specifically inside LinkedIn's LEFT job-list panel.
    Returns the number of unique job cards found.
    """
    # Bulletproof way to find the left panel: find a job card and get its scrollable parent
    list_container_js = await page.evaluate_handle("""
        () => {
            const card = document.querySelector('.job-card-container, [data-job-id], .jobs-search-results__list-item');
            if (!card) return null;
            
            let el = card.parentElement;
            while (el && el !== document.body) {
                const overflowY = window.getComputedStyle(el).overflowY;
                if (overflowY === 'auto' || overflowY === 'scroll') {
                    return el;
                }
                el = el.parentElement;
            }
            return null;
        }
    """)

    if not list_container_js:
        logger.warning("⚠ Could not find LinkedIn left panel via JS. Falling back to full-page scroll.")
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        return 0

    jobs_seen = set()

    for i in range(max_scrolls):
        logger.info(f"📜 LinkedIn left-panel scroll pass {i + 1}/{max_scrolls}...")

        # Scroll the LEFT container element (not window)
        await page.evaluate("""
            (el) => {
                if (el) el.scrollTop += 1500;
            }
        """, list_container_js)

        # Also press End key focused on the container
        await list_container_js.focus()
        await page.keyboard.press("End")
        await asyncio.sleep(2)

        # Count unique job cards
        job_ids = await page.evaluate("""
            () => {
                const cards = document.querySelectorAll('[data-job-id], .job-card-container, .jobs-search-results__list-item');
                return Array.from(cards).map(c => c.getAttribute('data-job-id') || c.innerText.substring(0, 50));
            }
        """)
        for jid in job_ids:
            jobs_seen.add(jid)

        logger.info(f"   📊 LinkedIn: {len(jobs_seen)} unique job cards visible so far")

        # Try to wait for new content to load
        try:
            await page.wait_for_load_state("networkidle", timeout=3000)
        except Exception:
            pass

    return len(jobs_seen)


# ── LinkedIn structured job extractor ────────────────────────────────────────

async def extract_linkedin_jobs(page) -> str:
    """
    Extract structured job data directly from LinkedIn's DOM.
    Clicks on each job card to load the full description in the right panel.
    """
    logger.info("🔍 Extracting detailed job data from LinkedIn DOM (clicking each card)...")

    # Get all job card elements
    cards = await page.query_selector_all('.job-card-container, [data-job-id], .jobs-search-results__list-item')
    
    unique_jobs = []
    seen = set()
    
    # Process up to 25 jobs to avoid taking forever (25 jobs * ~1.5s = ~35 seconds)
    max_jobs_to_process = 25
    
    for i, card in enumerate(cards[:max_jobs_to_process]):
        try:
            # Scroll card into view and click
            await card.scroll_into_view_if_needed()
            await card.click()
            await asyncio.sleep(1.5) # Wait for right panel to fetch and render description
            
            # Extract details from the right panel AND the card
            job_data = await page.evaluate("""
                (card) => {
                    const titleEl = card.querySelector('.job-card-list__title, h3, .job-card-container__link');
                    const companyEl = card.querySelector('.job-card-container__company-name, h4, .artdeco-entity-lockup__subtitle');
                    const locationEl = card.querySelector('.job-card-container__metadata-item, .artdeco-entity-lockup__caption');
                    
                    const title = titleEl ? titleEl.innerText.trim() : 'Unknown Title';
                    const company = companyEl ? companyEl.innerText.trim() : 'Unknown Company';
                    const location = locationEl ? locationEl.innerText.trim() : 'Unknown Location';
                    
                    // Right panel extraction
                    const rightPanel = document.querySelector('.jobs-search__job-details, .job-view-layout, .scaffold-layout__detail');
                    let description = '';
                    let poster = '';
                    
                    if (rightPanel) {
                        const descEl = rightPanel.querySelector('.jobs-description-content__text, #job-details, article');
                        if (descEl) description = descEl.innerText.trim();
                        
                        // Robust poster extraction: Try standard classes first
                        const posterEl = rightPanel.querySelector('.hirer-card__container, .job-details-jobs-unified-top-card__hiring-team, .jobs-poster');
                        if (posterEl) {
                            poster = posterEl.innerText.trim();
                        } else {
                            // Fallback: search DOM for "Meet the hiring team" text
                            const allHeaders = Array.from(rightPanel.querySelectorAll('h2, div'));
                            const teamHeader = allHeaders.find(el => el.innerText && el.innerText.includes('Meet the hiring team'));
                            if (teamHeader && teamHeader.parentElement) {
                                poster = teamHeader.parentElement.innerText.trim();
                            }
                        }
                    }
                    
                    return {title, company, location, description, poster};
                }
            """, card)
            
            # Skip empty cards
            if job_data['title'] == 'Unknown Title':
                continue
                
            key = f"{job_data['title']}|{job_data['company']}"
            if key not in seen:
                seen.add(key)
                unique_jobs.append(job_data)
                logger.info(f"   ✅ Extracted details for: {job_data['title']} at {job_data['company']}")
                
        except Exception as e:
            logger.warning(f"⚠ Failed to extract details for a job card: {e}")

    logger.info(f"✅ Finished extracting {len(unique_jobs)} detailed jobs.")

    lines = []
    for j in unique_jobs:
        lines.append(f"**Job Title:** {j['title']}")
        lines.append(f"**Company:** {j['company']}")
        lines.append(f"**Location:** {j['location']}")
        if j.get('poster'):
            # Replace newlines in poster info to make it compact
            poster_clean = " | ".join([line.strip() for line in j['poster'].split('\n') if line.strip()])
            lines.append(f"**Posted By:** {poster_clean}")
        if j.get('description'):
            desc = j['description']
            # Limit description to 2500 chars to save tokens, but keep enough for requirements
            if len(desc) > 2500:
                desc = desc[:2500] + "... [Truncated]"
            lines.append(f"**Description & Requirements:**\n{desc}\n")
        lines.append("---")

    return "\n".join(lines)
