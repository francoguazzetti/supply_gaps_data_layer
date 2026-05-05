"""Product data model."""

from dataclasses import dataclass


@dataclass
class Product:
    title: str
    price: str
    currency: str
    original_price: str
    discount: str
    seller: str
    rating: str
    installments: str
    shipping: str
    product_url: str
    image_url: str
    offer_type: str   # "main" | "alternative (best_price)" | ...

    def to_dict(self) -> dict:
        return self.__dict__.copy()
