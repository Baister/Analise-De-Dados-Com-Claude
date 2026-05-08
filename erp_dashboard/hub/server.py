# hub/server.py
import asyncio
import json
import logging
import pathlib
import secrets
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config.settings import DASHBOARD_PASSWORD
from core.cache import cache as _cache

logger = logging.getLogger(__name__)

# ── Globals ───────────────────────────────────────────────────────────
_loop: asyncio.AbstractEventLoop | None = None
_sse_queues: list[asyncio.Queue] = []
_manager = None  # BotManager — definido por run_hub()


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


class AuthRequest(BaseModel):
    password: str


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
async def stream(_: str = Depends(verify_token)):
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


@app.get("/dados/{bot_name}")
def dados(bot_name: str, _: str = Depends(verify_token)):
    data = _cache.load(bot_name)
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

    logger.info("ERP Hub iniciado → %s", net_url)
    print(f"\n{'=' * 52}")
    print(f"  ERP Dashboard rodando!")
    print(f"  Local:  {local_url}")
    print(f"  Rede:   {net_url}")
    print(f"{'=' * 52}\n")

    threading.Timer(1.5, lambda: webbrowser.open(local_url)).start()
    uvicorn.run(app, host="0.0.0.0", port=_port, log_level="info")
