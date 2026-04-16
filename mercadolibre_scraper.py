"""
MercadoLibre Argentina Scraper
==============================
A general-purpose scraping script that extracts product listing data
from MercadoLibre Argentina (mercadolibre.com.ar) search results.

Uses browser automation (Playwright or Selenium) to handle Mercadolibre's anti-bot protections and JavaScript-rendered content.

Features
--------
  - Search by keyword or provide a direct listing URL
  - Scrape multiple pages of results (configurable)
  - Extract main offer AND alternative buying options per product
  - 13 data fields per offer: title, price, original price, currency, discount, seller, rating, installments, shipping, product URL,
  image URL, offer type, and alternative offer details.
  - Export results to CSV or JSON
  - Dual browser engine: Playwright (primary) with Selenium fallback
  - Stealth mode via playwright-stealth

Usage
-----
  python3 mercadolibre_scraper.py "notebook" --pages 3 --output results.csv
  python3 mercadolibre_scraper.py "celular samsung" --pages2 --format json
  python3 mercadolibre_scraper.py --url "https://listado.mercadolibre.com.ar/notebook"
  python3 mercadolibre_scraper.py "zapatillas" --engine selenium

Setup
-----
  pip install beautifulsoup4 playwright playwright-stealth
  python -m playwright install chromium
  python -m playwright install-deps

  # Optional (for Selenium fallback):
  pip install selenium
"""

import argparse
import asyncio
import csv
import json
import logging
import os
import random
import re
import sys
import time
from typing import Optional
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

# Configuration

BASE_SEARCH_URL = "https://listado.mercadolibre.com.ar/{query}{pagination}"
ITEMS_PER_PAGE = 48

# Logging

logging.basicConfig(
  level=logging.INFO,
  format="%(asctime)s [%(levelname)s] %(message)s",
  datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# URL Helpers

def build_search_url(query: str, page: int = 1) -> str:
  """Build a MercadoLibre search URL for the given query and page number."""
  encoded_query = quote_plus(query).replace("+", "-")
  if page <= 1:
    pagination = ""
  else:
    offset = (page - 1) * ITEMS_PER_PAGE + 1
    pagination = f"_Desde_{offset}"
  return BASE_SEARCH_URL.format(query=encoded_query, pagination=pagination)

def build_page_url(base_url: str, page: int) -> str:
  """Append pagination to an existing URL."""
  if page <= 1:
    return base_url
  offset = (page - 1) * ITEMS_PER_PAGE + 1
  return f"{base_url}_Desde_{offset}"

# Parsing logic (shared by all engines)

def clean_price(text: str) -> Optional[str]:
  """Extract a numeric price string (e.g., '339.999' -> '339999')."""
  if not text:
    return None
  digits = re.sub(r"[^\d]", "", text)
  return digits if digits else None

def _extract_price_block(container) -> dict:
  """Extract price, original_price, discount, and installments form a price container."""
  data = {
    "price": "",
    "currency": "$",
    "original_price": "",
    "discount": "",
    "installments": "",
  }

  if not container:
    return data

  # Original price (before discount)
  orig_tag = container.find(
    "s", class_=lambda c: c and "andes-money-amount--previous" in c
  )
  if orig_tag:
    frac = orig_tag.find("span", class_="andes-money-amount__fraction")
    data["original_price"] = clean_price(frac.get_text(strip=True)) if frac else ""

  # Current price
  price_div = container.find("div", class_="poly-price__current")
  if price_div:
    frac = price_div.find("span", class_="andes-money-amount__fraction")
    data["price"] = clean_price(frac.get_text(strip=True)) if frac else ""
                                
    cur = price_div.find("span", class_="andes-money-amount__currency-symbol")
    data["currency"] = cur.get_text(strip=True) if cur else "$"

  # Discount
  disc_tag = container.find("span", class_="poly-price__disc_label")
  data["discount"] = disc_tag.get_text(strip=True) if disc_tag else ""

  # Installments
  inst_tag = container.find("span", class_="poly-price__installments")
  data["installments"] = inst_tag.get_text(strip=True) if inst_tag else ""

  return data

def parse_products(html: str) -> list[dict]:
  """
  Parse product data from MercadoLibre search results HTML page.

  Each product generates one row for the **main offer** and, if present,
  an additional row for the **alternative buying option** ("Otra opción
  de compra"). The ''offer_type'' field distinguishes them:

  - ''"main"'' -> the primary/featured offer
  - ''"alternative"'' -> the secondary offer (often cheaper or with different financing)
  """
  soup = BeautifulSoup(html, "html.parser")
  products = []

  items = soup.find_all(
    "li",
    class_=lambda c: c
    and "ui-search-layout__item" in c
    and "intervention" not in c,
  )

  for item in items:
    # title & url
    title_tag = item.find("a", class_="poly-component__title")
    if not title_tag:
      continue # skip non-product items

    base_title = title_tag.get_text(strip=True)
    base_href = title_tag.get("href", "")
    base_url = base_href.split("#")[0] if base_href else ""

    # Seller
    seller_tag = item.find("span", class_="poly-component__seller")
    base_seller = seller_tag.get_text(strip=True) if seller_tag else ""

    # Rating
    rating_tag = item.find("span", class_="poly-component__review-compacted")
    base_rating = ""
    if rating_tag:
      label = rating_tag.find("span", class_="poly-phrase-label")
      base_rating = label.get_text(strip=True) if label else ""

    # Shipping
    ship_tag = item.find("div", class_="poly-component__shipping")
    base_shipping = ship_tag.get_text(strip=True) if ship_tag else ""

    # Image URL
    img_tag = item.find("img", class_="poly-component__picture")
    base_image = img_tag.get("src", "") if img_tag else ""

    ##
    # Main offer
    ##
    # The main price block sits directly inside poly-card__content,
    # NOT inside the buy-box.
    main_price_container = item.find("div", class_="poly-card__content")

    # We need to be careful: the buy-box also contains a price block.
    # Extract the FIRST poly-component__price that is NOT inside the
    # buy-box.
    buy_box = item.find("div", class_="poly-component__buy-box")

    # Get the main price block (the one directly in card content)
    main_price_div = None
    all_price_divs = item.find_all("div", class_="poly-component__price")
    for pd in all_price_divs:
      # Check if this price div is inside the buy-box
      if buy_box and pd.find_parent("div", class_="poly-component__buy-box"):
        continue # skip buy-box prices
      main_price_div = pd
      break

    main_prices = _extract_price_block(main_price_div)

    main_product = {
      "title": base_title,
      "price": main_prices["price"],
      "currency": main_prices["currency"],
      "original_price": main_prices["original_price"],
      "discount": main_prices["discount"],
      "installments": main_prices["installments"],
      "seller": base_seller,
      "rating": base_rating,
      "shipping": base_shipping,
      "product_url": base_url,
      "image_url": base_image,
      "offer_type": "main",
    }
    products.append(main_product)

    ##
    # Alternative offer ("Otra opción de compra")
    ##
    if buy_box:
      alt_link = buy_box.find("a", class_="poly-buy-box__alternative-option")
      alt_price_div = buy_box.find("div", class_="poly-component__price")
      alt_prices = _extract_price_block(alt_price_div)

      alt_url = ""
      if alt_link:
        alt_href = alt_link.get("href", "")
        alt_url = alt_href.split("#")[0] if alt_href else ""

      # Determine the type of alternative offer from the URL
      alt_offer_label = ""
      if alt_url:
        if "BEST_PRICE" in alt_url:
          alt_offer_label = "best_price"
        elif "BEST_INSTALLMENTS" in alt_url:
          alt_offer_label = "best_installments"
        else:
          alt_offer_label = "alternative"
        
      # Extract the alternative seller if present
      alt_seller_tag = buy_box.find("span", class_="poly-component__seller")
      alt_seller = alt_seller_tag.get_text(strip=True) if alt_seller_tag else ""

      alt_product = {
        "title": base_title,
        "price": alt_prices["price"],
        "currency": alt_prices["currency"],
        "original_price": alt_prices["original_price"],
        "discount": alt_prices["discount"],
        "seller": alt_seller if alt_seller else base_seller,
        "rating": base_rating,
        "installments": alt_prices["installments"],
        "shipping": base_shipping,
        "product_url": alt_url if alt_url else base_url,
        "image_url": base_image,
        "offer_type": f"alternative ({alt_offer_label})" if alt_offer_label else "alternative",
      }
      products.append(alt_product)

  return products

def check_has_next_page(html: str) -> bool:
  """Check if there is a next page in the search results."""
  soup = BeautifulSoup(html, "html.parser")
  next_link = soup.find(
    "a",
    class_=lambda c: c and "andes-pagination__link" in c and "next" in c
  )
  if next_link:
    return True
  next_text = soup.find("a", string=re.compile(r"Siguiente", re.IGNORECASE))
  return next_text is not None

##
# Engine: Playwright (primary)
##

async def _playwright_fetch(url: str, context, retries: int = 2) -> Optional[str]:
  """Fetch a page using a Playwright browser context."""
  for attempt in range(1, retries + 1):
    page = await context.new_page()
    try:
      await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

      try:
        await page.wait_for_selector(
          "li.ui-search-layout__item, ol.ui-search-layout",
          timeout=15_000,
        )
      except Exception:
        pass
      
      await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
      await page.wait_for_timeout(1000)
      await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
      await page.wait_for_timeout(1500)

      html = await page.content()

      if "account-verification" in page.url or len(html) < 50_000:
        logger.warning(
          "Attempt %d/%d: verification page or short content for %s",
          attempt, retries, url,
        )
        await page.close()
        if attempt < retries:
          await asyncio.sleep(3 + random.uniform(0, 2))
        continue

      await page.close()
      return html

    except Exception as exc:
      logger.warning("Attempt %d/%d: error fetching %s - %s", attempt, retries, url, exc)
      try:
        await page.close()
      except Exception:
        pass
      if attempt < retries:
        await asyncio.sleep(3 + random.uniform(0, 2))
    
  return None

async def scrape_playwright(
  query: str,
  url: str,
  max_pages: int,
  delay: float,
  headless: bool,
) -> list[dict]:
  """Scrape using Playwright with stealth."""
  try:
    from playwright.async_api import async_playwright
  except ImportError:
    logger.error(
      "Playwright is not installed. Run: "
      "pip install playwright && python -m playwright install chromium"
    )
    return []
  
  stealth_obj = None
  try:
    from playwright_stealth import Stealth
    stealth_obj = Stealth(
      navigator_languages_override=("es-AR", "es"),
      navigator_platform_override="Win32",
    )
  except ImportError:
    logger.warning("playwright-stealth not installed, running without stealth mode.")

  all_products: list[dict] = []

  async with async_playwright() as p:
    browser = await p.chromium.launch(
      headless=headless,
      args=[
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
      ],
    )
    context = await browser.new_context(
      viewport={"width": 1920, "height": 1080},
      locale="es-AR",
      user_agent=(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
      ),
    )
    
    if stealth_obj:
      await context.add_init_script(stealth_obj.script_payload)

    for page_num in range(1, max_pages + 1):
      if url:
        page_url = url if page_num == 1 else build_page_url(url, page_num)
      else:
        page_url = build_search_url(query, page_num)
      logger.info("Scraping page %d/%d: %s", page_num, max_pages, page_url)

      html = await _playwright_fetch(page_url, context)
      if html is None:
        logger.error("Failed to fetch page %d after retries: %s", page_num, page_url)
        break
      
      products = parse_products(html)
      main_count = sum(1 for p in products if p["offer_type"] == "main")
      alt_count = len(products) - main_count
      logger.info(
        "Found %d products on page %d (%d main + %d alternative offers)",
        main_count, page_num, main_count, alt_count,
      )

      if not products:
        logger.info("No products found on page %d. Stopping.", page_num)
        break
      
      all_products.extend(products)

      if not check_has_next_page(html):
        logger.info("No next page link found on page %d. Stopping.", page_num)
        break

      if page_num < max_pages:
        wait = delay + random.uniform(1, 3)
        logger.info("Waiting %.1f seconds...", wait)
        await asyncio.sleep(wait)
      
    await browser.close()

  return all_products

##
# Engine: Selenium (fallback)
##

def _selenium_create_driver(headless: bool = True):
  """Create a Selenium Chrome/Chromium driver."""
  from selenium import webdriver
  from selenium.webdriver.chrome.options import Options

  options = Options()
  if headless:
    options.add_argument("--headless=new")
  options.add_argument("--no-sandbox")
  options.add_argument("--disable-dev-shm-usage")
  options.add_argument("--disable-gpu")
  options.add_argument("--window-size=1920,1080")
  options.add_argument("--disable-blink-features=AutomationControlled")
  options.add_experimental_option("excludeSwitches", ["enable-automation"])
  options.add_experimental_option("useAutomationExtension", False)
  options.add_argument(
    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
  )
  options.add_argument("--lang=es-AR")

  for binary in ["/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"]:
    if os.path.exists(binary):
      options.binary_location = binary
      break
  
  driver = webdriver.Chrome(options=options)
  driver.execute_cdp_cmd(
    "Page.addScriptToEvaluateOnNewDocument",
    {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"},
  )
  driver.set_page_load_timeout(60)
  return driver

def _selenium_fetch(driver, url: str, retries: int = 2) -> Optional[str]:
  """Fetch a page using Selenium."""
  from selenium.webdriver.common.by import By
  from selenium.webdriver.support.ui import WebDriverWait
  from selenium.webdriver.support import expected_conditions as EC

  for attempt in range(1, retries + 1):
    try:
      driver.get(url)

      try:
        WebDriverWait(driver, 15).until(
          EC.presence_of_element_located((By.CSS_SELECTOR, "li.ui-search-layout__item, ol.ui-search-layout"))
        )
      except Exception:
        pass

      driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
      time.sleep(1)
      driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
      time.sleep(1.5)

      html = driver.page_source

      if "account-verification" in driver.current_url or len(html) < 50_000:
        logger.warning(
          "Attempt %d/%d: verification page or short content for %s",
          attempt, retries, url,
        )
        if attempt < retries:
          time.sleep(3 + random.uniform(0, 2))
        continue

      return html

    except Exception as exc:
      logger.warning("Attempt %d/%d: error fetching %s - %s", attempt, retries, url, exc)
      if attempt < retries:
        time.sleep(3 + random.uniform(0, 2))
  return None

def scrape_selenium(
  query: str,
  url: str,
  max_pages: int,
  delay: float,
  headless: bool,
) -> list[dict]:
  """Scrape using Selenium."""
  try:
    from selenium import webdriver # noqa: F401
  except ImportError:
    logger.error(
      "Selenium is not installed. Run: pip install selenium "
      "and ensure you have ChromeDriver installed and in your PATH."
    )
    return []

  all_products: list[dict] = []
  driver = _selenium_create_driver(headless)

  try:
    for page_num in range(1, max_pages + 1):
      if url:
        page_url = url if page_num == 1 else build_page_url(url, page_num)
      else:
        page_url = build_search_url(query, page_num)
      logger.info("Scraping page %d/%d: %s", page_num, max_pages, page_url)

      html = _selenium_fetch(driver, page_url)
      if html is None:
        logger.error("Failed to fetch page %d after retries: %s", page_num, page_url)
        break
      
      products = parse_products(html)
      main_count = sum(1 for p in products if p["offer_type"] == "main")
      alt_count = len(products) - main_count
      logger.info(
        "Found %d products on page %d (%d main + %d alternative offers)",
        main_count, page_num, main_count, alt_count,
      )

      if not products:
        logger.info("No products found on page %d. Stopping.", page_num)
        break
      
      all_products.extend(products)

      if not check_has_next_page(html):
        logger.info("No next page link found on page %d. Stopping.", page_num)
        break

      if page_num < max_pages:
        wait = delay + random.uniform(1, 3)
        logger.info("Waiting %.1f seconds...", wait)
        time.sleep(wait)
  finally:
    driver.quit()

  return all_products

##
# Export functions
##

FIELDNAMES = [
  "title",
  "price",
  "currency",
  "original_price",
  "discount",
  "seller",
  "rating",
  "installments",
  "shipping",
  "product_url",
  "image_url",
  "offer_type",
]

def export_csv(products: list[dict], filename: str) -> None:
  """Export products to a CSV file."""
  if not products:
    logger.warning("No products to export.")
    return
  with open(filename, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(products)
  logger.info("Exported %d products to %s", len(products), filename)


def export_json(products: list[dict], filename: str) -> None:
  """Export products to a JSON file."""
  if not products:
    logger.warning("No products to export.")
    return
  with open(filename, "w", encoding="utf-8") as f:
    json.dump(products, f, ensure_ascii=False, indent=2)
  logger.info("Exported %d products to %s", len(products), filename)

##
# Main orchestrator
##

def scrape(
  query: str = "",
  url: str = "",
  max_pages: int = 1,
  delay: float = 3.0,
  output: str = "mercadolibre_results.csv",
  fmt: str = "csv",
  headless: bool = True,
  engine: str = "playwright",
) -> list[dict]:
  """Main scraping function.

    Parameters
    ----------
    query : str
        Search keyword(s) to look up on MercadoLibre.
    url : str
        Direct listing URL (overrides query if provided).
    max_pages : int
        Maximum number of pages to scrape.
    delay : float
        Base delay (in seconds) between page requests to avoid rate-limiting.
    output : str
        Output file path for the scraped data.
    fmt : str
        Output format: "csv" or "json".
    headless : bool
        Run browser in headless mode (no GUI).
    engine : str
        Browser engine: 'playwright' (default) or 'selenium' (fallback).
    
    Returns
    -------
    list[dict]
        A list of product data dictionaries extracted from the search results.
  """
  logger.info("Starting MercadoLibre scraper with engine: %s (headless=%s)", engine, headless)

  if engine == "playwright":
    all_products = asyncio.run(
        scrape_playwright(query, url, max_pages, delay, headless)
    )
    if not all_products:
      logger.warning("Playwright scraping failed or returned no products. Trying Selenium fallback...")
      all_products = scrape_selenium(query, url, max_pages, delay, headless)
  else:
    all_products = scrape_selenium(query, url, max_pages, delay, headless)

  main_count = sum(1 for p in all_products if p["offer_type"] == "main")
  alt_count = len(all_products) - main_count
  logger.info(
    "Scraping completed. Total products: %d (%d main + %d alternative offers)",
    len(all_products), main_count, alt_count,
  )

  if all_products:
    if fmt == "json":
      export_json(all_products, output)
    else:
      export_csv(all_products, output)

  return all_products

##
# CLI entry point
##

def main():
  parser = argparse.ArgumentParser(
    description="Scrape product listings from MercadoLibre Argentina.",
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    epilog="""
  Examples:
    %(prog)s "notebook" --pages 3 --output results.csv
    %(prog)s "celular samsung" --pages 2 --format json
    %(prog)s --url "https://listado.mercadolibre.com.ar/notebook"
    %(prog)s "zapatillas" --engine selenium
    %(prog)s "tv smart" --no-headless
    %(prog)s "auriculares" --engine selenium
    """,
  )
  parser.add_argument("query", nargs="?", default="", help="Search keyword(s) to look up.")
  parser.add_argument("--url", help="Direct listing URL (overrides query if provided).")
  parser.add_argument("--pages", type=int, default=1, help="Maximum number of pages to scrape.")
  parser.add_argument("--delay", type=float, default=3.0, help="Base delay (in seconds) between page requests to avoid rate-limiting.")
  parser.add_argument("--output", default="", help="Output file path for the scraped data.")
  parser.add_argument("--format", choices=["csv", "json"], default="csv", help="Output format: 'csv' or 'json'.")
  parser.add_argument("--no-headless", action="store_false", dest="headless", help="Run browser in non-headless mode (with GUI).")
  parser.add_argument("--engine", choices=["playwright", "selenium"], default="playwright", help="Browser engine to use: 'playwright' (default) or 'selenium' (fallback).")
  args = parser.parse_args()

  if not args.query and not args.url:
    parser.error("You must provide either a search query or a direct URL.")
  
  if not args.output:
    ext = "json" if args.format == "json" else "csv"
    safe_name = (re.sub(r"[^\w\-]+", "_", args.query.strip())[:50] or "results").strip("_")
    args.output = f"mercadolibre_{safe_name}.{ext}"

  products = scrape(
    query=args.query,
    url=args.url,
    max_pages=args.pages,
    delay=args.delay,
    output=args.output,
    fmt=args.format,
    headless=args.headless,
    engine=args.engine,
  )

  if products:
    main_count = sum(1 for p in products if p["offer_type"] == "main")
    alt_count = len(products) - main_count

    print(f"\n{'='*80}")
    print(f" Done! {len(products)} rows saved to: {args.output}")
    print(f" ({main_count} main offers + {alt_count} alternative offers)")
    print(f"{'='*80}\n")
    print("\nSample (first 5 rows):")
    print("-" * 80)
    for p in products[:5]:
      offer_label = p["offer_type"].upper()
      print(f" [{offer_label}]")
      print(f" Title: {p['title'][:65]}")
      print(f" Price: {p['currency']} {p['price']}")
      if p["original_price"]:
        print(f" Was: {p['currency']} {p['original_price']}")
      print(f" Seller: {p['seller']}")
      print(f" Rating: {p['rating']}")
      print(f" Discount: {p['discount']}")
      print(f" Installments: {p['installments']}")
      print(f" Shipping: {p['shipping']}")
      print(f" URL: {p['product_url']}")
      print("-" * 80)
  else:
    print("\nNo products were found. Try a different search query.")
    print("Tips:")
    print(" - MercadoLibre may block automated access from certain IPs.")
    print(" - Try running with --no-headless to see what happens.")
    print(" - Try a different --engine (playwright or selenium).")
    sys.exit(1)

if __name__ == "__main__":
  main()