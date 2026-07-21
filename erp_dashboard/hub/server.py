# hub/server.py
import asyncio
import concurrent.futures as _cf
import json
import logging
import math
import pathlib
import re as _re
import secrets
import time

import pandas as _pd
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

from config.settings import DASHBOARD_PASSWORD, ACCESS_PROFILES, ALERTAS
from core.cache import cache as _cache, _clean_nan as _clean_nan

logger = logging.getLogger(__name__)

# ── Globals ───────────────────────────────────────────────────────────
_loop: asyncio.AbstractEventLoop | None = None
_sse_queues: list[asyncio.Queue] = []
_manager = None  # BotManager — definido por run_hub()
_METAS_PATH = pathlib.Path(__file__).parent.parent / "config" / "metas.json"


# ── Lifespan ──────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _loop
    _loop = asyncio.get_event_loop()
    yield


# ── App ───────────────────────────────────────────────────────────────
app = FastAPI(title="G2 Analytics API", version="2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Auth ──────────────────────────────────────────────────────────────
# _tokens[token] = {"exp": float, "tabs": list}  (tabs = abas permitidas; "*" = todas)
_tokens: dict[str, dict] = {}
TOKEN_TTL = 8 * 3600  # 8 horas
_bearer = HTTPBearer()


def _purge_expired():
    now = time.time()
    for t in [k for k, info in _tokens.items() if info["exp"] < now]:
        del _tokens[t]


def verify_token(creds: HTTPAuthorizationCredentials = Depends(_bearer)) -> str:
    token = creds.credentials
    info = _tokens.get(token)
    if info is None or time.time() > info["exp"]:
        _tokens.pop(token, None)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado",
        )
    return token


_bearer_optional = HTTPBearer(auto_error=False)

async def verify_token_or_query(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_optional),
    token: Optional[str] = Query(default=None),
) -> str:
    t = (creds.credentials if creds else None) or token
    info = _tokens.get(t) if t else None
    if not t or info is None or time.time() > info["exp"]:
        if t:
            _tokens.pop(t, None)
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")
    return t


def _tabs_for(token: str) -> list:
    info = _tokens.get(token)
    return info["tabs"] if info else []


def _require_tab(token: str, tab: str):
    """Bloqueia (403) se o perfil do token não inclui a aba pedida."""
    tabs = _tabs_for(token)
    if "*" not in tabs and tab not in tabs:
        raise HTTPException(status_code=403, detail=f"Acesso negado à aba '{tab}'")


class AuthRequest(BaseModel):
    password: str


class MetasPayload(BaseModel):
    meta_mensal_total: float
    metas_individuais: dict[str, float]


@app.post("/auth")
def login(req: AuthRequest):
    tabs = ACCESS_PROFILES.get(req.password)
    if tabs is None:
        raise HTTPException(status_code=400, detail="Senha incorreta")
    _purge_expired()
    token = secrets.token_urlsafe(32)
    _tokens[token] = {"exp": time.time() + TOKEN_TTL, "tabs": tabs}
    return {"access_token": token, "token_type": "bearer", "tabs": tabs}


# ── Root ──────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "ok", "api": "G2 Analytics v2.0", "docs": "/docs"}


@app.get("/config")
def config_route(_: str = Depends(verify_token)):
    return {"meta_faturamento_mensal": ALERTAS.get("meta_faturamento_mensal", 400000)}


@app.get("/metas")
def get_metas(_: str = Depends(verify_token)):
    if not _METAS_PATH.exists():
        return {"meta_mensal_total": 0.0, "metas_individuais": {}, "ultima_atualizacao": None}
    try:
        data = json.loads(_METAS_PATH.read_text(encoding="utf-8"))
        data.setdefault("meta_mensal_total", 0)
        data.setdefault("metas_individuais", {})
        data.setdefault("ultima_atualizacao", None)
        return data
    except Exception as e:
        logger.error("get_metas erro: %s", e)
        return {"meta_mensal_total": 0.0, "metas_individuais": {}, "ultima_atualizacao": None}


@app.post("/metas")
def post_metas(payload: MetasPayload, token: str = Depends(verify_token)):
    _require_tab(token, "configuracoes")
    # NaN/Infinity passam por 'v < 0' (NaN < 0 é False) e envenenariam o
    # metas.json → 500 permanente no GET /metas. Rejeitar não-finitos.
    if not math.isfinite(payload.meta_mensal_total) or payload.meta_mensal_total < 0:
        raise HTTPException(status_code=422, detail="meta_mensal_total deve ser um número >= 0")
    if any((not math.isfinite(v)) or v < 0 for v in payload.metas_individuais.values()):
        raise HTTPException(status_code=422, detail="Valores individuais devem ser números >= 0")
    data = {
        "meta_mensal_total": payload.meta_mensal_total,
        "metas_individuais": payload.metas_individuais,
        "ultima_atualizacao": datetime.now().isoformat(timespec="seconds"),
    }
    try:
        _METAS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _tmp = _METAS_PATH.with_suffix(".tmp")
        _tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        _tmp.replace(_METAS_PATH)
        return {"ok": True}
    except Exception as e:
        logger.error("[metas] Erro ao salvar: %s", e)
        raise HTTPException(status_code=500, detail="Erro ao salvar metas")


# ── SSE — broadcast chamado de threads dos bots ───────────────────────
def _broadcast_update(bot_name: str, _resultado: dict):
    """Thread-safe: coloca evento nas filas asyncio dos clientes SSE conectados."""
    if not _loop or not _sse_queues:
        return
    payload = {"bot": bot_name, "ts": int(time.time())}
    for q in list(_sse_queues):
        try:
            _loop.call_soon_threadsafe(q.put_nowait, payload)
        except Exception:
            pass


async def _sse_generator(q: asyncio.Queue):
    try:
        # Emit an immediate ping so clients (and tests) can confirm the connection
        yield "event: ping\ndata: {}\n\n"
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=30.0)
                yield f"event: update\ndata: {json.dumps(event)}\n\n"
            except asyncio.TimeoutError:
                yield "event: ping\ndata: {}\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        try:
            _sse_queues.remove(q)
        except ValueError:
            pass


@app.get("/stream")
async def stream(_: str = Depends(verify_token_or_query)):
    q: asyncio.Queue = asyncio.Queue()
    _sse_queues.append(q)
    return StreamingResponse(
        _sse_generator(q),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Endpoints de dados ────────────────────────────────────────────────
@app.get("/status")
def status_route(token: str = Depends(verify_token)):
    # Mostra só os bots das abas do perfil (ex.: vendas não vê Estoque/Financeiro/CRM)
    tabs = _tabs_for(token)
    def _allowed(name: str) -> bool:
        return "*" in tabs or name in tabs
    if _manager is not None:
        return {
            "bots": {
                name: {
                    "status": b.status,
                    "ultimo_update": b.ultimo_update,
                    "erro_msg": b.erro_msg,
                    "seconds_until_next": b.seconds_until_next(),
                }
                for name, b in _manager.bots.items()
                if _allowed(name)
            }
        }
    st = _cache.status()
    return {"bots": {name: info for name, info in st.items() if _allowed(name)}}


# ── Cliente 360º ──────────────────────────────────────────────────────
# Dois modos: ?busca=<termo>  → lista de clientes candidatos (TbCli)
#             ?cod=<CodRedCt> → perfil completo (7 consultas em paralelo)
def _cliente_buscar(termo: str) -> dict:
    from core.database import db
    t = f"%{termo[:80]}%"
    df = db.new_conn_query("""
        SELECT TOP 20 RTRIM(c.CodRedCt) AS cod,
            RTRIM(c.NomeFantCli) AS nome,
            RTRIM(c.RzsCli)      AS razao,
            RTRIM(c.CGCCPFCli)   AS doc,
            RTRIM(c.UFMunicFat)  AS uf,
            c.DtUltCmpCli        AS ultima_compra
        FROM Blue.dbo.TbCli c WITH (NOLOCK)
        WHERE c.NomeFantCli LIKE ? OR c.RzsCli LIKE ?
           OR c.CodRedCt LIKE ? OR c.CGCCPFCli LIKE ?
        ORDER BY c.DtUltCmpCli DESC
    """, [t, t, t, t])
    res = []
    if df is not None and not df.empty:
        for _, r in df.iterrows():
            u = r["ultima_compra"]
            res.append({
                "cod": r["cod"], "nome": r["nome"] or r["razao"] or "—",
                "razao": r["razao"], "doc": r["doc"], "uf": r["uf"],
                "ultima_compra": u.strftime("%Y-%m-%d") if u is not None and not _pd.isna(u) else None,
            })
    return {"modo": "busca", "resultados": res}


def _cliente_perfil(cod: str) -> dict:
    from core.database import db
    cod = cod.strip()[:20]

    sqls = {
        # Cadastro + limite de crédito (TbCli ⋈ TbLimCredCli)
        "cad": ("""
            SELECT RTRIM(c.CodRedCt) AS cod, RTRIM(c.NomeFantCli) AS nome,
                RTRIM(c.RzsCli) AS razao, RTRIM(c.CGCCPFCli) AS doc,
                RTRIM(c.Fone1Cli) AS fone, RTRIM(c.UFMunicFat) AS uf,
                c.dthrcadcli AS cadastro, c.DtUltCmpCli AS ultima_compra_cad,
                RTRIM(c.CodPlanoVndPadrao) AS plano_padrao,
                l.ValLimCred1 AS limite_credito
            FROM Blue.dbo.TbCli c WITH (NOLOCK)
            LEFT JOIN Blue.dbo.TbLimCredCli l WITH (NOLOCK)
                ON l.CodLimCredCli = c.CodLimCredCli
            WHERE c.CodRedCt = ?
        """, [cod]),
        # Documentos 24m (1 pull → KPIs, evolução, vendedores, últimas compras)
        "docs": ("""
            SELECT v.NrDoc, MAX(v.DtVnd) AS DtVnd, MAX(v.Vendedor) AS Vendedor,
                SUM(v.ValVndTotal) AS valor,
                MIN(v.CustoRepTotal) AS custo_min
            FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
            WHERE v.CodCli = ? AND v.DtVnd >= DATEADD(month, -24, GETDATE())
            GROUP BY v.NrDoc
        """, [cod]),
        "primeira": ("SELECT MIN(v.DtVnd) AS primeira FROM Blue.dbo.vmVndDoc v WITH (NOLOCK) WHERE v.CodCli = ?", [cod]),
        "produtos": ("""
            SELECT TOP 10 i.CodItem, MAX(i.DescrItem) AS produto, MAX(i.DescrMarca) AS marca,
                SUM(i.QtdItem) AS qtd, SUM(i.PrecoVndTotItem) AS valor
            FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
            WHERE i.CodCli = ? AND i.DtVnd >= DATEADD(month, -12, GETDATE())
            GROUP BY i.CodItem ORDER BY valor DESC
        """, [cod]),
        "marcas": ("""
            SELECT TOP 8 ISNULL(RTRIM(i.DescrMarca), '—') AS marca,
                SUM(i.PrecoVndTotItem) AS valor, SUM(i.QtdItem) AS qtd
            FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
            WHERE i.CodCli = ? AND i.DtVnd >= DATEADD(month, -12, GETDATE())
            GROUP BY i.DescrMarca ORDER BY valor DESC
        """, [cod]),
        # Títulos em aberto (vmCtRecDetalhe é a visão de abertos do Financeiro)
        "titulos": ("""
            SELECT TOP 20 RTRIM(Documento) AS documento, DtVencimento,
                Valor, RTRIM(Receita) AS receita
            FROM Blue.dbo.vmCtRecDetalhe WITH (NOLOCK)
            WHERE CodCli = ? ORDER BY DtVencimento
        """, [cod]),
        "orcamentos": ("""
            SELECT TOP 10 RTRIM(o.NrOrcPedVnd) AS nr, o.DtOrcPedVnd AS data,
                DATEDIFF(day, o.DtOrcPedVnd, GETDATE()) AS dias_aberto,
                o.ValTotalOrcPedVnd AS valor
            FROM Blue.dbo.TbOrcPedVnd o WITH (NOLOCK)
            WHERE o.OrcPedVnd = 1
              AND TRY_CAST(o.CodRedCtRecOrcPedVnd AS INT) = TRY_CAST(? AS INT)
              AND o.DtOrcPedVnd >= DATEADD(day, -180, GETDATE())
            ORDER BY o.DtOrcPedVnd DESC
        """, [cod]),
    }
    res: dict = {}
    with _cf.ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(db.new_conn_query, sql, prm): k for k, (sql, prm) in sqls.items()}
        for f in _cf.as_completed(futs):
            k = futs[f]
            try:
                res[k] = f.result()
            except Exception as e:
                logger.error("[Cliente360] %s: %s", k, e)
                res[k] = None

    df_cad = res.get("cad")
    if df_cad is None or df_cad.empty:
        return {"modo": "perfil", "erro": f"Cliente '{cod}' não encontrado"}
    c = df_cad.iloc[0]

    def _dt(v, fmt="%Y-%m-%d"):
        return v.strftime(fmt) if v is not None and not _pd.isna(v) else None

    cadastro = {
        "cod": c["cod"], "nome": c["nome"] or c["razao"] or "—", "razao": c["razao"],
        "doc": c["doc"], "fone": c["fone"], "uf": c["uf"],
        "cadastro": _dt(c["cadastro"]), "plano_padrao": c["plano_padrao"],
        "limite_credito": float(c["limite_credito"]) if c["limite_credito"] is not None and not _pd.isna(c["limite_credito"]) else None,
    }

    # ── Derivados dos documentos (24 meses) ───────────────────────
    kpis, evolucao, vendedores, ultimas = {}, [], [], []
    df_d = res.get("docs")
    if df_d is not None and not df_d.empty:
        df_d = df_d.copy()
        df_d["DtVnd"] = _pd.to_datetime(df_d["DtVnd"], errors="coerce")
        for col in ("valor", "custo_min"):
            df_d[col] = _pd.to_numeric(df_d[col], errors="coerce").fillna(0.0)
        df_d["is_dev"] = df_d["custo_min"] < 0
        hoje = _pd.Timestamp.now()
        d12 = df_d[df_d["DtVnd"] >= hoje - _pd.DateOffset(months=12)]
        vnd12 = d12[~d12["is_dev"]]
        ult = df_d["DtVnd"].max()
        n12 = int(len(vnd12))
        # frequência média: dias entre compras nos últimos 12m
        freq = None
        if n12 >= 2:
            dias_span = (vnd12["DtVnd"].max() - vnd12["DtVnd"].min()).days
            freq = round(dias_span / (n12 - 1)) if dias_span > 0 else None
        kpis = {
            "comprado_12m":    float(vnd12["valor"].sum()),
            "pedidos_12m":     n12,
            "ticket_medio":    round(float(vnd12["valor"].sum()) / n12, 2) if n12 else 0.0,
            "devolucoes_12m":  float(d12[d12["is_dev"]]["valor"].sum()),
            "ultima_compra":   _dt(ult),
            "dias_sem_compra": int((hoje - ult).days) if ult is not None and not _pd.isna(ult) else None,
            "freq_media_dias": freq,
        }
        df_m = (df_d[df_d["DtVnd"] >= hoje - _pd.DateOffset(months=12)]
                .assign(mes=lambda x: x["DtVnd"].dt.strftime("%m/%Y"),
                        _ord=lambda x: x["DtVnd"].dt.strftime("%Y%m"))
                .groupby(["_ord", "mes"], as_index=False)
                .agg(valor=("valor", "sum"), pedidos=("NrDoc", "nunique"))
                .sort_values("_ord"))
        evolucao = [{"mes": r["mes"], "valor": round(float(r["valor"]), 2),
                     "pedidos": int(r["pedidos"])} for _, r in df_m.iterrows()]
        df_v = (df_d.groupby("Vendedor", as_index=False)
                .agg(pedidos=("NrDoc", "nunique"), valor=("valor", "sum"),
                     primeira=("DtVnd", "min"), ultima=("DtVnd", "max"))
                .sort_values("ultima", ascending=False))
        vendedores = [{"vendedor": (r["Vendedor"] or "—").strip(),
                       "pedidos": int(r["pedidos"]), "valor": round(float(r["valor"]), 2),
                       "primeira": _dt(r["primeira"]), "ultima": _dt(r["ultima"]),
                       "atual": i == 0}
                      for i, (_, r) in enumerate(df_v.iterrows())]
        ultimas = [{"nr_doc": str(r["NrDoc"]).strip(), "data": _dt(r["DtVnd"]),
                    "vendedor": (r["Vendedor"] or "—").strip(),
                    "valor": round(float(r["valor"]), 2),
                    "devolucao": bool(r["is_dev"])}
                   for _, r in df_d.sort_values("DtVnd", ascending=False).head(15).iterrows()]

    df_p = res.get("primeira")
    primeira = _dt(df_p["primeira"].iloc[0]) if df_p is not None and not df_p.empty else None

    def _recs(key, conv):
        df = res.get(key)
        return [conv(r) for _, r in df.iterrows()] if df is not None and not df.empty else []

    top_produtos = _recs("produtos", lambda r: {
        "cod_item": str(r["CodItem"]).strip(), "produto": (r["produto"] or "—").strip(),
        "marca": (r["marca"] or "—").strip(), "qtd": float(r["qtd"] or 0),
        "valor": float(r["valor"] or 0)})
    top_marcas = _recs("marcas", lambda r: {
        "marca": r["marca"], "valor": float(r["valor"] or 0), "qtd": float(r["qtd"] or 0)})
    orcamentos = _recs("orcamentos", lambda r: {
        "nr": r["nr"], "data": _dt(r["data"]), "dias_aberto": int(r["dias_aberto"] or 0),
        "valor": float(r["valor"] or 0)})

    titulos_lista = _recs("titulos", lambda r: {
        "documento": r["documento"], "vencimento": _dt(r["DtVencimento"]),
        "valor": float(r["Valor"] or 0), "receita": r["receita"]})
    _hoje_str = datetime.now().strftime("%Y-%m-%d")
    tit_venc = [t for t in titulos_lista if t["vencimento"] and t["vencimento"] < _hoje_str]
    titulos = {
        "qtd": len(titulos_lista),
        "valor": round(sum(t["valor"] for t in titulos_lista), 2),
        "vencidos_qtd": len(tit_venc),
        "vencidos_valor": round(sum(t["valor"] for t in tit_venc), 2),
        "lista": titulos_lista,
    }

    return {
        "modo": "perfil", "cadastro": cadastro, "kpis": kpis,
        "cliente_desde": primeira, "evolucao": evolucao,
        "top_produtos": top_produtos, "top_marcas": top_marcas,
        "vendedores": vendedores, "ultimas_compras": ultimas,
        "orcamentos_abertos": orcamentos, "titulos": titulos,
    }


# NOTE: /dados/cliente must be registered BEFORE /dados/{bot_name} to avoid
# FastAPI matching "cliente" as the bot_name path parameter.
@app.get("/dados/painel_pedidos")
def dados_painel_pedidos(token: str = Depends(verify_token)):
    """Esteira de pedidos AO VIVO (vmPainelPedidoVndConf) — consulta direta,
    sem bot/cache: a view é leve (dezenas de linhas) e muda em tempo real."""
    _require_tab(token, "painel_pedidos")
    df = db.new_conn_query("""
        SELECT TOP 500
            p.NrOrcPedVnd            AS pedido,
            p.NomeFantCli            AS cliente,
            p.RzsCli                 AS razao,
            p.VendOrcPedVnd          AS vendedor,
            p.DtOrcPedVnd            AS emissao,
            p.DtEntrOrcPedVnd        AS entrega,
            p.StatusOrcPedConsig     AS status,
            p.DescrStatusOrcPedConsig AS status_descr,
            p.GrauPrioridade         AS prioridade
        FROM Blue.dbo.vmPainelPedidoVndConf p
        ORDER BY p.DtOrcPedVnd DESC
    """)
    if df.empty and db.last_error:
        raise HTTPException(status_code=503, detail=f"Painel indisponível: {db.last_error}")
    pedidos = df.to_dict("records")
    resumo: dict = {}
    for r in pedidos:
        resumo[r["status"]] = resumo.get(r["status"], 0) + 1
    payload = {"pedidos": pedidos, "resumo": resumo,
               "ts": datetime.now().strftime("%H:%M:%S")}
    return Response(content=json.dumps(_clean_nan(payload), default=str),
                    media_type="application/json")


@app.get("/dados/cliente")
def dados_cliente(
    busca: Optional[str] = Query(default=None),
    cod: Optional[str] = Query(default=None),
    token: str = Depends(verify_token),
):
    _require_tab(token, "cliente")
    try:
        if cod:
            payload = _cliente_perfil(cod)
        elif busca and busca.strip():
            payload = _cliente_buscar(busca.strip())
        else:
            payload = {"modo": "vazio"}
        return Response(content=json.dumps(_clean_nan(payload), default=str),
                        media_type="application/json")
    except Exception as e:
        logger.error("dados_cliente erro: %s", e)
        raise HTTPException(status_code=503, detail=str(e))


# NOTE: /dados/{bot_name}/filtered must be registered BEFORE /dados/{bot_name}
# so FastAPI does not absorb "filtered" as a bot_name value.
@app.get("/dados/{bot_name}/filtered")
def dados_filtrado(
    bot_name: str,
    vendedor:        Optional[str] = Query(default=None),
    cod_vend:        Optional[str] = Query(default=None),
    marca:           Optional[str] = Query(default=None),
    periodo:         Optional[str] = Query(default=None),
    dt_de:           Optional[str] = Query(default=None),
    dt_ate:          Optional[str] = Query(default=None),
    dias_atraso_min: Optional[str] = Query(default=None),
    token: str = Depends(verify_token),
):
    _require_tab(token, bot_name)
    if _manager is None:
        raise HTTPException(status_code=503, detail="Hub não iniciado — modo cliente")

    bot = _manager.bots.get(bot_name)
    if bot is None:
        raise HTTPException(status_code=404, detail=f"Bot '{bot_name}' não encontrado")

    filtros = {}
    if vendedor:        filtros["vendedor"]        = vendedor
    if cod_vend:        filtros["cod_vend"]        = cod_vend
    if marca:           filtros["marca"]           = marca
    if periodo:         filtros["periodo"]         = periodo
    if dt_de:           filtros["dt_de"]           = dt_de
    if dt_ate:          filtros["dt_ate"]          = dt_ate
    if dias_atraso_min: filtros["dias_atraso_min"] = dias_atraso_min

    try:
        resultado = bot.analisar_filtrado(filtros)
        return JSONResponse(content=_clean_nan(resultado))
    except Exception as e:
        logger.error("dados_filtrado [%s] erro: %s", bot_name, e)
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/dados/{bot_name}")
def dados(bot_name: str, token: str = Depends(verify_token)):
    _require_tab(token, bot_name)

    # Caminho quente: servir da MEMÓRIA do hub (sem disco, sem lock de cache).
    # Serializa EXATAMENTE como o cache (_clean_nan + default=str), então os
    # dados apresentados são idênticos ao caminho antigo — só que sem SQLite.
    if _manager is not None:
        bot = _manager.bots.get(bot_name)
        if bot is not None and bot.resultado:
            payload = json.dumps(_clean_nan(bot.resultado), default=str)
            return Response(content=payload, media_type="application/json")

    # Fallback: modo cliente (sem manager) ou bot ainda sem resultado → cache em disco.
    try:
        data = _cache.load(bot_name)
    except Exception as e:
        logger.error("cache.load [%s] erro: %s", bot_name, e)
        raise HTTPException(status_code=503, detail="Erro ao carregar dados do cache")
    if data is None:
        raise HTTPException(status_code=404, detail=f"Sem dados para '{bot_name}'")
    return JSONResponse(content=data)


# ── Static files — React build (Sub-projeto 2) ────────────────────────
# Quando Sub-projeto 2 colocar o build React em hub/static/, este bloco
# servirá automaticamente o frontend em /app sem alterar este arquivo.
_static = pathlib.Path(__file__).parent / "static"
if _static.exists() and any(_static.iterdir()):
    app.mount("/app", StaticFiles(directory=str(_static), html=True), name="static")


# ── Hub runner ────────────────────────────────────────────────────────
def run_hub(port: int | None = None):
    """Inicia bots + servidor FastAPI na rede local. Bloqueia até ser encerrado."""
    import socket
    import threading
    import webbrowser
    import uvicorn
    from bots.analise_bots import BotManager
    from config.settings import HUB_PORT

    global _manager
    _port = port or HUB_PORT

    _manager = BotManager(use_hub=False)
    for name in _manager.bots:
        _manager.add_callback(name, _broadcast_update)
    _manager.load_from_cache()
    _manager.start_all()

    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = "localhost"

    local_url = f"http://localhost:{_port}"
    net_url   = f"http://{local_ip}:{_port}"
    app_url   = f"{local_url}/app"

    logger.info("G2 Analytics Hub iniciado → %s", net_url)
    print(f"\n{'=' * 52}")
    print(f"  G2 Analytics rodando!")
    print(f"  Local:  {app_url}")
    print(f"  Rede:   {net_url}/app")
    print(f"  API:    {local_url}/docs")
    print(f"{'=' * 52}\n")

    threading.Timer(1.5, lambda: webbrowser.open(app_url)).start()
    uvicorn.run(app, host="0.0.0.0", port=_port, log_level="info")
