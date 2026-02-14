from __future__ import annotations

from datetime import date

from mcp.server.fastmcp import FastMCP

from . import client, storage
from .models import CustomProduct, FoodEntry

mcp = FastMCP(
    name="OpenFoodFacts Nutrition Tracker",
    instructions=(
        "Serwer do śledzenia odżywiania z bazą OpenFoodFacts. "
        "Wyszukuj polskie produkty, loguj posiłki i sprawdzaj dzienne/tygodniowe podsumowania."
    ),
)


# --- Search tools ---


@mcp.tool()
async def search_products(query: str, page: int = 1, page_size: int = 10) -> str:
    """Szukaj produktów spożywczych po nazwie (polska baza OpenFoodFacts).

    Args:
        query: Nazwa produktu do wyszukania (np. "mleko", "chleb żytni")
        page: Numer strony wyników (domyślnie 1)
        page_size: Liczba wyników na stronę (domyślnie 10, max 50)
    """
    page_size = min(page_size, 50)
    products = await client.search_products(query, page, page_size)
    if not products:
        return f"Nie znaleziono produktów dla: '{query}'"

    lines = [f"Wyniki wyszukiwania: '{query}' (strona {page})\n"]
    for i, p in enumerate(products, 1):
        n = p.nutriments
        brand = f" ({p.brands})" if p.brands else ""
        grade = f" [Nutri-Score {p.nutrition_grade.upper()}]" if p.nutrition_grade else ""
        lines.append(
            f"{i}. **{p.name}**{brand}{grade}\n"
            f"   Barcode: {p.barcode}\n"
            f"   Per 100g: {n.calories_kcal:.0f} kcal | "
            f"B:{n.proteins_g:.1f} T:{n.fats_g:.1f} W:{n.carbs_g:.1f}\n"
        )
    return "\n".join(lines)


@mcp.tool()
async def get_product(barcode: str) -> str:
    """Szczegóły produktu po kodzie kreskowym.

    Args:
        barcode: Kod kreskowy produktu (EAN-13)
    """
    product = await client.get_product(barcode)
    if not product:
        return f"Nie znaleziono produktu o kodzie: {barcode}"
    return product.format_per_100g()


@mcp.tool()
async def compare_products(barcodes: list[str]) -> str:
    """Porównaj wartości odżywcze kilku produktów obok siebie.

    Args:
        barcodes: Lista kodów kreskowych do porównania (2-5 produktów)
    """
    if len(barcodes) < 2:
        return "Podaj co najmniej 2 kody kreskowe do porównania."
    if len(barcodes) > 5:
        barcodes = barcodes[:5]

    products = []
    for bc in barcodes:
        p = await client.get_product(bc)
        if p:
            products.append(p)

    if len(products) < 2:
        return "Nie udało się znaleźć wystarczającej liczby produktów do porównania."

    # Header
    names = [f"{p.name[:25]}" for p in products]
    lines = [
        "| Wartość | " + " | ".join(names) + " |",
        "| --- | " + " | ".join("---" for _ in products) + " |",
    ]

    rows = [
        ("Kalorie (kcal)", [f"{p.nutriments.calories_kcal:.0f}" for p in products]),
        ("Białko (g)", [f"{p.nutriments.proteins_g:.1f}" for p in products]),
        ("Tłuszcze (g)", [f"{p.nutriments.fats_g:.1f}" for p in products]),
        ("Węglowodany (g)", [f"{p.nutriments.carbs_g:.1f}" for p in products]),
        ("Cukry (g)", [f"{p.nutriments.sugars_g:.1f}" for p in products]),
        ("Błonnik (g)", [f"{p.nutriments.fiber_g:.1f}" for p in products]),
        ("Nutri-Score", [p.nutrition_grade.upper() or "—" for p in products]),
    ]

    for label, values in rows:
        lines.append(f"| {label} | " + " | ".join(values) + " |")

    return "\n".join(lines)


# --- Logging tools ---


@mcp.tool()
async def log_food(
    barcode_or_name: str,
    amount_g: float,
    meal_type: str = "snack",
) -> str:
    """Zaloguj posiłek do dziennika żywieniowego.

    Args:
        barcode_or_name: Kod kreskowy produktu LUB nazwa (jeśli nazwa - szukamy w bazie)
        amount_g: Ilość w gramach
        meal_type: Typ posiłku: breakfast, lunch, dinner, snack (domyślnie snack)
    """
    meal_type = meal_type.lower()
    valid_meals = {"breakfast", "lunch", "dinner", "snack"}
    if meal_type not in valid_meals:
        return f"Nieprawidłowy typ posiłku. Użyj: {', '.join(valid_meals)}"

    # 1. Check custom products first
    custom = await storage.find_custom_product(barcode_or_name)
    product = custom.to_product() if custom else None

    # 2. Try barcode in OpenFoodFacts
    if not product and barcode_or_name.isdigit() and len(barcode_or_name) >= 8:
        product = await client.get_product(barcode_or_name)

    # 3. Search OpenFoodFacts by name
    if not product:
        results = await client.search_products(barcode_or_name, page_size=1)
        if results:
            product = results[0]

    if not product:
        return f"Nie znaleziono produktu: '{barcode_or_name}'. Dodaj go przez add_custom_product."

    # Scale nutrients from per-100g to actual amount
    ratio = amount_g / 100.0
    n = product.nutriments

    entry = FoodEntry(
        date=date.today().isoformat(),
        meal_type=meal_type,
        product_name=product.name,
        barcode=product.barcode or None,
        amount_g=amount_g,
        calories_kcal=n.calories_kcal * ratio,
        proteins_g=n.proteins_g * ratio,
        fats_g=n.fats_g * ratio,
        carbs_g=n.carbs_g * ratio,
        sugars_g=n.sugars_g * ratio,
        fiber_g=n.fiber_g * ratio,
    )

    entry_id = await storage.log_food(entry)

    meal_names = {
        "breakfast": "śniadanie",
        "lunch": "obiad",
        "dinner": "kolacja",
        "snack": "przekąska",
    }

    return (
        f"Zapisano (ID: {entry_id}):\n"
        f"  {product.name} — {amount_g:.0f}g ({meal_names[meal_type]})\n"
        f"  {entry.calories_kcal:.0f} kcal | "
        f"B:{entry.proteins_g:.1f} T:{entry.fats_g:.1f} W:{entry.carbs_g:.1f}"
    )


@mcp.tool()
async def delete_food_entry(entry_id: int) -> str:
    """Usuń wpis z dziennika żywieniowego.

    Args:
        entry_id: ID wpisu do usunięcia (widoczne w podsumowaniu dziennym)
    """
    deleted = await storage.delete_entry(entry_id)
    if deleted:
        return f"Usunięto wpis #{entry_id}."
    return f"Nie znaleziono wpisu #{entry_id}."


# --- Custom products ---


@mcp.tool()
async def add_custom_product(
    name: str,
    calories_kcal_100g: float,
    proteins_g_100g: float = 0,
    fats_g_100g: float = 0,
    carbs_g_100g: float = 0,
    brand: str = "",
    serving_g: float = 0,
    sugars_g_100g: float = 0,
    fiber_g_100g: float = 0,
) -> str:
    """Dodaj własny produkt do lokalnej bazy (np. danie z restauracji).

    Wartości odżywcze podaj na 100g. Jeśli znasz wartości na porcję,
    przelicz: wartość_na_100g = wartość_na_porcję / gramatura_porcji * 100.

    Args:
        name: Nazwa produktu (np. "Urban Mix Salad Story")
        calories_kcal_100g: Kalorie na 100g
        proteins_g_100g: Białko na 100g
        fats_g_100g: Tłuszcze na 100g
        carbs_g_100g: Węglowodany na 100g
        brand: Marka/restauracja (np. "Salad Story")
        serving_g: Typowa porcja w gramach (opcjonalne)
        sugars_g_100g: Cukry na 100g (opcjonalne)
        fiber_g_100g: Błonnik na 100g (opcjonalne)
    """
    product = CustomProduct(
        name=name,
        brand=brand,
        serving_g=serving_g or None,
        calories_kcal_100g=calories_kcal_100g,
        proteins_g_100g=proteins_g_100g,
        fats_g_100g=fats_g_100g,
        carbs_g_100g=carbs_g_100g,
        sugars_g_100g=sugars_g_100g,
        fiber_g_100g=fiber_g_100g,
    )
    product_id = await storage.add_custom_product(product)

    serving_info = f" | porcja: {serving_g:.0f}g" if serving_g else ""
    brand_info = f" ({brand})" if brand else ""
    return (
        f"Dodano produkt #{product_id}: {name}{brand_info}\n"
        f"  Per 100g: {calories_kcal_100g:.0f} kcal | "
        f"B:{proteins_g_100g:.1f} T:{fats_g_100g:.1f} W:{carbs_g_100g:.1f}"
        f"{serving_info}"
    )


@mcp.tool()
async def list_custom_products() -> str:
    """Wyświetl wszystkie własne produkty z lokalnej bazy."""
    products = await storage.list_custom_products()
    if not products:
        return "Brak własnych produktów. Dodaj przez add_custom_product."

    lines = [f"Własne produkty ({len(products)}):\n"]
    for p in products:
        brand = f" ({p.brand})" if p.brand else ""
        serving = f" | porcja: {p.serving_g:.0f}g" if p.serving_g else ""
        lines.append(
            f"#{p.id}. **{p.name}**{brand}\n"
            f"   Per 100g: {p.calories_kcal_100g:.0f} kcal | "
            f"B:{p.proteins_g_100g:.1f} T:{p.fats_g_100g:.1f} W:{p.carbs_g_100g:.1f}"
            f"{serving}\n"
        )
    return "\n".join(lines)


@mcp.tool()
async def delete_custom_product(product_id: int) -> str:
    """Usuń własny produkt z lokalnej bazy.

    Args:
        product_id: ID produktu (widoczne w list_custom_products)
    """
    deleted = await storage.delete_custom_product(product_id)
    if deleted:
        return f"Usunięto produkt #{product_id}."
    return f"Nie znaleziono produktu #{product_id}."


# --- Summary tools ---


@mcp.tool()
async def get_daily_summary(target_date: str = "today") -> str:
    """Dzienny bilans żywieniowy: kalorie, makro, lista posiłków.

    Args:
        target_date: Data w formacie YYYY-MM-DD lub "today" (domyślnie dziś)
    """
    if target_date == "today":
        target_date = date.today().isoformat()

    summary = await storage.get_daily_summary(target_date)
    if not summary.entries:
        return f"Brak wpisów na dzień {target_date}."
    return summary.format()


@mcp.tool()
async def get_weekly_summary() -> str:
    """Średnie wartości odżywcze z ostatnich 7 dni + trend kaloryczny."""
    return await storage.get_weekly_summary()


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
