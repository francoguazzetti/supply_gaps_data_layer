"""Playwright browser engine — page fetching and per-request context management."""

import asyncio
import logging
import random
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Browser

logger = logging.getLogger(__name__)

# User-agent that blends in with real Argentine traffic
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

_LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-blink-features=AutomationControlled",
]


def _get_stealth_script() -> Optional[str]:
    """Return the playwright-stealth init script payload, or None if not installed."""
    try:
        from playwright_stealth import Stealth

        stealth = Stealth(
            navigator_languages_override=("es-AR", "es"),
            navigator_platform_override="Win32",
        )
        return stealth.script_payload
    except Exception:
        logger.warning("playwright-stealth not available — running without stealth mode")
        return None


async def create_context(browser: "Browser"):
    """Create a fresh browser context with Argentine locale and stealth applied."""
    context = await browser.new_context(
        viewport={"width": 1920, "height": 1080},
        locale="es-AR",
        user_agent=_USER_AGENT,
    )
    script = _get_stealth_script()
    if script:
        await context.add_init_script(script)
    return context


async def fetch_page(url: str, context, timeout_ms: int = 30_000, retries: int = 2) -> Optional[str]:
    """
    Fetch a single URL using an existing Playwright browser context.

    Returns the page HTML on success, or None after all retries are exhausted.
    """
    for attempt in range(1, retries + 1):
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

            # Wait for the product grid (best-effort)
            try:
                await page.wait_for_selector(
                    "li.ui-search-layout__item, ol.ui-search-layout",
                    timeout=15_000,
                )
            except Exception:
                pass

            # Scroll to trigger lazy-loaded images / JS
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            await page.wait_for_timeout(1_000)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1_500)

            html = await page.content()

            if "account-verification" in page.url or len(html) < 50_000:
                logger.warning(
                    "Attempt %d/%d: verification page or suspiciously short content (%d bytes) for %s",
                    attempt, retries, len(html), url,
                )
                await page.close()
                if attempt < retries:
                    await asyncio.sleep(3 + random.uniform(0, 2))
                continue

            await page.close()
            return html

        except Exception as exc:
            logger.warning("Attempt %d/%d: error fetching %s — %s", attempt, retries, url, exc)
            try:
                await page.close()
            except Exception:
                pass
            if attempt < retries:
                await asyncio.sleep(3 + random.uniform(0, 2))

    return None


async def launch_browser(playwright, proxy: Optional[str] = None, headless: bool = True):
    """Launch a fresh Chromium browser, optionally via proxy."""
    kwargs: dict = {"headless": headless, "args": _LAUNCH_ARGS}
    if proxy:
        kwargs["proxy"] = {"server": proxy}
    return await playwright.chromium.launch(**kwargs)
