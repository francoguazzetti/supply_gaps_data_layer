"""
BrowserPool — keeps Playwright browsers warm between requests.

Eliminates the 3-5 second cold-start cost of launching Chromium per request.
Each scrape acquires a browser from the pool, creates a fresh context (so
there is no cookie/state leakage between requests), does its work, then
releases the browser back. If a browser crashes it is automatically replaced.

Usage (FastAPI lifespan):

    from mercadolibre.browser_pool import init_pool, shutdown_pool, get_pool

    @asynccontextmanager
    async def lifespan(app):
        await init_pool(size=2, proxy=os.environ.get("SCRAPER_PROXY"))
        yield
        await shutdown_pool()
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

logger = logging.getLogger(__name__)


class BrowserPool:
    def __init__(
        self,
        size: int = 2,
        proxy: Optional[str] = None,
        headless: bool = True,
    ) -> None:
        self._size = size
        self._proxy = proxy
        self._headless = headless
        self._queue: asyncio.Queue = asyncio.Queue()
        self._playwright = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        from playwright.async_api import async_playwright
        from .browser.playwright_engine import launch_browser

        self._playwright = await async_playwright().start()
        for _ in range(self._size):
            browser = await launch_browser(self._playwright, proxy=self._proxy, headless=self._headless)
            await self._queue.put(browser)
        logger.info("BrowserPool started with %d browser(s) (proxy=%s)", self._size, bool(self._proxy))

    async def stop(self) -> None:
        closed = 0
        while not self._queue.empty():
            try:
                browser = self._queue.get_nowait()
                await browser.close()
                closed += 1
            except asyncio.QueueEmpty:
                break
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        logger.info("BrowserPool stopped (%d browser(s) closed)", closed)

    # ------------------------------------------------------------------
    # Acquire / release
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def acquire(self):
        """
        Context manager that yields a browser from the pool.
        On exit the browser is returned (or replaced if it crashed).
        """
        browser = await self._queue.get()
        try:
            yield browser
        finally:
            if browser.is_connected():
                await self._queue.put(browser)
            else:
                # Browser crashed — replace it so pool size stays stable
                logger.warning("Browser crashed; launching replacement")
                try:
                    from .browser.playwright_engine import launch_browser
                    replacement = await launch_browser(
                        self._playwright, proxy=self._proxy, headless=self._headless
                    )
                    await self._queue.put(replacement)
                except Exception as exc:
                    logger.error("Failed to launch replacement browser: %s", exc)
                    # Pool shrinks by 1 — acceptable graceful degradation


# ---------------------------------------------------------------------------
# Module-level singleton (shared across all FastAPI requests)
# ---------------------------------------------------------------------------

_pool: Optional[BrowserPool] = None


async def init_pool(
    size: int = 2,
    proxy: Optional[str] = None,
    headless: bool = True,
) -> BrowserPool:
    """Create and warm the global browser pool. Call once at app startup."""
    global _pool
    _pool = BrowserPool(size=size, proxy=proxy, headless=headless)
    await _pool.start()
    return _pool


def get_pool() -> Optional[BrowserPool]:
    """Return the global pool, or None if not yet initialised."""
    return _pool


async def shutdown_pool() -> None:
    """Drain and close the global pool. Call at app shutdown."""
    global _pool
    if _pool is not None:
        await _pool.stop()
        _pool = None
