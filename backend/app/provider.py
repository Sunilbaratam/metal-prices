import json

import httpx

from .config import get_settings
from .pricing import per_gram_from_oz

SYMBOLS = {"gold": "XAU", "silver": "XAG"}


class ProviderError(Exception):
    pass


def _num(v):
    return float(v) if isinstance(v, (int, float)) else None


async def fetch_metal(client: httpx.AsyncClient, metal: str) -> dict:
    """Fetch the latest INR price for one metal from GoldAPI.io (costs 1 request)."""
    s = get_settings()
    if not s.goldapi_key:
        raise ProviderError("GOLDAPI_KEY is not set")

    url = f"{s.goldapi_base_url}/{SYMBOLS[metal]}/INR"
    try:
        resp = await client.get(url, headers={"x-access-token": s.goldapi_key}, timeout=15)
    except httpx.HTTPError as e:
        raise ProviderError(f"network error: {e}") from e

    if resp.status_code != 200:
        raise ProviderError(f"HTTP {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    price_oz = _num(data.get("price"))
    if price_oz is None:
        raise ProviderError(f"unexpected response: {json.dumps(data)[:200]}")

    return {
        "source_ts": data.get("timestamp"),
        "price_per_oz": price_oz,
        # Prefer provider's own per-gram figure if present, else convert.
        "price_per_gram": _num(data.get("price_gram_24k")) or per_gram_from_oz(price_oz),
        "prev_close_per_oz": _num(data.get("prev_close_price")),
        "change": _num(data.get("ch")),
        "change_pct": _num(data.get("chp")),
        "raw": json.dumps(data),
    }
