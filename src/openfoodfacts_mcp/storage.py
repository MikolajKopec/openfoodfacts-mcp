from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import aiosqlite

from .models import DailySummary, FoodEntry

DB_DIR = Path.home() / ".openfoodfacts-mcp"
DB_PATH = DB_DIR / "nutrition.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS food_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    meal_type TEXT NOT NULL,
    product_name TEXT NOT NULL,
    barcode TEXT,
    amount_g REAL NOT NULL,
    calories_kcal REAL,
    proteins_g REAL,
    fats_g REAL,
    carbs_g REAL,
    sugars_g REAL,
    fiber_g REAL,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_food_log_date ON food_log(date);
"""


async def _get_db() -> aiosqlite.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.executescript(SCHEMA)
    return db


async def log_food(entry: FoodEntry) -> int:
    """Insert a food entry and return its ID."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO food_log
               (date, meal_type, product_name, barcode, amount_g,
                calories_kcal, proteins_g, fats_g, carbs_g, sugars_g, fiber_g)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry.date,
                entry.meal_type,
                entry.product_name,
                entry.barcode,
                entry.amount_g,
                entry.calories_kcal,
                entry.proteins_g,
                entry.fats_g,
                entry.carbs_g,
                entry.sugars_g,
                entry.fiber_g,
            ),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]
    finally:
        await db.close()


async def delete_entry(entry_id: int) -> bool:
    """Delete a food entry by ID. Returns True if deleted."""
    db = await _get_db()
    try:
        cursor = await db.execute("DELETE FROM food_log WHERE id = ?", (entry_id,))
        await db.commit()
        return cursor.rowcount > 0  # type: ignore[return-value]
    finally:
        await db.close()


async def get_entries_for_date(target_date: str) -> list[FoodEntry]:
    """Get all food entries for a given date (YYYY-MM-DD)."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM food_log WHERE date = ? ORDER BY meal_type, id",
            (target_date,),
        )
        rows = await cursor.fetchall()
        return [
            FoodEntry(
                id=row["id"],
                date=row["date"],
                meal_type=row["meal_type"],
                product_name=row["product_name"],
                barcode=row["barcode"],
                amount_g=row["amount_g"],
                calories_kcal=row["calories_kcal"] or 0,
                proteins_g=row["proteins_g"] or 0,
                fats_g=row["fats_g"] or 0,
                carbs_g=row["carbs_g"] or 0,
                sugars_g=row["sugars_g"] or 0,
                fiber_g=row["fiber_g"] or 0,
            )
            for row in rows
        ]
    finally:
        await db.close()


async def get_daily_summary(target_date: str) -> DailySummary:
    """Get aggregated daily nutrition summary."""
    entries = await get_entries_for_date(target_date)
    return DailySummary(
        date=target_date,
        total_calories=sum(e.calories_kcal for e in entries),
        total_proteins=sum(e.proteins_g for e in entries),
        total_fats=sum(e.fats_g for e in entries),
        total_carbs=sum(e.carbs_g for e in entries),
        total_sugars=sum(e.sugars_g for e in entries),
        total_fiber=sum(e.fiber_g for e in entries),
        entries=entries,
    )


async def get_weekly_summary() -> str:
    """Get average nutrition over the last 7 days + trend."""
    today = date.today()
    days: list[DailySummary] = []
    for i in range(7):
        d = today - timedelta(days=i)
        summary = await get_daily_summary(d.isoformat())
        days.append(summary)

    active_days = [d for d in days if d.entries]
    if not active_days:
        return "Brak wpisów z ostatnich 7 dni."

    n = len(active_days)
    avg_cal = sum(d.total_calories for d in active_days) / n
    avg_prot = sum(d.total_proteins for d in active_days) / n
    avg_fat = sum(d.total_fats for d in active_days) / n
    avg_carb = sum(d.total_carbs for d in active_days) / n
    avg_sugar = sum(d.total_sugars for d in active_days) / n
    avg_fiber = sum(d.total_fiber for d in active_days) / n

    lines = [
        "# Podsumowanie tygodnia (ostatnie 7 dni)",
        f"Dni z wpisami: {n}/7",
        "",
        f"Średnio dziennie:",
        f"  Kalorie: **{avg_cal:.0f} kcal**",
        f"  Białko: **{avg_prot:.1f} g**",
        f"  Tłuszcze: **{avg_fat:.1f} g**",
        f"  Węglowodany: **{avg_carb:.1f} g**",
        f"  Cukry: {avg_sugar:.1f} g",
        f"  Błonnik: {avg_fiber:.1f} g",
        "",
        "Dzień po dniu:",
    ]

    for d in reversed(days):
        if d.entries:
            lines.append(f"  {d.date}: {d.total_calories:.0f} kcal | B:{d.total_proteins:.0f} T:{d.total_fats:.0f} W:{d.total_carbs:.0f}")
        else:
            lines.append(f"  {d.date}: — brak wpisów")

    # Simple trend: compare last 3 days vs previous 4
    recent = [d for d in days[:3] if d.entries]
    earlier = [d for d in days[3:] if d.entries]
    if recent and earlier:
        avg_recent = sum(d.total_calories for d in recent) / len(recent)
        avg_earlier = sum(d.total_calories for d in earlier) / len(earlier)
        diff = avg_recent - avg_earlier
        if abs(diff) < 50:
            trend = "stabilne"
        elif diff > 0:
            trend = f"wzrost +{diff:.0f} kcal"
        else:
            trend = f"spadek {diff:.0f} kcal"
        lines.append(f"\nTrend kaloryczny: {trend}")

    return "\n".join(lines)
