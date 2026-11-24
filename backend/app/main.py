import logging
import secrets
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .config import get_settings
from .jobs import build_scheduler, refresh_prices
from .pricing import build_view, retail_adjust

logging.basicConfig(level=logging.INFO)
METALS = ("gold", "silver")
RANGES = {"1w": 7, "1m": 30, "3m": 90, "6m": 180, "1y": 365}


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    if not get_settings().duty_schedule:
        logging.getLogger("prices").warning(
            "DUTY_SCHEDULE is empty: IMPORT_DUTY_PCT=%s is applied to every date, including old history.",
            get_settings().import_duty_pct,
        )
    scheduler = build_scheduler()
    scheduler.start()
    # First run on an empty DB: fetch once so the site isn't blank.
    if db.latest_price("gold") is None:
        await refresh_prices()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Gold & Silver Prices (India)", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _is_stale(updated_at: str) -> bool:
    age = datetime.now(timezone.utc) - datetime.fromisoformat(updated_at)
    return age > timedelta(hours=get_settings().stale_after_hours)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/prices/latest")
def latest():
    s = get_settings()
    duty_today = s.duty_pct_on(datetime.now(ZoneInfo(s.timezone)).date())
    out, newest = {}, None
    for metal in METALS:
        row = db.latest_price(metal)
        if row:
            out[metal] = build_view(row, metal, duty_today, s.gst_pct)
            newest = max(newest or row["fetched_at"], row["fetched_at"])
    if not out:
        raise HTTPException(503, "No price data yet")
    return {
        **out,
        "updated_at": newest,
        "stale": _is_stale(newest),
        "note": "Indicative prices. Retail = spot + import duty + GST; excludes making charges and local premiums.",
    }


@app.get("/api/prices/history")
def history(metal: str = Query("gold"), range: str = Query("1m")):
    if metal not in METALS:
        raise HTTPException(400, "metal must be 'gold' or 'silver'")
    if range not in RANGES:
        raise HTTPException(400, f"range must be one of {list(RANGES)}")
    since = (datetime.now(timezone.utc) - timedelta(days=RANGES[range])).isoformat(timespec="seconds")
    rows = db.price_history(metal, since)
    s = get_settings()
    points = []
    for r in rows:
        duty = s.duty_pct_on(date.fromisoformat(r["day"]))  # the rate in force on that day
        points.append(
            {
                "date": r["day"],
                "spot_per_gram": round(r["price_per_gram"], 2),
                "retail_per_gram": round(retail_adjust(r["price_per_gram"], duty, s.gst_pct), 2),
                "duty_pct": duty,
                "per_oz": round(r["price_per_oz"], 2),
            }
        )
    return {"metal": metal, "range": range, "points": points}


@app.get("/api/usage")
def usage():
    s = get_settings()
    used = db.requests_this_month()
    return {"used": used, "budget": s.monthly_request_budget, "remaining": max(s.monthly_request_budget - used, 0)}


@app.post("/api/admin/refresh")
async def admin_refresh(x_admin_token: str = Header(default="")):
    expected = get_settings().admin_token
    if not expected or not secrets.compare_digest(x_admin_token, expected):
        raise HTTPException(401, "Invalid admin token")
    return await refresh_prices(force=True)
