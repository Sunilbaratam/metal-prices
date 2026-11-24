GRAMS_PER_TROY_OZ = 31.1035

PURITIES = {"gold": {"24K": 1.0, "22K": 22 / 24, "18K": 18 / 24}}


def per_gram_from_oz(price_per_oz: float) -> float:
    return price_per_oz / GRAMS_PER_TROY_OZ


def retail_adjust(spot_per_gram: float, import_duty_pct: float, gst_pct: float) -> float:
    """Indicative retail price: spot + import duty + GST. Excludes making charges and local premium."""
    return spot_per_gram * (1 + import_duty_pct / 100) * (1 + gst_pct / 100)


def build_view(row: dict, metal: str, duty_pct: float, gst_pct: float) -> dict:
    """Shape a DB row into what the frontend needs."""
    spot_g = row["price_per_gram"]
    retail_g = retail_adjust(spot_g, duty_pct, gst_pct)
    out = {
        "metal": metal,
        "currency": "INR",
        "updated_at": row["fetched_at"],
        "price_per_oz": round(row["price_per_oz"], 2),
        "spot_per_gram": round(spot_g, 2),
        "spot_per_10g": round(spot_g * 10, 2),
        "spot_per_kg": round(spot_g * 1000, 2),
        "retail_per_gram": round(retail_g, 2),
        "retail_per_10g": round(retail_g * 10, 2),
        "retail_per_kg": round(retail_g * 1000, 2),
        "change": row.get("change"),
        "change_pct": row.get("change_pct"),
    }
    if metal in PURITIES:
        out["by_purity_per_gram"] = {
            k: round(retail_g * f, 2) for k, f in PURITIES[metal].items()
        }
    return out
