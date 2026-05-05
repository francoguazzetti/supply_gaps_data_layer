"""Simple in-memory TTL cache for scrape results."""

import time
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .config import ScraperConfig


class ResultCache:
    """Short-lived cache — avoids re-scraping identical queries within the TTL window."""

    def __init__(self, ttl_seconds: int = 300) -> None:
        self._store: dict[str, tuple[float, list]] = {}
        self._ttl = ttl_seconds

    def get(self, key: str) -> Optional[list]:
        entry = self._store.get(key)
        if entry is None:
            return None
        ts, products = entry
        if time.time() - ts < self._ttl:
            return products
        del self._store[key]   # evict expired entry
        return None

    def set(self, key: str, products: list) -> None:
        self._store[key] = (time.time(), products)

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    @staticmethod
    def key_for(config: "ScraperConfig") -> str:
        return f"{config.query}|{config.url}|{config.max_pages}"


# Module-level singleton — shared across requests
_cache = ResultCache(ttl_seconds=300)


def get_cache() -> ResultCache:
    return _cache
