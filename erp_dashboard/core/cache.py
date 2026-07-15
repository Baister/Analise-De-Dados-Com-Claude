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

    def _connect(self):
        # WAL: leitores não bloqueiam escritores (nem vice-versa) → uma gravação
        # de bot não trava a leitura de outro cliente. synchronous=NORMAL é seguro
        # sob WAL. Ambos os PRAGMAs são idempotentes; WAL persiste no header do DB.
        conn = sqlite3.connect(self._path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self):
        with self._lock:
            con = self._connect()
            try:
                con.execute("""
                    CREATE TABLE IF NOT EXISTS cache (
                        name  TEXT PRIMARY KEY,
                        data  TEXT NOT NULL,
                        ts    TEXT NOT NULL
                    )
                """)
                con.execute("""
                    CREATE TABLE IF NOT EXISTS cache_snapshot (
                        name  TEXT NOT NULL,
                        day   TEXT NOT NULL,
                        data  TEXT NOT NULL,
                        PRIMARY KEY (name, day)
                    )
                """)
                con.commit()
            finally:
                con.close()

    def save_snapshot(self, name: str, day: str, data: dict):
        """Grava/atualiza 1 snapshot por dia (série histórica local — ex.: evolução
        do estoque). day no formato 'YYYY-MM-DD'."""
        payload = json.dumps(_clean_nan(data), default=str)
        with self._lock:
            con = self._connect()
            try:
                con.execute(
                    "INSERT OR REPLACE INTO cache_snapshot (name, day, data) VALUES (?, ?, ?)",
                    (name, day, payload),
                )
                con.commit()
            finally:
                con.close()

    def load_snapshots(self, name: str, limit: int = 180) -> list:
        """Últimos N snapshots de `name`, em ordem cronológica: [{'day':..., **data}]."""
        with self._lock:
            con = self._connect()
            try:
                rows = con.execute(
                    "SELECT day, data FROM cache_snapshot WHERE name=? ORDER BY day DESC LIMIT ?",
                    (name, limit),
                ).fetchall()
            finally:
                con.close()
        out = []
        for day, data in reversed(rows):
            try:
                d = json.loads(data)
                d["day"] = day
                out.append(d)
            except (json.JSONDecodeError, ValueError):
                continue
        return out

    def save(self, name: str, data: dict):
        ts = data.get("_ts") or datetime.now().isoformat(timespec="seconds")
        payload = json.dumps(_clean_nan(data), default=str)
        with self._lock:
            con = self._connect()
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
            con = self._connect()
            try:
                con.execute("DELETE FROM cache WHERE name=?", (name,))
                con.commit()
            finally:
                con.close()

    def load(self, name: str) -> dict | None:
        with self._lock:
            con = self._connect()
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
            con = self._connect()
            try:
                rows = con.execute("SELECT name, ts FROM cache").fetchall()
            finally:
                con.close()
        return {name: {"ts": ts} for name, ts in rows}


# module-level singleton — import this in other modules
cache = CacheManager()
