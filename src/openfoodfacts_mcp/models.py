from __future__ import annotations

from pydantic import BaseModel, Field


class Nutriments(BaseModel):
    calories_kcal: float = Field(0, alias="energy-kcal_100g")
    proteins_g: float = Field(0, alias="proteins_100g")
    fats_g: float = Field(0, alias="fat_100g")
    carbs_g: float = Field(0, alias="carbohydrates_100g")
    sugars_g: float = Field(0, alias="sugars_100g")
    fiber_g: float = Field(0, alias="fiber_100g")
    salt_g: float = Field(0, alias="salt_100g")

    model_config = {"populate_by_name": True}


class Product(BaseModel):
    barcode: str = ""
    name: str = ""
    brands: str = ""
    nutrition_grade: str = ""
    nova_group: int | None = None
    image_url: str = ""
    serving_size: str = ""
    nutriments: Nutriments = Field(default_factory=Nutriments)

    @classmethod
    def from_api(cls, data: dict) -> Product:
        product = data.get("product", data)
        nutriments_raw = product.get("nutriments", {})

        return cls(
            barcode=product.get("code", product.get("_id", "")),
            name=product.get("product_name_pl") or product.get("product_name", ""),
            brands=product.get("brands", ""),
            nutrition_grade=product.get("nutrition_grades", ""),
            nova_group=product.get("nova_groups"),
            image_url=product.get("image_url", ""),
            serving_size=product.get("serving_size", ""),
            nutriments=Nutriments.model_validate(nutriments_raw),
        )

    def format_per_100g(self) -> str:
        n = self.nutriments
        lines = [
            f"**{self.name}** ({self.brands})" if self.brands else f"**{self.name}**",
            f"Barcode: {self.barcode}" if self.barcode else "",
            f"Nutri-Score: {self.nutrition_grade.upper()}" if self.nutrition_grade else "",
            f"NOVA: {self.nova_group}" if self.nova_group else "",
            "",
            "Per 100g:",
            f"  Kalorie: {n.calories_kcal:.0f} kcal",
            f"  Białko: {n.proteins_g:.1f} g",
            f"  Tłuszcze: {n.fats_g:.1f} g",
            f"  Węglowodany: {n.carbs_g:.1f} g",
            f"  Cukry: {n.sugars_g:.1f} g",
            f"  Błonnik: {n.fiber_g:.1f} g",
            f"  Sól: {n.salt_g:.2f} g",
        ]
        if self.serving_size:
            lines.append(f"  Porcja: {self.serving_size}")
        return "\n".join(line for line in lines if line is not None)


class CustomProduct(BaseModel):
    id: int = 0
    name: str
    brand: str = ""
    serving_g: float | None = None
    calories_kcal_100g: float
    proteins_g_100g: float = 0
    fats_g_100g: float = 0
    carbs_g_100g: float = 0
    sugars_g_100g: float = 0
    fiber_g_100g: float = 0

    def to_product(self) -> Product:
        """Convert to Product for unified handling in log_food."""
        return Product(
            name=self.name,
            brands=self.brand,
            serving_size=f"{self.serving_g:.0f}g" if self.serving_g else "",
            nutriments=Nutriments(
                **{
                    "energy-kcal_100g": self.calories_kcal_100g,
                    "proteins_100g": self.proteins_g_100g,
                    "fat_100g": self.fats_g_100g,
                    "carbohydrates_100g": self.carbs_g_100g,
                    "sugars_100g": self.sugars_g_100g,
                    "fiber_100g": self.fiber_g_100g,
                }
            ),
        )


class FoodEntry(BaseModel):
    id: int = 0
    date: str = ""
    meal_type: str = ""
    product_name: str = ""
    barcode: str | None = None
    amount_g: float = 0
    calories_kcal: float = 0
    proteins_g: float = 0
    fats_g: float = 0
    carbs_g: float = 0
    sugars_g: float = 0
    fiber_g: float = 0


class DailySummary(BaseModel):
    date: str
    total_calories: float = 0
    total_proteins: float = 0
    total_fats: float = 0
    total_carbs: float = 0
    total_sugars: float = 0
    total_fiber: float = 0
    entries: list[FoodEntry] = Field(default_factory=list)

    def format(self) -> str:
        lines = [
            f"# Podsumowanie dnia: {self.date}",
            "",
            f"Kalorie: **{self.total_calories:.0f} kcal**",
            f"Białko: **{self.total_proteins:.1f} g**",
            f"Tłuszcze: **{self.total_fats:.1f} g**",
            f"Węglowodany: **{self.total_carbs:.1f} g**",
            f"Cukry: {self.total_sugars:.1f} g",
            f"Błonnik: {self.total_fiber:.1f} g",
            "",
        ]
        if self.entries:
            meal_order = ["breakfast", "lunch", "dinner", "snack"]
            meal_names = {
                "breakfast": "Śniadanie",
                "lunch": "Obiad",
                "dinner": "Kolacja",
                "snack": "Przekąska",
            }
            by_meal: dict[str, list[FoodEntry]] = {}
            for e in self.entries:
                by_meal.setdefault(e.meal_type, []).append(e)

            for meal in meal_order:
                if meal not in by_meal:
                    continue
                meal_entries = by_meal[meal]
                meal_cal = sum(e.calories_kcal for e in meal_entries)
                lines.append(f"### {meal_names.get(meal, meal)} ({meal_cal:.0f} kcal)")
                for e in meal_entries:
                    lines.append(
                        f"- {e.product_name} ({e.amount_g:.0f}g) — "
                        f"{e.calories_kcal:.0f} kcal | "
                        f"B:{e.proteins_g:.1f} T:{e.fats_g:.1f} W:{e.carbs_g:.1f}"
                    )
                lines.append("")

        return "\n".join(lines)
