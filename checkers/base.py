"""
Shared Playwright browser setup and search helpers used by all airline checkers.

Each checker intercepts the airline's internal JSON API responses rather than
scraping HTML, which is more reliable and less affected by UI changes.
"""
import asyncio
import logging
from playwright.async_api import async_playwright, BrowserContext

logger = logging.getLogger(__name__)

# Max concurrent searches across all tabs in one browser session
CONCURRENCY = 4


async def with_browser(checker_fn, *args, **kwargs):
    """Launch a headless browser, run checker_fn(context, ...), return results."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="Asia/Jerusalem",
        )
        try:
            return await checker_fn(context, *args, **kwargs)
        finally:
            await browser.close()


async def search_with_interception(context: BrowserContext, url: str, intercept_patterns: list[str], timeout_ms: int = 15000) -> list[dict]:
    """
    Navigate to `url` and collect all JSON responses whose URLs match any of
    `intercept_patterns`.  Returns a list of parsed JSON dicts.
    """
    captured = []

    async def on_response(response):
        if any(p in response.url for p in intercept_patterns):
            try:
                data = await response.json()
                captured.append({"url": response.url, "data": data})
                logger.debug(f"Intercepted: {response.url}")
            except Exception:
                pass

    page = await context.new_page()
    page.on("response", on_response)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        # Give the JS app time to fire its search API calls
        await page.wait_for_timeout(timeout_ms)
    except Exception as e:
        logger.warning(f"Page load issue for {url}: {e}")
    finally:
        page.remove_listener("response", on_response)
        await page.close()

    return captured


async def run_concurrent(tasks, concurrency: int = CONCURRENCY):
    """Run async tasks with a bounded semaphore."""
    sem = asyncio.Semaphore(concurrency)

    async def bounded(t):
        async with sem:
            return await t

    return await asyncio.gather(*[bounded(t) for t in tasks], return_exceptions=True)
