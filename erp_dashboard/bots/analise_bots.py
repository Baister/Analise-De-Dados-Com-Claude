# bots/analise_bots.py
# Bots de análise — queries com os nomes reais do banco Blue.
# CodPlanoVnd = FORMA DE PAGAMENTO (não tipo de documento).
# Separação Orçamento × Venda usa Blue.dbo.TbOrcPedVnd.OrcPedVnd (1=Orc, 2=Venda).

import concurrent.futures
import math
import re as _re
import pandas as pd
import threading
import time
import logging
from datetime import datetime
from config.settings import BOT_INTERVALS, ALERTAS, PLANOS_EXCLUIR_FAT
from core.database import db
from core.cache import cache as _cache

logger = logging.getLogger(__name__)

MAX               = ALERTAS.get("query_max_rows", 5000)
DIAS_RISCO        = ALERTAS.get("cliente_em_risco_dias", 60)
DIAS_INATIVO      = ALERTAS.get("cliente_inativo_dias", 90)
DIAS_CRITICO      = ALERTAS.get("estoque_critico_dias_sem_vnd", 90)
DIAS_LISTA_INAT   = 30   # mostra inativos a partir de 30 dias
DIAS_ALERTA_RISCO = 40   # início da zona de alerta (antes de DIAS_RISCO=60 "risco confirmado")
_MES_INI        = "DATEADD(month, DATEDIFF(month, 0, GETDATE()), 0)"
_MES_FIM        = "DATEADD(month, DATEDIFF(month, 0, GETDATE()) + 1, 0)"
_MES_INI_ANT    = "DATEADD(month, DATEDIFF(month, 0, GETDATE()) - 1, 0)"
_MES_FIM_ANT    = "DATEADD(month, DATEDIFF(month, 0, GETDATE()),     0)"
_pl = "','".join(PLANOS_EXCLUIR_FAT)
_EXCLUIR_PLANO  = f"AND v.CodPlanoVnd NOT IN ('{_pl}')"


def _valid_date(s: str) -> bool:
    return bool(s and _re.fullmatch(r'\d{4}-\d{2}(-\d{2})?', s))


def _safe_float(df: pd.DataFrame, col: str) -> float:
    if df.empty or col not in df.columns:
        return 0.0
    v = df[col].iloc[0]
    try:
        return 0.0 if pd.isna(v) else float(v)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(df: pd.DataFrame, col: str) -> int:
    return int(_safe_float(df, col))


# ──────────────────────────────────────────────────────────────────
class BaseBot(threading.Thread):
    def __init__(self, name: str):
        super().__init__(daemon=True, name=name)
        self.name_label  = name
        self.interval    = BOT_INTERVALS.get(name, 600)
        self.resultado: dict = {}
        self.ultimo_update   = "—"
        self.status          = "aguardando"
        self._stop           = threading.Event()
        self.callbacks: list = []
        self.erro_msg: str   = ""
        self._ultimo_update_dt: "datetime | None" = None

    def stop(self):
        self._stop.set()

    def add_callback(self, fn):
        self.callbacks.append(fn)

    def _notify(self):
        _now = datetime.now()
        self._ultimo_update_dt = _now
        self.ultimo_update = _now.strftime("%H:%M:%S")
        for cb in self.callbacks:
            try:
                cb(self.name_label, self.resultado)
            except Exception as e:
                logger.warning("Callback error [%s]: %s", self.name_label, e)
        try:
            if self.resultado:  # only persist if there's actual data
                _cache.save(self.name_label, self.resultado)
        except Exception as e:
            logger.warning("cache.save error for %s: %s", self.name_label, e)

    def seconds_until_next(self) -> "int | None":
        if self.status == "executando":
            return 0
        if self._ultimo_update_dt is None:
            return None
        elapsed = (datetime.now() - self._ultimo_update_dt).total_seconds()
        return max(0, int(self.interval - elapsed))

    def run(self):
        logger.info("Bot [%s] iniciado. Intervalo: %ds", self.name_label, self.interval)
        while not self._stop.is_set():
            self.status = "executando"
            try:
                self.resultado = self.analisar()
                self.status = "ok"
                self.erro_msg = ""
            except Exception as e:
                logger.error("Bot [%s] erro: %s", self.name_label, e)
                self.status = "erro"
                self.erro_msg = str(e)
            self._notify()
            for _ in range(max(1, self.interval // 5)):
                if self._stop.is_set():
                    break
                time.sleep(5)

    def analisar(self) -> dict:
        raise NotImplementedError


# ──────────────────────────────────────────────────────────────────
#  BOT DASHBOARD  — KPIs gerais do mês (somente vendas faturadas)
# ──────────────────────────────────────────────────────────────────
class BotDashboard(BaseBot):
    def __init__(self):
        super().__init__("dashboard")

    def analisar(self) -> dict:
        df_kpi = db.query(f"""
            SELECT
                SUM(CASE WHEN v.CustoRepTotal >= 0 THEN v.ValVndTotal ELSE 0 END)   AS venda_bruta,
                SUM(CASE WHEN v.CustoRepTotal <  0 THEN v.ValVndTotal ELSE 0 END)   AS devolucao,
                COUNT(DISTINCT CASE WHEN v.CustoRepTotal >= 0 THEN v.NrDoc END)     AS qtd_documentos,
                COUNT(DISTINCT CASE WHEN v.CustoRepTotal <  0 THEN v.NrDoc END)     AS qtd_devolucoes,
                COUNT(DISTINCT v.CodCli)                                             AS clientes_ativos,
                SUM(CASE WHEN v.CustoRepTotal >= 0 THEN v.ValVndTotal ELSE 0 END)
                    / NULLIF(COUNT(DISTINCT CASE WHEN v.CustoRepTotal >= 0 THEN v.NrDoc END), 0)
                                                                                     AS ticket_medio,
                SUM(CASE WHEN v.CustoRepTotal >= 0 THEN v.ValVndTotal - v.CustoRepTotal ELSE 0 END)
                                                                                     AS margem_bruta
            FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
            INNER JOIN Blue.dbo.vwVndDoc d WITH (NOLOCK) ON v.NrDoc = d.NrDoc AND v.NSUDoc = d.NSUDoc
            WHERE v.DtVnd >= {_MES_INI}
              AND v.DtVnd <  {_MES_FIM}
              AND d.Cancelado    = ''
              AND d.Fat          = 1
              {_EXCLUIR_PLANO}
        """)

        df_vend = db.query(f"""
            SELECT TOP 10
                v.Vendedor,
                v.CodVend,
                SUM(CASE WHEN v.CustoRepTotal >= 0 THEN v.ValVndTotal ELSE 0 END)
                    AS total_venda,
                SUM(CASE WHEN v.CustoRepTotal <  0 THEN v.ValVndTotal ELSE 0 END)
                    AS devolucao,
                COUNT(DISTINCT CASE WHEN v.CustoRepTotal >= 0 THEN v.NrDoc END)
                    AS qtd_pedidos,
                COUNT(DISTINCT CASE WHEN v.CustoRepTotal <  0 THEN v.NrDoc END)
                    AS qtd_devolucoes,
                SUM(CASE WHEN v.CustoRepTotal >= 0 THEN v.ValVndTotal ELSE 0 END)
                    / NULLIF(COUNT(DISTINCT CASE WHEN v.CustoRepTotal >= 0 THEN v.NrDoc END), 0)
                    AS ticket_medio,
                SUM(CASE WHEN v.CustoRepTotal >= 0 THEN v.ValVndTotal - v.CustoRepTotal ELSE 0 END)
                    AS margem_bruta
            FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
            INNER JOIN Blue.dbo.vwVndDoc d WITH (NOLOCK) ON v.NrDoc = d.NrDoc AND v.NSUDoc = d.NSUDoc
            WHERE v.DtVnd >= {_MES_INI}
              AND v.DtVnd <  {_MES_FIM}
              AND d.Cancelado = ''
              AND d.Fat = 1
              {_EXCLUIR_PLANO}
            GROUP BY v.Vendedor, v.CodVend
            ORDER BY total_venda DESC
        """)

        df_diario = db.query(f"""
            SELECT dia, faturamento FROM (
                SELECT TOP 30
                    CONVERT(date, v.DtVnd) AS dia,
                    SUM(CASE WHEN v.CustoRepTotal >= 0 THEN v.ValVndTotal ELSE 0 END) AS faturamento
                FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
                INNER JOIN Blue.dbo.vwVndDoc d WITH (NOLOCK) ON v.NrDoc = d.NrDoc AND v.NSUDoc = d.NSUDoc
                WHERE v.DtVnd >= DATEADD(day, -30, GETDATE())
                  AND d.Cancelado = ''
                  AND d.Fat = 1
                  {_EXCLUIR_PLANO}
                GROUP BY CONVERT(date, v.DtVnd)
                ORDER BY dia DESC
            ) _sub ORDER BY dia
        """)

        df_marcas = db.query(f"""
            SELECT TOP 8
                i.DescrMarca,
                SUM(CASE WHEN i.CustoRepTotItem >= 0 THEN i.PrecoVndTotItem ELSE 0 END) AS faturamento,
                SUM(CASE WHEN i.CustoRepTotItem <  0 THEN i.PrecoVndTotItem ELSE 0 END) AS devolucao,
                SUM(CASE WHEN i.CustoRepTotItem >= 0 THEN i.PrecoVndTotItem - i.CustoRepTotItem ELSE 0 END) AS margem_bruta,
                SUM(CASE WHEN i.CustoRepTotItem >= 0 THEN i.QtdItem ELSE 0 END)         AS quantidade,
                COUNT(DISTINCT CASE WHEN i.CustoRepTotItem >= 0 THEN i.NrDoc END)       AS qtd_documentos,
                COUNT(DISTINCT CASE WHEN i.CustoRepTotItem <  0 THEN i.NrDoc END)       AS qtd_devolucoes
            FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
            WHERE i.DtVnd >= {_MES_INI}
              AND i.DtVnd <  {_MES_FIM}
              AND i.Fat = 1
              AND i.DescrMarca IS NOT NULL
            GROUP BY i.DescrMarca
            ORDER BY faturamento DESC
        """)

        # Map CodVend → Vendedor using df_vend so names match top_vendedores exactly
        _cod_vend_map: dict = {}
        if not df_vend.empty and 'CodVend' in df_vend.columns:
            _cod_vend_map = dict(zip(df_vend['CodVend'].astype(str), df_vend['Vendedor']))

        if _cod_vend_map:
            _in_codvend = ','.join(f"'{c}'" for c in _cod_vend_map)
            _raw = db.new_conn_query(f"""
                SELECT TOP 500
                    i.CodVend,
                    i.DescrMarca,
                    SUM(i.PrecoVndTotItem) AS faturamento,
                    SUM(i.QtdItem)         AS quantidade
                FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
                WHERE i.DtVnd >= {_MES_INI}
                  AND i.DtVnd <  {_MES_FIM}
                  AND i.Fat = 1
                  AND i.DescrMarca IS NOT NULL
                  AND i.CustoRepTotItem >= 0
                  AND i.CodVend IN ({_in_codvend})
                GROUP BY i.CodVend, i.DescrMarca
                ORDER BY i.CodVend, faturamento DESC
            """)
            if not _raw.empty:
                _raw['Vendedor'] = _raw['CodVend'].astype(str).map(_cod_vend_map)
                df_marcas_vend = _raw.dropna(subset=['Vendedor'])[
                    ['Vendedor', 'DescrMarca', 'faturamento', 'quantidade']
                ].copy()
            else:
                df_marcas_vend = pd.DataFrame()
        else:
            df_marcas_vend = pd.DataFrame()

        df_diario_vend = db.query(f"""
            SELECT
                CONVERT(date, v.DtVnd) AS dia,
                v.Vendedor,
                SUM(CASE WHEN v.CustoRepTotal >= 0 THEN v.ValVndTotal ELSE 0 END) AS faturamento
            FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
            INNER JOIN Blue.dbo.vwVndDoc d WITH (NOLOCK) ON v.NrDoc = d.NrDoc AND v.NSUDoc = d.NSUDoc
            WHERE v.DtVnd >= DATEADD(day, -30, GETDATE())
              AND d.Cancelado = ''
              AND d.Fat = 1
              {_EXCLUIR_PLANO}
            GROUP BY CONVERT(date, v.DtVnd), v.Vendedor
            ORDER BY dia, faturamento DESC
        """)

        df_diario_marca = db.query(f"""
            SELECT
                CONVERT(date, i.DtVnd) AS dia,
                i.DescrMarca,
                SUM(i.PrecoVndTotItem) AS faturamento
            FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
            WHERE i.DtVnd >= DATEADD(day, -30, GETDATE())
              AND i.Fat = 1
              AND i.DescrMarca IS NOT NULL
              AND i.CustoRepTotItem >= 0
            GROUP BY CONVERT(date, i.DtVnd), i.DescrMarca
            ORDER BY dia, faturamento DESC
        """)

        venda_bruta  = _safe_float(df_kpi, "venda_bruta")
        devolucao    = _safe_float(df_kpi, "devolucao")
        venda_liq    = venda_bruta + devolucao
        margem_bruta = _safe_float(df_kpi, "margem_bruta")
        meta         = ALERTAS.get("meta_faturamento_mensal", 400000)
        pct          = round(venda_liq / meta * 100, 1) if meta else 0

        return {
            "faturamento_atual":               venda_liq,
            "venda_bruta":                     venda_bruta,
            "devolucao":                       devolucao,
            "venda_liquida":                   venda_liq,
            "qtd_documentos":                  _safe_int(df_kpi, "qtd_documentos"),
            "qtd_devolucoes":                  _safe_int(df_kpi, "qtd_devolucoes"),
            "clientes_ativos":                 _safe_int(df_kpi, "clientes_ativos"),
            "ticket_medio":                    _safe_float(df_kpi, "ticket_medio"),
            "margem_bruta":                    margem_bruta,
            "pct_meta":                        pct,
            "meta_mensal":                     meta,
            "top_vendedores":                  df_vend.to_dict("records"),
            "faturamento_diario":              df_diario.to_dict("records"),
            "marcas_mes":                      df_marcas.to_dict("records"),
            "marcas_por_vendedor":             df_marcas_vend.to_dict("records"),
            "faturamento_diario_por_vendedor": df_diario_vend.to_dict("records"),
            "faturamento_diario_por_marca":    df_diario_marca.to_dict("records"),
            "ultimo_update":                   datetime.now().strftime("%H:%M:%S"),
        }

    def analisar_filtrado(self, filtros: dict) -> dict:
        parts  = [f"v.DtVnd >= {_MES_INI}", f"v.DtVnd < {_MES_FIM}",
                  "d.Cancelado = ''", "d.Fat = 1"]
        params: list = []

        if filtros.get("vendedor"):
            parts.append("v.Vendedor LIKE ?")
            params.append(f"%{filtros['vendedor'][:100]}%")
        if filtros.get("marca"):
            parts.append("EXISTS (SELECT 1 FROM Blue.dbo.vmVndItemDoc ii WITH (NOLOCK)"
                         " WHERE ii.NrDoc=v.NrDoc AND ii.NSUDoc=v.NSUDoc AND ii.DescrMarca LIKE ?)")
            params.append(f"%{filtros['marca'][:100]}%")

        where_v = " AND ".join(parts)

        df_kpi = db.query(f"""
            SELECT
                SUM(CASE WHEN v.CustoRepTotal >= 0 THEN v.ValVndTotal ELSE 0 END) AS venda_bruta,
                SUM(CASE WHEN v.CustoRepTotal < 0  THEN v.ValVndTotal ELSE 0 END) AS devolucao,
                COUNT(DISTINCT CASE WHEN v.CustoRepTotal >= 0 THEN v.NrDoc END)   AS qtd_documentos,
                COUNT(DISTINCT CASE WHEN v.CustoRepTotal < 0  THEN v.NrDoc END)   AS qtd_devolucoes,
                COUNT(DISTINCT v.CodCli)                                           AS clientes_ativos,
                AVG(CASE WHEN v.CustoRepTotal >= 0 THEN v.ValVndTotal END)        AS ticket_medio
            FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
            INNER JOIN Blue.dbo.vwVndDoc d WITH (NOLOCK) ON v.NrDoc = d.NrDoc AND v.NSUDoc = d.NSUDoc
            WHERE {where_v} {_EXCLUIR_PLANO}
        """, params if params else None)

        marca_params: list = []
        marca_parts = [f"i.DtVnd >= {_MES_INI}", f"i.DtVnd < {_MES_FIM}",
                       "i.Fat = 1", "i.DescrMarca IS NOT NULL", "i.CustoRepTotItem >= 0"]
        if filtros.get("marca"):
            marca_parts.append("i.DescrMarca LIKE ?")
            marca_params.append(f"%{filtros['marca'][:100]}%")
        if filtros.get("vendedor"):
            marca_parts.append(
                "EXISTS (SELECT 1 FROM Blue.dbo.vmVndDoc vv WITH (NOLOCK)"
                " WHERE vv.NrDoc=i.NrDoc AND vv.NSUDoc=i.NSUDoc AND vv.Vendedor LIKE ?)"
            )
            marca_params.append(f"%{filtros['vendedor'][:100]}%")

        df_marcas = db.query(f"""
            SELECT TOP 8 i.DescrMarca,
                SUM(i.PrecoVndTotItem) AS faturamento,
                SUM(i.PrecoVndTotItem) - SUM(i.CustoRepTotItem) AS margem_bruta,
                SUM(i.QtdItem) AS quantidade
            FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
            WHERE {" AND ".join(marca_parts)}
            GROUP BY i.DescrMarca ORDER BY faturamento DESC
        """, marca_params if marca_params else None)

        df_vend = db.query(f"""
            SELECT TOP 10 v.Vendedor, v.CodVend,
                SUM(v.ValVndTotal) AS total_venda,
                COUNT(DISTINCT v.NrDoc) AS qtd_pedidos,
                AVG(v.ValVndTotal) AS ticket_medio
            FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
            INNER JOIN Blue.dbo.vwVndDoc d WITH (NOLOCK) ON v.NrDoc = d.NrDoc AND v.NSUDoc = d.NSUDoc
            WHERE {where_v} {_EXCLUIR_PLANO}
            GROUP BY v.Vendedor, v.CodVend ORDER BY total_venda DESC
        """, params if params else None)

        # Faturamento diário — filtrado por marca (item level) e/ou vendedor (doc level)
        # Subquery com ORDER BY DESC garante os 30 dias mais recentes (TOP semântico correto)
        if filtros.get("marca"):
            diario_parts:  list = ["i.DtVnd >= DATEADD(day, -30, GETDATE())",
                                   "d.Cancelado = ''", "i.Fat = 1",
                                   "i.CustoRepTotItem >= 0",
                                   f"vv.CodPlanoVnd NOT IN ('{_pl}')"]
            diario_params: list = []
            diario_parts.append("i.DescrMarca LIKE ?")
            diario_params.append(f"%{filtros['marca'][:100]}%")
            if filtros.get("vendedor"):
                diario_parts.append("vv.Vendedor LIKE ?")
                diario_params.append(f"%{filtros['vendedor'][:100]}%")
            df_diario = db.query(f"""
                SELECT dia, faturamento FROM (
                    SELECT TOP 30 CONVERT(date, i.DtVnd) AS dia,
                           SUM(i.PrecoVndTotItem) AS faturamento
                    FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
                    INNER JOIN Blue.dbo.vwVndDoc d  WITH (NOLOCK) ON i.NrDoc=d.NrDoc  AND i.NSUDoc=d.NSUDoc
                    INNER JOIN Blue.dbo.vmVndDoc vv WITH (NOLOCK) ON i.NrDoc=vv.NrDoc AND i.NSUDoc=vv.NSUDoc
                    WHERE {" AND ".join(diario_parts)}
                    GROUP BY CONVERT(date, i.DtVnd) ORDER BY dia DESC
                ) _sub ORDER BY dia
            """, diario_params)
        else:
            df_diario = db.query(f"""
                SELECT dia, faturamento FROM (
                    SELECT TOP 30 CONVERT(date, v.DtVnd) AS dia, SUM(v.ValVndTotal) AS faturamento
                    FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
                    INNER JOIN Blue.dbo.vwVndDoc d WITH (NOLOCK) ON v.NrDoc=d.NrDoc AND v.NSUDoc=d.NSUDoc
                    WHERE v.DtVnd >= DATEADD(day, -30, GETDATE()) AND d.Cancelado = '' AND d.Fat = 1
                      {_EXCLUIR_PLANO} {("AND v.Vendedor LIKE ?" if filtros.get('vendedor') else '')}
                    GROUP BY CONVERT(date, v.DtVnd) ORDER BY dia DESC
                ) _sub ORDER BY dia
            """, ([f"%{filtros['vendedor'][:100]}%"] if filtros.get("vendedor") else None))

        venda_bruta = _safe_float(df_kpi, "venda_bruta")
        devolucao   = _safe_float(df_kpi, "devolucao")
        venda_liq   = venda_bruta + devolucao
        meta        = ALERTAS.get("meta_faturamento_mensal", 400000)
        pct         = round(venda_liq / meta * 100, 1) if meta else 0

        return {
            "faturamento_atual":  venda_liq,
            "venda_bruta":        venda_bruta,
            "devolucao":          devolucao,
            "venda_liquida":      venda_liq,
            "qtd_documentos":     _safe_int(df_kpi, "qtd_documentos"),
            "qtd_devolucoes":     _safe_int(df_kpi, "qtd_devolucoes"),
            "clientes_ativos":    _safe_int(df_kpi, "clientes_ativos"),
            "ticket_medio":       _safe_float(df_kpi, "ticket_medio"),
            "pct_meta":           pct,
            "meta_mensal":        meta,
            "top_vendedores":     df_vend.to_dict("records"),
            "faturamento_diario": df_diario.to_dict("records"),
            "marcas_mes":         df_marcas.to_dict("records"),
            "ultimo_update":      datetime.now().strftime("%H:%M:%S"),
        }


# ──────────────────────────────────────────────────────────────────
#  BOT VENDAS  — análise por marca, grupo, vendedor e devoluções
# ──────────────────────────────────────────────────────────────────
class BotVendas(BaseBot):
    def __init__(self):
        super().__init__("vendas")

    def analisar(self, filtro_data: str = "", planos_filter: list = None) -> dict:
        """filtro_data: fragmento SQL para WHERE de data. Vazio = mês atual.
        planos_filter: lista de CodPlanoVnd para filtrar (None = todos)."""
        if not filtro_data:
            filtro_data = (
                f"i.DtVnd >= {_MES_INI}"
                f" AND i.DtVnd < {_MES_FIM}"
            )
        filtro_v = filtro_data.replace("i.DtVnd", "v.DtVnd")
        filtro_d = filtro_data.replace("i.DtVnd", "dev.DtVnd")
        if planos_filter:
            _pl = ",".join(str(int(p)) for p in planos_filter)
            filtro_plano_v = f"AND v.CodPlanoVnd IN ({_pl})"
            filtro_plano_i = (
                f"AND EXISTS (SELECT 1 FROM Blue.dbo.vmVndDoc vv"
                f" WHERE vv.NrDoc = i.NrDoc AND vv.NSUDoc = i.NSUDoc"
                f" AND vv.CodPlanoVnd IN ({_pl}))"
            )
        else:
            filtro_plano_v = ""
            filtro_plano_i = ""

        df_kpi = db.query(f"""
            SELECT
                SUM(CASE WHEN v.CustoRepTotal >= 0 THEN v.ValVndTotal ELSE 0 END) AS venda_bruta,
                SUM(CASE WHEN v.CustoRepTotal < 0  THEN v.ValVndTotal ELSE 0 END) AS devolucao,
                COUNT(DISTINCT CASE WHEN v.CustoRepTotal >= 0 THEN v.NrDoc END)   AS qtd_vendas,
                COUNT(DISTINCT CASE WHEN v.CustoRepTotal < 0  THEN v.NrDoc END)   AS qtd_devolucoes,
                AVG(CASE WHEN v.CustoRepTotal >= 0 THEN v.ValVndTotal END)        AS ticket_medio,
                COUNT(DISTINCT v.CodCli)                                           AS clientes_ativos
            FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
            INNER JOIN Blue.dbo.vwVndDoc d WITH (NOLOCK) ON v.NrDoc = d.NrDoc AND v.NSUDoc = d.NSUDoc
            WHERE d.Cancelado = '' AND d.Fat = 1
              AND {filtro_v}
              {filtro_plano_v}
              {_EXCLUIR_PLANO}
        """)

        df_marca = db.query(f"""
            SELECT TOP 20
                i.DescrMarca,
                SUM(CASE WHEN i.CustoRepTotItem >= 0 THEN i.PrecoVndTotItem ELSE 0 END) AS faturamento,
                SUM(CASE WHEN i.CustoRepTotItem <  0 THEN i.PrecoVndTotItem ELSE 0 END) AS devolucao,
                SUM(CASE WHEN i.CustoRepTotItem >= 0 THEN i.PrecoVndTotItem - i.CustoRepTotItem ELSE 0 END) AS margem_bruta,
                SUM(CASE WHEN i.CustoRepTotItem >= 0 THEN i.QtdItem ELSE 0 END)         AS quantidade,
                COUNT(DISTINCT CASE WHEN i.CustoRepTotItem >= 0 THEN i.NrDoc END)       AS qtd_documentos,
                COUNT(DISTINCT CASE WHEN i.CustoRepTotItem <  0 THEN i.NrDoc END)       AS qtd_devolucoes
            FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
            INNER JOIN Blue.dbo.vwVndDoc d WITH (NOLOCK) ON i.NrDoc = d.NrDoc AND i.NSUDoc = d.NSUDoc
            WHERE d.Cancelado = '' AND i.Fat = 1
              AND {filtro_data}
              {filtro_plano_i}
              AND i.DescrMarca IS NOT NULL
            GROUP BY i.DescrMarca
            ORDER BY faturamento DESC
        """)

        df_grupo = db.query(f"""
            SELECT TOP 20
                i.CodGrpItem,
                i.DescrGrpItem,
                SUM(i.PrecoVndTotItem) AS faturamento,
                SUM(i.QtdItem)         AS quantidade
            FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
            INNER JOIN Blue.dbo.vwVndDoc d WITH (NOLOCK) ON i.NrDoc = d.NrDoc AND i.NSUDoc = d.NSUDoc
            WHERE d.Cancelado = '' AND i.Fat = 1
              AND {filtro_data}
              {filtro_plano_i}
            GROUP BY i.CodGrpItem, i.DescrGrpItem
            ORDER BY faturamento DESC
        """)

        df_itens_marca = db.query(f"""
            SELECT TOP 1000
                i.DescrMarca,
                i.DescrItem,
                SUM(i.PrecoVndTotItem) AS faturamento,
                SUM(i.QtdItem)         AS quantidade
            FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
            INNER JOIN Blue.dbo.vwVndDoc d WITH (NOLOCK)
                ON i.NrDoc = d.NrDoc AND i.NSUDoc = d.NSUDoc
            WHERE d.Cancelado = '' AND i.Fat = 1
              AND {filtro_data}
              {filtro_plano_i}
              AND i.DescrMarca IS NOT NULL
              AND i.DescrItem  IS NOT NULL
              AND i.CustoRepTotItem >= 0
            GROUP BY i.DescrMarca, i.DescrItem
            ORDER BY faturamento DESC
        """)
        _tim: dict = {}
        if not df_itens_marca.empty:
            for _mrc, _g in df_itens_marca.groupby("DescrMarca"):
                _tim[_mrc] = _g.nlargest(8, "faturamento")[
                    ["DescrItem", "faturamento", "quantidade"]
                ].to_dict("records")

        df_vend = db.query(f"""
            SELECT TOP 10
                v.Vendedor,
                v.CodVend,
                SUM(CASE WHEN v.CustoRepTotal >= 0 THEN v.ValVndTotal ELSE 0 END) AS total_venda,
                SUM(CASE WHEN v.CustoRepTotal <  0 THEN v.ValVndTotal ELSE 0 END) AS devolucao,
                COUNT(DISTINCT CASE WHEN v.CustoRepTotal >= 0 THEN v.NrDoc END)   AS qtd_pedidos,
                COUNT(DISTINCT CASE WHEN v.CustoRepTotal <  0 THEN v.NrDoc END)   AS qtd_devolucoes,
                SUM(CASE WHEN v.CustoRepTotal >= 0 THEN v.ValVndTotal ELSE 0 END)
                    / NULLIF(COUNT(DISTINCT CASE WHEN v.CustoRepTotal >= 0 THEN v.NrDoc END), 0) AS ticket_medio,
                SUM(CASE WHEN v.CustoRepTotal >= 0 THEN v.ValVndTotal - v.CustoRepTotal ELSE 0 END) AS margem_bruta
            FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
            INNER JOIN Blue.dbo.vwVndDoc d WITH (NOLOCK) ON v.NrDoc = d.NrDoc AND v.NSUDoc = d.NSUDoc
            WHERE d.Cancelado = '' AND d.Fat = 1
              AND {filtro_v}
              {filtro_plano_v}
              {_EXCLUIR_PLANO}
            GROUP BY v.Vendedor, v.CodVend
            ORDER BY total_venda DESC
        """)

        # marcas por vendedor — mesmo approach do BotDashboard (garante paridade de nomes)
        _cod_vend_map_v: dict = {}
        if not df_vend.empty and 'CodVend' in df_vend.columns:
            _cod_vend_map_v = dict(zip(df_vend['CodVend'].astype(str), df_vend['Vendedor']))
        if _cod_vend_map_v:
            _in_cv = ','.join(f"'{c}'" for c in _cod_vend_map_v)
            _raw_mv = db.new_conn_query(f"""
                SELECT TOP 500
                    i.CodVend,
                    i.DescrMarca,
                    SUM(CASE WHEN i.CustoRepTotItem >= 0 THEN i.PrecoVndTotItem ELSE 0 END) AS faturamento,
                    SUM(CASE WHEN i.CustoRepTotItem >= 0 THEN i.QtdItem ELSE 0 END)         AS quantidade
                FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
                WHERE i.DtVnd >= {_MES_INI}
                  AND i.DtVnd <  {_MES_FIM}
                  AND i.Fat = 1
                  AND i.DescrMarca IS NOT NULL
                  AND i.CodVend IN ({_in_cv})
                GROUP BY i.CodVend, i.DescrMarca
                ORDER BY i.CodVend, faturamento DESC
            """)
            if not _raw_mv.empty:
                _raw_mv['Vendedor'] = _raw_mv['CodVend'].astype(str).map(_cod_vend_map_v)
                df_marcas_vend = _raw_mv.dropna(subset=['Vendedor'])[
                    ['Vendedor', 'DescrMarca', 'faturamento', 'quantidade']
                ].copy()
            else:
                df_marcas_vend = pd.DataFrame()
            _raw_iv = db.new_conn_query(f"""
                SELECT TOP 1000
                    i.CodVend,
                    i.DescrItem,
                    SUM(CASE WHEN i.CustoRepTotItem >= 0 THEN i.PrecoVndTotItem ELSE 0 END) AS faturamento,
                    SUM(CASE WHEN i.CustoRepTotItem >= 0 THEN i.QtdItem ELSE 0 END)         AS quantidade
                FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
                WHERE i.DtVnd >= {_MES_INI}
                  AND i.DtVnd <  {_MES_FIM}
                  AND i.Fat = 1
                  AND i.DescrItem IS NOT NULL
                  AND i.CodVend IN ({_in_cv})
                GROUP BY i.CodVend, i.DescrItem
                ORDER BY faturamento DESC
            """)
            _tiv: dict = {}
            if not _raw_iv.empty:
                _raw_iv['Vendedor'] = _raw_iv['CodVend'].astype(str).map(_cod_vend_map_v)
                _raw_iv = _raw_iv.dropna(subset=['Vendedor'])
                for _vnd, _g in _raw_iv.groupby('Vendedor'):
                    _tiv[_vnd] = _g.nlargest(8, 'faturamento')[
                        ['DescrItem', 'faturamento', 'quantidade']
                    ].to_dict('records')
        else:
            df_marcas_vend = pd.DataFrame()
            _tiv = {}

        df_hoje = db.query(f"""
            SELECT TOP 50
                v.Vendedor,
                SUM(CASE WHEN v.CustoRepTotal >= 0 THEN v.ValVndTotal ELSE 0 END) AS venda_hoje
            FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
            INNER JOIN Blue.dbo.vwVndDoc d WITH (NOLOCK) ON v.NrDoc = d.NrDoc AND v.NSUDoc = d.NSUDoc
            WHERE d.Cancelado = ''
              AND d.Fat = 1
              AND v.DtVnd >= CAST(GETDATE() AS DATE)
              AND v.DtVnd <  DATEADD(day, 1, CAST(GETDATE() AS DATE))
              {_EXCLUIR_PLANO}
            GROUP BY v.Vendedor
            ORDER BY venda_hoje DESC
        """)

        margem = sum(float(r.get("margem_bruta", 0) or 0)
                     for r in df_marca.to_dict("records"))

        venda_bruta = _safe_float(df_kpi, "venda_bruta")
        devolucao   = _safe_float(df_kpi, "devolucao")
        vend_records = df_vend.to_dict("records")
        return {
            "faturamento_atual":     venda_bruta,
            "qtd_documentos":        _safe_int(df_kpi, "qtd_vendas"),
            "ticket_medio":          _safe_float(df_kpi, "ticket_medio"),
            "clientes_ativos":       _safe_int(df_kpi, "clientes_ativos"),
            "devolucao":             devolucao,
            "qtd_devolucoes":        _safe_int(df_kpi, "qtd_devolucoes"),
            "margem_total":          margem,
            "top_vendedores":        vend_records,
            "marcas_mes":            df_marca.to_dict("records"),
            "ticket_medio_vendedor": vend_records,
            "marcas_por_vendedor":   df_marcas_vend.to_dict("records"),
            "por_grupo":             df_grupo.to_dict("records"),
            "top_itens_por_marca":   _tim,
            "top_itens_por_vendedor": _tiv,
            "venda_hoje_vendedor":   df_hoje.to_dict("records"),
            "ultimo_update":         datetime.now().strftime("%H:%M:%S"),
        }

    def analisar_filtrado(self, filtros: dict) -> dict:
        parts  = [f"v.DtVnd >= {_MES_INI}", f"v.DtVnd < {_MES_FIM}",
                  "d.Cancelado = ''", "d.Fat = 1"]
        params: list = []

        if filtros.get("vendedor"):
            parts.append("v.Vendedor LIKE ?")
            params.append(f"%{filtros['vendedor'][:100]}%")
        if filtros.get("marca"):
            parts.append("EXISTS (SELECT 1 FROM Blue.dbo.vmVndItemDoc ii WITH (NOLOCK)"
                         " WHERE ii.NrDoc=v.NrDoc AND ii.NSUDoc=v.NSUDoc AND ii.DescrMarca LIKE ?)")
            params.append(f"%{filtros['marca'][:100]}%")

        where_v = " AND ".join(parts)

        df_kpi = db.query(f"""
            SELECT
                SUM(CASE WHEN v.CustoRepTotal >= 0 THEN v.ValVndTotal ELSE 0 END) AS venda_bruta,
                SUM(CASE WHEN v.CustoRepTotal < 0  THEN v.ValVndTotal ELSE 0 END) AS devolucao,
                COUNT(DISTINCT CASE WHEN v.CustoRepTotal >= 0 THEN v.NrDoc END)   AS qtd_vendas,
                COUNT(DISTINCT CASE WHEN v.CustoRepTotal < 0  THEN v.NrDoc END)   AS qtd_devolucoes,
                AVG(CASE WHEN v.CustoRepTotal >= 0 THEN v.ValVndTotal END)        AS ticket_medio,
                COUNT(DISTINCT v.CodCli)                                           AS clientes_ativos
            FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
            INNER JOIN Blue.dbo.vwVndDoc d WITH (NOLOCK) ON v.NrDoc = d.NrDoc AND v.NSUDoc = d.NSUDoc
            WHERE {where_v} {_EXCLUIR_PLANO}
        """, params if params else None)

        i_parts: list = [f"i.DtVnd >= {_MES_INI}", f"i.DtVnd < {_MES_FIM}",
                         "d.Cancelado = ''", "i.Fat = 1"]
        i_params: list = []
        if filtros.get("vendedor"):
            i_parts.append("EXISTS (SELECT 1 FROM Blue.dbo.vmVndDoc vv WITH (NOLOCK)"
                           " WHERE vv.NrDoc=i.NrDoc AND vv.NSUDoc=i.NSUDoc AND vv.Vendedor LIKE ?)")
            i_params.append(f"%{filtros['vendedor'][:100]}%")
        if filtros.get("marca"):
            i_parts.append("i.DescrMarca LIKE ?")
            i_params.append(f"%{filtros['marca'][:100]}%")

        df_marca = db.query(f"""
            SELECT TOP 20 i.CodMarca, i.DescrMarca,
                SUM(i.PrecoVndTotItem) AS faturamento,
                SUM(i.QtdItem) AS quantidade,
                SUM(i.CustoRepTotItem) AS custo_total,
                SUM(i.PrecoVndTotItem) - SUM(i.CustoRepTotItem) AS margem_bruta
            FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
            INNER JOIN Blue.dbo.vwVndDoc d WITH (NOLOCK) ON i.NrDoc = d.NrDoc AND i.NSUDoc = d.NSUDoc
            WHERE {" AND ".join(i_parts)}
            GROUP BY i.CodMarca, i.DescrMarca ORDER BY faturamento DESC
        """, i_params if i_params else None)

        df_vend = db.query(f"""
            SELECT TOP 10 v.Vendedor, v.CodVend,
                SUM(v.ValVndTotal) AS total_venda,
                COUNT(DISTINCT v.NrDoc) AS qtd_pedidos,
                AVG(v.ValVndTotal) AS ticket_medio,
                SUM(v.CustoRepTotal) AS custo_total
            FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
            INNER JOIN Blue.dbo.vwVndDoc d WITH (NOLOCK) ON v.NrDoc = d.NrDoc AND v.NSUDoc = d.NSUDoc
            WHERE {where_v} {_EXCLUIR_PLANO}
            GROUP BY v.Vendedor, v.CodVend ORDER BY total_venda DESC
        """, params if params else None)

        margem      = sum(float(r.get("margem_bruta", 0) or 0) for r in df_marca.to_dict("records"))
        venda_bruta = _safe_float(df_kpi, "venda_bruta")
        devolucao   = _safe_float(df_kpi, "devolucao")
        vend_records = df_vend.to_dict("records")

        hoje_parts: list = [
            "d.Cancelado = ''",
            "d.Fat = 1",
            "v.DtVnd >= CAST(GETDATE() AS DATE)",
            "v.DtVnd <  DATEADD(day, 1, CAST(GETDATE() AS DATE))",
        ]
        hoje_params: list = []
        if filtros.get("vendedor"):
            hoje_parts.append("v.Vendedor LIKE ?")
            hoje_params.append(f"%{filtros['vendedor'][:100]}%")
        where_hoje = " AND ".join(hoje_parts)

        df_hoje = db.query(f"""
            SELECT TOP 50
                v.Vendedor,
                SUM(CASE WHEN v.CustoRepTotal >= 0 THEN v.ValVndTotal ELSE 0 END) AS venda_hoje
            FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
            INNER JOIN Blue.dbo.vwVndDoc d WITH (NOLOCK) ON v.NrDoc = d.NrDoc AND v.NSUDoc = d.NSUDoc
            WHERE {where_hoje}
              {_EXCLUIR_PLANO}
            GROUP BY v.Vendedor
            ORDER BY venda_hoje DESC
        """, hoje_params if hoje_params else None)

        return {
            "faturamento_atual":     venda_bruta,
            "qtd_documentos":        _safe_int(df_kpi, "qtd_vendas"),
            "ticket_medio":          _safe_float(df_kpi, "ticket_medio"),
            "clientes_ativos":       _safe_int(df_kpi, "clientes_ativos"),
            "devolucao":             devolucao,
            "qtd_devolucoes":        _safe_int(df_kpi, "qtd_devolucoes"),
            "margem_total":          margem,
            "top_vendedores":        vend_records,
            "marcas_mes":            df_marca.to_dict("records"),
            "ticket_medio_vendedor": vend_records,
            "por_grupo":             [],
            "venda_hoje_vendedor":   df_hoje.to_dict("records"),
            "ultimo_update":         datetime.now().strftime("%H:%M:%S"),
        }


# ──────────────────────────────────────────────────────────────────
#  BOT ESTOQUE
# ──────────────────────────────────────────────────────────────────
class BotEstoque(BaseBot):
    """Detecta colunas em runtime via SELECT TOP 0 * para tolerar variações de schema.
    Views usadas (somente SELECT): vmAnaliseEstqItem, vmAnaliseEstqVnd,
    vmItemMovEstq, vmSugestaoTransfEstq, vwEstqTempOs, vwFuncRespEstq."""

    _VIEWS = {
        "item": "Blue.dbo.vmAnaliseEstqItem",
        "vnd":  "Blue.dbo.vmAnaliseEstqVnd",
        "mov":  "Blue.dbo.vmItemMovEstq",
        "sug":  "Blue.dbo.vmSugestaoTransfEstq",
        "os":   "Blue.dbo.vwEstqTempOs",
        "func": "Blue.dbo.vwFuncRespEstq",
    }

    def __init__(self):
        super().__init__("estoque")
        self._s: dict[str, list] = {}
        self._loaded = False

    def _load_schemas(self):
        if self._loaded:
            return
        for tag, view in self._VIEWS.items():
            df = db.query(f"SELECT TOP 0 * FROM {view} WITH (NOLOCK)")
            if len(df.columns) > 0:
                self._s[tag] = list(df.columns)
            else:
                # TOP 0 pode falhar em views com erros de compilação — tenta TOP 1 como fallback
                df1 = db.query(f"SELECT TOP 1 * FROM {view} WITH (NOLOCK)")
                self._s[tag] = list(df1.columns) if len(df1.columns) > 0 else []
            logger.info("[Estq] %-4s %-32s → %s",
                        tag, view.split(".")[-1],
                        self._s[tag] if self._s[tag] else "(INACESSÍVEL)")
        self._loaded = True

    def _c(self, tag: str, *cands: str) -> str:
        """Retorna o primeiro candidato encontrado no schema (insensível a maiúsculas)."""
        lc = {c.lower(): c for c in self._s.get(tag, [])}
        for cand in cands:
            if cand.lower() in lc:
                return lc[cand.lower()]
        return ""

    def _best(self, *tags: str) -> tuple:
        """(view_path, tag) para o primeiro tag com schema disponível."""
        for t in tags:
            if self._s.get(t):
                return self._VIEWS[t], t
        return self._VIEWS[tags[0]], tags[0]

    def analisar_rapido(self) -> dict:
        """Apenas queries rápidas: KPIs + críticos + marcas. run() chama isso antes do analisar() completo."""
        self._load_schemas()
        ev, et = self._best("item", "vnd")

        col_cod  = self._c(et, "CodItem",       "Codigo",         "CodigoItem",      "CodProduto")
        col_dsc  = self._c(et, "DescrItem",     "Descricao",      "NomeItem",        "DescrProduto",
                                "NomeProduto",   "DescrProd")
        col_mrc  = self._c(et, "DescrMarca",    "Marca",          "DescrMarcaItem",  "NomeMarca",
                                "DescrMarcaProd","MarcaItem")
        col_qtd  = self._c(et, "QtdEstq",       "SaldoEstq",      "QtdSaldo",        "Qtd",
                                "QtdEstoque",    "QtdTotEstq",     "QtdTotalEstq",    "SaldoQtd",
                                "QtdSaldoEstq",  "QuantidadeEstq", "Quantidade")
        col_disp = self._c(et, "QtdEstqDisp",   "SaldoDisp",      "QtdDisp",         "QtdSaldoDisp",
                                "QtdEstqDisponiveis","QtdDisponivel","QtdEstoqueDisp", "QtdSaldoDisponivel",
                                "SaldoDisponivel","QtdDispEstq")
        col_vlr  = self._c(et, "VlrEstq",       "ValEstq",        "VlrTotEstq",      "SaldoVlr",
                                "ValorEstoque",  "VlrTotalEstq",   "ValTotEstq",      "VlrTotal",
                                "ValorTotal",    "TotVlrEstq",     "VlrEstoque",      "VlrSaldoEstq",
                                "ValSaldoEstq",  "VlrTotItem",     "ValTotItem")
        col_cst  = self._c(et, "CustoRepProd",  "CustoRep",       "ValCustoRep",     "CustoReposicao",
                                "CustoRepItem",  "VlrCustoRep")
        col_forn = self._c(et, "FornecUltCmp",  "FornecUltima",   "CodFornecUlt",    "Fornecedor",
                                "NomeFornec",    "FornecedorUlt")
        col_pend = self._c(et, "QtdPendPedCmp", "PendPed",        "QtdPedCmp",       "QtdPendCmp",
                                "QtdPendentePed","QtdPendCompra")
        col_dtv  = (self._c(et, "DtUltVnd",     "DtUltimaVenda",  "DtVnd",           "UltDtVnd",
                                "DtUltVenda",    "DataUltVnd",     "DataUltimaVenda", "DtUltimaVnd")
                    or self._c(self._best("vnd", "item")[1],
                                "DtUltVnd",     "DtUltimaVenda",  "DtVnd",           "UltDtVnd",
                                "DtUltVenda",    "DataUltVnd",     "DataUltimaVenda", "DtUltimaVnd"))

        def _sum(col, alias):
            return f"SUM(ISNULL({col},0)) AS {alias}" if col else f"0 AS {alias}"

        wh_q    = f"WHERE ISNULL({col_qtd},0)>0" if col_qtd else ""
        zero_ex = (f"SUM(CASE WHEN ISNULL({col_disp},0)<=0 THEN 1 ELSE 0 END) AS itens_zerados"
                   if col_disp else "0 AS itens_zerados")
        giro_ex = (f"SUM(CASE WHEN ISNULL(DATEDIFF(day,{col_dtv},GETDATE()),9999)"
                   f">{DIAS_CRITICO} THEN 1 ELSE 0 END) AS itens_sem_giro"
                   if col_dtv else "0 AS itens_sem_giro")

        df_resumo = db.query(f"""
            SELECT COUNT(*) AS total_itens,
                   {_sum(col_vlr, 'valor_total_estoque')},
                   {_sum(col_qtd, 'qtd_total')},
                   {_sum(col_disp,'qtd_disponivel')},
                   {zero_ex}, {giro_ex}
            FROM {ev} WITH (NOLOCK) {wh_q}
        """)

        _cp = list(filter(None, [
            f"e.{col_cod}  AS CodItem"       if col_cod  else None,
            f"e.{col_dsc}  AS DescrItem"     if col_dsc  else None,
            f"e.{col_mrc}  AS DescrMarca"    if col_mrc  else None,
            f"e.{col_qtd}  AS QtdEstq"       if col_qtd  else None,
            f"e.{col_disp} AS QtdEstqDisp"   if col_disp else None,
            (f"CASE WHEN ISNULL(DATEDIFF(day,e.{col_dtv},GETDATE()),9999)>120 THEN 120"
             f" ELSE ISNULL(DATEDIFF(day,e.{col_dtv},GETDATE()),0) END AS DiasSemVnd"
             if col_dtv else None),
            f"e.{col_dtv}  AS DtUltVnd"      if col_dtv  else None,
            f"e.{col_cst}  AS CustoRepProd"  if col_cst  else None,
            f"e.{col_vlr}  AS VlrEstq"       if col_vlr  else None,
            f"e.{col_pend} AS QtdPendPedCmp" if col_pend else None,
            f"e.{col_forn} AS FornecUltCmp"  if col_forn else None,
        ]))
        _wd = (f"ISNULL(DATEDIFF(day,e.{col_dtv},GETDATE()),9999)>{DIAS_CRITICO}"
               if col_dtv else "")
        _wz = f"e.{col_disp}<=0" if col_disp else ""
        _od = f"ISNULL(DATEDIFF(day,e.{col_dtv},GETDATE()),9999) DESC," if col_dtv else ""
        _ov = f"e.{col_vlr} DESC" if col_vlr else "1"
        _where_crit = " OR ".join(filter(None, [_wd, _wz])) or "1=1"
        df_criticos = db.query(f"""
            SELECT TOP {MAX} {", ".join(_cp) if _cp else "e.*"}
            FROM {ev} e WITH (NOLOCK) WHERE {_where_crit}
            ORDER BY {_od} {_ov}
        """)

        df_marca = db.query(f"""
            SELECT TOP 30 e.{col_mrc} AS DescrMarca,
                COUNT(*) AS qtd_itens,
                {_sum(col_vlr, 'valor_estoque')},
                {_sum(col_qtd, 'quantidade_total')}
            FROM {ev} e WITH (NOLOCK) GROUP BY e.{col_mrc} ORDER BY valor_estoque DESC
        """) if col_mrc else pd.DataFrame()

        def _recs(df):
            return df.to_dict("records") if not df.empty else []

        # Deriva zerados_lista de df_criticos — sem query adicional ao banco
        _zer_keep = [c for c in ["CodItem", "DescrItem", "DescrMarca", "VlrEstq", "DtUltVnd"]
                     if c in df_criticos.columns]
        if not df_criticos.empty and "QtdEstqDisp" in df_criticos.columns:
            _df_zer = df_criticos[df_criticos["QtdEstqDisp"].fillna(0) <= 0].copy()
            if "DtUltVnd" in _df_zer.columns:
                _df_zer = _df_zer.sort_values("DtUltVnd", na_position="last")
            _zerados_lista = _df_zer[_zer_keep].to_dict("records") if not _df_zer.empty else []
        else:
            _zerados_lista = []

        # Deriva sem_giro_lista: itens com DiasSemVnd >= DIAS_CRITICO, mais parados primeiro
        _sg_keep = [c for c in ["CodItem", "DescrItem", "DescrMarca", "QtdEstq", "VlrEstq", "DtUltVnd"]
                    if c in df_criticos.columns]
        if not df_criticos.empty and "DiasSemVnd" in df_criticos.columns:
            _df_sg = df_criticos[df_criticos["DiasSemVnd"] >= DIAS_CRITICO].copy()
            if "DtUltVnd" in _df_sg.columns:
                _hoje = pd.Timestamp.now()
                _df_sg["DiasSemVndReal"] = _df_sg["DtUltVnd"].apply(
                    lambda d: int((_hoje - pd.Timestamp(d)).days) if pd.notna(d) else None
                )
                _sg_keep.append("DiasSemVndReal")
                _df_sg = _df_sg.sort_values("DiasSemVndReal", ascending=False, na_position="last")
            else:
                _df_sg = _df_sg.sort_values("DiasSemVnd", ascending=False, na_position="last")
            _sem_giro_lista = _df_sg[[c for c in _sg_keep if c in _df_sg.columns]].to_dict("records") if not _df_sg.empty else []
        else:
            _sem_giro_lista = []

        return {
            "total_itens":         _safe_int(df_resumo,  "total_itens"),
            "valor_total_estoque": _safe_float(df_resumo, "valor_total_estoque"),
            "qtd_disponivel":      _safe_int(df_resumo,  "qtd_disponivel"),
            "itens_zerados":       _safe_int(df_resumo,  "itens_zerados"),
            "itens_sem_giro":      _safe_int(df_resumo,  "itens_sem_giro"),
            "zerados_lista":       _zerados_lista,
            "sem_giro_lista":      _sem_giro_lista,
            "por_marca":           _recs(df_marca),
            "ultimo_update":       datetime.now().strftime("%H:%M:%S"),
        }

    def analisar(self) -> dict:
        t0 = time.time()
        self._load_schemas()
        ev,  et  = self._best("item", "vnd")
        evv, evt = self._best("vnd",  "item")

        # ── Detecção de colunas (sem DB) ───────────────────────────
        col_cod  = self._c(et,  "CodItem",       "Codigo",         "CodigoItem",      "CodProduto")
        col_dsc  = self._c(et,  "DescrItem",     "Descricao",      "NomeItem",        "DescrProduto",
                                "NomeProduto",   "DescrProd")
        col_mrc  = self._c(et,  "DescrMarca",    "Marca",          "DescrMarcaItem",  "NomeMarca",
                                "DescrMarcaProd","MarcaItem")
        col_qtd  = self._c(et,  "QtdEstq",       "SaldoEstq",      "QtdSaldo",        "Qtd",
                                "QtdEstoque",    "QtdTotEstq",     "QtdTotalEstq",    "SaldoQtd",
                                "QtdSaldoEstq",  "QuantidadeEstq", "Quantidade")
        col_disp = self._c(et,  "QtdEstqDisp",   "SaldoDisp",      "QtdDisp",         "QtdSaldoDisp",
                                "QtdEstqDisponiveis","QtdDisponivel","QtdEstoqueDisp",  "QtdSaldoDisponivel",
                                "SaldoDisponivel","QtdDispEstq")
        col_vlr  = self._c(et,  "VlrEstq",       "ValEstq",        "VlrTotEstq",      "SaldoVlr",
                                "ValorEstoque",  "VlrTotalEstq",   "ValTotEstq",      "VlrTotal",
                                "ValorTotal",    "TotVlrEstq",     "VlrEstoque",      "VlrSaldoEstq",
                                "ValSaldoEstq",  "VlrTotItem",     "ValTotItem")
        col_cst  = self._c(et,  "CustoRepProd",  "CustoRep",       "ValCustoRep",     "CustoReposicao",
                                "CustoRepItem",  "VlrCustoRep")
        col_forn = self._c(et,  "FornecUltCmp",  "FornecUltima",   "CodFornecUlt",    "Fornecedor",
                                "NomeFornec",    "FornecedorUlt")
        col_pend = self._c(et,  "QtdPendPedCmp", "PendPed",        "QtdPedCmp",       "QtdPendCmp",
                                "QtdPendentePed","QtdPendCompra")
        col_dtv  = (self._c(et,  "DtUltVnd",      "DtUltimaVenda",  "DtVnd",           "UltDtVnd",
                                "DtUltVenda",    "DataUltVnd",     "DataUltimaVenda", "DtUltimaVnd")
                    or self._c(evt,"DtUltVnd",   "DtUltimaVenda",  "DtVnd",           "UltDtVnd",
                                "DtUltVenda",    "DataUltVnd",     "DataUltimaVenda", "DtUltimaVnd"))

        logger.info("[Estq] Cols detectadas: ev=%s | cod='%s' qtd='%s' vlr='%s' disp='%s' dtv='%s'",
                    ev.split(".")[-1], col_cod, col_qtd, col_vlr, col_disp, col_dtv)
        if not col_qtd and not col_vlr and not col_disp:
            logger.warning("[Estq] NENHUMA coluna-chave detectada! Colunas brutas de [%s]: %s",
                           et, self._s.get(et, []))

        smov     = self._s.get("mov", [])
        col_mcod = self._c("mov", "CodItem",      "Codigo",      "CodProduto",    "CodigoItem",  "CodItm")
        col_mdsc = self._c("mov", "DescrItem",    "Descricao",  "NomeItem",      "DescrProduto","NomeProduto", "DescrProd")
        col_ment = self._c("mov", "QtdEntrada",   "Entrada",    "Qtd_Entrada",   "QtdEntradas", "TotEntrada",  "EntradaQtd",  "SaldoEntrada", "QtdEnt")
        col_msai = self._c("mov", "QtdSaida",     "Saida",      "Qtd_Saida",     "QtdSaidas",   "TotSaida",    "SaidaQtd",    "SaldoSaida",   "QtdSai", "QtdLiqVendas", "QtdLiq")
        col_mliq = self._c("mov", "QtdLiqVendas", "QtdLiq",     "Liquido",       "QtdLiquido",  "LiqVnd")
        col_mdt  = self._c("mov", "DtMovEstq",    "DtMov",      "Data",          "DtMovimento", "DtMov",       "DataMov")

        # ── Construção das SQL strings (sem DB) ────────────────────
        def _sum(col, alias):
            return f"SUM(ISNULL({col},0)) AS {alias}" if col else f"0 AS {alias}"

        wh_q    = f"WHERE ISNULL({col_qtd},0)>0" if col_qtd else ""
        zero_ex = (f"SUM(CASE WHEN ISNULL({col_disp},0)<=0 THEN 1 ELSE 0 END) AS itens_zerados"
                   if col_disp else "0 AS itens_zerados")
        giro_ex = (f"SUM(CASE WHEN ISNULL(DATEDIFF(day,{col_dtv},GETDATE()),9999)"
                   f">{DIAS_CRITICO} THEN 1 ELSE 0 END) AS itens_sem_giro"
                   if col_dtv else "0 AS itens_sem_giro")
        sql_resumo = f"""
            SELECT COUNT(*) AS total_itens,
                   {_sum(col_vlr, 'valor_total_estoque')},
                   {_sum(col_qtd, 'qtd_total')},
                   {_sum(col_disp,'qtd_disponivel')},
                   {zero_ex}, {giro_ex}
            FROM {ev} WITH (NOLOCK) {wh_q}
        """

        _cp = list(filter(None, [
            f"e.{col_cod}  AS CodItem"       if col_cod  else None,
            f"e.{col_dsc}  AS DescrItem"     if col_dsc  else None,
            f"e.{col_mrc}  AS DescrMarca"    if col_mrc  else None,
            f"e.{col_qtd}  AS QtdEstq"       if col_qtd  else None,
            f"e.{col_disp} AS QtdEstqDisp"   if col_disp else None,
            (f"CASE WHEN ISNULL(DATEDIFF(day,e.{col_dtv},GETDATE()),9999)>120 THEN 120"
             f" ELSE ISNULL(DATEDIFF(day,e.{col_dtv},GETDATE()),0) END AS DiasSemVnd"
             if col_dtv else None),
            f"e.{col_dtv}  AS DtUltVnd"      if col_dtv  else None,
            f"e.{col_cst}  AS CustoRepProd"  if col_cst  else None,
            f"e.{col_vlr}  AS VlrEstq"       if col_vlr  else None,
            f"e.{col_pend} AS QtdPendPedCmp" if col_pend else None,
            f"e.{col_forn} AS FornecUltCmp"  if col_forn else None,
        ]))
        _wd = (f"ISNULL(DATEDIFF(day,e.{col_dtv},GETDATE()),9999)>{DIAS_CRITICO}"
               if col_dtv else "")
        _wz = f"e.{col_disp}<=0" if col_disp else ""
        _od = f"ISNULL(DATEDIFF(day,e.{col_dtv},GETDATE()),9999) DESC," if col_dtv else ""
        _ov = f"e.{col_vlr} DESC" if col_vlr else "1"
        _where_crit = " OR ".join(filter(None, [_wd, _wz])) or "1=1"
        sql_criticos = f"""
            SELECT TOP {MAX} {", ".join(_cp) if _cp else "e.*"}
            FROM {ev} e WITH (NOLOCK) WHERE {_where_crit}
            ORDER BY {_od} {_ov}
        """

        sql_marca = (f"""
            SELECT TOP 30 e.{col_mrc} AS DescrMarca,
                COUNT(*) AS qtd_itens,
                {_sum(col_vlr, 'valor_estoque')},
                {_sum(col_qtd, 'quantidade_total')}
            FROM {ev} e WITH (NOLOCK) GROUP BY e.{col_mrc} ORDER BY valor_estoque DESC
        """ if col_mrc else None)

        _wm = f"m.{col_mdt}>=DATEADD(day,-30,GETDATE())" if col_mdt else "1=1"
        sql_mov = None
        if smov and col_mcod:
            _mp = [f"m.{col_mcod} AS CodItem"]
            if col_mdsc: _mp.append(f"m.{col_mdsc} AS DescrItem")
            _mp.append(f"SUM(m.{col_ment}) AS entradas" if col_ment else "0 AS entradas")
            _mp.append(f"SUM(m.{col_msai}) AS saidas"   if col_msai else "0 AS saidas")
            if col_mliq: _mp.append(f"SUM(m.{col_mliq}) AS vendas_liquidas")
            _grp = f"m.{col_mcod}" + (f", m.{col_mdsc}" if col_mdsc else "")
            sql_mov = f"""
                SELECT TOP 2000 {", ".join(_mp)}
                FROM Blue.dbo.vmItemMovEstq m WITH (NOLOCK) WHERE {_wm}
                GROUP BY {_grp} ORDER BY saidas DESC
            """

        sql_giro_bruto = None
        if col_cod:
            # GROUP BY e.CodItem para colapsar múltiplas linhas por filial (CodEmpr)
            # que vmAnaliseEstqItem retorna uma por (CodEmpr, CodItem).
            _gbp = [f"e.{col_cod} AS CodItem"]
            for _cx, _ax in [(col_dsc, "DescrItem"), (col_mrc, "DescrMarca")]:
                if _cx:
                    _gbp.append(f"MAX(e.{_cx}) AS {_ax}")
            if col_qtd:
                _gbp.append(f"SUM(ISNULL(e.{col_qtd}, 0)) AS QtdEstq")
            if col_dtv:
                _gbp.append(f"MAX(e.{col_dtv}) AS DtUltVnd")
            _gbp += [
                "ISNULL(MAX(v.qtd_vendida_90d), 0) AS qtd_vendida_90d",
                "ISNULL(MAX(v.val_vendido_90d),  0) AS val_vendido_90d",
            ]
            _having_gb = f"HAVING SUM(ISNULL(e.{col_qtd},0)) > 0" if col_qtd else ""
            sql_giro_bruto = f"""
                SELECT TOP 500 {", ".join(_gbp)}
                FROM {ev} e WITH (NOLOCK)
                LEFT JOIN (
                    SELECT i.CodItem,
                           SUM(i.QtdItem)         AS qtd_vendida_90d,
                           SUM(i.PrecoVndTotItem) AS val_vendido_90d
                    FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
                    INNER JOIN Blue.dbo.vwVndDoc d WITH (NOLOCK)
                        ON i.NrDoc = d.NrDoc AND i.NSUDoc = d.NSUDoc
                    WHERE d.Cancelado = '' AND i.Fat = 1
                      AND i.DtVnd >= DATEADD(day, -90, GETDATE())
                    GROUP BY i.CodItem
                ) v ON e.{col_cod} = v.CodItem
                GROUP BY e.{col_cod}
                {_having_gb}
                ORDER BY ISNULL(MAX(v.val_vendido_90d), 0) DESC
            """

        sql_orc_estq = None
        if col_cod:
            _oep = [f"e.{col_cod} AS CodItem"]
            if col_dsc: _oep.append(f"e.{col_dsc} AS DescrItem")
            if col_mrc: _oep.append(f"e.{col_mrc} AS DescrMarca")
            _col_disp_oe = col_disp or col_qtd
            _oep += [
                f"ISNULL(e.{_col_disp_oe},0) AS QtdEstqDisp" if _col_disp_oe else "0 AS QtdEstqDisp",
                "ISNULL(o.qtd_orcada,0) AS qtd_orcada",
                "ISNULL(o.val_orcado, 0) AS val_orcado",
            ]
            sql_orc_estq = f"""
                SELECT TOP 30 {", ".join(_oep)}
                FROM {ev} e WITH (NOLOCK)
                LEFT JOIN (
                    SELECT i.CodItem,
                           SUM(i.QtdItem)         AS qtd_orcada,
                           SUM(i.PrecoVndTotItem) AS val_orcado
                    FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
                    INNER JOIN Blue.dbo.TbOrcPedVnd p WITH (NOLOCK) ON i.NrDoc=p.NrOrcPedVnd
                    WHERE p.OrcPedVnd=1
                      AND i.DtVnd>=DATEADD(day,-30,GETDATE())
                    GROUP BY i.CodItem
                ) o ON e.{col_cod}=o.CodItem
                WHERE ISNULL(o.qtd_orcada,0)>0
                ORDER BY qtd_orcada DESC
            """

        sql_venda_compra = None
        if smov and col_mcod:
            _vcp = [f"m.{col_mcod} AS CodItem"]
            if col_mdsc: _vcp.append(f"m.{col_mdsc} AS DescrItem")
            _vcp.append(f"SUM(m.{col_msai}) AS saidas"   if col_msai else "0 AS saidas")
            _vcp.append(f"SUM(m.{col_ment}) AS entradas" if col_ment else "0 AS entradas")
            _grpvc = f"m.{col_mcod}" + (f", m.{col_mdsc}" if col_mdsc else "")
            _hvc = (f"SUM(m.{col_msai})>0 OR SUM(m.{col_ment})>0"
                    if col_msai and col_ment else "1=1")
            sql_venda_compra = f"""
                SELECT TOP 30 {", ".join(_vcp)}
                FROM Blue.dbo.vmItemMovEstq m WITH (NOLOCK)
                WHERE {_wm} GROUP BY {_grpvc}
                HAVING {_hvc} ORDER BY saidas DESC
            """

        sql_media_semanal = None
        if col_cod:
            _msp = ["i.CodItem"]
            if col_dsc: _msp.append(f"MAX(e.{col_dsc}) AS DescrItem")
            if col_mrc: _msp.append(f"MAX(e.{col_mrc}) AS DescrMarca")
            _msp += ["SUM(i.QtdItem) AS total_90d",
                     "CAST(SUM(i.QtdItem) AS FLOAT)/(90.0/7.0) AS media_semanal"]
            if col_qtd:  _msp.append(f"MAX(ISNULL(e.{col_qtd},0)) AS QtdEstq")
            if col_disp: _msp.append(f"MAX(ISNULL(e.{col_disp},0)) AS QtdEstqDisp")
            _cov = (f"MAX(ISNULL(e.{col_disp},0))/(CAST(SUM(i.QtdItem) AS FLOAT)/(90.0/7.0))"
                    if col_disp else "999")
            _msp.append(
                f"CASE WHEN SUM(i.QtdItem)>0 THEN {_cov} ELSE 999 END AS semanas_cobertura")
            # JOIN com estoque só quando há colunas úteis a buscar — evita fan-out quando
            # ev = vmAnaliseEstqVnd (N linhas por item → distorce SUM(i.QtdItem))
            _need_join_e = any([col_dsc, col_mrc, col_qtd, col_disp])
            _join_e_ms   = f"LEFT JOIN {ev} e WITH (NOLOCK) ON i.CodItem=e.{col_cod}" if _need_join_e else ""
            sql_media_semanal = f"""
                SELECT TOP {MAX} {", ".join(_msp)}
                FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
                INNER JOIN Blue.dbo.vwVndDoc d WITH (NOLOCK) ON i.NrDoc=d.NrDoc AND i.NSUDoc=d.NSUDoc
                {_join_e_ms}
                WHERE d.Cancelado='' AND i.Fat=1
                  AND i.DtVnd>=DATEADD(day,-90,GETDATE())
                GROUP BY i.CodItem ORDER BY media_semanal DESC
            """

        sql_sug = f"SELECT TOP {MAX} * FROM Blue.dbo.vmSugestaoTransfEstq WITH (NOLOCK)"
        sql_os  = "SELECT TOP 200 * FROM Blue.dbo.vwEstqTempOs WITH (NOLOCK)"

        # ── Execução paralela (4 workers, cada um com conexão própria) ─
        _all_sql: dict[str, str] = {k: v for k, v in {
            "resumo":         sql_resumo,
            "criticos":       sql_criticos,
            "marca":          sql_marca,
            "mov":            sql_mov,
            "giro_bruto":     sql_giro_bruto,
            "orc_estq":       sql_orc_estq,
            "venda_compra":   sql_venda_compra,
            "media_semanal":  sql_media_semanal,
            "sug":            sql_sug,
            "os":             sql_os,
        }.items() if v is not None}

        _res: dict[str, pd.DataFrame] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(db.new_conn_query, sql): key
                       for key, sql in _all_sql.items()}
            for f in concurrent.futures.as_completed(futures):
                key = futures[f]
                try:
                    _res[key] = f.result()
                except Exception as e:
                    logger.error("[Estq] Erro paralelo [%s]: %s", key, e)
                    _res[key] = pd.DataFrame()

        logger.info("[Estq] analisar() concluído em %.1fs (paralelo %d workers)",
                    time.time() - t0, min(4, len(_all_sql)))

        df_resumo        = _res.get("resumo",        pd.DataFrame())
        df_criticos      = _res.get("criticos",      pd.DataFrame())
        df_marca         = _res.get("marca",         pd.DataFrame())
        df_mov           = _res.get("mov",           pd.DataFrame())
        df_giro_bruto    = _res.get("giro_bruto",    pd.DataFrame())
        df_orc_estq      = _res.get("orc_estq",      pd.DataFrame())
        df_venda_compra  = _res.get("venda_compra",  pd.DataFrame())
        df_media_semanal = _res.get("media_semanal", pd.DataFrame())
        df_sug           = _res.get("sug",           pd.DataFrame())
        df_os            = _res.get("os",            pd.DataFrame())

        def _recs(df):
            return df.to_dict("records") if not df.empty else []

        # Deriva zerados_lista de df_criticos — sem query adicional ao banco
        _zer_keep2 = [c for c in ["CodItem", "DescrItem", "DescrMarca", "VlrEstq", "DtUltVnd"]
                      if c in df_criticos.columns]
        if not df_criticos.empty and "QtdEstqDisp" in df_criticos.columns:
            _df_zer2 = df_criticos[df_criticos["QtdEstqDisp"].fillna(0) <= 0].copy()
            if "DtUltVnd" in _df_zer2.columns:
                _df_zer2 = _df_zer2.sort_values("DtUltVnd", na_position="last")
            _zerados_lista2 = _df_zer2[_zer_keep2].to_dict("records") if not _df_zer2.empty else []
        else:
            _zerados_lista2 = []

        # Deriva sem_giro_lista: itens com DiasSemVnd >= DIAS_CRITICO, mais parados primeiro
        _sg_keep2 = [c for c in ["CodItem", "DescrItem", "DescrMarca", "QtdEstq", "VlrEstq", "DtUltVnd"]
                     if c in df_criticos.columns]
        if not df_criticos.empty and "DiasSemVnd" in df_criticos.columns:
            _df_sg2 = df_criticos[df_criticos["DiasSemVnd"] >= DIAS_CRITICO].copy()
            if "DtUltVnd" in _df_sg2.columns:
                _hoje2 = pd.Timestamp.now()
                _df_sg2["DiasSemVndReal"] = _df_sg2["DtUltVnd"].apply(
                    lambda d: int((_hoje2 - pd.Timestamp(d)).days) if pd.notna(d) else None
                )
                _sg_keep2.append("DiasSemVndReal")
                _df_sg2 = _df_sg2.sort_values("DiasSemVndReal", ascending=False, na_position="last")
            else:
                _df_sg2 = _df_sg2.sort_values("DiasSemVnd", ascending=False, na_position="last")
            _sem_giro_lista2 = _df_sg2[[c for c in _sg_keep2 if c in _df_sg2.columns]].to_dict("records") if not _df_sg2.empty else []
        else:
            _sem_giro_lista2 = []

        return {
            "total_itens":            _safe_int(df_resumo,  "total_itens"),
            "valor_total_estoque":    _safe_float(df_resumo,"valor_total_estoque"),
            "qtd_disponivel":         _safe_int(df_resumo,  "qtd_disponivel"),
            "itens_zerados":          _safe_int(df_resumo,  "itens_zerados"),
            "itens_sem_giro":         _safe_int(df_resumo,  "itens_sem_giro"),
            "zerados_lista":          _zerados_lista2,
            "sem_giro_lista":         _sem_giro_lista2,
            "giro_bruto":             _recs(df_giro_bruto),
            "por_marca":              _recs(df_marca),
            "movimentacao":           df_mov.head(50).to_dict("records") if not df_mov.empty else [],
            "orc_estoque":            _recs(df_orc_estq),
            "venda_compra":           _recs(df_venda_compra),
            "media_semanal":          _recs(df_media_semanal),
            "sugestao_transferencia": _recs(df_sug),
            "estq_os":                _recs(df_os),
            "ultimo_update":          datetime.now().strftime("%H:%M:%S"),
        }

    def analisar_filtrado(self, filtros: dict) -> dict:
        self._load_schemas()
        ev, et  = self._best("item", "vnd")
        col_cod = self._c(et, "CodItem",   "Codigo",    "CodigoItem",  "CodProduto")
        col_dsc = self._c(et, "DescrItem", "Descricao", "NomeItem",    "DescrProduto",
                              "NomeProduto", "DescrProd")
        col_mrc = self._c(et, "DescrMarca", "Marca",    "DescrMarcaItem", "NomeMarca",
                              "DescrMarcaProd", "MarcaItem")
        col_dtv = (self._c(et, "DtUltVnd", "DtUltimaVenda", "DtVnd", "UltDtVnd",
                               "DtUltVenda", "DataUltVnd", "DataUltimaVenda", "DtUltimaVnd")
                   or self._c(self._best("vnd", "item")[1],
                               "DtUltVnd", "DtUltimaVenda", "DtVnd", "UltDtVnd"))
        col_vlr = self._c(et, "VlrEstq", "ValEstq", "VlrTotEstq", "SaldoVlr",
                              "ValorEstoque", "VlrTotalEstq", "ValTotEstq")
        col_qtd = self._c(et, "QtdEstq", "SaldoEstq", "QtdSaldo", "Qtd",
                              "QtdEstoque", "QtdTotEstq", "QtdTotalEstq")

        # Apenas filtro de Marca (dt_de/dt_ate removidos — eram só para criticos)
        parts:  list = ["1=1"]
        params: list = []
        if filtros.get("marca") and col_mrc:
            parts.append(f"e.{col_mrc} LIKE ?")
            params.append(f"%{filtros['marca'][:100]}%")

        r = self.analisar_rapido()

        # Filtra zerados_lista e sem_giro_lista por Marca (Python, sem SQL extra)
        if filtros.get("marca"):
            m = filtros["marca"].lower()
            r["zerados_lista"] = [
                z for z in r.get("zerados_lista", [])
                if m in str(z.get("DescrMarca", "")).lower()
            ]
            r["sem_giro_lista"] = [
                z for z in r.get("sem_giro_lista", [])
                if m in str(z.get("DescrMarca", "")).lower()
            ]

        # giro_bruto com filtro de Marca aplicado
        if col_cod:
            _gbp = [f"e.{col_cod} AS CodItem"]
            if col_dsc: _gbp.append(f"MAX(e.{col_dsc}) AS DescrItem")
            if col_mrc: _gbp.append(f"MAX(e.{col_mrc}) AS DescrMarca")
            if col_qtd: _gbp.append(f"SUM(ISNULL(e.{col_qtd},0)) AS QtdEstq")
            if col_dtv: _gbp.append(f"MAX(e.{col_dtv}) AS DtUltVnd")
            _gbp += [
                "ISNULL(MAX(v.qtd_vendida_90d), 0) AS qtd_vendida_90d",
                "ISNULL(MAX(v.val_vendido_90d),  0) AS val_vendido_90d",
            ]
            gb_where_parts = ["1=1"]
            gb_having_parts: list = []
            gb_params: list = []
            if col_qtd:
                gb_having_parts.append(f"SUM(ISNULL(e.{col_qtd},0)) > 0")
            if filtros.get("marca") and col_mrc:
                gb_where_parts.append(f"e.{col_mrc} LIKE ?")
                gb_params.append(f"%{filtros['marca'][:100]}%")
            _gb_having = ("HAVING " + " AND ".join(gb_having_parts)) if gb_having_parts else ""
            sql_gb = f"""
                SELECT TOP 500 {", ".join(_gbp)}
                FROM {ev} e WITH (NOLOCK)
                LEFT JOIN (
                    SELECT i.CodItem,
                           SUM(i.QtdItem)         AS qtd_vendida_90d,
                           SUM(i.PrecoVndTotItem) AS val_vendido_90d
                    FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
                    INNER JOIN Blue.dbo.vwVndDoc d WITH (NOLOCK)
                        ON i.NrDoc = d.NrDoc AND i.NSUDoc = d.NSUDoc
                    WHERE d.Cancelado = '' AND i.Fat = 1
                      AND i.DtVnd >= DATEADD(day, -90, GETDATE())
                    GROUP BY i.CodItem
                ) v ON e.{col_cod} = v.CodItem
                WHERE {" AND ".join(gb_where_parts)}
                GROUP BY e.{col_cod}
                {_gb_having}
                ORDER BY ISNULL(MAX(v.val_vendido_90d), 0) DESC
            """
            df_gb = db.query(sql_gb, gb_params if gb_params else None)
            r["giro_bruto"] = df_gb.to_dict("records") if not df_gb.empty else []
        else:
            r["giro_bruto"] = []

        if params:
            def _sum(col, alias):
                return f"SUM(ISNULL({col},0)) AS {alias}" if col else f"0 AS {alias}"
            where = " AND ".join(parts)
            df_f = db.query(f"""
                SELECT COUNT(*) AS total_itens,
                       {_sum(col_vlr, 'valor_total_estoque')},
                       {_sum(col_qtd, 'qtd_total')}
                FROM {ev} e WITH (NOLOCK) WHERE {where}
            """, params)
            r["total_itens"]         = _safe_int(df_f,   "total_itens")
            r["valor_total_estoque"] = _safe_float(df_f, "valor_total_estoque")
            # itens_zerados/itens_sem_giro ficam do analisar_rapido (não filtrados por marca)
            # — recalculá-los exigiria DATEDIFF/DIAS_CRITICO por item, alto custo por chamada.
        return r


# ──────────────────────────────────────────────────────────────────
#  BOT FINANCEIRO
# ──────────────────────────────────────────────────────────────────
class BotFinanceiro(BaseBot):
    def __init__(self):
        super().__init__("financeiro")

    def analisar(self) -> dict:  # noqa: C901
        # Used only for TbCli.CodPlanoVndPadrao filter (credit limit query).
        # vmCtRecDetalhe drill-downs use Receita = 'BOLETO' — CodPlanoVnd does not exist there.
        # CodPlanoVndPadrao in TbCli is stored with 3 digits, zero-padded (e.g. '006' not '06').
        BOLETO_PADRAO_IN = ("'006','016','017','018','023','024','030',"
                            "'032','033','034','035','036','037','038','039',"
                            "'040','041','042','043','044','045','046','047',"
                            "'048','049','050','051','054'")

        # Títulos a partir de 2025 (exclui títulos históricos muito antigos ainda abertos)
        _DTINI_FIN = "'2025-01-01'"

        # ── Q1: Totais gerais (vmCtRecDetalhe — view already filters open) ─
        df_totais = db.query(f"""
            SELECT
                COUNT(*) AS qtd_total_aberto,
                COUNT(CASE WHEN Vencendo = 'Atrasados' THEN 1 END) AS qtd_vencidos,
                COUNT(CASE WHEN Vencendo <> 'Atrasados' THEN 1 END) AS qtd_a_vencer,
                SUM(CASE WHEN Vencendo = 'Atrasados' THEN Valor ELSE 0 END) AS vlr_vencidos,
                SUM(CASE WHEN Vencendo <> 'Atrasados' THEN Valor ELSE 0 END) AS vlr_a_vencer
            FROM Blue.dbo.vmCtRecDetalhe WITH (NOLOCK)
            WHERE DtVencimento >= {_DTINI_FIN}
        """)
        qtd_total_aberto = _safe_int(df_totais, "qtd_total_aberto")
        qtd_vencidos     = _safe_int(df_totais, "qtd_vencidos")
        qtd_a_vencer     = _safe_int(df_totais, "qtd_a_vencer")
        vlr_vencidos     = _safe_float(df_totais, "vlr_vencidos")
        vlr_a_vencer     = _safe_float(df_totais, "vlr_a_vencer")

        # ── Q2: Recebidos no mês — TbCtRec (índice nativo em DtQuitCtRec) ──
        # vmCtRecRecebido causa HYT00 em COUNT/SUM sem índice extra.
        # TbCtRec tem índice nativo em DtQuitCtRec e suporta GROUP BY sem timeout.
        # TpCobrCtRec=2 → boleto | outros → cash, PIX, etc.
        _MES_INI_REC = "DATEADD(month, DATEDIFF(month, 0, GETDATE()), 0)"
        _MES_FIM_REC = "DATEADD(month, DATEDIFF(month, 0, GETDATE()) + 1, 0)"

        df_tbrec_dist = db.query(f"""
            SELECT TpCobrCtRec, COUNT(*) AS qtd, SUM(ValCtRec) AS vlr
            FROM Blue.dbo.TbCtRec WITH (NOLOCK)
            WHERE DtQuitCtRec >= {_MES_INI_REC}
              AND DtQuitCtRec <  {_MES_FIM_REC}
            GROUP BY TpCobrCtRec
        """)

        qtd_recebido_mes = 0
        qtd_recebido_bol = 0
        qtd_recebido_car = 0
        vlr_recebido_mes = 0.0

        if not df_tbrec_dist.empty:
            for _, row in df_tbrec_dist.iterrows():
                tp  = int(row["TpCobrCtRec"]) if row["TpCobrCtRec"] is not None else -1
                qtd = int(row["qtd"])
                vlr = float(row["vlr"]) if row["vlr"] is not None else 0.0
                qtd_recebido_mes += qtd
                vlr_recebido_mes += vlr
                if tp == 2:        # boleto — TpCobrCtRec=2 confirmado via TbCtRec
                    qtd_recebido_bol = qtd
        else:
            logger.warning("[Fin] Q2 TbCtRec vazio ou erro: %s", db.last_error)

        # Q2c: Cartão — títulos quitados no mês com ValCartaoQuitCtRec > 0
        # JOIN composto: TbCtRec ↔ TbLctoQuitCtRec via CodEmpr+NrLctoCtRec+DtLctoCtRec
        df_car = db.query(f"""
            SELECT COUNT(*) AS qtd
            FROM Blue.dbo.TbCtRec r WITH (NOLOCK)
            WHERE r.DtQuitCtRec >= {_MES_INI_REC}
              AND r.DtQuitCtRec <  {_MES_FIM_REC}
              AND EXISTS (
                SELECT 1 FROM Blue.dbo.TbLctoQuitCtRec l WITH (NOLOCK)
                WHERE l.CodEmpr     = r.CodEmpr
                  AND l.NrLctoCtRec = r.NrLctoCtRec
                  AND l.DtLctoCtRec = r.DtLctoCtRec
                  AND l.ValCartaoQuitCtRec > 0
              )
        """)
        if not df_car.empty and not db.last_error:
            qtd_recebido_car = int(df_car["qtd"].iloc[0])

        logger.info("[Fin] Q2 final: global=%d bol=%d car=%d",
                    qtd_recebido_mes, qtd_recebido_bol, qtd_recebido_car)

        # ── Q3: Bar chart — vencimentos por dia próximos 30d ────────────
        df_venc30 = db.query("""
            SELECT TOP 30
                CAST(DtVencimento AS DATE) AS data_vcto,
                COUNT(*) AS qtd_titulos,
                SUM(Valor) AS valor_total
            FROM Blue.dbo.vmCtRecDetalhe WITH (NOLOCK)
            WHERE DtVencimento >= CAST(GETDATE() AS DATE)
              AND DtVencimento <  DATEADD(day, 30, CAST(GETDATE() AS DATE))
            GROUP BY CAST(DtVencimento AS DATE)
            ORDER BY data_vcto ASC
        """)
        vencimentos_30d = []
        if not df_venc30.empty:
            for _, row in df_venc30.iterrows():
                vencimentos_30d.append({
                    "data":  str(row.get("data_vcto", ""))[:10],
                    "qtd":   int(row.get("qtd_titulos", 0) or 0),
                    "valor": float(row.get("valor_total", 0) or 0),
                })

        # ── Q4: Boleto stats ──────────────────────────────────────────────
        df_bol_stats = db.query(f"""
            SELECT
                COUNT(*) AS qtd_total,
                SUM(Valor) AS valor_total,
                COUNT(CASE WHEN Vencendo = 'Atrasados' THEN 1 END) AS qtd_vencidos,
                COUNT(CASE WHEN Vencendo <> 'Atrasados' THEN 1 END) AS qtd_a_vencer,
                SUM(CASE WHEN Vencendo = 'Atrasados' THEN Valor ELSE 0 END) AS vlr_vencidos,
                SUM(CASE WHEN Vencendo <> 'Atrasados' THEN Valor ELSE 0 END) AS vlr_a_vencer
            FROM Blue.dbo.vmCtRecDetalhe WITH (NOLOCK)
            WHERE Receita = 'BOLETO'
              AND DtVencimento >= {_DTINI_FIN}
        """)

        # ── Q5: Cartão stats ──────────────────────────────────────────────
        df_car_stats = db.query(f"""
            SELECT
                COUNT(*) AS qtd_total,
                SUM(Valor) AS valor_total,
                COUNT(CASE WHEN Vencendo = 'Atrasados' THEN 1 END) AS qtd_vencidos,
                COUNT(CASE WHEN Vencendo <> 'Atrasados' THEN 1 END) AS qtd_a_vencer,
                SUM(CASE WHEN Vencendo = 'Atrasados' THEN Valor ELSE 0 END) AS vlr_vencidos,
                SUM(CASE WHEN Vencendo <> 'Atrasados' THEN Valor ELSE 0 END) AS vlr_a_vencer
            FROM Blue.dbo.vmCtRecDetalhe WITH (NOLOCK)
            WHERE Receita = 'CARTAO DE CREDITO'
              AND DtVencimento >= {_DTINI_FIN}
        """)

        # ── Q6: Drill-down Boleto Vencidos ────────────────────────────────
        df_bol_venc = db.query(f"""
            SELECT TOP 200
                ISNULL(c.CodRedCt, '') AS CodRedCt,
                d.NomeCli,
                d.Documento AS NrDoc,
                d.Valor AS VlrTitulo,
                d.DtVencimento AS DtVcto,
                DATEDIFF(day, d.DtVencimento, GETDATE()) AS dias_atraso
            FROM Blue.dbo.vmCtRecDetalhe d WITH (NOLOCK)
            LEFT JOIN Blue.dbo.TbCli c WITH (NOLOCK) ON d.CodCli = c.CodRedCt
            WHERE d.Receita = 'BOLETO'
              AND d.Vencendo = 'Atrasados'
              AND d.DtVencimento >= {_DTINI_FIN}
            ORDER BY dias_atraso DESC
        """)

        # ── Q7: Drill-down Boleto A Vencer ────────────────────────────────
        df_bol_aven = db.query(f"""
            SELECT TOP 200
                ISNULL(c.CodRedCt, '') AS CodRedCt,
                d.NomeCli,
                d.Documento AS NrDoc,
                d.Valor AS VlrTitulo,
                d.DtVencimento AS DtVcto,
                DATEDIFF(day, GETDATE(), d.DtVencimento) AS dias_faltando
            FROM Blue.dbo.vmCtRecDetalhe d WITH (NOLOCK)
            LEFT JOIN Blue.dbo.TbCli c WITH (NOLOCK) ON d.CodCli = c.CodRedCt
            WHERE d.Receita = 'BOLETO'
              AND d.Vencendo <> 'Atrasados'
              AND d.DtVencimento >= {_DTINI_FIN}
            ORDER BY d.DtVencimento ASC
        """)

        # ── Q8: Drill-down Cartão Vencidos ────────────────────────────────
        df_car_venc = db.query(f"""
            SELECT TOP 200
                ISNULL(c.CodRedCt, '') AS CodRedCt,
                d.NomeCli,
                d.Documento AS NrDoc,
                d.Valor AS VlrTitulo,
                d.DtVencimento AS DtVcto,
                DATEDIFF(day, d.DtVencimento, GETDATE()) AS dias_atraso
            FROM Blue.dbo.vmCtRecDetalhe d WITH (NOLOCK)
            LEFT JOIN Blue.dbo.TbCli c WITH (NOLOCK) ON d.CodCli = c.CodRedCt
            WHERE d.Receita = 'CARTAO DE CREDITO'
              AND d.Vencendo = 'Atrasados'
              AND d.DtVencimento >= {_DTINI_FIN}
            ORDER BY dias_atraso DESC
        """)

        # ── Q9: Drill-down Cartão A Vencer ────────────────────────────────
        df_car_aven = db.query(f"""
            SELECT TOP 200
                ISNULL(c.CodRedCt, '') AS CodRedCt,
                d.NomeCli,
                d.Documento AS NrDoc,
                d.Valor AS VlrTitulo,
                d.DtVencimento AS DtVcto,
                DATEDIFF(day, GETDATE(), d.DtVencimento) AS dias_faltando
            FROM Blue.dbo.vmCtRecDetalhe d WITH (NOLOCK)
            LEFT JOIN Blue.dbo.TbCli c WITH (NOLOCK) ON d.CodCli = c.CodRedCt
            WHERE d.Receita = 'CARTAO DE CREDITO'
              AND d.Vencendo <> 'Atrasados'
              AND d.DtVencimento >= {_DTINI_FIN}
            ORDER BY d.DtVencimento ASC
        """)

        # ── Q10: Drill-down Hoje (todos os tipos) ─────────────────────────
        df_hoje = db.query("""
            SELECT TOP 200
                ISNULL(c.CodRedCt, '') AS CodRedCt,
                d.NomeCli,
                d.Documento AS NrDoc,
                d.Valor AS VlrTitulo,
                d.DtVencimento AS DtVcto,
                d.Receita,
                0 AS dias_faltando
            FROM Blue.dbo.vmCtRecDetalhe d WITH (NOLOCK)
            LEFT JOIN Blue.dbo.TbCli c WITH (NOLOCK) ON d.CodCli = c.CodRedCt
            WHERE d.Vencendo = 'Hoje'
            ORDER BY d.Valor DESC
        """)

        # ── Schema discovery: TbCli + TbLimCredCli ───────────────────────
        _sch_cli = db.query("SELECT TOP 0 * FROM Blue.dbo.TbCli WITH (NOLOCK)")
        _sch_lim = db.query("SELECT TOP 0 * FROM Blue.dbo.TbLimCredCli WITH (NOLOCK)")
        cli_cols = list(_sch_cli.columns)
        lim_cols = list(_sch_lim.columns)

        # ── Q11: Limite de crédito boleto ─────────────────────────────────
        # Determine JOIN columns dynamically — PK name varies across installs
        _cli_fk = next((c for c in ('CodLimCredCli', 'CodLimCred') if c in cli_cols), None)
        _lim_pk = next((c for c in ('CodLimCredCli', 'CodLimCred') if c in lim_cols), None)

        _Q11_BODY = f"""
            SELECT TOP 100
                c.CodRedCt,
                c.NomeFantCli,
                l.ValLimCred1 AS limite_credito,
                ISNULL(SUM(d.Valor), 0) AS utilizado
            FROM Blue.dbo.TbCli c WITH (NOLOCK)
            JOIN Blue.dbo.TbLimCredCli l WITH (NOLOCK)
                ON {{join_cond}}
            LEFT JOIN Blue.dbo.vmCtRecDetalhe d WITH (NOLOCK)
                ON d.CodCli = c.CodRedCt
                AND d.Receita = 'BOLETO'
            WHERE c.StatusCli = '0'
              AND l.ValLimCred1 > 0
              AND c.CodPlanoVndPadrao IN ({BOLETO_PADRAO_IN})
            GROUP BY c.CodRedCt, c.NomeFantCli, l.ValLimCred1
            ORDER BY ISNULL(SUM(d.Valor), 0) / l.ValLimCred1 DESC
        """

        _join_cond_q11 = (
            f"c.{_cli_fk} = l.{_lim_pk}" if (_cli_fk and _lim_pk)
            else "c.CodRedCt = l.CodRedCt" if 'CodRedCt' in lim_cols
            else None
        )

        if _join_cond_q11:
            df_limite = db.query(_Q11_BODY.format(join_cond=_join_cond_q11))
            logger.info("[Fin] Q11: %d linhas (JOIN %s) last_error=%s",
                        len(df_limite), _join_cond_q11, db.last_error or "none")

            # Fallback: Q11 vazio com filtros — CodPlanoVndPadrao/StatusCli sem match
            if df_limite.empty and not db.last_error:
                logger.warning("[Fin] Q11 vazio com filtros; retentando sem CodPlanoVndPadrao/StatusCli")
                _Q11_BROAD = f"""
                    SELECT TOP 100
                        c.CodRedCt,
                        c.NomeFantCli,
                        l.ValLimCred1 AS limite_credito,
                        ISNULL(SUM(d.Valor), 0) AS utilizado
                    FROM Blue.dbo.TbCli c WITH (NOLOCK)
                    JOIN Blue.dbo.TbLimCredCli l WITH (NOLOCK)
                        ON {_join_cond_q11}
                    LEFT JOIN Blue.dbo.vmCtRecDetalhe d WITH (NOLOCK)
                        ON d.CodCli = c.CodRedCt
                        AND d.Receita = 'BOLETO'
                    WHERE l.ValLimCred1 > 0
                    GROUP BY c.CodRedCt, c.NomeFantCli, l.ValLimCred1
                    ORDER BY ISNULL(SUM(d.Valor), 0) / l.ValLimCred1 DESC
                """
                df_limite = db.query(_Q11_BROAD)
                logger.info("[Fin] Q11-broad (sem filtros extra): %d linhas last_error=%s",
                            len(df_limite), db.last_error or "none")
        else:
            logger.warning("[Fin] Q11 ignorado — colunas JOIN não encontradas: cli_fk=%s lim_pk=%s lim_cols=%s",
                           _cli_fk, _lim_pk, lim_cols)
            df_limite = pd.DataFrame()

        # ── Helper functions ──────────────────────────────────────────────
        def _stats(df):
            return {
                "qtd_total":    _safe_int(df, "qtd_total"),
                "valor_total":  round(_safe_float(df, "valor_total"), 2),
                "qtd_vencidos": _safe_int(df, "qtd_vencidos"),
                "qtd_a_vencer": _safe_int(df, "qtd_a_vencer"),
                "vlr_vencidos": round(_safe_float(df, "vlr_vencidos"), 2),
                "vlr_a_vencer": round(_safe_float(df, "vlr_a_vencer"), 2),
            }

        def _drill(df):
            if df.empty:
                return []
            has_receita = "Receita" in df.columns
            rows = []
            for _, r in df.iterrows():
                atraso   = r.get("dias_atraso")
                faltando = r.get("dias_faltando")
                if atraso is not None and not (isinstance(atraso, float) and math.isnan(atraso)):
                    dias = int(atraso)
                elif faltando is not None and not (isinstance(faltando, float) and math.isnan(faltando)):
                    dias = -int(faltando)
                else:
                    dias = 0
                entry = {
                    "CodRedCt":  str(r.get("CodRedCt") or ""),
                    "NomeCli":   str(r.get("NomeCli") or ""),
                    "NrDoc":     str(r.get("NrDoc") or ""),
                    "VlrTitulo": float(r.get("VlrTitulo") or 0),
                    "DtVcto":    str(r.get("DtVcto") or "")[:10],
                    "dias":      dias,
                }
                if has_receita:
                    entry["Receita"] = str(r.get("Receita") or "")
                rows.append(entry)
            return rows

        limite_lista = []
        if not df_limite.empty:
            for _, r in df_limite.iterrows():
                lim  = float(r.get("limite_credito") or 0)
                util = float(r.get("utilizado") or 0)
                pct  = round(util / lim * 100, 1) if lim > 0 else 0.0
                limite_lista.append({
                    "CodRedCt":       str(r.get("CodRedCt") or ""),
                    "NomeFantCli":    str(r.get("NomeFantCli") or ""),
                    "limite_credito": lim,
                    "utilizado":      round(util, 2),
                    "livre":          round(max(lim - util, 0), 2),
                    "pct_utilizado":  pct,
                })

        # ── Return dict ───────────────────────────────────────────────────
        return {
            "qtd_total_aberto":  qtd_total_aberto,
            "qtd_vencidos":      qtd_vencidos,
            "qtd_a_vencer":      qtd_a_vencer,
            "qtd_recebido_mes":  qtd_recebido_mes,
            "donut_status": [
                {"status": "Concluido", "qtd": qtd_recebido_mes, "valor": round(vlr_recebido_mes, 2)},
                {"status": "AVencer",   "qtd": qtd_a_vencer,     "valor": round(vlr_a_vencer, 2)},
                {"status": "Vencido",   "qtd": qtd_vencidos,     "valor": round(vlr_vencidos, 2)},
            ],
            "vencimentos_30d": vencimentos_30d,
            "qtd_recebido_bol": qtd_recebido_bol,
            "qtd_recebido_car": qtd_recebido_car,
            "boleto":         _stats(df_bol_stats),
            "cartao":         _stats(df_car_stats),
            "bol_vencidos":   _drill(df_bol_venc),
            "bol_a_vencer":   _drill(df_bol_aven),
            "car_vencidos":   _drill(df_car_venc),
            "car_a_vencer":   _drill(df_car_aven),
            "hoje_vencidos":  _drill(df_hoje),
            "limite_credito": limite_lista,
            "ultimo_update":  datetime.now().strftime("%H:%M:%S"),
        }

    def analisar_filtrado(self, filtros: dict) -> dict:
        return self.analisar()


# ──────────────────────────────────────────────────────────────────
#  BOT CRM  — Funil de conversão usando TbOrcPedVnd (OrcPedVnd 1/2)
# ──────────────────────────────────────────────────────────────────
class BotCRM(BaseBot):
    def __init__(self):
        super().__init__("crm")

    def analisar(self) -> dict:
        # ── KPIs de conversão do mês ──────────────────────────────
        # Usa vmVndDoc+vwVndDoc (mesmo padrão de df_ranking) para evitar
        # taxa >100% que ocorria com TbOrcPedVnd (orçamentos criados em meses
        # anteriores aparecem como OrcPedVnd=2 no mês atual, inflando conversões).
        df_conv = db.new_conn_query(f"""
            SELECT
                COUNT(DISTINCT v.NrDoc) AS total_orcamentos,
                COUNT(DISTINCT CASE WHEN d.TipoMovimento = '1.1-Docs Com Baixa / Com Faturamento'
                                    THEN v.NrDoc END) AS total_convertidos,
                CAST(COUNT(DISTINCT CASE WHEN d.TipoMovimento = '1.1-Docs Com Baixa / Com Faturamento'
                                         THEN v.NrDoc END) AS FLOAT) /
                    NULLIF(COUNT(DISTINCT v.NrDoc), 0) * 100 AS taxa_conversao_pct,
                SUM(v.ValVndTotal) AS valor_orcado,
                SUM(CASE WHEN d.TipoMovimento = '1.1-Docs Com Baixa / Com Faturamento'
                         THEN v.ValVndTotal ELSE 0 END) AS valor_convertido
            FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
            INNER JOIN Blue.dbo.vwVndDoc d WITH (NOLOCK) ON v.NrDoc = d.NrDoc AND v.NSUDoc = d.NSUDoc
            WHERE v.DtVnd >= {_MES_INI}
              AND v.DtVnd <  {_MES_FIM}
              {_EXCLUIR_PLANO}
        """)
        logger.info("[CRM] df_conv: %d linhas | valor_orcado=%s%s",
                    len(df_conv),
                    df_conv["valor_orcado"].iloc[0] if not df_conv.empty else "N/A",
                    f" | erro: {db.last_error}" if db.last_error else "")

        # ── KPIs do mês anterior (para deltas) ───────────────────
        df_anterior = db.query(f"""
            SELECT
                COUNT(DISTINCT v.NrDoc) AS total_orc_ant,
                COUNT(DISTINCT CASE WHEN d.TipoMovimento = '1.1-Docs Com Baixa / Com Faturamento'
                                    THEN v.NrDoc END) AS total_conv_ant,
                SUM(v.ValVndTotal) AS valor_orc_ant
            FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
            INNER JOIN Blue.dbo.vwVndDoc d WITH (NOLOCK) ON v.NrDoc = d.NrDoc AND v.NSUDoc = d.NSUDoc
            WHERE v.DtVnd >= {_MES_INI_ANT}
              AND v.DtVnd <  {_MES_FIM_ANT}
              {_EXCLUIR_PLANO}
        """)

        # ── Cancelamentos do mês atual ────────────────────────────
        # vwVndDoc.Cancelado = '*' é o discriminador direto de cancelados.
        # Não depende de vmVndDoc — orçamentos cancelados antes de virar NF
        # existem só em vwVndDoc, nunca em vmVndDoc.
        df_cancelados = db.query(f"""
            SELECT COUNT(*) AS cancelados
            FROM Blue.dbo.vwVndDoc WITH (NOLOCK)
            WHERE DataEmissao >= {_MES_INI}
              AND DataEmissao <  {_MES_FIM}
              AND Cancelado = '*'
        """)

        # ── Ranking de vendedores ─────────────────────────────────
        # NrOrcPedVnd (TbOrcPedVnd) != NrDoc (vmVndDoc — numeração NF).
        # Join direto não funciona; usar vmVndDoc+vwVndDoc como df_top_cli.
        # propostas = todos os docs do mês; convertidos = apenas faturados.
        df_ranking = db.query(f"""
            SELECT TOP 20
                v.Vendedor,
                COUNT(DISTINCT v.NrDoc) AS propostas,
                COUNT(DISTINCT CASE WHEN d.TipoMovimento = '1.1-Docs Com Baixa / Com Faturamento'
                                    THEN v.NrDoc END) AS convertidos,
                CAST(COUNT(DISTINCT CASE WHEN d.TipoMovimento = '1.1-Docs Com Baixa / Com Faturamento'
                                         THEN v.NrDoc END) AS FLOAT) /
                    NULLIF(COUNT(DISTINCT v.NrDoc), 0) * 100 AS taxa_conv,
                SUM(CASE WHEN d.TipoMovimento = '1.1-Docs Com Baixa / Com Faturamento'
                         THEN v.ValVndTotal ELSE 0 END) AS valor_convertido,
                CASE WHEN COUNT(DISTINCT CASE WHEN d.TipoMovimento = '1.1-Docs Com Baixa / Com Faturamento'
                                              THEN v.NrDoc END) > 0
                     THEN SUM(CASE WHEN d.TipoMovimento = '1.1-Docs Com Baixa / Com Faturamento'
                                   THEN v.ValVndTotal ELSE 0 END) /
                          COUNT(DISTINCT CASE WHEN d.TipoMovimento = '1.1-Docs Com Baixa / Com Faturamento'
                                              THEN v.NrDoc END)
                     ELSE 0 END AS ticket_medio
            FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
            INNER JOIN Blue.dbo.vwVndDoc d WITH (NOLOCK) ON v.NrDoc = d.NrDoc AND v.NSUDoc = d.NSUDoc
            WHERE v.DtVnd >= {_MES_INI}
              AND v.DtVnd <  {_MES_FIM}
              {_EXCLUIR_PLANO}
            GROUP BY v.Vendedor
            ORDER BY valor_convertido DESC
        """)

        # ── Cancelados por vendedor ───────────────────────────────
        # Cancelados existem em vwVndDoc (Cancelado='*') mas podem NÃO existir em
        # vmVndDoc (ex.: orçamentos cancelados antes de emitir NF). Qualquer join
        # com vmVndDoc perde esses docs. Abordagem: query direta em vwVndDoc,
        # nome do vendedor via CodFuncVnd → CodVend (lookup de vmVndDoc).
        df_canc_vend = db.query(f"""
            SELECT TOP 20
                vn.Vendedor,
                COUNT(*) AS cancelados
            FROM Blue.dbo.vwVndDoc d WITH (NOLOCK)
            INNER JOIN (
                SELECT DISTINCT CodVend, MAX(Vendedor) AS Vendedor
                FROM Blue.dbo.vmVndDoc WITH (NOLOCK)
                GROUP BY CodVend
            ) vn ON d.CodFuncVnd = vn.CodVend
            WHERE d.DataEmissao >= {_MES_INI}
              AND d.DataEmissao <  {_MES_FIM}
              AND d.Cancelado = '*'
            GROUP BY vn.Vendedor
            ORDER BY cancelados DESC
        """)

        # ── Top clientes do mês ───────────────────────────────────
        df_top_cli = db.query(f"""
            SELECT TOP 10
                v.CodCli,
                MAX(v.NomeFantCli) AS nome_cliente,
                MAX(v.Vendedor)    AS vendedor,
                COUNT(DISTINCT v.NrDoc) AS pedidos,
                SUM(v.ValVndTotal)      AS valor_mes
            FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
            WHERE v.DtVnd >= {_MES_INI}
              AND v.DtVnd <  {_MES_FIM}
              {_EXCLUIR_PLANO}
            GROUP BY v.CodCli
            ORDER BY valor_mes DESC
        """)

        logger.info("[CRM] df_top_cli: %d linhas%s", len(df_top_cli),
                    f" | erro: {db.last_error}" if db.last_error else "")

        # ── Clientes em risco (40–90 dias sem compra a partir de GETDATE()) ──────
        # WHERE filtra só 90 dias de vmVndDoc — muito mais rápido que varrer 2 anos.
        # HAVING usa -40 para a tabela mostrar 40–90d; KPI qtd_em_risco conta >= DIAS_RISCO (60d).
        df_risco = db.new_conn_query(f"""
            SELECT TOP {MAX}
                v.CodCli,
                MAX(v.NomeFantCli) AS nome_cliente,
                MAX(v.DtVnd)       AS ultima_compra,
                DATEDIFF(day, MAX(v.DtVnd), GETDATE()) AS dias_inativo,
                (SELECT TOP 1 v2.Vendedor FROM Blue.dbo.vmVndDoc v2 WITH (NOLOCK)
                 WHERE v2.CodCli = v.CodCli ORDER BY v2.DtVnd DESC) AS ultimo_vendedor
            FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
            WHERE v.DtVnd >= DATEADD(day, -{DIAS_INATIVO}, GETDATE())
              {_EXCLUIR_PLANO}
            GROUP BY v.CodCli
            HAVING MAX(v.DtVnd) < DATEADD(day, -{DIAS_ALERTA_RISCO}, GETDATE())
            ORDER BY dias_inativo DESC
        """)

        logger.info("[CRM] df_risco: %d linhas%s", len(df_risco),
                    f" | erro: {db.last_error}" if db.last_error else "")

        # ── Clientes inativos com último vendedor (>= DIAS_INATIVO) ──
        # WHERE limita a 2 anos (última compra pode ser antiga); HAVING compara datas.
        df_inativos_v = db.new_conn_query(f"""
            SELECT TOP {MAX}
                v.CodCli,
                MAX(v.NomeFantCli) AS nome_cliente,
                MAX(v.DtVnd)       AS ultima_compra,
                DATEDIFF(day, MAX(v.DtVnd), GETDATE()) AS dias_inativo,
                SUM(v.ValVndTotal) AS faturamento_historico,
                (SELECT TOP 1 v2.Vendedor FROM Blue.dbo.vmVndDoc v2 WITH (NOLOCK)
                 WHERE v2.CodCli = v.CodCli ORDER BY v2.DtVnd DESC) AS ultimo_vendedor
            FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
            WHERE v.DtVnd >= DATEADD(year, -2, GETDATE())
              {_EXCLUIR_PLANO}
            GROUP BY v.CodCli
            HAVING MAX(v.DtVnd) < DATEADD(day, -{DIAS_INATIVO}, GETDATE())
            ORDER BY dias_inativo DESC
        """)

        # ── Histograma de faixas de inatividade (sem nova query) ─
        _FAIXAS_INAT = [
            (90,  120, "90–120d"),
            (121, 180, "121–180d"),
            (181, 365, "181–365d"),
            (366, 9999, "+365d"),
        ]
        if not df_inativos_v.empty and "dias_inativo" in df_inativos_v.columns:
            _dias = df_inativos_v["dias_inativo"]
            faixas_inatividade = [
                {"faixa": label, "qtd": int(((_dias >= lo) & (_dias <= hi)).sum())}
                for lo, hi, label in _FAIXAS_INAT
            ]
        else:
            faixas_inatividade = [{"faixa": l, "qtd": 0} for _, _, l in _FAIXAS_INAT]

        # ── Evolução semanal (últimas 4 semanas corridas) ─────────
        df_evolucao = db.query(f"""
            SELECT
                DATEPART(week, DtOrcPedVnd) AS semana,
                MIN(DtOrcPedVnd)            AS inicio_semana,
                COUNT(CASE WHEN OrcPedVnd = 1 THEN 1 END) AS propostas,
                COUNT(CASE WHEN OrcPedVnd = 2 THEN 1 END) AS convertidos
            FROM Blue.dbo.TbOrcPedVnd WITH (NOLOCK)
            WHERE DtOrcPedVnd >= DATEADD(week, -4, GETDATE())
              AND DtOrcPedVnd <  {_MES_FIM}
            GROUP BY DATEPART(week, DtOrcPedVnd)
            ORDER BY semana
        """)

        # ── Funil por Vendedor e Marca ────────────────────────────
        df_conv_vend = db.query(f"""
            SELECT TOP 20
                v.Vendedor,
                i.DescrMarca,
                COUNT(CASE WHEN o.OrcPedVnd = 1 THEN 1 END)                              AS orcamentos,
                COUNT(CASE WHEN o.OrcPedVnd = 2 THEN 1 END)                              AS convertidos,
                SUM(CASE WHEN o.OrcPedVnd = 1 THEN i.PrecoVndTotItem ELSE 0 END)         AS valor_orcado,
                SUM(CASE WHEN o.OrcPedVnd = 2 THEN i.PrecoVndTotItem ELSE 0 END)         AS valor_convertido
            FROM Blue.dbo.TbOrcPedVnd o WITH (NOLOCK)
            INNER JOIN Blue.dbo.vmVndDoc v     WITH (NOLOCK) ON o.NrOrcPedVnd = v.NrDoc
            INNER JOIN Blue.dbo.vmVndItemDoc i WITH (NOLOCK) ON o.NrOrcPedVnd = i.NrDoc
            WHERE o.DtOrcPedVnd >= {_MES_INI}
              AND o.DtOrcPedVnd <  {_MES_FIM}
            GROUP BY v.Vendedor, i.DescrMarca
            ORDER BY valor_orcado DESC
        """)

        # ── Funil resumido por tipo (para gráfico de barras) ──────
        df_funil = db.query(f"""
            SELECT
                CASE OrcPedVnd WHEN 1 THEN 'Orcamento' WHEN 2 THEN 'Venda Convertida' ELSE 'Outro' END
                    AS tipo,
                COUNT(*)                   AS qtd_documentos,
                SUM(ValTotalOrcPedVnd)     AS valor_total
            FROM Blue.dbo.TbOrcPedVnd WITH (NOLOCK)
            WHERE DtOrcPedVnd >= {_MES_INI}
              AND DtOrcPedVnd <  {_MES_FIM}
            GROUP BY OrcPedVnd
            ORDER BY OrcPedVnd
        """)

        # ── Meta vs Realizado por Vendedor ────────────────────────
        # Schema discovery first — column names may vary
        _sch_meta = db.query("SELECT TOP 0 * FROM Blue.dbo.vmMetaRealizadoVnd WITH (NOLOCK)")
        _meta_cols = list(_sch_meta.columns) if not db.last_error else []
        _col_vend = next((c for c in _meta_cols if 'vend' in c.lower()), None)
        _col_meta = next((c for c in _meta_cols if 'meta' in c.lower() and 'realiz' not in c.lower()), None)
        _col_real = next((c for c in _meta_cols if 'realiz' in c.lower()), None)

        if _col_vend and _col_meta and _col_real:
            df_meta_vend = db.query(f"""
                SELECT TOP {MAX}
                    {_col_vend} AS Vendedor,
                    {_col_meta} AS ValMeta,
                    {_col_real} AS ValRealizado
                FROM Blue.dbo.vmMetaRealizadoVnd WITH (NOLOCK)
            """)
        else:
            logger.warning("[CRM] vmMetaRealizadoVnd colunas não encontradas: %s", _meta_cols)
            df_meta_vend = pd.DataFrame()

        if not df_meta_vend.empty and "ValMeta" in df_meta_vend.columns:
            def _cat(row):
                meta = float(row.get("ValMeta", 0) or 0)
                real = float(row.get("ValRealizado", 0) or 0)
                if meta <= 0:
                    return "Sem Meta"
                pct = real / meta * 100
                if pct >= 100:
                    return "Acima da Meta"
                if pct >= 80:
                    return "Próximo (80-99%)"
                return "Abaixo da Meta"
            df_meta_vend["categoria"] = df_meta_vend.apply(_cat, axis=1)
            meta_cats = df_meta_vend.groupby("categoria").size().reset_index(name="qtd").to_dict("records")
        else:
            meta_cats = []

        # ── Derivados ─────────────────────────────────────────────
        _orc  = _safe_int(df_conv, "total_orcamentos")
        _conv = _safe_int(df_conv, "total_convertidos")
        _vlro = _safe_float(df_conv, "valor_orcado")
        _vlrc = _safe_float(df_conv, "valor_convertido")
        _taxa = round(_safe_float(df_conv, "taxa_conversao_pct"), 1)
        _tick = round(_vlrc / _conv, 2) if _conv > 0 else 0.0
        _canc = _safe_int(df_cancelados, "cancelados") if not df_cancelados.empty else 0
        _ativ = max(_orc - _conv - _canc, 0)
        _orc_ant  = _safe_int(df_anterior, "total_orc_ant")
        _conv_ant = _safe_int(df_anterior, "total_conv_ant")
        _vlro_ant = _safe_float(df_anterior, "valor_orc_ant")
        _taxa_ant = round((_conv_ant / _orc_ant * 100) if _orc_ant > 0 else 0.0, 1)
        _delta_taxa  = round(_taxa - _taxa_ant, 1)
        _delta_vlro  = round(_vlro - _vlro_ant, 2)
        _total_d = _orc if _orc > 0 else 1
        _distribuicao = [
            {"status": "Convertidos",   "qtd": _conv, "pct": round(_conv / _total_d * 100, 1)},
            {"status": "Em Negociação", "qtd": _ativ, "pct": round(_ativ / _total_d * 100, 1)},
            {"status": "Cancelados",    "qtd": _canc, "pct": round(_canc / _total_d * 100, 1)},
        ]
        _funil_etapas = [
            {"etapa": "Propostas",     "qtd": _orc,  "pct": 100},
            {"etapa": "Em Negociação", "qtd": _ativ, "pct": round(_ativ / _total_d * 100, 1)},
            {"etapa": "Fechadas",      "qtd": _conv, "pct": round(_conv / _total_d * 100, 1)},
        ]

        return {
            # KPIs
            "total_orcamentos":   _orc,
            "total_convertidos":  _conv,
            "taxa_conversao_pct": _taxa,
            "valor_orcado":       _vlro,
            "valor_convertido":   _vlrc,
            "ticket_medio":       _tick,
            "delta_taxa_conv":    _delta_taxa,
            "delta_valor_orcado": _delta_vlro,
            "taxa_conversao_ant": _taxa_ant,
            "valor_orcado_ant":   _vlro_ant,
            "qtd_inativos":       len(df_inativos_v),
            "qtd_em_risco":       int((df_risco["dias_inativo"] >= DIAS_RISCO).sum()) if not df_risco.empty else 0,
            "qtd_ativos_mes":     len(df_top_cli),
            # Tabelas novas
            "ranking_vendedores":      df_ranking.to_dict("records"),
            "cancelados_por_vendedor": df_canc_vend.to_dict("records"),
            "top_clientes":            df_top_cli.to_dict("records"),
            "clientes_risco":          df_risco.to_dict("records"),
            "inativos_lista":          df_inativos_v.to_dict("records"),
            "faixas_inatividade":      faixas_inatividade,
            "evolucao_semanal":        df_evolucao.to_dict("records"),
            # Gráficos mantidos
            "distribuicao":            _distribuicao,
            "funil_etapas":            _funil_etapas,
            # Compatibilidade
            "funil":                   df_funil.to_dict("records"),
            "conv_por_vendedor":       df_conv_vend.to_dict("records"),
            "meta_vendedor":           meta_cats,
            "ultimo_update":           datetime.now().strftime("%H:%M:%S"),
        }

    def analisar_filtrado(self, filtros: dict) -> dict:
        has_vendedor = bool(filtros.get("vendedor"))
        has_marca    = bool(filtros.get("marca"))

        if not (has_vendedor or has_marca):
            return self.analisar()

        # Usa vmVndDoc+vwVndDoc — mesmo padrão da analisar() base.
        # TbOrcPedVnd.NrOrcPedVnd ≠ vmVndDoc.NrDoc (numerações distintas);
        # join direto retorna vazio e quebra os KPIs filtrados.
        parts  = [f"v.DtVnd >= {_MES_INI}", f"v.DtVnd < {_MES_FIM}"]
        params: list = []
        if has_vendedor:
            parts.append("v.Vendedor LIKE ?")
            params.append(f"%{filtros['vendedor'][:100]}%")

        marca_join = ""
        if has_marca:
            marca_join = "INNER JOIN Blue.dbo.vmVndItemDoc i WITH (NOLOCK) ON v.NrDoc = i.NrDoc"
            parts.append("i.DescrMarca LIKE ?")
            params.append(f"%{filtros['marca'][:100]}%")

        where = " AND ".join(parts)
        df_conv = db.new_conn_query(f"""
            SELECT
                COUNT(DISTINCT v.NrDoc) AS total_orcamentos,
                COUNT(DISTINCT CASE WHEN d.TipoMovimento = '1.1-Docs Com Baixa / Com Faturamento'
                                    THEN v.NrDoc END) AS total_convertidos,
                CAST(COUNT(DISTINCT CASE WHEN d.TipoMovimento = '1.1-Docs Com Baixa / Com Faturamento'
                                         THEN v.NrDoc END) AS FLOAT) /
                    NULLIF(COUNT(DISTINCT v.NrDoc), 0) * 100 AS taxa_conversao_pct,
                SUM(v.ValVndTotal) AS valor_orcado,
                SUM(CASE WHEN d.TipoMovimento = '1.1-Docs Com Baixa / Com Faturamento'
                         THEN v.ValVndTotal ELSE 0 END) AS valor_convertido
            FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
            INNER JOIN Blue.dbo.vwVndDoc d WITH (NOLOCK) ON v.NrDoc = d.NrDoc AND v.NSUDoc = d.NSUDoc
            {marca_join}
            WHERE {where} {_EXCLUIR_PLANO}
        """, params)

        # Usa o cache do ciclo de polling — evita re-executar analisar() completo
        # (seria 30-120s a mais por requisição filtrada, causando timeout HTTP).
        # Fallback para analisar() apenas no startup antes do primeiro polling.
        base = dict(self.resultado) if self.resultado else self.analisar()

        # Top Clientes refiltrado por vendedor (a query base usa TOP 10 global)
        if filtros.get("vendedor"):
            vend_like = f"%{filtros['vendedor'][:100]}%"
            df_top_cli_v = db.new_conn_query(f"""
                SELECT TOP 10 v.CodCli, MAX(v.NomeFantCli) AS nome_cliente,
                       MAX(v.Vendedor) AS vendedor,
                       COUNT(DISTINCT v.NrDoc) AS pedidos, SUM(v.ValVndTotal) AS valor_mes
                FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
                WHERE v.DtVnd >= {_MES_INI} AND v.DtVnd < {_MES_FIM} {_EXCLUIR_PLANO}
                  AND v.Vendedor LIKE ?
                GROUP BY v.CodCli ORDER BY valor_mes DESC
            """, [vend_like])
            base["top_clientes"] = df_top_cli_v.to_dict("records")

        _orc  = _safe_int(df_conv, "total_orcamentos")
        _conv = _safe_int(df_conv, "total_convertidos")
        _vlro = _safe_float(df_conv, "valor_orcado")
        _vlrc = _safe_float(df_conv, "valor_convertido")
        _taxa = round(_safe_float(df_conv, "taxa_conversao_pct"), 1)
        _tick = round(_vlrc / _conv, 2) if _conv > 0 else 0.0
        _canc = 0
        logger.info("[CRM filtrado] filtros=%s | orc=%d conv=%d taxa=%.1f%% orcado=%.0f%s",
                    filtros, _orc, _conv, _taxa, _vlro,
                    f" | erro: {db.last_error}" if db.last_error else "")
        _ativ = max(_orc - _conv - _canc, 0)
        _total_d = _orc if _orc > 0 else 1

        base["total_orcamentos"]   = _orc
        base["total_convertidos"]  = _conv
        base["taxa_conversao_pct"] = _taxa
        base["valor_orcado"]       = _vlro
        base["valor_convertido"]   = _vlrc
        base["ticket_medio"]       = _tick
        base["distribuicao"] = [
            {"status": "Convertidos",   "qtd": _conv, "pct": round(_conv / _total_d * 100, 1)},
            {"status": "Em Negociação", "qtd": _ativ, "pct": round(_ativ / _total_d * 100, 1)},
            {"status": "Cancelados",    "qtd": _canc, "pct": round(_canc / _total_d * 100, 1)},
        ]
        base["funil_etapas"] = [
            {"etapa": "Propostas",     "qtd": _orc,  "pct": 100},
            {"etapa": "Em Negociação", "qtd": _ativ, "pct": round(_ativ / _total_d * 100, 1)},
            {"etapa": "Fechadas",      "qtd": _conv, "pct": round(_conv / _total_d * 100, 1)},
        ]
        base["qtd_inativos"]   = base.get("qtd_inativos", 0)
        base["qtd_em_risco"]   = base.get("qtd_em_risco", 0)
        base["qtd_ativos_mes"] = base.get("qtd_ativos_mes", 0)
        # Deltas comparam empresa inteira vs. mês anterior; sem significado por vendedor/marca
        base["delta_taxa_conv"]    = None
        base["delta_valor_orcado"] = None
        base["taxa_conversao_ant"] = None
        base["valor_orcado_ant"]   = None
        # Tabelas não são refiltradas por vendedor/marca (retornam da base)
        return base


# ──────────────────────────────────────────────────────────────────
#  HUB POLLER BOT  — Polls hub REST API (client-side integration)
# ──────────────────────────────────────────────────────────────────
class HubPollerBot(BaseBot):
    """Replaces a real bot on client machines — polls the hub REST API."""

    def __init__(self, name_label: str):
        super().__init__(name_label)

    def analisar(self) -> dict:
        from core.data_client import data_client
        data = data_client.fetch(self.name_label)
        return data or {}


# ──────────────────────────────────────────────────────────────────
#  GERENCIADOR
# ──────────────────────────────────────────────────────────────────
class BotManager:
    def __init__(self, use_hub: bool = False):
        if use_hub:
            self.bots: dict[str, BaseBot] = {
                name: HubPollerBot(name)
                for name in ("dashboard", "vendas", "estoque", "financeiro", "crm")
            }
        else:
            self.bots: dict[str, BaseBot] = {
                "dashboard":  BotDashboard(),
                "vendas":     BotVendas(),
                "estoque":    BotEstoque(),
                "financeiro": BotFinanceiro(),
                "crm":        BotCRM(),
            }

    def load_from_cache(self):
        """Fire registered callbacks with last-known cache data for instant startup."""
        for name, bot in self.bots.items():
            data = _cache.load(name)
            if data:
                bot.resultado = data
                for cb in bot.callbacks:
                    try:
                        cb(bot.name_label, bot.resultado)
                    except Exception as e:
                        logger.warning("Callback error [%s]: %s", bot.name_label, e)

    def start_all(self):
        for bot in self.bots.values():
            bot.start()
        logger.info("Todos os bots iniciados.")

    def stop_all(self):
        for bot in self.bots.values():
            bot.stop()

    def add_callback(self, bot_name: str, fn):
        if bot_name in self.bots:
            self.bots[bot_name].add_callback(fn)

    def get_status(self) -> dict:
        return {
            name: {
                "status":        b.status,
                "ultimo_update": b.ultimo_update,
                "erro_msg":      b.erro_msg,
            }
            for name, b in self.bots.items()
        }

    def get_resultado(self, bot_name: str) -> dict:
        return self.bots.get(bot_name, BaseBot("__null__")).resultado
