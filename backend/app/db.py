import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metal TEXT NOT NULL,              -- 'gold' | 'silver'
    fetched_at TEXT NOT NULL,         -- ISO UTC, when we fetched
    source_ts INTEGER,                -- provider's unix timestamp
    price_per_oz REAL NOT NULL,       -- INR per troy ounce
    price_per_gram REAL NOT NULL,     -- INR per gram (spot, 24K / pure)
    prev_close_per_oz REAL,
    change REAL,
    change_pct REAL,
    raw TEXT
);
CREATE INDEX IF NOT EXISTS idx_prices_metal_time ON prices(metal, fetched_at);

CREATE TABLE IF NOT EXISTS request_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    metal TEXT NOT NULL,
    ok INTEGER NOT NULL,
    note TEXT
);
"""


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    conn = sqlite3.connect(get_settings().db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def log_request(metal: str, ok: bool, note: str = "") -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO request_log (at, metal, ok, note) VALUES (?,?,?,?)",
            (utcnow_iso(), metal, int(ok), note[:300]),
        )


def requests_this_month() -> int:
    """Count provider calls in the current UTC month (every attempt counts)."""
    prefix = datetime.now(timezone.utc).strftime("%Y-%m")
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM request_log WHERE at LIKE ?", (prefix + "%",)
        ).fetchone()
    return int(row["n"])


def save_price(metal: str, data: dict) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT INTO prices (metal, fetched_at, source_ts, price_per_oz, price_per_gram,
                                   prev_close_per_oz, change, change_pct, raw)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                metal,
                utcnow_iso(),
                data.get("source_ts"),
                data["price_per_oz"],
                data["price_per_gram"],
                data.get("prev_close_per_oz"),
                data.get("change"),
                data.get("change_pct"),
                data.get("raw"),
            ),
        )


def latest_price(metal: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM prices WHERE metal=? ORDER BY fetched_at DESC, id DESC LIMIT 1",
            (metal,),
        ).fetchone()
    return dict(row) if row else None


def price_history(metal: str, since_iso: str) -> list[dict]:
    """One row per day (the latest of that day) since the given ISO timestamp."""
    with connect() as conn:
        rows = conn.execute(
            """SELECT substr(fetched_at,1,10) AS day, price_per_gram, price_per_oz, MAX(fetched_at) AS fetched_at
               FROM prices WHERE metal=? AND fetched_at>=?
               GROUP BY substr(fetched_at,1,10) ORDER BY day""",
            (metal, since_iso),
        ).fetchall()
    return [dict(r) for r in rows]
