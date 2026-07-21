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


def _py_records(records: list) -> list:
    """Converte escalares numpy (int64/float64) em tipos Python nativos para que
    o JSON emita números de verdade (e não strings via default=str)."""
    out = []
    for r in records:
        out.append({k: (v.item() if hasattr(v, "item") and not isinstance(v, (str, bytes)) else v)
                    for k, v in r.items()})
    return out


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
        # Boot escalonado: 7 bots disparando juntos derrubavam queries pesadas
        # por timeout (HYT00) no rush pós-start. O cache cobre a espera.
        for _ in range(int(getattr(self, "boot_delay", 0))):
            if self._stop.is_set():
                return
            time.sleep(1)
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
        # Perf (Parte Y): as 17 consultas — antes sequenciais — rodam em 2 FASES
        # PARALELAS (4 workers, new_conn_query). SQLs e contrato de retorno
        # idênticos à versão sequencial; a fase 2 depende de df_vend
        # (_cod_vend_map) e df_marcas (_marca_names) para montar os IN(...).
        _t0 = time.time()

        _f1 = {
            "kpi": f"""
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
        """,
            "vend": f"""
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
        """,
            "diario": f"""
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
        """,
            "marcas": f"""
            SELECT TOP 8
                i.DescrMarca,
                SUM(i.PrecoVndTotItem)                          AS venda_liq_prod,
                SUM(i.CustoRepTotItem)                          AS custo_rep_prod,
                SUM(i.PrecoVndTotItem) - SUM(i.CustoRepTotItem) AS lucro_prod,
                SUM(i.QtdItem)                                  AS quantidade
            FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
            WHERE i.DtVnd >= {_MES_INI}
              AND i.DtVnd <  {_MES_FIM}
              AND i.DescrMarca IS NOT NULL
              AND i.CodPlanoVnd NOT IN ('004','012','025','027')
            GROUP BY i.DescrMarca
            ORDER BY venda_liq_prod DESC
        """,
            "diario_vend": f"""
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
        """,
            "diario_marca": f"""
            SELECT
                CONVERT(date, i.DtVnd) AS dia,
                i.DescrMarca,
                SUM(i.PrecoVndTotItem) AS faturamento
            FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
            WHERE i.DtVnd >= DATEADD(day, -30, GETDATE())
              AND i.DescrMarca IS NOT NULL
              AND i.CodPlanoVnd NOT IN ('004','012','025','027')
            GROUP BY CONVERT(date, i.DtVnd), i.DescrMarca
            ORDER BY dia, faturamento DESC
        """,
            "novos_kpis": f"""
            SELECT
                SUM(v.ValVndTotal)                                              AS venda_liq,
                SUM(v.CustoRepTotal)                                            AS custo_rep_liq,
                SUM(v.TotalFrete)                                               AS frete_total,
                COUNT(DISTINCT v.NrDoc)                                         AS qtd_vendas_bruta,
                COUNT(DISTINCT CASE WHEN v.CustoRepTotal < 0 THEN v.NrDoc END) AS qtd_vendas_dev
            FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
            WHERE v.DtVnd >= {_MES_INI}
              AND v.DtVnd <  {_MES_FIM}
              {_EXCLUIR_PLANO}
        """,
            "dev": f"""
            SELECT SUM(d.ValTotItem) AS devolucoes_total
            FROM Blue.dbo.vmMetricasMotivoDevItem d WITH (NOLOCK)
            WHERE d.DtVnd >= {_MES_INI}
              AND d.DtVnd <  {_MES_FIM}
              AND d.CodPlanoVnd NOT IN ('004','012','025','027')
        """,
            "canc": f"""
            SELECT SUM(d.ValTotalNFVnd) AS cancelados_total
            FROM Blue.dbo.vwVndDoc d WITH (NOLOCK)
            WHERE d.DataEmissao >= {_MES_INI}
              AND d.DataEmissao <  {_MES_FIM}
              AND d.TipoMovimento = '1.5-Documentos Cancelados'
              AND d.CodPlanoVnd NOT IN ('004','012','025','027')
        """,
            "top_itens": f"""
            SELECT TOP 10
                i.CodItem,
                MAX(i.DescrItem)       AS DescrItem,
                MAX(i.DescrMarca)      AS DescrMarca,
                SUM(i.QtdItem)         AS quantidade,
                SUM(i.PrecoVndTotItem) AS venda_liq_prod
            FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
            WHERE i.DtVnd >= {_MES_INI}
              AND i.DtVnd <  {_MES_FIM}
              AND i.DescrItem IS NOT NULL
              AND i.CodPlanoVnd NOT IN ('004','012','025','027')
            GROUP BY i.CodItem
            ORDER BY quantidade DESC
        """,
            "kpi_marca": f"""
            SELECT i.DescrMarca,
                SUM(CASE WHEN i.CustoRepTotItem >= 0 THEN i.PrecoVndTotItem ELSE 0 END) AS venda_liq,
                SUM(CASE WHEN i.CustoRepTotItem <  0 THEN i.PrecoVndTotItem ELSE 0 END) AS devolucoes,
                SUM(CASE WHEN i.CustoRepTotItem >= 0 THEN i.CustoRepTotItem ELSE 0 END) AS custo_rep,
                SUM(i.QtdItem)                                                          AS quantidade,
                COUNT(DISTINCT CASE WHEN i.CustoRepTotItem >= 0 THEN i.NrDoc END)       AS qtd_vendas_bruta,
                COUNT(DISTINCT CASE WHEN i.CustoRepTotItem <  0 THEN i.NrDoc END)       AS qtd_vendas_dev
            FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
            WHERE i.DtVnd >= {_MES_INI} AND i.DtVnd < {_MES_FIM}
              AND i.DescrMarca IS NOT NULL
              AND i.CodPlanoVnd NOT IN ('004','012','025','027')
            GROUP BY i.DescrMarca
        """,
        }

        _res: dict = {}

        def _run_pool(sqls: dict, params_map: dict | None = None):
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                futs = {pool.submit(db.new_conn_query, sql, (params_map or {}).get(k)): k
                        for k, sql in sqls.items()}
                for f in concurrent.futures.as_completed(futs):
                    k = futs[f]
                    try:
                        _res[k] = f.result()
                    except Exception as e:
                        logger.error("[Dash] Erro paralelo [%s]: %s", k, e)
                        _res[k] = pd.DataFrame()

        _run_pool(_f1)

        df_kpi          = _res.get("kpi",          pd.DataFrame())
        df_vend         = _res.get("vend",         pd.DataFrame())
        df_diario       = _res.get("diario",       pd.DataFrame())
        df_marcas       = _res.get("marcas",       pd.DataFrame())
        df_diario_vend  = _res.get("diario_vend",  pd.DataFrame())
        df_diario_marca = _res.get("diario_marca", pd.DataFrame())
        df_novos_kpis   = _res.get("novos_kpis",   pd.DataFrame())
        df_dev          = _res.get("dev",          pd.DataFrame())
        df_canc         = _res.get("canc",         pd.DataFrame())
        df_top_itens    = _res.get("top_itens",    pd.DataFrame())
        df_kpi_marca    = _res.get("kpi_marca",    pd.DataFrame())

        # Map CodVend → Vendedor using df_vend so names match top_vendedores exactly
        _cod_vend_map: dict = {}
        if not df_vend.empty and 'CodVend' in df_vend.columns:
            _cod_vend_map = dict(zip(df_vend['CodVend'].astype(str), df_vend['Vendedor']))
        _marca_names = [m for m in df_marcas['DescrMarca'].tolist() if m] if not df_marcas.empty else []

        # ── Fase 2 — dependem do IN(...) de vendedores/marcas ────────────
        _f2: dict = {}
        _f2_params: dict = {}
        if _cod_vend_map:
            _in_codvend = ','.join(f"'{c}'" for c in _cod_vend_map)
            _f2["marcas_vend_raw"] = f"""
                SELECT TOP 500
                    i.CodVend,
                    i.DescrMarca,
                    SUM(i.PrecoVndTotItem)                          AS venda_liq_prod,
                    SUM(i.CustoRepTotItem)                          AS custo_rep_prod,
                    SUM(i.PrecoVndTotItem) - SUM(i.CustoRepTotItem) AS lucro_prod,
                    SUM(i.QtdItem)                                  AS quantidade
                FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
                WHERE i.DtVnd >= {_MES_INI}
                  AND i.DtVnd <  {_MES_FIM}
                  AND i.DescrMarca IS NOT NULL
                  AND i.CodVend IN ({_in_codvend})
                  AND i.CodPlanoVnd NOT IN ('004','012','025','027')
                GROUP BY i.CodVend, i.DescrMarca
                ORDER BY i.CodVend, venda_liq_prod DESC
            """
            _f2["kpi_vend"] = f"""
                SELECT v.CodVend,
                    SUM(v.ValVndTotal)                                            AS venda_liq,
                    SUM(v.CustoRepTotal)                                          AS custo_rep,
                    SUM(v.TotalFrete)                                             AS frete,
                    COUNT(DISTINCT v.NrDoc)                                       AS qtd_vendas_bruta,
                    COUNT(DISTINCT CASE WHEN v.CustoRepTotal < 0 THEN v.NrDoc END) AS qtd_vendas_dev
                FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
                WHERE v.DtVnd >= {_MES_INI} AND v.DtVnd < {_MES_FIM} {_EXCLUIR_PLANO}
                GROUP BY v.CodVend
            """
            _f2["dev_vend"] = f"""
                SELECT d.CodVend, SUM(d.ValTotItem) AS devolucoes
                FROM Blue.dbo.vmMetricasMotivoDevItem d WITH (NOLOCK)
                WHERE d.DtVnd >= {_MES_INI} AND d.DtVnd < {_MES_FIM}
                  AND d.CodPlanoVnd NOT IN ('004','012','025','027')
                GROUP BY d.CodVend
            """
            _f2["canc_vend"] = f"""
                SELECT d.CodFuncVnd AS CodVend, SUM(d.ValTotalNFVnd) AS cancelados
                FROM Blue.dbo.vwVndDoc d WITH (NOLOCK)
                WHERE d.DataEmissao >= {_MES_INI} AND d.DataEmissao < {_MES_FIM}
                  AND d.TipoMovimento = '1.5-Documentos Cancelados'
                  AND d.CodPlanoVnd NOT IN ('004','012','025','027')
                GROUP BY d.CodFuncVnd
            """
            _f2["itens_vend"] = f"""
                SELECT i.CodVend, i.CodItem,
                    MAX(i.DescrItem) AS DescrItem, MAX(i.DescrMarca) AS DescrMarca,
                    SUM(i.QtdItem) AS quantidade, SUM(i.PrecoVndTotItem) AS venda_liq_prod
                FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
                WHERE i.DtVnd >= {_MES_INI} AND i.DtVnd < {_MES_FIM}
                  AND i.DescrItem IS NOT NULL
                  AND i.CodPlanoVnd NOT IN ('004','012','025','027')
                  AND i.CodVend IN ({_in_codvend})
                GROUP BY i.CodVend, i.CodItem
            """
        if _marca_names:
            _ph = ','.join('?' for _ in _marca_names)
            _f2["itens_marca"] = f"""
                SELECT i.DescrMarca, i.CodItem,
                    MAX(i.DescrItem)       AS DescrItem,
                    SUM(i.QtdItem)         AS quantidade,
                    SUM(i.PrecoVndTotItem) AS venda_liq_prod
                FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
                WHERE i.DtVnd >= {_MES_INI} AND i.DtVnd < {_MES_FIM}
                  AND i.DescrItem IS NOT NULL
                  AND i.CodPlanoVnd NOT IN ('004','012','025','027')
                  AND i.DescrMarca IN ({_ph})
                GROUP BY i.DescrMarca, i.CodItem
            """
            _f2_params["itens_marca"] = _marca_names
        if _f2:
            _run_pool(_f2, _f2_params)

        # ── Marcas por vendedor ───────────────────────────────────────────
        _raw = _res.get("marcas_vend_raw", pd.DataFrame())
        if _raw is not None and not _raw.empty:
            _raw = _raw.copy()
            _raw['Vendedor'] = _raw['CodVend'].astype(str).map(_cod_vend_map)
            df_marcas_vend = _raw.dropna(subset=['Vendedor'])[
                ['Vendedor', 'DescrMarca', 'venda_liq_prod', 'custo_rep_prod', 'lucro_prod', 'quantidade']
            ].copy()
        else:
            df_marcas_vend = pd.DataFrame()

        # ── KPIs e top itens POR VENDEDOR — para filtragem client-side ────
        kpis_por_vendedor: list = []
        top_itens_por_vendedor: dict = {}
        df_kpi_vend  = _res.get("kpi_vend",  pd.DataFrame())
        df_dev_vend  = _res.get("dev_vend",  pd.DataFrame())
        df_canc_vend = _res.get("canc_vend", pd.DataFrame())
        _dev_map  = dict(zip(df_dev_vend['CodVend'].astype(str),  df_dev_vend['devolucoes'])) if df_dev_vend is not None and not df_dev_vend.empty else {}
        _canc_map = dict(zip(df_canc_vend['CodVend'].astype(str), df_canc_vend['cancelados'])) if df_canc_vend is not None and not df_canc_vend.empty else {}

        if df_kpi_vend is not None and not df_kpi_vend.empty:
            for _, _r in df_kpi_vend.iterrows():
                _c = str(_r['CodVend']); _nome = _cod_vend_map.get(_c)
                if not _nome:
                    continue
                _vl = float(_r['venda_liq'] or 0); _cr = float(_r['custo_rep'] or 0); _fr = float(_r['frete'] or 0)
                _qb = int(_r['qtd_vendas_bruta'] or 0); _qd = int(_r['qtd_vendas_dev'] or 0)
                _dv = float(_dev_map.get(_c, 0) or 0); _cn = float(_canc_map.get(_c, 0) or 0)
                kpis_por_vendedor.append({
                    "CodVend": _c, "Vendedor": _nome,
                    "kpi_venda_liquida": _vl, "kpi_custo_rep": _cr, "kpi_frete": _fr,
                    "qtd_vendas_bruta": _qb, "qtd_vendas_dev": _qd,
                    "kpi_devolucoes": _dv, "kpi_cancelados": _cn,
                    "kpi_faturamento_bruto": _vl + _dv + _cn,
                    "kpi_lucro_bruto": _vl - _cr,
                    "ticket_medio": (_vl / _qb) if _qb > 0 else 0.0,
                })

        df_itens_vend = _res.get("itens_vend", pd.DataFrame())
        if df_itens_vend is not None and not df_itens_vend.empty:
            df_itens_vend = df_itens_vend.copy()
            df_itens_vend['Vendedor'] = df_itens_vend['CodVend'].astype(str).map(_cod_vend_map)
            for _nome, _grp in df_itens_vend.dropna(subset=['Vendedor']).groupby('Vendedor'):
                top_itens_por_vendedor[_nome] = (_grp.sort_values('quantidade', ascending=False)
                    .head(8)[['CodItem', 'DescrItem', 'DescrMarca', 'quantidade', 'venda_liq_prod']]
                    .to_dict('records'))

        # ── KPIs e top itens POR MARCA — para filtragem client-side ───────
        # KPIs de nível-item (vmVndItemDoc). Cancelados e Frete são de nível-documento
        # (vwVndDoc / vmVndDoc) e NÃO existem por marca → ficam None ("—" no front).
        kpis_por_marca: list = []
        top_itens_por_marca: dict = {}
        if df_kpi_marca is not None and not df_kpi_marca.empty:
            for _, _r in df_kpi_marca.iterrows():
                _vl = float(_r['venda_liq'] or 0); _dv = abs(float(_r['devolucoes'] or 0))
                _cr = float(_r['custo_rep'] or 0)
                _qb = int(_r['qtd_vendas_bruta'] or 0); _qd = int(_r['qtd_vendas_dev'] or 0)
                kpis_por_marca.append({
                    "DescrMarca": _r['DescrMarca'],
                    "kpi_venda_liquida": _vl, "kpi_custo_rep": _cr,
                    "kpi_devolucoes": _dv, "kpi_lucro_bruto": _vl - _cr,
                    "kpi_faturamento_bruto": _vl + _dv,   # sem cancelados (n/d por marca)
                    "qtd_vendas_bruta": _qb, "qtd_vendas_dev": _qd,
                    "quantidade": float(_r['quantidade'] or 0),
                    "ticket_medio": (_vl / _qb) if _qb > 0 else 0.0,
                    "kpi_cancelados": None,   # n/d por marca
                    "kpi_frete": None,        # n/d por marca
                })

        df_itens_marca = _res.get("itens_marca", pd.DataFrame())
        if df_itens_marca is not None and not df_itens_marca.empty:
            for _m, _grp in df_itens_marca.groupby('DescrMarca'):
                _recs = (_grp.sort_values('quantidade', ascending=False)
                    .head(8)[['CodItem', 'DescrItem', 'quantidade', 'venda_liq_prod']]
                    .to_dict('records'))
                for _rec in _recs:
                    _rec['DescrMarca'] = _m
                top_itens_por_marca[_m] = _recs

        # ── KPIs escalares ─────────────────────────────────────────────────
        kpi_venda_liquida     = _safe_float(df_novos_kpis, "venda_liq")
        kpi_custo_rep         = _safe_float(df_novos_kpis, "custo_rep_liq")
        kpi_frete             = _safe_float(df_novos_kpis, "frete_total")
        kpi_qtd_vendas_bruta  = _safe_int(df_novos_kpis, "qtd_vendas_bruta")
        kpi_qtd_vendas_dev    = _safe_int(df_novos_kpis, "qtd_vendas_dev")
        kpi_devolucoes        = _safe_float(df_dev,         "devolucoes_total")
        kpi_cancelados        = _safe_float(df_canc,        "cancelados_total")
        kpi_faturamento_bruto = kpi_venda_liquida + kpi_devolucoes + kpi_cancelados
        kpi_lucro_bruto       = kpi_venda_liquida - kpi_custo_rep

        venda_bruta  = _safe_float(df_kpi, "venda_bruta")
        devolucao    = _safe_float(df_kpi, "devolucao")
        venda_liq    = venda_bruta + devolucao
        margem_bruta = _safe_float(df_kpi, "margem_bruta")
        meta         = ALERTAS.get("meta_faturamento_mensal", 400000)
        pct          = round(venda_liq / meta * 100, 1) if meta else 0

        logger.info("[Dash] analisar() concluído em %.1fs (17 queries em 2 fases paralelas)",
                    time.time() - _t0)

        return {
            "faturamento_atual":               venda_liq,
            "venda_bruta":                     venda_bruta,
            "devolucao":                       devolucao,
            "venda_liquida":                   venda_liq,
            "qtd_documentos":                  _safe_int(df_kpi, "qtd_documentos"),
            "qtd_devolucoes":                  _safe_int(df_kpi, "qtd_devolucoes"),
            "clientes_ativos":                 _safe_int(df_kpi, "clientes_ativos"),
            "ticket_medio":                    (kpi_venda_liquida / kpi_qtd_vendas_bruta) if kpi_qtd_vendas_bruta > 0 else 0.0,
            "margem_bruta":                    margem_bruta,
            "pct_meta":                        pct,
            "meta_mensal":                     meta,
            "top_vendedores":                  df_vend.to_dict("records"),
            "faturamento_diario":              df_diario.to_dict("records"),
            "marcas_mes":                      df_marcas.to_dict("records"),
            "marcas_por_vendedor":             df_marcas_vend.to_dict("records"),
            "faturamento_diario_por_vendedor": df_diario_vend.to_dict("records"),
            "faturamento_diario_por_marca":    df_diario_marca.to_dict("records"),
            "top_itens_mes":                   df_top_itens.to_dict("records"),
            "kpis_por_vendedor":               kpis_por_vendedor,
            "top_itens_por_vendedor":          top_itens_por_vendedor,
            "kpis_por_marca":                  kpis_por_marca,
            "top_itens_por_marca":             top_itens_por_marca,
            "kpi_venda_liquida":               kpi_venda_liquida,
            "kpi_devolucoes":                  kpi_devolucoes,
            "kpi_cancelados":                  kpi_cancelados,
            "kpi_faturamento_bruto":           kpi_faturamento_bruto,
            "kpi_custo_rep":                   kpi_custo_rep,
            "kpi_lucro_bruto":                 kpi_lucro_bruto,
            "kpi_frete":                       kpi_frete,
            "qtd_vendas_bruta":                kpi_qtd_vendas_bruta,
            "qtd_vendas_dev":                  kpi_qtd_vendas_dev,
            "ultimo_update":                   datetime.now().strftime("%H:%M:%S"),
        }

    def analisar_filtrado(self, filtros: dict) -> dict:
        cod = filtros.get("cod_vend")
        parts  = [f"v.DtVnd >= {_MES_INI}", f"v.DtVnd < {_MES_FIM}",
                  "d.Cancelado = ''", "d.Fat = 1"]
        params: list = []

        if cod:
            parts.append("v.CodVend = ?")
            params.append(cod)
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
                       "i.DescrMarca IS NOT NULL",
                       "i.CodPlanoVnd NOT IN ('004','012','025','027')"]
        if filtros.get("marca"):
            marca_parts.append("i.DescrMarca LIKE ?")
            marca_params.append(f"%{filtros['marca'][:100]}%")
        if cod:
            marca_parts.append("i.CodVend = ?")
            marca_params.append(cod)

        df_marcas = db.query(f"""
            SELECT TOP 8 i.DescrMarca,
                SUM(i.PrecoVndTotItem)                          AS venda_liq_prod,
                SUM(i.CustoRepTotItem)                          AS custo_rep_prod,
                SUM(i.PrecoVndTotItem) - SUM(i.CustoRepTotItem) AS lucro_prod,
                SUM(i.QtdItem)                                  AS quantidade
            FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
            WHERE {" AND ".join(marca_parts)}
            GROUP BY i.DescrMarca ORDER BY venda_liq_prod DESC
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
                                   "i.DescrMarca IS NOT NULL",
                                   "i.CodPlanoVnd NOT IN ('004','012','025','027')"]
            diario_params: list = []
            diario_parts.append("i.DescrMarca LIKE ?")
            diario_params.append(f"%{filtros['marca'][:100]}%")
            if cod:
                diario_parts.append("i.CodVend = ?")
                diario_params.append(cod)
            df_diario = db.query(f"""
                SELECT dia, faturamento FROM (
                    SELECT TOP 30 CONVERT(date, i.DtVnd) AS dia,
                           SUM(i.PrecoVndTotItem) AS faturamento
                    FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
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
                      {_EXCLUIR_PLANO} {("AND v.CodVend = ?" if cod else '')}
                    GROUP BY CONVERT(date, v.DtVnd) ORDER BY dia DESC
                ) _sub ORDER BY dia
            """, ([cod] if cod else None))

        # ── Novos KPIs filtrados ──────────────────────────────────────
        vnd_parts  = [f"v.DtVnd >= {_MES_INI}", f"v.DtVnd < {_MES_FIM}"]
        vnd_params: list = []
        if cod:
            vnd_parts.append("v.CodVend = ?")
            vnd_params.append(cod)

        where_vnd = " AND ".join(vnd_parts)

        df_novos_kpis_f = db.new_conn_query(f"""
            SELECT
                SUM(v.ValVndTotal)                                              AS venda_liq,
                SUM(v.CustoRepTotal)                                            AS custo_rep_liq,
                SUM(v.TotalFrete)                                               AS frete_total,
                COUNT(DISTINCT v.NrDoc)                                         AS qtd_vendas_bruta,
                COUNT(DISTINCT CASE WHEN v.CustoRepTotal < 0 THEN v.NrDoc END) AS qtd_vendas_dev
            FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
            WHERE {where_vnd}
              {_EXCLUIR_PLANO}
        """, vnd_params if vnd_params else None)

        dev_parts  = [f"d.DtVnd >= {_MES_INI}", f"d.DtVnd < {_MES_FIM}",
                      "d.CodPlanoVnd NOT IN ('004','012','025','027')"]
        dev_params: list = []
        if cod:
            dev_parts.append("d.CodVend = ?")
            dev_params.append(cod)

        df_dev_f = db.new_conn_query(f"""
            SELECT SUM(d.ValTotItem) AS devolucoes_total
            FROM Blue.dbo.vmMetricasMotivoDevItem d WITH (NOLOCK)
            WHERE {" AND ".join(dev_parts)}
        """, dev_params if dev_params else None)

        canc_parts  = [f"d.DataEmissao >= {_MES_INI}", f"d.DataEmissao < {_MES_FIM}",
                       "d.TipoMovimento = '1.5-Documentos Cancelados'",
                       "d.CodPlanoVnd NOT IN ('004','012','025','027')"]
        canc_params: list = []
        if cod:
            canc_parts.append("d.CodFuncVnd = ?")
            canc_params.append(cod)

        df_canc_f = db.new_conn_query(f"""
            SELECT SUM(d.ValTotalNFVnd) AS cancelados_total
            FROM Blue.dbo.vwVndDoc d WITH (NOLOCK)
            WHERE {" AND ".join(canc_parts)}
        """, canc_params if canc_params else None)

        # Top itens filtrados por vendedor — vmVndItemDoc tem CodVend direto
        top_itens_parts = [f"i.DtVnd >= {_MES_INI}", f"i.DtVnd < {_MES_FIM}",
                           "i.DescrItem IS NOT NULL",
                           "i.CodPlanoVnd NOT IN ('004','012','025','027')"]
        top_itens_params: list = []
        if cod:
            top_itens_parts.append("i.CodVend = ?")
            top_itens_params.append(cod)

        df_top_itens_f = db.new_conn_query(f"""
            SELECT TOP 10
                i.CodItem,
                MAX(i.DescrItem)       AS DescrItem,
                MAX(i.DescrMarca)      AS DescrMarca,
                SUM(i.QtdItem)         AS quantidade,
                SUM(i.PrecoVndTotItem) AS venda_liq_prod
            FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
            WHERE {" AND ".join(top_itens_parts)}
            GROUP BY i.CodItem
            ORDER BY quantidade DESC
        """, top_itens_params if top_itens_params else None)

        kpi_venda_liquida_f     = _safe_float(df_novos_kpis_f, "venda_liq")
        kpi_custo_rep_f         = _safe_float(df_novos_kpis_f, "custo_rep_liq")
        kpi_frete_f             = _safe_float(df_novos_kpis_f, "frete_total")
        kpi_qtd_vendas_bruta_f  = _safe_int(df_novos_kpis_f, "qtd_vendas_bruta")
        kpi_qtd_vendas_dev_f    = _safe_int(df_novos_kpis_f, "qtd_vendas_dev")
        kpi_devolucoes_f        = _safe_float(df_dev_f,         "devolucoes_total")
        kpi_cancelados_f        = _safe_float(df_canc_f,        "cancelados_total")
        kpi_faturamento_bruto_f = kpi_venda_liquida_f + kpi_devolucoes_f + kpi_cancelados_f
        kpi_lucro_bruto_f       = kpi_venda_liquida_f - kpi_custo_rep_f

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
            "ticket_medio":       (kpi_venda_liquida_f / kpi_qtd_vendas_bruta_f) if kpi_qtd_vendas_bruta_f > 0 else 0.0,
            "pct_meta":           pct,
            "meta_mensal":        meta,
            "top_vendedores":     df_vend.to_dict("records"),
            "faturamento_diario": df_diario.to_dict("records"),
            "marcas_mes":         df_marcas.to_dict("records"),
            "top_itens_mes":      df_top_itens_f.to_dict("records"),
            "kpi_venda_liquida":     kpi_venda_liquida_f,
            "kpi_devolucoes":        kpi_devolucoes_f,
            "kpi_cancelados":        kpi_cancelados_f,
            "kpi_faturamento_bruto": kpi_faturamento_bruto_f,
            "kpi_custo_rep":         kpi_custo_rep_f,
            "kpi_lucro_bruto":       kpi_lucro_bruto_f,
            "kpi_frete":             kpi_frete_f,
            "qtd_vendas_bruta":      kpi_qtd_vendas_bruta_f,
            "qtd_vendas_dev":        kpi_qtd_vendas_dev_f,
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
        planos_filter: lista de CodPlanoVnd para filtrar (None = todos).
        Perf (Parte Z): 15 consultas em 2 FASES PARALELAS (4 workers,
        new_conn_query) — SQLs e contrato idênticos à versão sequencial;
        a fase 2 depende do top-10 de vendedores (df_vend)."""
        _t0 = time.time()
        if not filtro_data:
            filtro_data = (
                f"i.DtVnd >= {_MES_INI}"
                f" AND i.DtVnd < {_MES_FIM}"
            )
        filtro_v = filtro_data.replace("i.DtVnd", "v.DtVnd")
        filtro_d = filtro_data.replace("i.DtVnd", "dev.DtVnd")
        if planos_filter:
            _plf = ",".join(str(int(p)) for p in planos_filter)
            filtro_plano_v = f"AND v.CodPlanoVnd IN ({_plf})"
            filtro_plano_i = (
                f"AND EXISTS (SELECT 1 FROM Blue.dbo.vmVndDoc vv"
                f" WHERE vv.NrDoc = i.NrDoc AND vv.NSUDoc = i.NSUDoc"
                f" AND vv.CodPlanoVnd IN ({_plf}))"
            )
        else:
            filtro_plano_v = ""
            filtro_plano_i = ""

        _f1 = {
            "kpi": f"""
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
        """,
            "marca": f"""
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
        """,
            "grupo": f"""
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
        """,
            "itens_marca": f"""
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
        """,
            "vend": f"""
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
        """,
            "hoje": f"""
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
        """,
            "nk": f"""
            SELECT
                SUM(v.ValVndTotal)                                            AS venda_liq,
                SUM(v.CustoRepTotal)                                          AS custo_rep_liq,
                SUM(v.TotalFrete)                                             AS frete_total,
                COUNT(DISTINCT v.NrDoc)                                       AS qtd_vendas_bruta,
                COUNT(DISTINCT CASE WHEN v.CustoRepTotal < 0 THEN v.NrDoc END) AS qtd_vendas_dev
            FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
            WHERE v.DtVnd >= {_MES_INI} AND v.DtVnd < {_MES_FIM} {_EXCLUIR_PLANO}
        """,
            # Ritmo do Mês: venda líquida por dia (mesma base do kpi_venda_liquida —
            # o acumulado do último dia FECHA com o KPI usado no % da Meta)
            "fat_diario": f"""
            SELECT CONVERT(date, v.DtVnd) AS dia,
                SUM(v.ValVndTotal) AS faturamento
            FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
            WHERE v.DtVnd >= {_MES_INI} AND v.DtVnd < {_MES_FIM} {_EXCLUIR_PLANO}
            GROUP BY CONVERT(date, v.DtVnd)
            ORDER BY dia
        """,
            "devk": f"""
            SELECT SUM(d.ValTotItem) AS devolucoes_total
            FROM Blue.dbo.vmMetricasMotivoDevItem d WITH (NOLOCK)
            WHERE d.DtVnd >= {_MES_INI} AND d.DtVnd < {_MES_FIM}
              AND d.CodPlanoVnd NOT IN ('004','012','025','027')
        """,
            "canck": f"""
            SELECT SUM(d.ValTotalNFVnd) AS cancelados_total
            FROM Blue.dbo.vwVndDoc d WITH (NOLOCK)
            WHERE d.DataEmissao >= {_MES_INI} AND d.DataEmissao < {_MES_FIM}
              AND d.TipoMovimento = '1.5-Documentos Cancelados'
              AND d.CodPlanoVnd NOT IN ('004','012','025','027')
        """,
            "kpi_marca": f"""
            SELECT i.DescrMarca,
                SUM(CASE WHEN i.CustoRepTotItem >= 0 THEN i.PrecoVndTotItem ELSE 0 END) AS venda_liq,
                SUM(CASE WHEN i.CustoRepTotItem <  0 THEN i.PrecoVndTotItem ELSE 0 END) AS devolucoes,
                SUM(CASE WHEN i.CustoRepTotItem >= 0 THEN i.CustoRepTotItem ELSE 0 END) AS custo_rep,
                COUNT(DISTINCT CASE WHEN i.CustoRepTotItem >= 0 THEN i.NrDoc END)       AS qtd_vendas_bruta,
                COUNT(DISTINCT CASE WHEN i.CustoRepTotItem <  0 THEN i.NrDoc END)       AS qtd_vendas_dev
            FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
            WHERE i.DtVnd >= {_MES_INI} AND i.DtVnd < {_MES_FIM}
              AND i.DescrMarca IS NOT NULL
              AND i.CodPlanoVnd NOT IN ('004','012','025','027')
            GROUP BY i.DescrMarca
        """,
        }

        _res: dict = {}

        def _run_pool(sqls: dict):
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                futs = {pool.submit(db.new_conn_query, sql): k for k, sql in sqls.items()}
                for f in concurrent.futures.as_completed(futs):
                    k = futs[f]
                    try:
                        _res[k] = f.result()
                    except Exception as e:
                        logger.error("[Vnd] Erro paralelo [%s]: %s", k, e)
                        _res[k] = pd.DataFrame()

        _run_pool(_f1)

        df_kpi         = _res.get("kpi",         pd.DataFrame())
        df_marca       = _res.get("marca",       pd.DataFrame())
        df_grupo       = _res.get("grupo",       pd.DataFrame())
        df_itens_marca = _res.get("itens_marca", pd.DataFrame())
        df_vend        = _res.get("vend",        pd.DataFrame())
        df_hoje        = _res.get("hoje",        pd.DataFrame())
        df_nk          = _res.get("nk",          pd.DataFrame())
        df_devk        = _res.get("devk",        pd.DataFrame())
        df_canck       = _res.get("canck",       pd.DataFrame())
        df_kpi_marca   = _res.get("kpi_marca",   pd.DataFrame())
        df_fat_diario  = _res.get("fat_diario",  pd.DataFrame())

        fat_diario_mes = []
        if df_fat_diario is not None and not df_fat_diario.empty:
            fat_diario_mes = [{"dia": str(r["dia"])[:10],
                               "faturamento": float(r["faturamento"] or 0)}
                              for _, r in df_fat_diario.iterrows()]

        _tim: dict = {}
        if not df_itens_marca.empty:
            for _mrc, _g in df_itens_marca.groupby("DescrMarca"):
                _tim[_mrc] = _g.nlargest(8, "faturamento")[
                    ["DescrItem", "faturamento", "quantidade"]
                ].to_dict("records")

        # ── Fase 2 — dependem do top-10 de vendedores (df_vend) ──────────
        _cod_vend_map_v: dict = {}
        if not df_vend.empty and 'CodVend' in df_vend.columns:
            _cod_vend_map_v = dict(zip(df_vend['CodVend'].astype(str), df_vend['Vendedor']))
        if _cod_vend_map_v:
            _in_cv = ','.join(f"'{c}'" for c in _cod_vend_map_v)
            _f2 = {
                "raw_mv": f"""
                SELECT TOP 500
                    i.CodVend,
                    i.DescrMarca,
                    SUM(CASE WHEN i.CustoRepTotItem >= 0 THEN i.PrecoVndTotItem ELSE 0 END) AS faturamento,
                    SUM(CASE WHEN i.CustoRepTotItem <  0 THEN i.PrecoVndTotItem ELSE 0 END) AS devolucao,
                    SUM(CASE WHEN i.CustoRepTotItem >= 0 THEN i.PrecoVndTotItem - i.CustoRepTotItem ELSE 0 END) AS margem_bruta,
                    SUM(CASE WHEN i.CustoRepTotItem >= 0 THEN i.QtdItem ELSE 0 END)         AS quantidade,
                    COUNT(DISTINCT CASE WHEN i.CustoRepTotItem >= 0 THEN i.NrDoc END)       AS qtd_documentos,
                    COUNT(DISTINCT CASE WHEN i.CustoRepTotItem < 0 THEN i.NrDoc END)        AS qtd_devolucoes
                FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
                WHERE i.DtVnd >= {_MES_INI}
                  AND i.DtVnd <  {_MES_FIM}
                  AND i.Fat = 1
                  AND i.DescrMarca IS NOT NULL
                  AND i.CodVend IN ({_in_cv})
                GROUP BY i.CodVend, i.DescrMarca
                ORDER BY i.CodVend, faturamento DESC
            """,
                "raw_iv": f"""
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
            """,
                "kpi_vend": f"""
                SELECT v.CodVend,
                    SUM(v.ValVndTotal) AS venda_liq, SUM(v.CustoRepTotal) AS custo_rep,
                    SUM(v.TotalFrete) AS frete,
                    COUNT(DISTINCT v.NrDoc) AS qtd_vendas_bruta,
                    COUNT(DISTINCT CASE WHEN v.CustoRepTotal < 0 THEN v.NrDoc END) AS qtd_vendas_dev
                FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
                WHERE v.DtVnd >= {_MES_INI} AND v.DtVnd < {_MES_FIM} {_EXCLUIR_PLANO}
                GROUP BY v.CodVend
            """,
                "dev_vend": f"""
                SELECT d.CodVend, SUM(d.ValTotItem) AS devolucoes
                FROM Blue.dbo.vmMetricasMotivoDevItem d WITH (NOLOCK)
                WHERE d.DtVnd >= {_MES_INI} AND d.DtVnd < {_MES_FIM}
                  AND d.CodPlanoVnd NOT IN ('004','012','025','027')
                GROUP BY d.CodVend
            """,
                "canc_vend": f"""
                SELECT d.CodFuncVnd AS CodVend, SUM(d.ValTotalNFVnd) AS cancelados
                FROM Blue.dbo.vwVndDoc d WITH (NOLOCK)
                WHERE d.DataEmissao >= {_MES_INI} AND d.DataEmissao < {_MES_FIM}
                  AND d.TipoMovimento = '1.5-Documentos Cancelados'
                  AND d.CodPlanoVnd NOT IN ('004','012','025','027')
                GROUP BY d.CodFuncVnd
            """,
            }
            _run_pool(_f2)

        _raw_mv = _res.get("raw_mv", pd.DataFrame())
        if _raw_mv is not None and not _raw_mv.empty:
            _raw_mv = _raw_mv.copy()
            _raw_mv['Vendedor'] = _raw_mv['CodVend'].astype(str).map(_cod_vend_map_v)
            df_marcas_vend = _raw_mv.dropna(subset=['Vendedor'])[
                ['Vendedor', 'DescrMarca', 'faturamento', 'devolucao', 'margem_bruta', 'quantidade', 'qtd_documentos', 'qtd_devolucoes']
            ].copy()
        else:
            df_marcas_vend = pd.DataFrame()

        _tiv: dict = {}
        _raw_iv = _res.get("raw_iv", pd.DataFrame())
        if _raw_iv is not None and not _raw_iv.empty:
            _raw_iv = _raw_iv.copy()
            _raw_iv['Vendedor'] = _raw_iv['CodVend'].astype(str).map(_cod_vend_map_v)
            _raw_iv = _raw_iv.dropna(subset=['Vendedor'])
            for _vnd, _g in _raw_iv.groupby('Vendedor'):
                _tiv[_vnd] = _g.nlargest(8, 'faturamento')[
                    ['DescrItem', 'faturamento', 'quantidade']
                ].to_dict('records')

        margem = sum(float(r.get("margem_bruta", 0) or 0)
                     for r in df_marca.to_dict("records"))

        # ── KPIs financeiros estilo Dashboard (MESMA fórmula que BotDashboard) ──
        _kvl = _safe_float(df_nk, "venda_liq"); _kcr = _safe_float(df_nk, "custo_rep_liq")
        _kfr = _safe_float(df_nk, "frete_total")
        _kqb = _safe_int(df_nk, "qtd_vendas_bruta"); _kqd = _safe_int(df_nk, "qtd_vendas_dev")
        _kdev = _safe_float(df_devk, "devolucoes_total"); _kcanc = _safe_float(df_canck, "cancelados_total")
        kpi_faturamento_bruto = _kvl + _kdev + _kcanc
        kpi_lucro_bruto       = _kvl - _kcr

        # por vendedor (mesmas chaves dos globais) — para filtragem client-side
        kpis_por_vendedor = []
        df_kpi_vend  = _res.get("kpi_vend",  pd.DataFrame())
        df_dev_vend  = _res.get("dev_vend",  pd.DataFrame())
        df_canc_vend = _res.get("canc_vend", pd.DataFrame())
        _dm = dict(zip(df_dev_vend['CodVend'].astype(str), df_dev_vend['devolucoes'])) if df_dev_vend is not None and not df_dev_vend.empty else {}
        _cm = dict(zip(df_canc_vend['CodVend'].astype(str), df_canc_vend['cancelados'])) if df_canc_vend is not None and not df_canc_vend.empty else {}
        if df_kpi_vend is not None and not df_kpi_vend.empty:
            for _, _r in df_kpi_vend.iterrows():
                _c = str(_r['CodVend']); _nm = _cod_vend_map_v.get(_c)
                if not _nm:
                    continue
                _vl = float(_r['venda_liq'] or 0); _cr = float(_r['custo_rep'] or 0); _fr = float(_r['frete'] or 0)
                _qb = int(_r['qtd_vendas_bruta'] or 0); _qd = int(_r['qtd_vendas_dev'] or 0)
                _dv = float(_dm.get(_c, 0) or 0); _cn = float(_cm.get(_c, 0) or 0)
                kpis_por_vendedor.append({
                    "CodVend": _c, "Vendedor": _nm,
                    "kpi_venda_liquida": _vl, "kpi_custo_rep": _cr, "kpi_frete": _fr,
                    "qtd_vendas_bruta": _qb, "qtd_vendas_dev": _qd,
                    "kpi_devolucoes": _dv, "kpi_cancelados": _cn,
                    "kpi_faturamento_bruto": _vl + _dv + _cn,
                    "kpi_lucro_bruto": _vl - _cr,
                    "ticket_medio": (_vl / _qb) if _qb > 0 else 0.0,
                })

        # por marca (nível-item; cancelados/frete = None pois são nível-documento)
        kpis_por_marca = []
        if df_kpi_marca is not None and not df_kpi_marca.empty:
            for _, _r in df_kpi_marca.iterrows():
                _vl = float(_r['venda_liq'] or 0); _dv = abs(float(_r['devolucoes'] or 0)); _cr = float(_r['custo_rep'] or 0)
                _qb = int(_r['qtd_vendas_bruta'] or 0); _qd = int(_r['qtd_vendas_dev'] or 0)
                kpis_por_marca.append({
                    "DescrMarca": _r['DescrMarca'],
                    "kpi_venda_liquida": _vl, "kpi_custo_rep": _cr, "kpi_devolucoes": _dv,
                    "kpi_lucro_bruto": _vl - _cr, "kpi_faturamento_bruto": _vl + _dv,
                    "qtd_vendas_bruta": _qb, "qtd_vendas_dev": _qd,
                    "ticket_medio": (_vl / _qb) if _qb > 0 else 0.0,
                    "kpi_cancelados": None, "kpi_frete": None,
                })

        venda_bruta = _safe_float(df_kpi, "venda_bruta")
        devolucao   = _safe_float(df_kpi, "devolucao")
        vend_records = df_vend.to_dict("records")
        logger.info("[Vnd] analisar() concluído em %.1fs (15 queries em 2 fases paralelas)",
                    time.time() - _t0)
        return {
            "faturamento_atual":     venda_bruta,
            "kpi_faturamento_bruto": kpi_faturamento_bruto,
            "kpi_venda_liquida":     _kvl,
            "kpi_devolucoes":        _kdev,
            "kpi_cancelados":        _kcanc,
            "kpi_custo_rep":         _kcr,
            "kpi_lucro_bruto":       kpi_lucro_bruto,
            "kpi_frete":             _kfr,
            "qtd_vendas_bruta":      _kqb,
            "qtd_vendas_dev":        _kqd,
            "kpis_por_vendedor":     kpis_por_vendedor,
            "kpis_por_marca":        kpis_por_marca,
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
            "fat_diario_mes":        fat_diario_mes,
            # Aliases legadas do desktop (ui/app.py TelaVendas) — contrato aditivo
            "faturamento_total":     venda_bruta,
            "qtd_vendas":            _safe_int(df_kpi, "qtd_vendas"),
            "total_devolucoes":      devolucao,
            "por_marca":             df_marca.to_dict("records"),
            "por_vendedor":          vend_records,
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
    """Análise de estoque — KPIs, Curva ABC, giro, cobertura, estoque parado,
    entradas×saídas e evolução (reconstruída por movimentos + snapshots diários
    locais no cache). Views (somente SELECT): vmAnaliseEstqItem, vmVndItemDoc,
    vmItemMovEstq, vmSugestaoTransfEstq, vwEstqTempOs; tabela TbProd (EstqMinExpo).
    Uma query-base por item alimenta KPIs/ABC/giro/cobertura/tabela detalhada;
    o restante roda em paralelo. Chaves legadas do desktop (ui/app.py) mantidas."""

    def __init__(self):
        super().__init__("estoque")

    def analisar(self) -> dict:
        t0 = time.time()

        # ── Q1 · Base por item: estoque agregado (todas as filiais) + mínimo (TbProd)
        sql_itens = """
            SELECT e.CodItem,
                MAX(e.DescrItem)             AS DescrItem,
                MAX(e.DescrMarca)            AS DescrMarca,
                SUM(ISNULL(e.QtdEstq,0))     AS QtdEstq,
                SUM(ISNULL(e.QtdEstqDisp,0)) AS QtdEstqDisp,
                SUM(ISNULL(e.VlrEstq,0))     AS VlrEstq,
                MAX(e.DtUltVnd)              AS DtUltVnd,
                MAX(ISNULL(p.EstqMinExpo,0)) AS EstqMin
            FROM Blue.dbo.vmAnaliseEstqItem e WITH (NOLOCK)
            LEFT JOIN Blue.dbo.TbProd p WITH (NOLOCK)
                ON p.CodItem = e.CodItem AND p.CodEmpr = e.CodEmpr
            GROUP BY e.CodItem
        """
        # ── Q2 · Vendas 90d por item (demanda p/ giro, cobertura e Curva ABC)
        # qtd_vendida_90d é a VENDA LÍQUIDA (devoluções entram com QtdItem negativo);
        # brutas e devoluções também saem separadas p/ tooltip transparente no front.
        sql_vnd90 = f"""
            SELECT i.CodItem,
                SUM(i.QtdItem)         AS qtd_vendida_90d,
                SUM(i.PrecoVndTotItem) AS val_vendido_90d,
                SUM(CASE WHEN i.QtdItem > 0 THEN i.QtdItem  ELSE 0 END) AS qtd_vendas_brutas_90d,
                SUM(CASE WHEN i.QtdItem < 0 THEN -i.QtdItem ELSE 0 END) AS qtd_devolvida_90d
            FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
            INNER JOIN Blue.dbo.vwVndDoc d WITH (NOLOCK)
                ON i.NrDoc = d.NrDoc AND i.NSUDoc = d.NSUDoc
            WHERE i.DtVnd >= DATEADD(day, -90, GETDATE())
              AND d.Cancelado = '' AND i.Fat = 1
              AND i.CodPlanoVnd NOT IN ('{_pl}')
            GROUP BY i.CodItem
        """
        # ── Q3 · Entradas × Saídas por mês (12 meses)
        sql_mov12 = """
            SELECT YEAR(m.DtMovEstq) AS ano, MONTH(m.DtMovEstq) AS mes,
                SUM(ISNULL(m.QtdEntrada,0)) AS entradas,
                SUM(ISNULL(m.QtdSaida,0))   AS saidas
            FROM Blue.dbo.vmItemMovEstq m WITH (NOLOCK)
            WHERE m.DtMovEstq >= DATEADD(month, DATEDIFF(month,0,GETDATE()) - 11, 0)
            GROUP BY YEAR(m.DtMovEstq), MONTH(m.DtMovEstq)
            ORDER BY ano, mes
        """
        # ── Q4 · Movimentação por item 30d (legado desktop: movimentacao/venda_compra)
        sql_mov_item = """
            SELECT TOP 2000 m.CodItem,
                MAX(m.DescrItem)              AS DescrItem,
                SUM(ISNULL(m.QtdEntrada,0))   AS entradas,
                SUM(ISNULL(m.QtdSaida,0))     AS saidas,
                SUM(ISNULL(m.QtdLiqVendas,0)) AS vendas_liquidas
            FROM Blue.dbo.vmItemMovEstq m WITH (NOLOCK)
            WHERE m.DtMovEstq >= DATEADD(day, -30, GETDATE())
            GROUP BY m.CodItem
            ORDER BY saidas DESC
        """
        # ── Q5 · Orçamentos 30d × estoque disponível (legado desktop)
        sql_orc = """
            SELECT TOP 30 e.CodItem,
                MAX(e.DescrItem)             AS DescrItem,
                MAX(e.DescrMarca)            AS DescrMarca,
                SUM(ISNULL(e.QtdEstqDisp,0)) AS QtdEstqDisp,
                ISNULL(MAX(o.qtd_orcada),0)  AS qtd_orcada,
                ISNULL(MAX(o.val_orcado),0)  AS val_orcado
            FROM Blue.dbo.vmAnaliseEstqItem e WITH (NOLOCK)
            INNER JOIN (
                SELECT i.CodItem,
                       SUM(i.QtdItem)         AS qtd_orcada,
                       SUM(i.PrecoVndTotItem) AS val_orcado
                FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
                INNER JOIN Blue.dbo.TbOrcPedVnd p WITH (NOLOCK) ON i.NrDoc = p.NrOrcPedVnd
                WHERE p.OrcPedVnd = 1
                  AND i.DtVnd >= DATEADD(day, -30, GETDATE())
                GROUP BY i.CodItem
            ) o ON e.CodItem = o.CodItem
            GROUP BY e.CodItem
            ORDER BY ISNULL(MAX(o.qtd_orcada),0) DESC
        """
        sql_sug = "SELECT TOP 1000 * FROM Blue.dbo.vmSugestaoTransfEstq WITH (NOLOCK)"
        sql_os  = "SELECT TOP 200 * FROM Blue.dbo.vwEstqTempOs WITH (NOLOCK)"

        # ── Execução paralela (4 workers, cada um com conexão própria) ─────
        # itens/vnd90 são agregadas por item — truncar no teto global (5000)
        # distorceria os totais; por isso recebem teto próprio de 20000.
        _all_sql = {"itens": sql_itens, "vnd90": sql_vnd90, "mov12": sql_mov12,
                    "mov_item": sql_mov_item, "orc": sql_orc, "sug": sql_sug, "os": sql_os}
        _max_rows = {"itens": 20000, "vnd90": 20000}
        _res: dict[str, pd.DataFrame] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(db.new_conn_query, sql, None, _max_rows.get(key)): key
                       for key, sql in _all_sql.items()}
            for f in concurrent.futures.as_completed(futures):
                key = futures[f]
                try:
                    _res[key] = f.result()
                except Exception as e:
                    logger.error("[Estq] Erro paralelo [%s]: %s", key, e)
                    _res[key] = pd.DataFrame()

        df_it  = _res.get("itens",    pd.DataFrame())
        df_v90 = _res.get("vnd90",    pd.DataFrame())
        df_m12 = _res.get("mov12",    pd.DataFrame())
        df_mi  = _res.get("mov_item", pd.DataFrame())

        def _recs(df):
            return _py_records(df.to_dict("records")) if df is not None and not df.empty else []

        _now_str = datetime.now().strftime("%H:%M:%S")
        if df_it.empty:
            if self.resultado:
                # Timeout transitório (ex.: rush de boot): NUNCA sobrescrever um
                # resultado bom — o payload mínimo destruiria cache e tela.
                logger.warning("[Estq] vmAnaliseEstqItem sem dados — mantendo último resultado bom")
                return self.resultado
            logger.warning("[Estq] vmAnaliseEstqItem sem dados — payload mínimo")
            return {
                "total_itens": 0, "valor_total_estoque": 0.0, "qtd_disponivel": 0,
                "itens_zerados": 0, "itens_sem_giro": 0, "zerados_lista": [],
                "sem_giro_lista": [], "giro_bruto": [], "por_marca": [],
                "movimentacao": _recs(df_mi), "orc_estoque": _recs(_res.get("orc")),
                "venda_compra": [], "media_semanal": [],
                "sugestao_transferencia": _recs(_res.get("sug")), "estq_os": _recs(_res.get("os")),
                "skus": 0, "skus_com_estoque": 0, "qtd_total": 0.0,
                "cobertura_media_dias": None,
                "abaixo_min_qtd": 0, "abaixo_min_total_config": 0, "abaixo_min_lista": [],
                "parado_qtd": 0, "parado_valor": 0.0, "parado_lista": [],
                "abc_resumo": [], "giro_top": [], "giro_bottom": [],
                "entradas_saidas": [], "evolucao_estimada": [], "evolucao_real": [],
                "tabela_detalhada": [],
                "ultimo_update": _now_str,
            }

        # ── Base por item (pandas) ─────────────────────────────────────────
        base = df_it.copy()
        base["CodItem"]    = base["CodItem"].astype(str).str.strip()
        base["DescrItem"]  = base["DescrItem"].fillna("—").astype(str).str.strip()
        base["DescrMarca"] = base["DescrMarca"].fillna("—").astype(str).str.strip()
        for c in ("QtdEstq", "QtdEstqDisp", "VlrEstq", "EstqMin"):
            base[c] = pd.to_numeric(base[c], errors="coerce").fillna(0.0).astype(float)

        _v90_cols = ("qtd_vendida_90d", "val_vendido_90d",
                     "qtd_vendas_brutas_90d", "qtd_devolvida_90d")
        if not df_v90.empty:
            df_v90 = df_v90.copy()
            df_v90["CodItem"] = df_v90["CodItem"].astype(str).str.strip()
            for c in _v90_cols:
                df_v90[c] = pd.to_numeric(df_v90[c], errors="coerce").fillna(0.0)
            base = base.merge(df_v90, on="CodItem", how="left")
        for c in _v90_cols:
            if c not in base.columns:
                base[c] = 0.0
            base[c] = base[c].fillna(0.0).astype(float)

        _hoje = pd.Timestamp.now()
        base["DtUltVnd"] = pd.to_datetime(base["DtUltVnd"], errors="coerce")
        base["DiasSemVndReal"] = base["DtUltVnd"].apply(
            lambda d: int((_hoje - d).days) if pd.notna(d) else None)
        base["DtUltVnd"] = base["DtUltVnd"].apply(
            lambda d: d.strftime("%Y-%m-%d") if pd.notna(d) else None)

        # Giro 90d = vendas ÷ estoque atual · Cobertura = disponível ÷ demanda diária
        base["giro90d"] = base.apply(
            lambda r: round(r["qtd_vendida_90d"] / r["QtdEstq"], 2) if r["QtdEstq"] > 0 else 0.0,
            axis=1)

        def _cobertura(r):
            demanda_dia = r["qtd_vendida_90d"] / 90.0
            if demanda_dia <= 0:
                return None                     # sem demanda no período
            if r["QtdEstqDisp"] <= 0:
                return 0
            return int(min(round(r["QtdEstqDisp"] / demanda_dia), 999))
        base["cobertura_dias"] = base.apply(_cobertura, axis=1)

        # Curva ABC pelo valor vendido 90d (A = 80% · B = 80–95% · C = resto/sem venda)
        base = base.sort_values("val_vendido_90d", ascending=False).reset_index(drop=True)
        tot_v = float(base["val_vendido_90d"].sum())
        if tot_v > 0:
            _acum = base["val_vendido_90d"].cumsum() / tot_v
            base["abc"] = ["A" if a <= 0.80 else "B" if a <= 0.95 else "C" for a in _acum]
            base.loc[base["val_vendido_90d"] <= 0, "abc"] = "C"
        else:
            base["abc"] = "C"

        # ── Máscaras / KPIs ────────────────────────────────────────────────
        com_estq  = base[base["QtdEstq"] > 0]
        zer_mask  = base["QtdEstqDisp"] <= 0
        _dias     = pd.to_numeric(base["DiasSemVndReal"], errors="coerce").fillna(99999)
        par_mask  = (base["QtdEstq"] > 0) & (_dias > DIAS_CRITICO)
        min_mask  = base["EstqMin"] > 0
        abx_mask  = min_mask & (base["QtdEstqDisp"] < base["EstqMin"])

        skus            = int(base["CodItem"].nunique())
        skus_com_estq   = int(len(com_estq))
        qtd_total       = float(base["QtdEstq"].sum())
        qtd_disponivel  = float(base["QtdEstqDisp"].sum())
        valor_total     = float(base["VlrEstq"].sum())
        demanda_dia_tot = float(base["qtd_vendida_90d"].sum()) / 90.0
        cobertura_media = (int(min(round(qtd_disponivel / demanda_dia_tot), 999))
                           if demanda_dia_tot > 0 else None)

        # ── Listas ─────────────────────────────────────────────────────────
        df_zer = base[zer_mask].sort_values("DtUltVnd", na_position="last")
        zerados_lista = _py_records(
            df_zer[["CodItem", "DescrItem", "DescrMarca", "VlrEstq", "DtUltVnd"]]
            .head(500).to_dict("records"))

        df_par = base[par_mask].sort_values("VlrEstq", ascending=False)
        parado_valor = float(df_par["VlrEstq"].sum())
        parado_lista = _py_records(
            df_par[["CodItem", "DescrItem", "DescrMarca", "QtdEstq", "VlrEstq",
                    "DiasSemVndReal", "DtUltVnd"]].head(500).to_dict("records"))

        df_abx = base[abx_mask].copy()
        df_abx["falta"] = (df_abx["EstqMin"] - df_abx["QtdEstqDisp"]).round(1)
        abaixo_lista = _py_records(
            df_abx.sort_values("falta", ascending=False)
            [["CodItem", "DescrItem", "DescrMarca", "QtdEstqDisp", "EstqMin", "falta"]]
            .head(300).to_dict("records"))

        abc_resumo = []
        for cls in ("A", "B", "C"):
            sub = base[base["abc"] == cls]
            _vv = float(sub["val_vendido_90d"].sum())
            abc_resumo.append({
                "classe":            cls,
                "itens":             int(len(sub)),
                "itens_com_estoque": int((sub["QtdEstq"] > 0).sum()),
                "valor_estoque":     float(sub["VlrEstq"].sum()),
                "val_vendido_90d":   _vv,
                "pct_valor_vendido": round(_vv / tot_v * 100, 1) if tot_v > 0 else 0.0,
            })

        _giro_cols = ["CodItem", "DescrItem", "DescrMarca", "giro90d",
                      "qtd_vendida_90d", "qtd_vendas_brutas_90d", "qtd_devolvida_90d",
                      "QtdEstq", "VlrEstq", "cobertura_dias"]
        _ge = base[(base["QtdEstq"] > 0) & (base["qtd_vendida_90d"] > 0)]
        giro_top = _py_records(
            _ge.sort_values("giro90d", ascending=False)[_giro_cols].head(10).to_dict("records"))
        giro_bottom = _py_records(
            com_estq.sort_values(["giro90d", "VlrEstq"], ascending=[True, False])
            [_giro_cols].head(10).to_dict("records"))

        tabela = _py_records(
            com_estq.sort_values("VlrEstq", ascending=False)
            [["CodItem", "DescrItem", "DescrMarca", "QtdEstq", "QtdEstqDisp", "EstqMin",
              "giro90d", "cobertura_dias", "abc", "VlrEstq", "DtUltVnd"]]
            .to_dict("records"))

        df_marca = (com_estq.groupby("DescrMarca")
                    .agg(qtd_itens=("CodItem", "count"),
                         valor_estoque=("VlrEstq", "sum"),
                         quantidade_total=("QtdEstq", "sum"))
                    .reset_index().sort_values("valor_estoque", ascending=False).head(30))
        por_marca = [{"DescrMarca": r["DescrMarca"], "qtd_itens": int(r["qtd_itens"]),
                      "valor_estoque": float(r["valor_estoque"]),
                      "quantidade_total": float(r["quantidade_total"])}
                     for _, r in df_marca.iterrows()]

        giro_bruto = _py_records(
            com_estq.sort_values("val_vendido_90d", ascending=False)
            [["CodItem", "DescrItem", "DescrMarca", "QtdEstq", "DtUltVnd",
              "qtd_vendida_90d", "val_vendido_90d"]].head(500).to_dict("records"))

        df_ms = base[base["qtd_vendida_90d"] > 0].copy()
        df_ms["media_semanal"] = (df_ms["qtd_vendida_90d"] / (90.0 / 7.0)).round(2)
        df_ms["total_90d"]     = df_ms["qtd_vendida_90d"]
        df_ms["semanas_cobertura"] = df_ms.apply(
            lambda r: round(min(r["QtdEstqDisp"] / r["media_semanal"], 999), 1)
            if r["media_semanal"] > 0 else 999.0, axis=1)
        media_semanal = _py_records(
            df_ms.sort_values("media_semanal", ascending=False)
            [["CodItem", "DescrItem", "DescrMarca", "media_semanal", "total_90d",
              "QtdEstq", "QtdEstqDisp", "semanas_cobertura"]].head(500).to_dict("records"))

        movimentacao, venda_compra = [], []
        if not df_mi.empty:
            df_mi = df_mi.copy()
            for c in ("entradas", "saidas", "vendas_liquidas"):
                if c in df_mi.columns:
                    df_mi[c] = pd.to_numeric(df_mi[c], errors="coerce").fillna(0.0)
            movimentacao = _py_records(df_mi.head(50).to_dict("records"))
            venda_compra = _py_records(
                df_mi[["CodItem", "DescrItem", "saidas", "entradas"]].head(30).to_dict("records"))

        # ── Entradas × Saídas + evolução reconstruída (12 meses) ──────────
        entradas_saidas, evolucao_estimada = [], []
        if not df_m12.empty:
            df_m12 = df_m12.copy()
            for c in ("entradas", "saidas"):
                df_m12[c] = pd.to_numeric(df_m12[c], errors="coerce").fillna(0.0)
            df_m12 = df_m12.sort_values(["ano", "mes"])
            entradas_saidas = [{"mes": f"{int(r['mes']):02d}/{int(r['ano'])}",
                                "entradas": float(r["entradas"]),
                                "saidas":   float(r["saidas"])}
                               for _, r in df_m12.iterrows()]
            # Saldo no fim do mês m = qtd_atual − Σ(entradas−saídas) dos meses seguintes.
            # Valor estimado ao custo médio ATUAL (rotulado como estimativa no frontend).
            custo_medio = (valor_total / qtd_total) if qtd_total > 0 else 0.0
            _liqs = [float(r["entradas"]) - float(r["saidas"]) for _, r in df_m12.iterrows()]
            _saldo = qtd_total
            _saldos = [0.0] * len(_liqs)
            for i in range(len(_liqs) - 1, -1, -1):
                _saldos[i] = _saldo
                _saldo -= _liqs[i]
            evolucao_estimada = [{"mes": entradas_saidas[i]["mes"],
                                  "qtd": round(_saldos[i], 1),
                                  "valor_estimado": round(_saldos[i] * custo_medio, 2)}
                                 for i in range(len(_saldos))]

        # Snapshot diário REAL no cache local (1 por dia) → série cresce com o tempo
        evolucao_real = []
        try:
            _cache.save_snapshot("estoque", datetime.now().strftime("%Y-%m-%d"),
                                 {"qtd": round(qtd_total, 1), "valor": round(valor_total, 2)})
            evolucao_real = _cache.load_snapshots("estoque", limit=180)
        except Exception as e:
            logger.warning("[Estq] snapshot: %s", e)

        logger.info("[Estq] analisar() concluído em %.1fs (%d itens, %d na tabela)",
                    time.time() - t0, len(base), len(tabela))

        return {
            # ── chaves legadas (desktop ui/app.py) ──
            "total_itens":            skus_com_estq,
            "valor_total_estoque":    valor_total,
            "qtd_disponivel":         int(qtd_disponivel),
            "itens_zerados":          int(zer_mask.sum()),
            "itens_sem_giro":         int(par_mask.sum()),
            "zerados_lista":          zerados_lista,
            "sem_giro_lista":         parado_lista,
            "giro_bruto":             giro_bruto,
            "por_marca":              por_marca,
            "movimentacao":           movimentacao,
            "orc_estoque":            _recs(_res.get("orc")),
            "venda_compra":           venda_compra,
            "media_semanal":          media_semanal,
            "sugestao_transferencia": _recs(_res.get("sug")),
            "estq_os":                _recs(_res.get("os")),
            # ── novas chaves (aba web reestruturada) ──
            "skus":                    skus,
            "skus_com_estoque":        skus_com_estq,
            "qtd_total":               qtd_total,
            "cobertura_media_dias":    cobertura_media,
            "abaixo_min_qtd":          int(abx_mask.sum()),
            "abaixo_min_total_config": int(min_mask.sum()),
            "abaixo_min_lista":        abaixo_lista,
            "parado_qtd":              int(par_mask.sum()),
            "parado_valor":            parado_valor,
            "parado_lista":            parado_lista,
            "abc_resumo":              abc_resumo,
            "giro_top":                giro_top,
            "giro_bottom":             giro_bottom,
            "entradas_saidas":         entradas_saidas,
            "evolucao_estimada":       evolucao_estimada,
            "evolucao_real":           evolucao_real,
            "tabela_detalhada":        tabela,
            "ultimo_update":           _now_str,
        }

    def analisar_filtrado(self, filtros: dict) -> dict:
        # Filtros (marca/texto/classe) agora são client-side no frontend,
        # como nas demais abas. Devolve o último resultado completo.
        return self.resultado or self.analisar()


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
                tp  = int(row["TpCobrCtRec"]) if not pd.isna(row["TpCobrCtRec"]) else -1
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
        _carteira_aberta = vlr_vencidos + vlr_a_vencer
        return {
            "qtd_total_aberto":  qtd_total_aberto,
            "qtd_vencidos":      qtd_vencidos,
            "qtd_a_vencer":      qtd_a_vencer,
            "qtd_recebido_mes":  qtd_recebido_mes,
            # Valores em R$ (antes só existiam dentro do donut) + inadimplência
            "vlr_total_aberto":  round(_carteira_aberta, 2),
            "vlr_vencidos":      round(vlr_vencidos, 2),
            "vlr_a_vencer":      round(vlr_a_vencer, 2),
            "vlr_recebido_mes":  round(vlr_recebido_mes, 2),
            "pct_inadimplencia": round(vlr_vencidos / _carteira_aberta * 100, 1) if _carteira_aberta > 0 else 0.0,
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
#  BOT IMPOSTO  — ICMS · CFOP · Tributação por item
#  Fonte real dos impostos de venda: Blue.dbo.TbNFVnd (nota fiscal).
#  As tabelas de "livro fiscal"/apuração/saldo do ERP estão vazias ou
#  só têm dados de 2019 — por isso NÃO são usadas aqui.
#  IPI e ICMS-ST aparecem ~R$0: a empresa é revenda/comércio (não
#  indústria e o ST foi retido a montante). O ST é refletido pelo CFOP
#  (5405/6404 = saída sujeita a substituição tributária).
# ──────────────────────────────────────────────────────────────────
class BotImposto(BaseBot):
    """Imposto v2 — ICMS · CFOP · Tributação, com comparativo mensal, ICMS
    diário, evolução por CFOP, maiores NFs e regras PIS/COFINS.
    Fonte real dos impostos de venda: Blue.dbo.TbNFVnd (as tabelas de livro
    fiscal/apuração/ajuste do ERP estão vazias ou pararam em 2019 — ver
    doc/ABA_IMPOSTO.txt). IPI e ICMS-ST ~R$0: empresa é revenda/comércio e o
    ST foi retido a montante — refletido pelo CFOP (5405/6404).
    8 queries somente-leitura em paralelo (4 workers, conexões independentes)."""

    _CFOP_ST = {'5401', '5402', '5403', '5405', '5409',
                '6401', '6402', '6403', '6404', '6409'}

    def __init__(self):
        super().__init__("imposto")

    @staticmethod
    def _classifica_uf(cod: str) -> str:
        c = (cod or "").strip()
        if   c.startswith('5'): return 'Dentro do Estado'
        elif c.startswith('6'): return 'Fora do Estado'
        elif c.startswith('7'): return 'Exterior'
        else:                   return 'Entrada/Outras'

    @staticmethod
    def _kpis_de(df: pd.DataFrame) -> dict:
        icms      = _safe_float(df, 'icms')
        base_icms = _safe_float(df, 'base_icms')
        return {
            "qtd_nf":           _safe_int(df, 'qtd_nf'),
            "nfs_canceladas":   _safe_int(df, 'nfs_canc'),
            "faturamento":      _safe_float(df, 'faturamento'),
            "base_icms":        base_icms,
            "icms":             icms,
            "base_st":          _safe_float(df, 'base_st'),
            "icms_st":          _safe_float(df, 'icms_st'),
            "base_ipi":         _safe_float(df, 'base_ipi'),
            "ipi":              _safe_float(df, 'ipi'),
            # Livro ICMS: Valor Contábil ≈ Base + Isentas + OUTRAS.
            # "Outras" = parcela SEM débito próprio → concentra as operações com
            # ICMS-ST retido na origem (CFOP 5405/6404) — confirmado nos dados.
            "isentas":          _safe_float(df, 'isentas'),
            "outras":           _safe_float(df, 'outras'),
            # Livro IPI (revenda não destaca IPI → valor cai em Isentas/Outras IPI)
            "isentas_ipi":      _safe_float(df, 'isentas_ipi'),
            "outras_ipi":       _safe_float(df, 'outras_ipi'),
            "frete":            _safe_float(df, 'frete'),
            "aliquota_efetiva": (icms / base_icms * 100) if base_icms else 0.0,
        }

    def analisar(self) -> dict:
        t0 = time.time()

        # KPIs fiscais de um período (somas só de NFs NÃO canceladas + nº de canceladas)
        def _sql_kpis(ini: str, fim: str) -> str:
            return f"""
                SELECT
                    COUNT(CASE WHEN n.DataHoraCanc IS NULL THEN 1 END)     AS qtd_nf,
                    COUNT(CASE WHEN n.DataHoraCanc IS NOT NULL THEN 1 END) AS nfs_canc,
                    SUM(CASE WHEN n.DataHoraCanc IS NULL THEN n.ValTotalNFVnd              ELSE 0 END) AS faturamento,
                    SUM(CASE WHEN n.DataHoraCanc IS NULL THEN n.BaseICMSNFVnd              ELSE 0 END) AS base_icms,
                    SUM(CASE WHEN n.DataHoraCanc IS NULL THEN n.DebICMSNFVnd               ELSE 0 END) AS icms,
                    SUM(CASE WHEN n.DataHoraCanc IS NULL THEN n.BaseCalcICMSSubstTribNFVnd ELSE 0 END) AS base_st,
                    SUM(CASE WHEN n.DataHoraCanc IS NULL THEN n.ValICMSSubstTribNFVnd      ELSE 0 END) AS icms_st,
                    SUM(CASE WHEN n.DataHoraCanc IS NULL THEN n.BaseIPINFVnd               ELSE 0 END) AS base_ipi,
                    SUM(CASE WHEN n.DataHoraCanc IS NULL THEN n.DebIPINFVnd                ELSE 0 END) AS ipi,
                    SUM(CASE WHEN n.DataHoraCanc IS NULL THEN n.IsentasNaoTribICMSNFVnd    ELSE 0 END) AS isentas,
                    SUM(CASE WHEN n.DataHoraCanc IS NULL THEN n.OutrasOperICMSNFVnd        ELSE 0 END) AS outras,
                    SUM(CASE WHEN n.DataHoraCanc IS NULL THEN n.IsentasNaoTribIPINFVnd     ELSE 0 END) AS isentas_ipi,
                    SUM(CASE WHEN n.DataHoraCanc IS NULL THEN n.OutrasOperIPINFVnd         ELSE 0 END) AS outras_ipi,
                    SUM(CASE WHEN n.DataHoraCanc IS NULL THEN n.FreteNFVnd                 ELSE 0 END) AS frete
                FROM Blue.dbo.TbNFVnd n WITH (NOLOCK)
                WHERE n.DtEmisNFVnd >= {ini} AND n.DtEmisNFVnd < {fim}
                  AND n.Fat = 1
            """

        sql_kpi_atual = _sql_kpis(_MES_INI, _MES_FIM)
        sql_kpi_ant   = _sql_kpis(_MES_INI_ANT, _MES_FIM_ANT)

        # ICMS por dia do mês corrente
        sql_diario = f"""
            SELECT DAY(n.DtEmisNFVnd) AS dia,
                COUNT(*)             AS qtd_nf,
                SUM(n.DebICMSNFVnd)  AS icms,
                SUM(n.ValTotalNFVnd) AS faturamento
            FROM Blue.dbo.TbNFVnd n WITH (NOLOCK)
            WHERE n.DtEmisNFVnd >= {_MES_INI} AND n.DtEmisNFVnd < {_MES_FIM}
              AND n.DataHoraCanc IS NULL
              AND n.Fat = 1
            GROUP BY DAY(n.DtEmisNFVnd)
            ORDER BY dia
        """

        # Evolução mensal (12 meses)
        sql_evo = f"""
            SELECT YEAR(n.DtEmisNFVnd) AS ano, MONTH(n.DtEmisNFVnd) AS mes,
                COUNT(*) AS qtd,
                SUM(n.DebICMSNFVnd)          AS icms,
                SUM(n.ValICMSSubstTribNFVnd) AS icms_st,
                SUM(n.DebIPINFVnd)           AS ipi,
                SUM(n.ValTotalNFVnd)         AS faturamento,
                SUM(n.BaseICMSNFVnd)         AS base_icms
            FROM Blue.dbo.TbNFVnd n WITH (NOLOCK)
            WHERE n.DtEmisNFVnd >= DATEADD(month, DATEDIFF(month, 0, GETDATE()) - 11, 0)
              AND n.DtEmisNFVnd <  {_MES_FIM}
              AND n.DataHoraCanc IS NULL
              AND n.Fat = 1
            GROUP BY YEAR(n.DtEmisNFVnd), MONTH(n.DtEmisNFVnd)
            ORDER BY ano, mes
        """

        # Por CFOP no mês (⋈ catálogo TbCodFiscOper)
        sql_cfop = f"""
            SELECT n.CodFisc,
                MAX(f.AbrevNat) AS descricao,
                MAX(f.Nat)      AS descricao_full,
                COUNT(*)                     AS qtd,
                SUM(n.ValTotalNFVnd)         AS total,
                SUM(n.BaseICMSNFVnd)         AS base_icms,
                SUM(n.DebICMSNFVnd)          AS icms,
                SUM(n.ValICMSSubstTribNFVnd) AS icms_st,
                SUM(n.DebIPINFVnd)           AS ipi,
                SUM(n.IsentasNaoTribICMSNFVnd) AS isentas,
                SUM(n.OutrasOperICMSNFVnd)     AS outras
            FROM Blue.dbo.TbNFVnd n WITH (NOLOCK)
            LEFT JOIN Blue.dbo.TbCodFiscOper f WITH (NOLOCK) ON f.CodFisc = n.CodFisc
            WHERE n.DtEmisNFVnd >= {_MES_INI} AND n.DtEmisNFVnd < {_MES_FIM}
              AND n.DataHoraCanc IS NULL
              AND n.Fat = 1
            GROUP BY n.CodFisc
            ORDER BY total DESC
        """

        # ICMS mensal por CFOP (6 meses) — vira séries no frontend
        sql_cfop_evo = f"""
            SELECT YEAR(n.DtEmisNFVnd) AS ano, MONTH(n.DtEmisNFVnd) AS mes,
                RTRIM(n.CodFisc)    AS cfop,
                SUM(n.DebICMSNFVnd) AS icms
            FROM Blue.dbo.TbNFVnd n WITH (NOLOCK)
            WHERE n.DtEmisNFVnd >= DATEADD(month, DATEDIFF(month, 0, GETDATE()) - 5, 0)
              AND n.DtEmisNFVnd <  {_MES_FIM}
              AND n.DataHoraCanc IS NULL
              AND n.Fat = 1
            GROUP BY YEAR(n.DtEmisNFVnd), MONTH(n.DtEmisNFVnd), RTRIM(n.CodFisc)
            ORDER BY ano, mes
        """

        # Maiores NFs por ICMS no mês (com nome do cliente)
        sql_top_nfs = f"""
            SELECT TOP 10 RTRIM(n.NrNFVnd) AS nr_nf,
                n.DtEmisNFVnd,
                ISNULL(c.NomeFantCli, RTRIM(n.CodRedCliNFVnd)) AS cliente,
                RTRIM(n.CodFisc)  AS cfop,
                n.BaseICMSNFVnd   AS base_icms,
                n.DebICMSNFVnd    AS icms,
                n.ValTotalNFVnd   AS total
            FROM Blue.dbo.TbNFVnd n WITH (NOLOCK)
            LEFT JOIN Blue.dbo.TbCli c WITH (NOLOCK) ON c.CodRedCt = n.CodRedCliNFVnd
            WHERE n.DtEmisNFVnd >= {_MES_INI} AND n.DtEmisNFVnd < {_MES_FIM}
              AND n.DataHoraCanc IS NULL
              AND n.Fat = 1
            ORDER BY n.DebICMSNFVnd DESC
        """

        # Tributação configurada por item (cadastro TbTribItem)
        sql_dist = """
            SELECT t.TpTribItem, t.TribSaiItem, COUNT(DISTINCT t.CodItem) AS qtd_itens
            FROM Blue.dbo.TbTribItem t WITH (NOLOCK)
            GROUP BY t.TpTribItem, t.TribSaiItem
            ORDER BY qtd_itens DESC
        """
        sql_itens = f"""
            SELECT TOP 200 i.CodItem,
                MAX(i.DescrItem)  AS DescrItem,
                MAX(i.DescrMarca) AS marca,
                SUM(i.QtdItem)        AS qtd_vendida,
                SUM(i.PrecoVndTotItem) AS valor_vendido,
                MAX(t.TpTribItem)    AS TpTribItem,
                MAX(t.TribSaiItem)   AS TribSaiItem,
                MAX(t.CodUFTribItem) AS uf_trib
            FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
            LEFT JOIN (
                SELECT CodItem, MAX(TpTribItem) AS TpTribItem,
                       MAX(TribSaiItem) AS TribSaiItem, MAX(CodUFTribItem) AS CodUFTribItem
                FROM Blue.dbo.TbTribItem WITH (NOLOCK) GROUP BY CodItem
            ) t ON t.CodItem = i.CodItem
            WHERE i.DtVnd >= {_MES_INI} AND i.DtVnd < {_MES_FIM}
              AND i.CodPlanoVnd NOT IN ('{_pl}')
            GROUP BY i.CodItem
            ORDER BY valor_vendido DESC
        """

        # Regras PIS/COFINS configuradas (cadastro — tabela pequena)
        sql_piscofins = """
            SELECT TOP 20 RTRIM(p.DescrConjTribPisCofins) AS descricao,
                RTRIM(p.CodSitTribPIS)    AS cst_pis,
                p.AliqPIS                 AS aliq_pis,
                RTRIM(p.CodSitTribCOFINS) AS cst_cofins,
                p.AliqCOFINS              AS aliq_cofins
            FROM Blue.dbo.TbTribPisCofins p WITH (NOLOCK)
            ORDER BY p.CodTribPisCofins
        """

        _all_sql = {
            "kpi":       sql_kpi_atual,
            "kpi_ant":   sql_kpi_ant,
            "diario":    sql_diario,
            "evo":       sql_evo,
            "cfop":      sql_cfop,
            "cfop_evo":  sql_cfop_evo,
            "top_nfs":   sql_top_nfs,
            "dist":      sql_dist,
            "itens":     sql_itens,
            "piscofins": sql_piscofins,
        }
        _res: dict[str, pd.DataFrame] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(db.new_conn_query, sql): key
                       for key, sql in _all_sql.items()}
            for f in concurrent.futures.as_completed(futures):
                key = futures[f]
                try:
                    _res[key] = f.result()
                except Exception as e:
                    logger.error("[Imposto] Erro paralelo [%s]: %s", key, e)
                    _res[key] = pd.DataFrame()

        # ── KPIs + comparativo com o mês anterior ──────────────────────
        kpis     = self._kpis_de(_res.get("kpi", pd.DataFrame()))
        kpis_ant = self._kpis_de(_res.get("kpi_ant", pd.DataFrame()))
        deltas = {
            "icms":        round(kpis["icms"] - kpis_ant["icms"], 2),
            "faturamento": round(kpis["faturamento"] - kpis_ant["faturamento"], 2),
            "aliquota":    round(kpis["aliquota_efetiva"] - kpis_ant["aliquota_efetiva"], 2),
            "qtd_nf":      kpis["qtd_nf"] - kpis_ant["qtd_nf"],
        }

        # ── ICMS diário do mês ─────────────────────────────────────────
        icms_diario = []
        df_d = _res.get("diario", pd.DataFrame())
        if df_d is not None and not df_d.empty:
            for _, r in df_d.iterrows():
                icms_diario.append({
                    "dia":         f"{int(r['dia']):02d}",
                    "qtd_nf":      int(r['qtd_nf'] or 0),
                    "icms":        float(r['icms'] or 0),
                    "faturamento": float(r['faturamento'] or 0),
                })

        # ── Evolução mensal 12m ────────────────────────────────────────
        evolucao_mensal = []
        df_evo = _res.get("evo", pd.DataFrame())
        if df_evo is not None and not df_evo.empty:
            for _, r in df_evo.iterrows():
                bi = float(r['base_icms'] or 0)
                ic = float(r['icms'] or 0)
                evolucao_mensal.append({
                    "mes":         f"{int(r['mes']):02d}/{int(r['ano'])}",
                    "icms":        ic,
                    "icms_st":     float(r['icms_st'] or 0),
                    "ipi":         float(r['ipi'] or 0),
                    "faturamento": float(r['faturamento'] or 0),
                    "qtd":         int(r['qtd'] or 0),
                    "aliquota":    (ic / bi * 100) if bi else 0.0,
                })

        # ── Por CFOP no mês + resumo dentro/fora do estado ─────────────
        por_cfop = []
        resumo_uf_map: dict = {}
        tot_icms_mes = kpis["icms"] or 0.0
        df_cfop = _res.get("cfop", pd.DataFrame())
        if df_cfop is not None and not df_cfop.empty:
            for _, r in df_cfop.iterrows():
                cod = (str(r['CodFisc']) if r['CodFisc'] is not None else "").strip()
                uf  = self._classifica_uf(cod)
                tot = float(r['total'] or 0)
                ic  = float(r['icms'] or 0)
                desc = (r['descricao'] or r['descricao_full'] or "—")
                por_cfop.append({
                    "cfop":      cod,
                    "descricao": str(desc).strip(),
                    "qtd":       int(r['qtd'] or 0),
                    "total":     tot,
                    "base_icms": float(r['base_icms'] or 0),
                    "icms":      ic,
                    "icms_st":   float(r['icms_st'] or 0),
                    "ipi":       float(r['ipi'] or 0),
                    "isentas":   float(r['isentas'] or 0),
                    "outras":    float(r['outras'] or 0),   # oper. c/ ST retido na origem
                    "pct_icms":  round(ic / tot_icms_mes * 100, 1) if tot_icms_mes else 0.0,
                    "uf":        uf,
                    "st":        cod in self._CFOP_ST,
                })
                acc = resumo_uf_map.setdefault(uf, {"label": uf, "total": 0.0, "icms": 0.0})
                acc["total"] += tot
                acc["icms"]  += ic
        resumo_uf = sorted(resumo_uf_map.values(), key=lambda x: x["total"], reverse=True)

        # ── Evolução 6m por CFOP (top 5 por ICMS acumulado) ────────────
        cfop_evolucao, cfop_series = [], []
        df_ce = _res.get("cfop_evo", pd.DataFrame())
        if df_ce is not None and not df_ce.empty:
            df_ce = df_ce.copy()
            df_ce["icms"] = pd.to_numeric(df_ce["icms"], errors="coerce").fillna(0.0)
            cfop_series = (df_ce.groupby("cfop")["icms"].sum()
                           .sort_values(ascending=False).head(5).index.tolist())
            meses_map: dict = {}
            for _, r in df_ce.iterrows():
                mes_lbl = f"{int(r['mes']):02d}/{int(r['ano'])}"
                row = meses_map.setdefault(mes_lbl, {"mes": mes_lbl})
                if r["cfop"] in cfop_series:
                    row[r["cfop"]] = round(float(r["icms"]), 2)
            cfop_evolucao = list(meses_map.values())
            for row in cfop_evolucao:               # zera séries ausentes no mês
                for s in cfop_series:
                    row.setdefault(s, 0.0)

        # ── Maiores NFs do mês por ICMS ────────────────────────────────
        top_nfs = []
        df_nfs = _res.get("top_nfs", pd.DataFrame())
        if df_nfs is not None and not df_nfs.empty:
            for _, r in df_nfs.iterrows():
                dt = r['DtEmisNFVnd']
                top_nfs.append({
                    "nr_nf":     str(r['nr_nf'] or "—").strip(),
                    "data":      dt.strftime("%Y-%m-%d") if pd.notna(dt) else None,
                    "cliente":   str(r['cliente'] or "—").strip(),
                    "cfop":      str(r['cfop'] or "—").strip(),
                    "base_icms": float(r['base_icms'] or 0),
                    "icms":      float(r['icms'] or 0),
                    "total":     float(r['total'] or 0),
                })

        # ── Tributação por item (cadastro + vendidos no mês) ──────────
        trib_distribuicao = []
        df_dist = _res.get("dist", pd.DataFrame())
        if df_dist is not None and not df_dist.empty:
            for _, r in df_dist.iterrows():
                tp  = (str(r['TpTribItem']).strip() if r['TpTribItem'] is not None else "—")
                sai = r['TribSaiItem']
                sai = "—" if sai is None or pd.isna(sai) else str(int(sai)) if float(sai).is_integer() else str(sai)
                trib_distribuicao.append({
                    "label":     f"Trib. Saída {sai}" + (f" ({tp})" if tp not in ("—", "P") else ""),
                    "tp_trib":   tp,
                    "trib_sai":  sai,
                    "qtd_itens": int(r['qtd_itens'] or 0),
                })

        itens_tributacao = []
        df_itens = _res.get("itens", pd.DataFrame())
        if df_itens is not None and not df_itens.empty:
            for _, r in df_itens.iterrows():
                sai = r['TribSaiItem']
                sai = "—" if sai is None or pd.isna(sai) else str(int(sai)) if float(sai).is_integer() else str(sai)
                itens_tributacao.append({
                    "cod_item":      str(r['CodItem']).strip() if r['CodItem'] is not None else "—",
                    "descricao":     (str(r['DescrItem']).strip() if r['DescrItem'] is not None else "—"),
                    "marca":         (str(r['marca']).strip() if r['marca'] is not None else "—"),
                    "qtd_vendida":   float(r['qtd_vendida'] or 0),
                    "valor_vendido": float(r['valor_vendido'] or 0),
                    "tp_trib":       (str(r['TpTribItem']).strip() if r['TpTribItem'] is not None else "—"),
                    "trib_sai":      sai,
                    "uf_trib":       (str(r['uf_trib']).strip() if r['uf_trib'] is not None else "—"),
                })

        # ── Regras PIS/COFINS configuradas ─────────────────────────────
        pis_cofins = []
        df_pc = _res.get("piscofins", pd.DataFrame())
        if df_pc is not None and not df_pc.empty:
            for _, r in df_pc.iterrows():
                pis_cofins.append({
                    "descricao":   str(r['descricao'] or "—").strip(),
                    "cst_pis":     str(r['cst_pis'] or "—").strip(),
                    "aliq_pis":    float(r['aliq_pis'] or 0),
                    "cst_cofins":  str(r['cst_cofins'] or "—").strip(),
                    "aliq_cofins": float(r['aliq_cofins'] or 0),
                })

        logger.info("[Imposto] analisar() concluído em %.1fs", time.time() - t0)
        return {
            "mes_referencia":    datetime.now().strftime("%m/%Y"),
            "kpis":              kpis,
            "kpis_ant":          kpis_ant,
            "deltas":            deltas,
            "icms_diario":       icms_diario,
            "evolucao_mensal":   evolucao_mensal,
            "por_cfop":          por_cfop,
            "resumo_uf":         resumo_uf,
            "cfop_evolucao":     cfop_evolucao,
            "cfop_series":       cfop_series,
            "top_nfs":           top_nfs,
            "trib_distribuicao": trib_distribuicao,
            "itens_tributacao":  itens_tributacao,
            "pis_cofins":        pis_cofins,
            "ultimo_update":     datetime.now().strftime("%H:%M:%S"),
        }

    def analisar_filtrado(self, filtros: dict) -> dict:
        return self.resultado or self.analisar()


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
        # Funil/KPIs de orçamento na FONTE REAL: TbOrcPedVnd por DtOrcPedVnd
        # (validado contra o BI do usuário em 17/07/2026: OrcPedVnd=1 → 952/
        # bateu com o gabarito de referência (diferença de 4 conversões pós-conferência)
        # ocorridas entre o print e a medição — banco vivo).
        #   emitidos (IN 1,2) = em_aberto (=1) + convertidos (=2) → taxa ≤ 100%.
        #   valor_orcado = SUM dos EM ABERTO (pipeline real de orçamentos).
        def _sql_orc_kpis(ini: str, fim: str) -> str:
            return f"""
            SELECT
                COUNT(*)                                    AS total_orcamentos,
                COUNT(CASE WHEN o.OrcPedVnd = 2 THEN 1 END) AS total_convertidos,
                COUNT(CASE WHEN o.OrcPedVnd = 1 THEN 1 END) AS em_aberto,
                COUNT(nf.nr)                                AS faturadas,
                SUM(CASE WHEN nf.nr IS NOT NULL
                         THEN o.ValTotalOrcPedVnd ELSE 0 END) AS valor_faturadas,
                SUM(CASE WHEN o.OrcPedVnd = 1 THEN o.ValTotalOrcPedVnd ELSE 0 END) AS valor_orcado,
                SUM(CASE WHEN o.OrcPedVnd = 2 THEN o.ValTotalOrcPedVnd ELSE 0 END) AS valor_convertido
            FROM Blue.dbo.TbOrcPedVnd o WITH (NOLOCK)
            LEFT JOIN (
                SELECT DISTINCT TRY_CAST(n.NrOrcPedVnd AS INT) AS nr
                FROM Blue.dbo.TbNFVnd n WITH (NOLOCK)
                WHERE n.DataHoraCanc IS NULL AND n.Fat = 1
                  AND n.NrOrcPedVnd IS NOT NULL
            ) nf ON nf.nr = TRY_CAST(o.NrOrcPedVnd AS INT)
            WHERE o.OrcPedVnd IN (1, 2)
              AND o.DtOrcPedVnd >= {ini} AND o.DtOrcPedVnd < {fim}
        """

        df_conv = db.new_conn_query(_sql_orc_kpis(_MES_INI, _MES_FIM))
        logger.info("[CRM] df_conv (TbOrcPedVnd): emitidos=%s abertos=%s | valor_orcado=%s%s",
                    df_conv["total_orcamentos"].iloc[0] if not df_conv.empty else "N/A",
                    df_conv["em_aberto"].iloc[0] if not df_conv.empty else "N/A",
                    df_conv["valor_orcado"].iloc[0] if not df_conv.empty else "N/A",
                    f" | erro: {db.last_error}" if db.last_error else "")

        # ── KPIs do mês anterior (para deltas — mesma base TbOrcPedVnd) ──
        _df_ant = db.new_conn_query(_sql_orc_kpis(_MES_INI_ANT, _MES_FIM_ANT))
        df_anterior = _df_ant.rename(columns={
            "total_orcamentos": "total_orc_ant",
            "total_convertidos": "total_conv_ant",
            "valor_orcado": "valor_orc_ant",
        }) if not _df_ant.empty else _df_ant

        # Faturamento líquido (mesma base do Dashboard/Vendas) para a nova taxa:
        # Taxa de Conversão = fat_liq do mês ÷ valor EM NEGOCIAÇÃO (definição do usuário)
        def _sql_fatliq(ini: str, fim: str) -> str:
            return f"""
            SELECT SUM(v.ValVndTotal) AS fat_liq
            FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
            WHERE v.DtVnd >= {ini} AND v.DtVnd < {fim} {_EXCLUIR_PLANO}
        """
        _fat_liq     = _safe_float(db.new_conn_query(_sql_fatliq(_MES_INI, _MES_FIM)), "fat_liq")
        _fat_liq_ant = _safe_float(db.new_conn_query(_sql_fatliq(_MES_INI_ANT, _MES_FIM_ANT)), "fat_liq")

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
        # new_conn_query: conexão própria (90s) — alimenta TODA a seção Equipe
        # de Vendas do front; no lock compartilhado (45s) estourava HYT00 no
        # rush pós-boot e a seção inteira ficava "Sem dados".
        df_ranking = db.new_conn_query(f"""
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
        df_canc_vend = db.new_conn_query(f"""
            SELECT TOP 20
                vn.Vendedor,
                COUNT(*) AS cancelados
            FROM Blue.dbo.vwVndDoc d WITH (NOLOCK)
            INNER JOIN (
                SELECT DISTINCT CodVend, MAX(Vendedor) AS Vendedor
                FROM Blue.dbo.vmVndDoc WITH (NOLOCK)
                WHERE DtVnd >= DATEADD(month, -12, GETDATE())
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
        # REMOVIDA (Parte AG): a query legada juntava vmVndDoc/vmVndItemDoc SEM
        # filtro de data e com join NrOrcPedVnd = NrDoc (numerações distintas —
        # ver comentário do df_ranking), estourando HYT00 em todo ciclo (~90s
        # perdidos). Nenhum consumidor: front usa ranking_vendedores; desktop
        # usa meta_vendedor. Chave mantida vazia por compatibilidade de payload.
        df_conv_vend = pd.DataFrame()

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
        _fatu = _safe_int(df_conv, "faturadas")
        # Taxa de Conversão (definição do usuário, 17/07): faturamento líquido
        # do mês ÷ valor EM NEGOCIAÇÃO = universo movimentado (1+2), pois quem
        # virou pedido também passou por negociação
        _vneg = _vlro + _vlrc
        _taxa = round(_fat_liq / _vneg * 100, 1) if _vneg > 0 else 0.0
        _tick = round(_vlrc / _conv, 2) if _conv > 0 else 0.0
        _canc = _safe_int(df_cancelados, "cancelados") if not df_cancelados.empty else 0
        # Em Negociação = orçamentos EM ABERTO (OrcPedVnd=1) — contagem direta da
        # TbOrcPedVnd (952/R$4,0M em 17/07), não mais derivada por subtração.
        _ativ = _safe_int(df_conv, "em_aberto")
        _orc_ant  = _safe_int(df_anterior, "total_orc_ant")
        _conv_ant = _safe_int(df_anterior, "total_conv_ant")
        _vlro_ant = _safe_float(df_anterior, "valor_orc_ant")
        _vneg_ant = _vlro_ant + _safe_float(df_anterior, "valor_convertido")
        _taxa_ant = round(_fat_liq_ant / _vneg_ant * 100, 1) if _vneg_ant > 0 else 0.0
        _delta_taxa  = round(_taxa - _taxa_ant, 1)
        _delta_vlro  = round(_vlro - _vlro_ant, 2)
        _total_d = _orc if _orc > 0 else 1
        _distribuicao = [
            {"status": "Convertidos",   "qtd": _conv, "pct": round(_conv / _total_d * 100, 1)},
            {"status": "Em Negociação", "qtd": _ativ, "pct": round(_ativ / _total_d * 100, 1)},
            {"status": "Cancelados",    "qtd": _canc, "pct": round(_canc / _total_d * 100, 1)},
        ]
        # Funil (definição do usuário, 17/07): Em Negociação (em aberto, do
        # universo movimentado 1+2) · Fechadas (=2) · FATURADAS (fechadas com
        # NF Fat=1 vinculada via TbNFVnd.NrOrcPedVnd). % sobre o universo.
        _funil_etapas = [
            {"etapa": "Em Negociação", "qtd": _orc,  "pct": 100},
            {"etapa": "Fechadas",      "qtd": _conv, "pct": round(_conv / _total_d * 100, 1)},
            {"etapa": "Faturadas",     "qtd": _fatu, "pct": round(_fatu / _total_d * 100, 1)},
        ]

        # ── CRM v4 · Carteira e oportunidades (2026-07-15) ────────
        # Clientes ativos no mês — número REAL (substitui o proxy len(top10))
        df_ativos = db.new_conn_query(f"""
            SELECT COUNT(DISTINCT v.CodCli) AS ativos
            FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
            WHERE v.DtVnd >= {_MES_INI} AND v.DtVnd < {_MES_FIM} {_EXCLUIR_PLANO}
        """)
        qtd_ativos_real = _safe_int(df_ativos, "ativos")

        # Clientes NOVOS — primeira compra da HISTÓRIA dentro do mês corrente.
        # (HAVING MIN(DtVnd) garante que todas as compras do cliente são deste mês,
        #  então SUM(ValVndTotal) == valor do mês.)
        df_novos = db.new_conn_query(f"""
            SELECT v.CodCli,
                MAX(v.NomeFantCli) AS nome_cliente,
                MAX(v.Vendedor)    AS vendedor,
                MIN(v.DtVnd)       AS primeira_compra,
                SUM(v.ValVndTotal) AS valor_mes
            FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
            GROUP BY v.CodCli
            HAVING MIN(v.DtVnd) >= {_MES_INI}
            ORDER BY valor_mes DESC
        """)
        logger.info("[CRM] clientes novos (1ª compra no mês): %d", len(df_novos))

        # Novos CADASTROS no mês (TbCli.dthrcadcli) — clientes registrados, com ou sem compra
        df_cad = db.new_conn_query(f"""
            SELECT COUNT(*) AS n FROM Blue.dbo.TbCli WITH (NOLOCK)
            WHERE dthrcadcli >= {_MES_INI} AND dthrcadcli < {_MES_FIM}
        """)

        # Orçamentos ABERTOS (follow-up) — OrcPedVnd=1 nos últimos 90 dias.
        # Quando o orçamento converte ele passa a OrcPedVnd=2, então 1 = ainda aberto.
        df_orc_ab = db.new_conn_query("""
            SELECT TOP 100
                o.NrOrcPedVnd,
                o.DtOrcPedVnd,
                DATEDIFF(day, o.DtOrcPedVnd, GETDATE()) AS dias_aberto,
                o.ValTotalOrcPedVnd AS valor,
                ISNULL(c.NomeFantCli, RTRIM(o.CodRedCtRecOrcPedVnd)) AS cliente,
                ISNULL(vn.Vendedor,  RTRIM(o.VendOrcPedVnd))         AS vendedor
            FROM Blue.dbo.TbOrcPedVnd o WITH (NOLOCK)
            LEFT JOIN Blue.dbo.TbCli c WITH (NOLOCK)
                ON TRY_CAST(c.CodRedCt AS INT) = TRY_CAST(o.CodRedCtRecOrcPedVnd AS INT)
            LEFT JOIN (
                SELECT CodVend, MAX(Vendedor) AS Vendedor
                FROM Blue.dbo.vmVndDoc WITH (NOLOCK) GROUP BY CodVend
            ) vn ON vn.CodVend = o.VendOrcPedVnd
            WHERE o.OrcPedVnd = 1
              AND o.DtOrcPedVnd >= DATEADD(day, -90, GETDATE())
            ORDER BY o.ValTotalOrcPedVnd DESC
        """)
        df_orc_tot = db.new_conn_query("""
            SELECT COUNT(*) AS qtd, SUM(o.ValTotalOrcPedVnd) AS valor
            FROM Blue.dbo.TbOrcPedVnd o WITH (NOLOCK)
            WHERE o.OrcPedVnd = 1
              AND o.DtOrcPedVnd >= DATEADD(day, -90, GETDATE())
        """)

        return {
            # KPIs
            "total_orcamentos":   _orc,
            "total_convertidos":  _conv,
            "taxa_conversao_pct": _taxa,
            "valor_orcado":       _vlro,
            "fat_liq_mes":        _fat_liq,
            "fat_liq_ant":        _fat_liq_ant,
            "valor_faturadas":    _safe_float(df_conv, "valor_faturadas"),
            "valor_convertido":   _vlrc,
            "ticket_medio":       _tick,
            "delta_taxa_conv":    _delta_taxa,
            "delta_valor_orcado": _delta_vlro,
            "taxa_conversao_ant": _taxa_ant,
            "valor_orcado_ant":   _vlro_ant,
            "qtd_inativos":       len(df_inativos_v),
            "qtd_em_risco":       int((df_risco["dias_inativo"] >= DIAS_RISCO).sum()) if not df_risco.empty else 0,
            "qtd_ativos_mes":     len(df_top_cli),
            # CRM v4 — carteira e oportunidades
            "qtd_ativos_mes_real":  qtd_ativos_real,
            "clientes_novos_qtd":   len(df_novos),
            "clientes_novos_lista": df_novos.head(50).to_dict("records"),
            "novos_cadastros_mes":  _safe_int(df_cad, "n"),
            "orc_abertos_qtd":      _safe_int(df_orc_tot, "qtd"),
            "orc_abertos_valor":    _safe_float(df_orc_tot, "valor"),
            "orc_abertos_lista":    df_orc_ab.to_dict("records"),
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
        if has_vendedor and not has_marca:
            # Mesma base do funil global (TbOrcPedVnd); vendedor via VendOrcPedVnd
            # mapeado por nome→CodVend (vmVndDoc, janela de 24m p/ não varrer tudo).
            df_conv = db.new_conn_query(f"""
                SELECT
                    COUNT(*)                                    AS total_orcamentos,
                    COUNT(CASE WHEN o.OrcPedVnd = 2 THEN 1 END) AS total_convertidos,
                    COUNT(CASE WHEN o.OrcPedVnd = 1 THEN 1 END) AS em_aberto,
                    CAST(COUNT(CASE WHEN o.OrcPedVnd = 2 THEN 1 END) AS FLOAT)
                        / NULLIF(COUNT(*), 0) * 100             AS taxa_conversao_pct,
                    SUM(CASE WHEN o.OrcPedVnd = 1 THEN o.ValTotalOrcPedVnd ELSE 0 END) AS valor_orcado,
                    SUM(CASE WHEN o.OrcPedVnd = 2 THEN o.ValTotalOrcPedVnd ELSE 0 END) AS valor_convertido
                FROM Blue.dbo.TbOrcPedVnd o WITH (NOLOCK)
                WHERE o.OrcPedVnd IN (1, 2)
                  AND o.DtOrcPedVnd >= {_MES_INI} AND o.DtOrcPedVnd < {_MES_FIM}
                  AND o.VendOrcPedVnd IN (
                      SELECT DISTINCT v.CodVend FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
                      WHERE v.DtVnd >= DATEADD(month, -24, GETDATE()) AND v.Vendedor LIKE ?
                  )
            """, [f"%{filtros['vendedor'][:100]}%"])
        else:
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

        logger.info("[CRM filtrado] iniciando query | filtros=%s", filtros)

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
        _ativ = (_safe_int(df_conv, "em_aberto")
                 if not df_conv.empty and "em_aberto" in df_conv.columns
                 else max(_orc - _conv - _canc, 0))
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
        # Marca timestamp atualizado para que o frontend possa confirmar que dados filtrados chegaram
        base["ultimo_update"] = datetime.now().strftime("%H:%M:%S") + " (f)"
        return base


# ──────────────────────────────────────────────────────────────────
#  BOT CLIENTES (carteira) — análise AGREGADA de todos os clientes
#  (a aba "Cliente" singular é o perfil 360º individual, sob demanda)
# ──────────────────────────────────────────────────────────────────
class BotClientes(BaseBot):
    """Carteira: segmentação por recência, Curva ABC de clientes (receita 12m),
    concentração, evolução de ativos/mês e top clientes. 3 consultas paralelas
    (somente leitura). name == tab key 'cliente_comportamento'."""

    def __init__(self):
        super().__init__("cliente_comportamento")

    def analisar(self) -> dict:
        t0 = time.time()
        sqls = {
            "base": f"""
                SELECT v.CodCli, MAX(v.NomeFantCli) AS nome,
                    COUNT(DISTINCT v.NrDoc) AS pedidos,
                    SUM(v.ValVndTotal)      AS receita,
                    MAX(v.DtVnd)            AS ultima_compra
                FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
                WHERE v.DtVnd >= DATEADD(month, -12, GETDATE()) {_EXCLUIR_PLANO}
                GROUP BY v.CodCli
            """,
            "evolucao": f"""
                SELECT YEAR(v.DtVnd) AS ano, MONTH(v.DtVnd) AS mes,
                    COUNT(DISTINCT v.CodCli) AS ativos,
                    SUM(v.ValVndTotal)       AS receita
                FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
                WHERE v.DtVnd >= DATEADD(month, -12, GETDATE()) {_EXCLUIR_PLANO}
                GROUP BY YEAR(v.DtVnd), MONTH(v.DtVnd)
                ORDER BY ano, mes
            """,
            "novos": f"""
                SELECT COUNT(*) AS novos FROM (
                    SELECT v.CodCli FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
                    GROUP BY v.CodCli
                    HAVING MIN(v.DtVnd) >= {_MES_INI}
                ) t
            """,
        }
        _res: dict = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futs = {pool.submit(db.new_conn_query, q, None, 30000): k for k, q in sqls.items()}
            for f in concurrent.futures.as_completed(futs):
                k = futs[f]
                try:
                    _res[k] = f.result()
                except Exception as e:
                    logger.error("[Clientes] Erro paralelo [%s]: %s", k, e)
                    _res[k] = pd.DataFrame()

        df = _res.get("base", pd.DataFrame())
        _now = datetime.now().strftime("%H:%M:%S")
        if df is None or df.empty:
            return {"kpis": {}, "segmentacao": [], "abc_resumo": [],
                    "evolucao": [], "top_clientes": [], "ultimo_update": _now}

        df = df.copy()
        df["CodCli"] = df["CodCli"].astype(str).str.strip()
        df["nome"] = df["nome"].fillna("—").astype(str).str.strip()
        for c in ("pedidos", "receita"):
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
        df["ultima_compra"] = pd.to_datetime(df["ultima_compra"], errors="coerce")
        _hoje = pd.Timestamp.now()
        df["dias"] = (_hoje - df["ultima_compra"]).dt.days.fillna(9999).astype(int)

        # Curva ABC por receita 12m (A=80% · B=95% · C=resto)
        df = df.sort_values("receita", ascending=False).reset_index(drop=True)
        tot = float(df["receita"].sum())
        acum = df["receita"].cumsum() / tot if tot > 0 else df["receita"] * 0
        df["abc"] = ["A" if a <= 0.80 else "B" if a <= 0.95 else "C" for a in acum]

        # Segmentação por recência (mesmas faixas do Cliente 360º)
        _FAIXAS = [(0, 30, "Ativo (até 30d)"), (31, 60, "Atenção (31–60d)"),
                   (61, 90, "Em risco (61–90d)"), (91, 99999, "Inativo (+90d)")]
        segmentacao = [{"faixa": lbl,
                        "qtd": int(((df["dias"] >= lo) & (df["dias"] <= hi)).sum()),
                        "receita": float(df.loc[(df["dias"] >= lo) & (df["dias"] <= hi), "receita"].sum())}
                       for lo, hi, lbl in _FAIXAS]

        abc_resumo = []
        for cls in ("A", "B", "C"):
            sub = df[df["abc"] == cls]
            abc_resumo.append({"classe": cls, "clientes": int(len(sub)),
                               "receita": float(sub["receita"].sum()),
                               "pct_receita": round(float(sub["receita"].sum()) / tot * 100, 1) if tot > 0 else 0.0})

        top10_pct = round(float(df.head(10)["receita"].sum()) / tot * 100, 1) if tot > 0 else 0.0
        _ini_mes = _hoje.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        ativos_mes = int((df["ultima_compra"] >= _ini_mes).sum())

        top_clientes = [{"CodCli": r["CodCli"], "nome": r["nome"],
                         "receita": round(float(r["receita"]), 2),
                         "pedidos": int(r["pedidos"]),
                         "ticket": round(float(r["receita"]) / r["pedidos"], 2) if r["pedidos"] > 0 else 0.0,
                         "ultima_compra": r["ultima_compra"].strftime("%Y-%m-%d") if pd.notna(r["ultima_compra"]) else None,
                         "dias": int(r["dias"]), "abc": r["abc"]}
                        for _, r in df.head(50).iterrows()]

        evolucao = []
        df_e = _res.get("evolucao", pd.DataFrame())
        if df_e is not None and not df_e.empty:
            evolucao = [{"mes": "%02d/%d" % (int(r["mes"]), int(r["ano"])),
                         "ativos": int(r["ativos"]), "receita": float(r["receita"] or 0)}
                        for _, r in df_e.iterrows()]

        _tot_ped = float(df["pedidos"].sum())
        kpis = {
            "clientes_12m": int(len(df)),
            "ativos_mes":   ativos_mes,
            "novos_mes":    _safe_int(_res.get("novos", pd.DataFrame()), "novos"),
            "receita_12m":  round(tot, 2),
            "ticket_medio": round(tot / _tot_ped, 2) if _tot_ped > 0 else 0.0,
            "top10_pct":    top10_pct,
        }
        logger.info("[Clientes] analisar() concluído em %.1fs (%d clientes)", time.time() - t0, len(df))
        return {"kpis": kpis, "segmentacao": segmentacao, "abc_resumo": abc_resumo,
                "evolucao": evolucao, "top_clientes": top_clientes, "ultimo_update": _now}

    def analisar_filtrado(self, filtros: dict) -> dict:
        return self.resultado or self.analisar()


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
                for name in ("dashboard", "vendas", "estoque", "financeiro", "crm", "imposto", "cliente_comportamento")
            }
        else:
            self.bots: dict[str, BaseBot] = {
                "dashboard":  BotDashboard(),
                "vendas":     BotVendas(),
                "estoque":    BotEstoque(),
                "financeiro": BotFinanceiro(),
                "crm":        BotCRM(),
                "imposto":    BotImposto(),
                "cliente_comportamento": BotClientes(),
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
        for i, bot in enumerate(self.bots.values()):
            bot.boot_delay = i * 20  # 0s, 20s, ... 120s — espalha o rush de boot
            bot.start()
        logger.info("Todos os bots iniciados (boot escalonado: 20s entre bots).")

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
