# core/database.py

import pyodbc
import pandas as pd
import threading
import time
import logging
from config.settings import DB_CONFIG, ALERTAS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

_lock = threading.Lock()
_RETRY_DELAYS = [5, 10, 30, 60]


class DatabaseManager:
    def __init__(self):
        self._conn = None
        self._last_ping = 0
        self.last_error: str = ""

    def _build_conn_str(self) -> str:
        c = DB_CONFIG
        return (
            f"DSN={c['dsn']};"
            f"UID={c['user']};"
            f"PWD={c['password']};"
            f"Connection Timeout={c['timeout']};"
        )

    def connect(self) -> bool:
        for delay in [0] + _RETRY_DELAYS:
            if delay:
                logger.warning("Aguardando %ds antes de reconectar...", delay)
                time.sleep(delay)
            try:
                self._conn = pyodbc.connect(self._build_conn_str(), autocommit=True)
                self._conn.timeout = 60  # command timeout
                self._last_ping = time.time()
                logger.info("Conectado ao SQL Server via DSN=%s", DB_CONFIG["dsn"])
                return True
            except Exception as e:
                logger.error("Falha na conexao: %s", e)
                self._conn = None
        return False

    def disconnect(self):
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def is_connected(self) -> bool:
        if not self._conn:
            return False
        now = time.time()
        if now - self._last_ping > 60:
            try:
                self._conn.execute("SELECT 1")
                self._last_ping = now
            except Exception:
                self._conn = None
                return False
        return True

    def ensure_connected(self) -> bool:
        if self.is_connected():
            return True
        logger.warning("Reconectando...")
        return self.connect()

    def query(self, sql: str, params=None) -> pd.DataFrame:
        with _lock:
            if not self.ensure_connected():
                return pd.DataFrame()
            try:
                cursor = self._conn.cursor()
                if params is not None:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                if cursor.description is None:
                    return pd.DataFrame()
                cols = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                df = pd.DataFrame([list(r) for r in rows], columns=cols)
                max_rows = ALERTAS.get("query_max_rows", 5000)
                if len(df) > max_rows:
                    df = df.head(max_rows)
                self.last_error = ""
                return df
            except Exception as e:
                self.last_error = str(e)
                logger.error("Erro na query: %s\n→ SQL: %.400s", e, sql.strip())
                self._conn = None
                return pd.DataFrame()

    def listar_bancos(self) -> list[str]:
        df = self.query("SELECT name FROM sys.databases ORDER BY name")
        return df["name"].tolist() if not df.empty else []

    def mapear_planos(self) -> pd.DataFrame:
        for tbl in ("Blue.dbo.TbPlanoVnd", "Blue.dbo.vwPlanoVnd"):
            df = self.query(f"SELECT CodPlanoVnd, NomePlanoVnd FROM {tbl} ORDER BY CodPlanoVnd")
            if not df.empty:
                return df
        return pd.DataFrame()


db = DatabaseManager()
