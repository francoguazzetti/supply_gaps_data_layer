"""HTML parser for MercadoLibre search results pages."""

import re
from typing import Optional

from bs4 import BeautifulSoup


def clean_price(text: str) -> Optional[str]:
    """Strip non-digit characters from a price string."""
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    return digits if digits else None


def _extract_price_block(container) -> dict:
    """Extract price, original_price, discount, and installments from a price container."""
    data: dict = {
        "price": "",
        "currency": "$",
        "original_price": "",
        "discount": "",
        "installments": "",
    }
    if not container:
        return data

    # Original price (crossed out, before discount)
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

    # Discount badge
    disc_tag = container.find("span", class_="poly-price__disc_label")
    data["discount"] = disc_tag.get_text(strip=True) if disc_tag else ""

    # Installments line
    inst_tag = container.find("span", class_="poly-price__installments")
    data["installments"] = inst_tag.get_text(strip=True) if inst_tag else ""

    return data


def parse_products(html: str) -> list[dict]:
    """
    Parse product listings from a MercadoLibre search results page.

    Returns one dict per offer — a product with a buy-box alternative yields two dicts
    (offer_type="main" and offer_type="alternative (<label>)").
    """
    soup = BeautifulSoup(html, "html.parser")
    products: list[dict] = []

    items = soup.find_all(
        "li",
        class_=lambda c: c and "ui-search-layout__item" in c and "intervention" not in c,
    )

    for item in items:
        title_tag = item.find("a", class_="poly-component__title")
        if not title_tag:
            continue

        base_title = title_tag.get_text(strip=True)
        base_href = title_tag.get("href", "")
        base_url = base_href.split("#")[0] if base_href else ""

        seller_tag = item.find("span", class_="poly-component__seller")
        base_seller = seller_tag.get_text(strip=True) if seller_tag else ""

        rating_tag = item.find("span", class_="poly-component__review-compacted")
        base_rating = ""
        if rating_tag:
            label = rating_tag.find("span", class_="poly-phrase-label")
            base_rating = label.get_text(strip=True) if label else ""

        ship_tag = item.find("div", class_="poly-component__shipping")
        base_shipping = ship_tag.get_text(strip=True) if ship_tag else ""

        img_tag = item.find("img", class_="poly-component__picture")
        base_image = img_tag.get("src", "") if img_tag else ""

        buy_box = item.find("div", class_="poly-component__buy-box")

        # Main offer — first price block NOT inside the buy-box
        main_price_div = None
        for pd in item.find_all("div", class_="poly-component__price"):
            if buy_box and pd.find_parent("div", class_="poly-component__buy-box"):
                continue
            main_price_div = pd
            break

        main_prices = _extract_price_block(main_price_div)
        products.append({
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
        })

        # Alternative offer ("Otra opción de compra")
        if buy_box:
            alt_link = buy_box.find("a", class_="poly-buy-box__alternative-option")
            alt_price_div = buy_box.find("div", class_="poly-component__price")
            alt_prices = _extract_price_block(alt_price_div)

            alt_url = ""
            alt_offer_label = ""
            if alt_link:
                alt_href = alt_link.get("href", "")
                alt_url = alt_href.split("#")[0] if alt_href else ""
                if "BEST_PRICE" in alt_url:
                    alt_offer_label = "best_price"
                elif "BEST_INSTALLMENTS" in alt_url:
                    alt_offer_label = "best_installments"
                else:
                    alt_offer_label = "alternative"

            alt_seller_tag = buy_box.find("span", class_="poly-component__seller")
            alt_seller = alt_seller_tag.get_text(strip=True) if alt_seller_tag else ""

            products.append({
                "title": base_title,
                "price": alt_prices["price"],
                "currency": alt_prices["currency"],
                "original_price": alt_prices["original_price"],
                "discount": alt_prices["discount"],
                "installments": alt_prices["installments"],
                "seller": alt_seller or base_seller,
                "rating": base_rating,
                "shipping": base_shipping,
                "product_url": alt_url or base_url,
                "image_url": base_image,
                "offer_type": f"alternative ({alt_offer_label})" if alt_offer_label else "alternative",
            })

    return products
