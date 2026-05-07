import sqlite3
import json
import threading
from datetime import datetime

from config.settings import CACHE_DB_PATH


class CacheManager:
    def __init__(self, path: str | None = None):
        self._path = path or CACHE_DB_PATH
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with self._lock:
            con = sqlite3.connect(self._path)
            con.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    name  TEXT PRIMARY KEY,
                    data  TEXT NOT NULL,
                    ts    TEXT NOT NULL
                )
            """)
            con.commit()
            con.close()

    def save(self, name: str, data: dict):
        ts = data.get("_ts") or datetime.now().isoformat(timespec="seconds")
        payload = json.dumps(data, default=str)
        with self._lock:
            con = sqlite3.connect(self._path)
            con.execute(
                "INSERT OR REPLACE INTO cache (name, data, ts) VALUES (?, ?, ?)",
                (name, payload, ts),
            )
            con.commit()
            con.close()

    def load(self, name: str) -> dict | None:
        with self._lock:
            con = sqlite3.connect(self._path)
            row = con.execute(
                "SELECT data FROM cache WHERE name=?", (name,)
            ).fetchone()
            con.close()
        return json.loads(row[0]) if row else None

    def status(self) -> dict:
        with self._lock:
            con = sqlite3.connect(self._path)
            rows = con.execute("SELECT name, ts FROM cache").fetchall()
            con.close()
        return {name: {"ts": ts} for name, ts in rows}


# module-level singleton — import this in other modules
cache = CacheManager()
