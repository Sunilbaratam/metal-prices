"""Daily job for the GitHub Actions + static site setup.

    python scripts/daily_job.py --refresh   # fetch gold + silver from GoldAPI (2 requests), then export
    python scripts/daily_job.py             # export only (no GoldAPI call, uses no quota)

Export writes the JSON files the website reads (same shapes the old API returned):
    <out>/latest.json
    <out>/history_gold.json
    <out>/history_silver.json

Setting REFRESH=true in the environment is the same as --refresh (the workflow uses this).
Exit code is 1 if the refresh failed, but the export still runs, so the site keeps working
with the last known prices (it shows a warning once they are older than STALE_AFTER_HOURS).
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import HTTPException  # noqa: E402

from app import db  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.jobs import refresh_prices  # noqa: E402
from app.main import history, latest  # noqa: E402


def write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, separators=(",", ":")))
    print(f"  wrote {path} ({path.stat().st_size:,} bytes)")


def main() -> None:
    p = argparse.ArgumentParser(description="Refresh prices (optional) and export JSON for the website.")
    p.add_argument("--refresh", action="store_true", help="call GoldAPI first (uses 2 requests)")
    p.add_argument("--out", default="../frontend/public/data", help="folder for the JSON files")
    args = p.parse_args()

    refresh = args.refresh or os.environ.get("REFRESH", "").strip().lower() == "true"
    settings = get_settings()
    print(f"Database: {Path(settings.db_path).resolve()}")
    db.init_db()

    refresh_failed = False
    if refresh:
        print("Refreshing prices from GoldAPI...")
        result = asyncio.run(refresh_prices())
        print("  result:", result)
        refresh_failed = not result.get("ok")
    else:
        print("Export only (no GoldAPI call).")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    try:
        payload = latest()
    except HTTPException:
        sys.exit("No prices in the database yet. Copy your prices.db to data/prices.db first.")
    # The page works out "stale" itself from this, so it stays correct even if this job stops running.
    payload["stale_after_hours"] = settings.stale_after_hours
    payload.pop("stale", None)

    print("Exporting JSON:")
    write_json(out / "latest.json", payload)
    for metal in ("gold", "silver"):
        write_json(out / f"history_{metal}.json", history(metal=metal, range="1y"))

    used = db.requests_this_month()
    print(f"GoldAPI requests logged this month: {used}/{settings.monthly_request_budget}")
    if refresh_failed:
        print("Refresh failed. Site will use the last known prices.")
        sys.exit(1)


if __name__ == "__main__":
    main()
