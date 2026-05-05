"""ScraperConfig — all settings in one place."""

from dataclasses import dataclass, field
from typing import Optional
import os


@dataclass
class ScraperConfig:
    query: str = ""
    url: str = ""
    max_pages: int = 1
    delay: float = 3.0
    headless: bool = True
    engine: str = "playwright"
    proxy: Optional[str] = None        # e.g. "http://user:pass@gate.smartproxy.com:7000"
    max_workers: int = 4               # for scrape_many_parallel
    timeout_seconds: float = 25.0      # per-page timeout

    def __post_init__(self) -> None:
        # Pick up proxy from env if not set explicitly
        if self.proxy is None:
            self.proxy = os.environ.get("SCRAPER_PROXY")
