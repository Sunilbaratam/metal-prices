from datetime import date
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


@lru_cache
def parse_duty_schedule(text: str) -> tuple[tuple[date, float], ...]:
    """'2000-01-01:6,2026-05-13:15' -> ((2000-01-01, 6.0), (2026-05-13, 15.0)), sorted by date."""
    entries = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            d, pct = part.split(":")
            entries.append((date.fromisoformat(d.strip()), float(pct)))
        except ValueError:
            raise ValueError(
                f"Bad DUTY_SCHEDULE entry '{part}'. Use YYYY-MM-DD:percent, comma separated, "
                "e.g. 2000-01-01:6,2026-05-13:15"
            ) from None
    return tuple(sorted(entries))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    goldapi_key: str = ""
    goldapi_base_url: str = "https://www.goldapi.io/api"

    monthly_request_budget: int = 90
    refresh_hours: str = "10"  # comma-separated hours in IST, e.g. "10" or "10,17"
    timezone: str = "Asia/Kolkata"

    admin_token: str = ""

    # Import duty in force from each date, e.g. "2000-01-01:6,2026-05-13:15".
    # When set, it is used for the cards (today's rate) and the chart (each day's rate).
    duty_schedule: str = ""
    # Used for every date only when DUTY_SCHEDULE is empty.
    import_duty_pct: float = 0.0
    gst_pct: float = 3.0

    cors_origins: str = "http://localhost:5173"
    db_path: str = "prices.db"
    stale_after_hours: int = 30

    @field_validator("duty_schedule")
    @classmethod
    def _check_schedule(cls, v: str) -> str:
        parse_duty_schedule(v)  # fail at startup with a clear message if it is malformed
        return v

    def duty_pct_on(self, day: date) -> float:
        """Import duty % that applied on a given day."""
        entries = parse_duty_schedule(self.duty_schedule)
        if not entries:
            return self.import_duty_pct
        rate = entries[0][1]  # days before the first entry use the first rate
        for start, pct in entries:
            if start <= day:
                rate = pct
        return rate

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def refresh_hour_list(self) -> list[int]:
        return [int(h) for h in self.refresh_hours.split(",") if h.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
