"""One-time backfill of historical prices into the prices table.

Run from the backend folder (the one that contains .env and prices.db):

    python scripts/import_history.py history.csv            # preview only, writes nothing
    python scripts/import_history.py history.csv --apply    # actually write
    python scripts/import_history.py --remove-backfill --apply   # undo every imported row

CSV layout A: prices already in INR per gram (international SPOT, i.e. before duty and GST)
    date,gold_per_gram,silver_per_gram

CSV layout B: international prices in USD per troy ounce plus the USD/INR rate for that day
    date,gold_usd_oz,silver_usd_oz,usdinr

Dates: YYYY-MM-DD, or DD-MM-YYYY / DD/MM/YYYY (day first). A blank cell skips that metal for that day.

Rules:
  * Never overwrites a day that already has a price for that metal (your real fetches win).
  * Skips today and future dates.
  * Imported rows are tagged, so --remove-backfill deletes only them.
  * Makes no GoldAPI calls and doesn't touch the monthly request counter.
"""
import argparse
import csv
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# Allow running as "python scripts/import_history.py" from the backend folder.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.pricing import GRAMS_PER_TROY_OZ  # noqa: E402

MARKER = "manual_backfill"
RAW = json.dumps({"source": MARKER})

# Plausible INR-per-gram spot ranges. They catch the classic unit mix-ups
# (per 10 g or per kg pasted by mistake). Widen with --allow-outliers if prices move a lot.
SANE = {"gold": (3000, 50000), "silver": (30, 800)}
JUMP_WARN_PCT = 12.0


def parse_date(text: str) -> date:
    text = text.strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"unrecognised date '{text}'")


def to_float(text: str | None) -> float | None:
    if text is None:
        return None
    text = text.strip().replace(",", "")
    return float(text) if text else None


def read_csv(path: str) -> tuple[list[tuple[date, str, float]], list[str]]:
    """Return ([(date, metal, inr_per_gram)], errors)."""
    rows: list[tuple[date, str, float]] = []
    errors: list[str] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise SystemExit("CSV is empty.")
        cols = {c.strip().lower() for c in reader.fieldnames}
        layout_a = {"date", "gold_per_gram", "silver_per_gram"} & cols
        layout_b = {"gold_usd_oz", "silver_usd_oz", "usdinr"} & cols
        if "date" not in cols or not (layout_a - {"date"} or layout_b):
            raise SystemExit(
                "Header not recognised. Use one of:\n"
                "  date,gold_per_gram,silver_per_gram\n"
                "  date,gold_usd_oz,silver_usd_oz,usdinr"
            )
        use_b = "usdinr" in cols

        for n, raw in enumerate(reader, start=2):  # line 1 is the header
            r = {k.strip().lower(): v for k, v in raw.items() if k}
            try:
                d = parse_date(r["date"])
                if use_b:
                    fx = to_float(r.get("usdinr"))
                    if not fx or fx <= 0:
                        raise ValueError("missing or invalid usdinr")
                    vals = {
                        "gold": to_float(r.get("gold_usd_oz")),
                        "silver": to_float(r.get("silver_usd_oz")),
                    }
                    vals = {m: (v * fx / GRAMS_PER_TROY_OZ if v else None) for m, v in vals.items()}
                else:
                    vals = {
                        "gold": to_float(r.get("gold_per_gram")),
                        "silver": to_float(r.get("silver_per_gram")),
                    }
                for metal, v in vals.items():
                    if v is None:
                        continue
                    if v <= 0:
                        raise ValueError(f"{metal} price must be positive")
                    rows.append((d, metal, v))
            except (ValueError, KeyError) as e:
                errors.append(f"line {n}: {e}")
    return rows, errors


def existing_days(metal: str) -> set[str]:
    with db.connect() as conn:
        cur = conn.execute("SELECT DISTINCT substr(fetched_at,1,10) AS d FROM prices WHERE metal=?", (metal,))
        return {r["d"] for r in cur.fetchall()}


def latest_real_gram(metal: str) -> float | None:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT price_per_gram FROM prices WHERE metal=? AND (raw IS NULL OR raw NOT LIKE ?) "
            "ORDER BY fetched_at DESC LIMIT 1",
            (metal, f"%{MARKER}%"),
        ).fetchone()
    return row["price_per_gram"] if row else None


def main() -> None:
    p = argparse.ArgumentParser(description="Backfill historical prices (see file header for CSV format).")
    p.add_argument("csv_file", nargs="?", help="CSV file to import")
    p.add_argument("--apply", action="store_true", help="write changes (default is a preview)")
    p.add_argument("--allow-outliers", action="store_true", help="import even if values look out of range")
    p.add_argument("--remove-backfill", action="store_true", help="delete all rows previously imported by this script")
    args = p.parse_args()

    db.init_db()
    print(f"Database: {Path(get_settings().db_path).resolve()}")

    if args.remove_backfill:
        with db.connect() as conn:
            n = conn.execute("SELECT COUNT(*) AS n FROM prices WHERE raw LIKE ?", (f"%{MARKER}%",)).fetchone()["n"]
            print(f"{n} imported rows found.")
            if args.apply and n:
                conn.execute("DELETE FROM prices WHERE raw LIKE ?", (f"%{MARKER}%",))
                print("Deleted.")
            elif n:
                print("Preview only. Add --apply to delete them.")
        return

    if not args.csv_file:
        p.error("csv_file is required")

    rows, errors = read_csv(args.csv_file)
    if errors:
        print(f"\n{len(errors)} problem row(s):")
        for e in errors[:15]:
            print("  ", e)
        raise SystemExit("Fix these rows and run again. Nothing was written.")
    if not rows:
        raise SystemExit("No usable rows found.")

    # Range check for unit mix-ups.
    bad = [(d, m, v) for d, m, v in rows if not (SANE[m][0] <= v <= SANE[m][1])]
    if bad and not args.allow_outliers:
        print(f"\n{len(bad)} value(s) outside the expected INR/gram range (gold {SANE['gold']}, silver {SANE['silver']}):")
        for d, m, v in bad[:10]:
            print(f"   {d} {m}: {v:,.2f}")
        raise SystemExit(
            "These look like the wrong unit (per 10 g or per kg?). Fix the file, or use --allow-outliers. "
            "Nothing was written."
        )

    # De-duplicate within the file (last one wins), then filter.
    by_key: dict[tuple[date, str], float] = {}
    for d, m, v in rows:
        by_key[(d, m)] = v

    today = datetime.now(timezone.utc).date()
    to_insert, skipped_exist, skipped_recent = [], 0, 0
    have = {m: existing_days(m) for m in ("gold", "silver")}
    for (d, m), v in sorted(by_key.items()):
        if d >= today:
            skipped_recent += 1
        elif d.isoformat() in have[m]:
            skipped_exist += 1
        else:
            to_insert.append((d, m, v))

    # Report.
    print(f"\nRead {len(by_key)} day/metal values from {args.csv_file}")
    for m in ("gold", "silver"):
        ins = [(d, v) for d, mm, v in to_insert if mm == m]
        if ins:
            print(f"  {m:6}: {len(ins)} to add, {ins[0][0]} to {ins[-1][0]}, "
                  f"first {ins[0][1]:,.2f}/g, last {ins[-1][1]:,.2f}/g")
        else:
            print(f"  {m:6}: nothing to add")
    print(f"  skipped: {skipped_exist} already in DB, {skipped_recent} today/future")

    # Warn about big day-to-day jumps (often a bad cell or a unit change midway).
    for m in ("gold", "silver"):
        series = [(d, v) for d, mm, v in to_insert if mm == m]
        for (d0, v0), (d1, v1) in zip(series, series[1:]):
            chg = abs(v1 - v0) / v0 * 100
            if chg > JUMP_WARN_PCT:
                print(f"  WARNING {m}: {chg:.1f}% jump between {d0} and {d1}. Check these rows.")

    # Continuity check against your real fetched data (same basis = spot INR per gram).
    for m in ("gold", "silver"):
        real = latest_real_gram(m)
        series = [(d, v) for d, mm, v in to_insert if mm == m]
        if real and series:
            gap = (series[-1][1] - real) / real * 100
            note = "  <-- check basis (should be spot, before duty/GST)" if abs(gap) > 10 else ""
            print(f"  {m}: last imported {series[-1][1]:,.2f}/g vs latest real {real:,.2f}/g ({gap:+.1f}%){note}")

    if not args.apply:
        print("\nPreview only. Nothing written. Add --apply to import.")
        return
    if not to_insert:
        print("\nNothing to import.")
        return

    with db.connect() as conn:
        conn.executemany(
            """INSERT INTO prices (metal, fetched_at, source_ts, price_per_oz, price_per_gram,
                                   prev_close_per_oz, change, change_pct, raw)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            [
                (m, f"{d.isoformat()}T12:00:00+00:00", None, v * GRAMS_PER_TROY_OZ, v, None, None, None, RAW)
                for d, m, v in to_insert
            ],
        )
    print(f"\nImported {len(to_insert)} rows. Reload the site and open the History chart.")


if __name__ == "__main__":
    main()
