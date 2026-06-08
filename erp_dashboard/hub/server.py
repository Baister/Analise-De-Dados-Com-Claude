# hub/server.py
import asyncio
import json
import logging
import pathlib
import re as _re
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

from config.settings import DASHBOARD_PASSWORD, ALERTAS
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
app = FastAPI(title="ERP Dashboard API", version="2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Auth ──────────────────────────────────────────────────────────────
_tokens: dict[str, float] = {}
TOKEN_TTL = 8 * 3600  # 8 horas
_bearer = HTTPBearer()


def _purge_expired():
    now = time.time()
    for t in [k for k, exp in _tokens.items() if exp < now]:
        del _tokens[t]


def verify_token(creds: HTTPAuthorizationCredentials = Depends(_bearer)) -> str:
    token = creds.credentials
    exp = _tokens.get(token)
    if exp is None or time.time() > exp:
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
    exp = _tokens.get(t) if t else None
    if not t or exp is None or time.time() > exp:
        if t:
            _tokens.pop(t, None)
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")
    return t


class AuthRequest(BaseModel):
    password: str


class MetasPayload(BaseModel):
    meta_mensal_total: float
    metas_individuais: dict[str, float]


@app.post("/auth")
def login(req: AuthRequest):
    if req.password != DASHBOARD_PASSWORD:
        raise HTTPException(status_code=400, detail="Senha incorreta")
    _purge_expired()
    token = secrets.token_urlsafe(32)
    _tokens[token] = time.time() + TOKEN_TTL
    return {"access_token": token, "token_type": "bearer"}


# ── Root ──────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "ok", "api": "ERP Dashboard v2.0", "docs": "/docs"}


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
def post_metas(payload: MetasPayload, _: str = Depends(verify_token)):
    if payload.meta_mensal_total < 0:
        raise HTTPException(status_code=422, detail="meta_mensal_total deve ser >= 0")
    if any(v < 0 for v in payload.metas_individuais.values()):
        raise HTTPException(status_code=422, detail="Valores individuais devem ser >= 0")
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
def status_route(_: str = Depends(verify_token)):
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
            }
        }
    st = _cache.status()
    return {"bots": {name: info for name, info in st.items()}}


# NOTE: /dados/cliente must be registered BEFORE /dados/{bot_name} to avoid
# FastAPI matching "cliente" as the bot_name path parameter.
@app.get("/dados/cliente")
def dados_cliente(
    de: Optional[str] = Query(default=None),
    ate: Optional[str] = Query(default=None),
    vendedor: Optional[str] = Query(default=None),
    cliente: Optional[str] = Query(default=None),
    marca: Optional[str] = Query(default=None),
    produto: Optional[str] = Query(default=None),
    _: str = Depends(verify_token),
):
    def _valid_date(s: str) -> bool:
        return bool(s and _re.fullmatch(r'\d{4}-\d{2}-\d{2}', s))

    try:
        from core.database import db
        conds  = ["1=1"]
        params = []
        if de      and _valid_date(de):    conds.append("d.DtVnd >= ?"); params.append(de)
        if ate     and _valid_date(ate):   conds.append("d.DtVnd <= ?"); params.append(ate)
        if vendedor:  conds.append("d.NomeVend LIKE ?"); params.append(f"%{vendedor[:100]}%")
        if cliente:   conds.append("d.NomeCli  LIKE ?"); params.append(f"%{cliente[:100]}%")
        if marca:     conds.append("i.DescrMarca LIKE ?"); params.append(f"%{marca[:100]}%")
        if produto:   conds.append("i.DescrItem  LIKE ?"); params.append(f"%{produto[:100]}%")
        where = " AND ".join(conds)

        df = db.query(f"""
            SELECT TOP 500
                d.NomeCli      AS cliente,
                i.DescrItem    AS produto,
                i.DescrMarca   AS marca,
                d.NomeVend     AS vendedor,
                SUM(i.QtdFat)  AS quantidade,
                SUM(i.TotalFat) AS faturamento
            FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
            INNER JOIN Blue.dbo.vmVndDoc d WITH (NOLOCK)
                ON i.NrDoc = d.NrDoc AND i.NSUDoc = d.NSUDoc
            WHERE {where}
            GROUP BY d.NomeCli, i.DescrItem, i.DescrMarca, d.NomeVend
            ORDER BY faturamento DESC
        """, params if params else None)

        if df is None or df.empty:
            return {"kpis": {}, "top_clientes": [], "por_marca": [], "detalhe": []}

        top_clientes = (
            df.groupby("cliente")["faturamento"].sum()
            .reset_index().sort_values("faturamento", ascending=False)
            .head(10).to_dict("records")
        )
        por_marca = (
            df.groupby("marca")["faturamento"].sum()
            .reset_index().sort_values("faturamento", ascending=False)
            .head(10).to_dict("records")
        )
        total_fat = float(df["faturamento"].sum())
        n_clientes = int(df["cliente"].nunique())
        return {
            "kpis": {
                "total_clientes":     n_clientes,
                "faturamento":        total_fat,
                "produtos_distintos": int(df["produto"].nunique()),
                "ticket_medio":       round(total_fat / max(n_clientes, 1), 2),
            },
            "top_clientes": top_clientes,
            "por_marca":    por_marca,
            "detalhe":      df.to_dict("records"),
        }
    except Exception as e:
        logger.error("dados_cliente erro: %s", e)
        raise HTTPException(status_code=503, detail=str(e))


# NOTE: /dados/cliente_comportamento must be registered BEFORE /dados/{bot_name}
# to avoid FastAPI matching "cliente_comportamento" as the bot_name path parameter.
@app.get("/dados/cliente_comportamento")
def dados_cliente_comportamento(
    cliente:  Optional[str] = Query(default=None),
    de:       Optional[str] = Query(default=None),
    ate:      Optional[str] = Query(default=None),
    vendedor: Optional[str] = Query(default=None),
    marca:    Optional[str] = Query(default=None),
    _: str = Depends(verify_token),
):
    def _valid_date(s: str) -> bool:
        return bool(s and _re.fullmatch(r'\d{4}-\d{2}-\d{2}', s))

    try:
        from core.database import db
        conds  = ["d.Fat = 1", "d.Cancelado = ''"]
        params: list = []

        if de  and _valid_date(de):   conds.append("v.DtVnd >= ?"); params.append(de)
        if ate and _valid_date(ate):  conds.append("v.DtVnd <= ?"); params.append(ate)
        if not de and not ate:
            conds.append("v.DtVnd >= DATEADD(month, -12, GETDATE())")

        if vendedor: conds.append("v.Vendedor LIKE ?");   params.append(f"%{vendedor[:100]}%")
        if marca:    conds.append("i.DescrMarca LIKE ?"); params.append(f"%{marca[:100]}%")
        if cliente:  conds.append("v.NomeRazCli LIKE ?"); params.append(f"%{cliente[:100]}%")

        where = " AND ".join(conds)

        df_info = db.query(f"""
            SELECT TOP 1 v.NomeRazCli AS nome, v.CodCli AS cod, v.Vendedor AS vendedor
            FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
            INNER JOIN Blue.dbo.vwVndDoc d WITH (NOLOCK) ON v.NrDoc = d.NrDoc AND v.NSUDoc = d.NSUDoc
            WHERE {where}
            ORDER BY v.DtVnd DESC
        """, params if params else None)

        df_kpi = db.query(f"""
            SELECT
                SUM(CASE WHEN v.CustoRepTotal >= 0 THEN v.ValVndTotal ELSE 0 END) AS venda_bruta,
                SUM(CASE WHEN v.CustoRepTotal < 0  THEN v.ValVndTotal ELSE 0 END) AS devolucao,
                COUNT(DISTINCT CASE WHEN v.CustoRepTotal >= 0 THEN v.NrDoc END)   AS qtd_vendas,
                SUM(v.CustoRepTotal)                                               AS custo_total
            FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
            INNER JOIN Blue.dbo.vwVndDoc d WITH (NOLOCK) ON v.NrDoc = d.NrDoc AND v.NSUDoc = d.NSUDoc
            WHERE {where}
        """, params if params else None)

        df_mensal = db.query(f"""
            SELECT
                FORMAT(v.DtVnd, 'yyyy-MM') AS mes,
                SUM(CASE WHEN v.CustoRepTotal >= 0 THEN v.ValVndTotal ELSE 0 END) AS venda_bruta,
                SUM(CASE WHEN v.CustoRepTotal < 0  THEN v.ValVndTotal ELSE 0 END) AS devolucao
            FROM Blue.dbo.vmVndDoc v WITH (NOLOCK)
            INNER JOIN Blue.dbo.vwVndDoc d WITH (NOLOCK) ON v.NrDoc = d.NrDoc AND v.NSUDoc = d.NSUDoc
            WHERE {where}
            GROUP BY FORMAT(v.DtVnd, 'yyyy-MM')
            ORDER BY mes
        """, params if params else None)

        i_params = list(params)
        df_marcas = db.query(f"""
            SELECT TOP 10 i.DescrMarca,
                SUM(i.PrecoVndTotItem) AS faturamento,
                SUM(i.QtdItem) AS quantidade
            FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
            INNER JOIN Blue.dbo.vwVndDoc d WITH (NOLOCK) ON i.NrDoc = d.NrDoc AND i.NSUDoc = d.NSUDoc
            INNER JOIN Blue.dbo.vmVndDoc v WITH (NOLOCK) ON i.NrDoc = v.NrDoc AND i.NSUDoc = v.NSUDoc
            WHERE i.DescrMarca IS NOT NULL AND i.CustoRepTotItem >= 0 AND {where}
            GROUP BY i.DescrMarca ORDER BY faturamento DESC
        """, i_params if i_params else None)

        df_prod = db.query(f"""
            SELECT TOP 10 i.DescrItem,
                SUM(i.PrecoVndTotItem) AS faturamento,
                SUM(i.QtdItem) AS quantidade
            FROM Blue.dbo.vmVndItemDoc i WITH (NOLOCK)
            INNER JOIN Blue.dbo.vwVndDoc d WITH (NOLOCK) ON i.NrDoc = d.NrDoc AND i.NSUDoc = d.NSUDoc
            INNER JOIN Blue.dbo.vmVndDoc v WITH (NOLOCK) ON i.NrDoc = v.NrDoc AND i.NSUDoc = v.NSUDoc
            WHERE i.DescrItem IS NOT NULL AND i.CustoRepTotItem >= 0 AND {where}
            GROUP BY i.DescrItem ORDER BY faturamento DESC
        """, i_params if i_params else None)

        venda_bruta = float(df_kpi["venda_bruta"].iloc[0]) if not df_kpi.empty and df_kpi["venda_bruta"].iloc[0] is not None else 0.0
        devolucao   = float(df_kpi["devolucao"].iloc[0])   if not df_kpi.empty and df_kpi["devolucao"].iloc[0] is not None else 0.0
        venda_liq   = venda_bruta + devolucao
        custo       = float(df_kpi["custo_total"].iloc[0]) if not df_kpi.empty and df_kpi["custo_total"].iloc[0] is not None else 0.0
        qtd_vendas  = int(df_kpi["qtd_vendas"].iloc[0])    if not df_kpi.empty and df_kpi["qtd_vendas"].iloc[0] is not None else 0
        margem_pct  = round((venda_liq - custo) / venda_liq * 100, 1) if venda_liq else 0.0
        ticket      = round(venda_bruta / max(qtd_vendas, 1), 2)

        info = {}
        if not df_info.empty:
            row = df_info.iloc[0]
            info = {
                "nome":     str(row.get("nome", "") or ""),
                "cod":      str(row.get("cod", "") or ""),
                "vendedor": str(row.get("vendedor", "") or ""),
            }

        return {
            "cliente_info":    info,
            "kpis": {
                "venda_bruta":   venda_bruta,
                "devolucao":     devolucao,
                "venda_liquida": venda_liq,
                "margem_pct":    margem_pct,
                "ticket_medio":  ticket,
            },
            "evolucao_mensal": df_mensal.to_dict("records") if not df_mensal.empty else [],
            "top_marcas":      df_marcas.to_dict("records") if not df_marcas.empty else [],
            "top_produtos":    df_prod.to_dict("records")   if not df_prod.empty   else [],
        }
    except Exception as e:
        logger.error("dados_cliente_comportamento erro: %s", e)
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
    _: str = Depends(verify_token),
):
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
def dados(bot_name: str, _: str = Depends(verify_token)):
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

    logger.info("ERP Hub iniciado → %s", net_url)
    print(f"\n{'=' * 52}")
    print(f"  ERP Dashboard rodando!")
    print(f"  Local:  {app_url}")
    print(f"  Rede:   {net_url}/app")
    print(f"  API:    {local_url}/docs")
    print(f"{'=' * 52}\n")

    threading.Timer(1.5, lambda: webbrowser.open(app_url)).start()
    uvicorn.run(app, host="0.0.0.0", port=_port, log_level="info")
