"""
mercadolibre — production scraper package for MercadoLibre Argentina.

Public API
----------
    from mercadolibre import scrape_one, scrape_many_parallel, ScraperConfig
    from mercadolibre.browser_pool import init_pool, shutdown_pool, get_pool
"""

from .config import ScraperConfig
from .models import Product
from .scraper import scrape_one, scrape_many_parallel

__all__ = [
    "ScraperConfig",
    "Product",
    "scrape_one",
    "scrape_many_parallel",
]
