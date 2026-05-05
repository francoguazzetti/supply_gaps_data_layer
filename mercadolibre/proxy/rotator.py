"""ProxyRotator — round-robin over a list of proxy URLs.

Single-proxy usage (from .env):
    rotator = ProxyRotator(os.environ.get("SCRAPER_PROXY"))
    proxy_cfg = rotator.playwright_config()   # None if no proxy configured

Multi-proxy pool (future):
    rotator = ProxyRotator(["http://u:p@host1:7000", "http://u:p@host2:7000"])
"""

from typing import Optional, Union


class ProxyRotator:
    def __init__(self, proxies: Optional[Union[str, list[str]]] = None) -> None:
        if isinstance(proxies, str) and proxies.strip():
            proxies = [proxies.strip()]
        self._proxies: list[str] = proxies if proxies else []
        self._index = 0

    @property
    def has_proxy(self) -> bool:
        return bool(self._proxies)

    def current(self) -> Optional[str]:
        """Return current proxy URL without advancing the index."""
        if not self._proxies:
            return None
        return self._proxies[self._index % len(self._proxies)]

    def rotate(self) -> Optional[str]:
        """Return current proxy URL and advance to the next one."""
        if not self._proxies:
            return None
        proxy = self._proxies[self._index % len(self._proxies)]
        self._index += 1
        return proxy

    def playwright_config(self, rotate: bool = False) -> Optional[dict]:
        """Return a dict suitable for Playwright's `proxy=` launch argument."""
        url = self.rotate() if rotate else self.current()
        if not url:
            return None
        return {"server": url}
