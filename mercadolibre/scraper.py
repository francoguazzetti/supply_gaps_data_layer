"""
Main scraper orchestrator.

Public API
----------
    scrape_one(config)               -> list[dict]   # single query
    scrape_many_parallel(configs)    -> list[list[dict]]  # multiple queries

Both functions:
  - Check the result cache first (5-min TTL)
  - Use the warm browser pool when available (no cold-start cost)
  - Fall back to launching a temporary browser when pool is not running
  - Return partial results on timeout rather than failing silently
  - Retry up to 2 times on transient failures
"""

import asyncio
import logging
import random
from typing import Optional

from .browser_pool import get_pool, BrowserPool
from .browser.playwright_engine import create_context, fetch_page, launch_browser
from .cache import get_cache, ResultCache
from .config import ScraperConfig
from .parsers.pagination import build_search_url, build_page_url, check_has_next_page
from .parsers.product_parser import parse_products

logger = logging.getLogger(__name__)

# Maximum retries per scrape attempt
_MAX_RETRIES = 2


# ---------------------------------------------------------------------------
# Core page-level scraping (given an open browser)
# ---------------------------------------------------------------------------


async def _scrape_with_browser(config: ScraperConfig, browser) -> list[dict]:
    """
    Run a full multi-page scrape using an already-open browser.
    Creates a fresh context per call to avoid cookie/state leakage.
    Returns partial results if a page fails.
    """
    context = await create_context(browser)
    all_products: list[dict] = []

    try:
        for page_num in range(1, config.max_pages + 1):
            if config.url:
                page_url = config.url if page_num == 1 else build_page_url(config.url, page_num)
            else:
                page_url = build_search_url(config.query, page_num)

            logger.info("Scraping page %d/%d: %s", page_num, config.max_pages, page_url)

            timeout_ms = int(config.timeout_seconds * 1_000)
            html = await fetch_page(page_url, context, timeout_ms=timeout_ms)

            if html is None:
                logger.warning("Page %d returned no content — returning partial results", page_num)
                break

            products = parse_products(html)
            main_n = sum(1 for p in products if p["offer_type"] == "main")
            logger.info(
                "Page %d: %d products (%d main + %d alternative)",
                page_num, len(products), main_n, len(products) - main_n,
            )

            if not products:
                logger.info("No products on page %d — stopping early", page_num)
                break

            all_products.extend(products)

            if not check_has_next_page(html):
                logger.info("No next-page link on page %d — done", page_num)
                break

            if page_num < config.max_pages:
                wait = config.delay + random.uniform(1, 3)
                logger.info("Waiting %.1fs before next page", wait)
                await asyncio.sleep(wait)

    finally:
        await context.close()

    return all_products


# ---------------------------------------------------------------------------
# Retry wrapper
# ---------------------------------------------------------------------------


async def _scrape_with_retry(config: ScraperConfig, pool: Optional[BrowserPool]) -> list[dict]:
    """Attempt a scrape up to _MAX_RETRIES times, returning partial results on exhaustion."""
    last_exc: Optional[Exception] = None

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            if pool is not None:
                async with pool.acquire() as browser:
                    return await _scrape_with_browser(config, browser)
            else:
                # Standalone mode — launch a temporary browser
                from playwright.async_api import async_playwright
                async with async_playwright() as p:
                    browser = await launch_browser(p, proxy=config.proxy, headless=config.headless)
                    try:
                        return await _scrape_with_browser(config, browser)
                    finally:
                        await browser.close()

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            last_exc = exc
            logger.warning("Scrape attempt %d/%d failed: %s", attempt, _MAX_RETRIES, exc)
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(2 ** attempt)

    logger.error("All %d scrape attempts failed. Last error: %s", _MAX_RETRIES, last_exc)
    return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def scrape_one(config: ScraperConfig, pool: Optional[BrowserPool] = None) -> list[dict]:
    """
    Scrape a single query, using the cache when available.

    `pool` defaults to the module-level singleton (set by init_pool() in lifespan).
    Pass an explicit pool only in tests or standalone scripts.
    """
    if pool is None:
        pool = get_pool()

    cache = get_cache()
    cache_key = ResultCache.key_for(config)

    cached = cache.get(cache_key)
    if cached is not None:
        logger.info("Cache hit for %r — returning %d cached products", cache_key, len(cached))
        return cached

    results = await _scrape_with_retry(config, pool)

    if results:
        cache.set(cache_key, results)

    return results


async def scrape_many_parallel(
    configs: list[ScraperConfig],
    pool: Optional[BrowserPool] = None,
) -> list[list[dict]]:
    """
    Run multiple queries in parallel, bounded by config.max_workers.
    Returns a list of result-lists in the same order as `configs`.
    """
    if not configs:
        return []

    max_workers = configs[0].max_workers
    sem = asyncio.Semaphore(max_workers)

    async def _worker(cfg: ScraperConfig) -> list[dict]:
        async with sem:
            return await scrape_one(cfg, pool=pool)

    return list(await asyncio.gather(*[_worker(c) for c in configs]))
