"""URL building and pagination detection for MercadoLibre Argentina."""

import re
from urllib.parse import quote_plus

BASE_SEARCH_URL = "https://listado.mercadolibre.com.ar/{query}{pagination}"
ITEMS_PER_PAGE = 48


def build_search_url(query: str, page: int = 1) -> str:
    """Build a MercadoLibre search URL for the given query and page number."""
    encoded = quote_plus(query).replace("+", "-")
    pagination = "" if page <= 1 else f"_Desde_{(page - 1) * ITEMS_PER_PAGE + 1}"
    return BASE_SEARCH_URL.format(query=encoded, pagination=pagination)


def build_page_url(base_url: str, page: int) -> str:
    """Append pagination offset to an existing listing URL."""
    if page <= 1:
        return base_url
    return f"{base_url}_Desde_{(page - 1) * ITEMS_PER_PAGE + 1}"


def check_has_next_page(html: str) -> bool:
    """Return True if the HTML contains a 'next page' pagination link."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    next_link = soup.find(
        "a",
        class_=lambda c: c and "andes-pagination__link" in c and "next" in c,
    )
    if next_link:
        return True
    return soup.find("a", string=re.compile(r"Siguiente", re.IGNORECASE)) is not None
