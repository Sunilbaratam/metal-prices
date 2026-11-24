import asyncio
import logging

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from . import db
from .config import get_settings
from .provider import SYMBOLS, ProviderError, fetch_metal

log = logging.getLogger("prices")
_lock = asyncio.Lock()


async def refresh_prices(force: bool = False) -> dict:
    """Fetch gold + silver and store them. Skips if the monthly budget would be exceeded."""
    s = get_settings()
    async with _lock:
        used = db.requests_this_month()
        needed = len(SYMBOLS)
        if used + needed > s.monthly_request_budget:
            msg = f"budget reached ({used}/{s.monthly_request_budget}); skipping refresh"
            log.warning(msg)
            return {"ok": False, "reason": msg}

        results = {}
        async with httpx.AsyncClient() as client:
            for metal in SYMBOLS:
                try:
                    data = await fetch_metal(client, metal)
                    db.save_price(metal, data)
                    db.log_request(metal, True)
                    results[metal] = "ok"
                except ProviderError as e:
                    # Failed calls may still count against the provider quota, so log them.
                    db.log_request(metal, False, str(e))
                    log.error("fetch %s failed: %s", metal, e)
                    results[metal] = f"error: {e}"
        return {"ok": all(v == "ok" for v in results.values()), "results": results}


def build_scheduler() -> AsyncIOScheduler:
    s = get_settings()
    scheduler = AsyncIOScheduler(timezone=s.timezone)
    hours = ",".join(str(h) for h in s.refresh_hour_list)
    scheduler.add_job(
        refresh_prices, "cron", hour=hours, minute=0,
        id="refresh", max_instances=1, coalesce=True, misfire_grace_time=3600,
    )
    return scheduler
