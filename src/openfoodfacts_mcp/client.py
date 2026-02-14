from __future__ import annotations

import httpx

from .models import Product

BASE_URL = "https://pl.openfoodfacts.org"
USER_AGENT = "OpenFoodFactsMCP/1.0 (https://github.com/openfoodfacts-mcp)"
PRODUCT_FIELDS = (
    "code,product_name,product_name_pl,brands,nutrition_grades,"
    "nutriments,allergens,nova_groups,image_url,serving_size"
)


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=BASE_URL,
        headers={"User-Agent": USER_AGENT},
        timeout=15.0,
    )


async def search_products(query: str, page: int = 1, page_size: int = 10) -> list[Product]:
    """Search OpenFoodFacts for products by name (Polish locale)."""
    async with _client() as client:
        resp = await client.get(
            "/cgi/search.pl",
            params={
                "search_terms": query,
                "search_simple": 1,
                "action": "process",
                "json": 1,
                "lc": "pl",
                "page": page,
                "page_size": page_size,
                "fields": PRODUCT_FIELDS,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    products = []
    for item in data.get("products", []):
        try:
            products.append(Product.from_api(item))
        except Exception:
            continue
    return products


async def get_product(barcode: str) -> Product | None:
    """Get product details by barcode."""
    async with _client() as client:
        resp = await client.get(
            f"/api/v2/product/{barcode}",
            params={"lc": "pl", "fields": PRODUCT_FIELDS},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()

    if data.get("status") == 0:
        return None
    return Product.from_api(data)
