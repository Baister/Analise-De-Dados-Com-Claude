import sqlite3
import json
import logging
import math
import threading
import datetime as _dt
from datetime import datetime

from config.settings import CACHE_DB_PATH

logger = logging.getLogger(__name__)


def _clean_nan(obj):
    """Recursively replace float NaN/Inf with None and datetime objects with ISO strings."""
    if isinstance(obj, _dt.datetime):
        return obj.isoformat()
    if isinstance(obj, _dt.date):
        return obj.isoformat()
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_nan(v) for v in obj]
    return obj


class CacheManager:
    def __init__(self, path: str | None = None):
        self._path = path or CACHE_DB_PATH
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with self._lock:
            con = sqlite3.connect(self._path)
            try:
                con.execute("""
                    CREATE TABLE IF NOT EXISTS cache (
                        name  TEXT PRIMARY KEY,
                        data  TEXT NOT NULL,
                        ts    TEXT NOT NULL
                    )
                """)
                con.commit()
            finally:
                con.close()

    def save(self, name: str, data: dict):
        ts = data.get("_ts") or datetime.now().isoformat(timespec="seconds")
        payload = json.dumps(_clean_nan(data), default=str)
        with self._lock:
            con = sqlite3.connect(self._path)
            try:
                con.execute(
                    "INSERT OR REPLACE INTO cache (name, data, ts) VALUES (?, ?, ?)",
                    (name, payload, ts),
                )
                con.commit()
            finally:
                con.close()

    def _delete(self, name: str):
        with self._lock:
            con = sqlite3.connect(self._path)
            try:
                con.execute("DELETE FROM cache WHERE name=?", (name,))
                con.commit()
            finally:
                con.close()

    def load(self, name: str) -> dict | None:
        with self._lock:
            con = sqlite3.connect(self._path)
            try:
                row = con.execute(
                    "SELECT data FROM cache WHERE name=?", (name,)
                ).fetchone()
            finally:
                con.close()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except (json.JSONDecodeError, ValueError):
            logger.warning("Cache entry '%s' contém JSON inválido — descartando", name)
            self._delete(name)
            return None

    def status(self) -> dict:
        with self._lock:
            con = sqlite3.connect(self._path)
            try:
                rows = con.execute("SELECT name, ts FROM cache").fetchall()
            finally:
                con.close()
        return {name: {"ts": ts} for name, ts in rows}


# module-level singleton — import this in other modules
cache = CacheManager()
