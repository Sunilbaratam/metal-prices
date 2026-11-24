"""One-time download of ~1 year of gold and silver history for the chart.

Run from the backend folder (the one with .env):

    python scripts/fetch_history.py                    # show the plan, spends nothing
    python scripts/fetch_history.py --go --max-calls 1 # first call only: check your GoldAPI dashboard cost
    python scripts/fetch_history.py --go               # the rest (already-saved chunks are reused)

Then load it into the database:

    python scripts/import_history.py history.csv            # preview
    python scripts/import_history.py history.csv --apply

What it does:
  * Calls GoldAPI /history/{XAU|XAG}/USD in 31-day chunks (the same shape as your sample curl).
  * Saves every raw chunk under history_cache/, so a re-run never pays twice for the same data.
  * Logs each real call to the app's request counter (see /api/usage).
  * Gets daily USD/INR from Frankfurter (free, ECB rates, no key, no GoldAPI quota).
  * Writes history.csv (date, gold_usd_oz, silver_usd_oz, usdinr) for import_history.py.

Stops at the first error and never prints your API key.
"""
import argparse
import csv
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402
from app.config import get_settings  # noqa: E402

SYMBOLS = {"gold": "XAU", "silver": "XAG"}
CHUNK_DAYS = 31  # same span as your sample (24 Oct to 23 Nov = 31 days inclusive)
FX_URL = "https://api.frankfurter.dev/v1/{start}..{end}"
FX_WINDOW_DAYS = 80  # keep each FX request short; long ranges may be returned weekly


def make_client() -> httpx.Client:
    return httpx.Client(timeout=30)


def chunk_ranges(start: date, end: date) -> list[tuple[date, date]]:
    out, s = [], start
    while s <= end:
        e = min(s + timedelta(days=CHUNK_DAYS - 1), end)
        out.append((s, e))
        s = e + timedelta(days=1)
    return out


def cache_path(cache_dir: Path, symbol: str, s: date, e: date) -> Path:
    return cache_dir / f"{symbol}_{s}_{e}.json"


def validate_chunk(data: dict, symbol: str) -> list[dict]:
    if not isinstance(data, dict) or not isinstance(data.get("prices"), list):
        raise ValueError(f"unexpected response shape: {json.dumps(data)[:200]}")
    if data.get("currency") != "USD":
        raise ValueError(f"expected currency USD, got {data.get('currency')!r}")
    if data.get("metal") not in (None, symbol):
        raise ValueError(f"expected metal {symbol}, got {data.get('metal')!r}")
    for item in data["prices"]:
        if not isinstance(item.get("price"), (int, float)) or not item.get("date"):
            raise ValueError(f"bad price item: {item}")
    return data["prices"]


def load_prices(cache_dir: Path, symbol: str, ranges: list[tuple[date, date]]) -> dict[str, float]:
    prices: dict[str, float] = {}
    for s, e in ranges:
        data = json.loads(cache_path(cache_dir, symbol, s, e).read_text())
        for item in validate_chunk(data, symbol):
            prices[item["date"]] = float(item["price"])
    return prices


def fetch_fx(client: httpx.Client, start: date, end: date) -> dict[str, float]:
    """Daily USD->INR (business days only) from Frankfurter, fetched in short windows."""
    rates: dict[str, float] = {}
    s = start
    while s <= end:
        e = min(s + timedelta(days=FX_WINDOW_DAYS - 1), end)
        resp = client.get(FX_URL.format(start=s, end=e), params={"base": "USD", "symbols": "INR"})
        resp.raise_for_status()
        for d, row in resp.json().get("rates", {}).items():
            if "INR" in row:
                rates[d] = float(row["INR"])
        s = e + timedelta(days=1)
    if not rates:
        raise ValueError("no USD/INR rates returned")
    return rates


def load_fx_csv(path: str) -> dict[str, float]:
    rates: dict[str, float] = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            r = {k.strip().lower(): v for k, v in r.items() if k}
            rates[r["date"].strip()] = float(r["usdinr"])
    return rates


def fx_for(rates: dict[str, float], day: str) -> float:
    """Rate on that day, else the latest earlier one (weekends/holidays), else the first known."""
    keys = sorted(rates)
    prior = [k for k in keys if k <= day]
    return rates[prior[-1]] if prior else rates[keys[0]]


def main() -> None:
    p = argparse.ArgumentParser(description="Download one year of gold/silver history (see file header).")
    p.add_argument("--go", action="store_true", help="actually call GoldAPI (default only shows the plan)")
    p.add_argument("--max-calls", type=int, default=24, help="stop after this many real GoldAPI calls")
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--out", default="history.csv")
    p.add_argument("--cache-dir", default="history_cache")
    p.add_argument("--fx-csv", help="use your own file (columns: date,usdinr) instead of Frankfurter")
    args = p.parse_args()

    settings = get_settings()
    cache_dir = Path(args.cache_dir)
    end = datetime.now(timezone.utc).date() - timedelta(days=1)
    start = end - timedelta(days=args.days - 1)
    ranges = chunk_ranges(start, end)

    todo = [(m, s, e) for m in SYMBOLS for s, e in ranges if not cache_path(cache_dir, SYMBOLS[m], s, e).exists()]
    print(f"Period: {start} to {end}  ({len(ranges)} chunks x {len(SYMBOLS)} metals = {len(ranges) * len(SYMBOLS)} calls)")
    print(f"Already saved: {len(ranges) * len(SYMBOLS) - len(todo)}   Still to download: {len(todo)}")

    if not args.go:
        print("\nPlan only. Nothing was called. Add --go to download "
              "(use --max-calls 1 first to check how your dashboard counts the call).")
        return

    db.init_db()
    if todo and not settings.goldapi_key:
        raise SystemExit("GOLDAPI_KEY is not set in .env")

    cache_dir.mkdir(exist_ok=True)
    calls = 0
    with make_client() as client:
        for metal, s, e in todo:
            if calls >= args.max_calls:
                print(f"\nReached --max-calls {args.max_calls}. Check your GoldAPI dashboard, then run again.")
                return
            symbol = SYMBOLS[metal]
            url = f"{settings.goldapi_base_url}/history/{symbol}/USD"
            try:
                resp = client.get(url, params={"from": str(s), "to": str(e)},
                                  headers={"x-access-token": settings.goldapi_key})
            except httpx.HTTPError as ex:
                raise SystemExit(f"Network error on {symbol} {s}..{e}: {ex}")
            calls += 1
            if resp.status_code != 200:
                db.log_request(metal, False, f"history {s}..{e} HTTP {resp.status_code}")
                raise SystemExit(f"{symbol} {s}..{e}: HTTP {resp.status_code}: {resp.text[:200]}\n"
                                 "Stopped. Saved chunks are kept; fix the problem and run again.")
            try:
                data = resp.json()
                validate_chunk(data, symbol)
            except ValueError as ex:
                db.log_request(metal, False, f"history {s}..{e} bad response")
                raise SystemExit(f"{symbol} {s}..{e}: {ex}\nStopped. Nothing from this call was saved.")
            cache_path(cache_dir, symbol, s, e).write_text(json.dumps(data))
            db.log_request(metal, True, f"history {s}..{e}")
            print(f"  saved {symbol} {s}..{e}: {len(data['prices'])} days")
            time.sleep(1)

        # All chunks are saved. Now the exchange rate.
        if args.fx_csv:
            fx = load_fx_csv(args.fx_csv)
        else:
            print("Fetching USD/INR from Frankfurter...")
            try:
                fx = fetch_fx(client, start - timedelta(days=10), end)
            except (httpx.HTTPError, ValueError) as ex:
                raise SystemExit(
                    f"Could not get USD/INR ({ex}). Your gold/silver chunks are saved, so nothing is lost.\n"
                    "Provide your own daily rates with: --fx-csv rates.csv (columns: date,usdinr)"
                )

    gold = load_prices(cache_dir, "XAU", ranges)
    silver = load_prices(cache_dir, "XAG", ranges)
    days = sorted(set(gold) | set(silver))
    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "gold_usd_oz", "silver_usd_oz", "usdinr"])
        for d in days:
            w.writerow([d, gold.get(d, ""), silver.get(d, ""), round(fx_for(fx, d), 4)])
    print(f"\nWrote {args.out}: {len(days)} days ({days[0]} to {days[-1]}).")
    print(f"GoldAPI calls this run: {calls}.  Next:\n"
          f"  python scripts/import_history.py {args.out}           # preview\n"
          f"  python scripts/import_history.py {args.out} --apply")


if __name__ == "__main__":
    main()
